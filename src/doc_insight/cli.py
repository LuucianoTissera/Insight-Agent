"""Interfaz de línea de comandos.

  doc-insight run data/samples --provider gemini
  doc-insight evaluate data/samples data/expected --provider groq
  doc-insight evaluate data/samples data/expected --provider openrouter --model google/gemma-3-27b-it:free
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .evaluate import evaluate
from .extractor import Extractor
from .llm import PROVIDERS, LLMError, create_client
from .report import build_summary, render_markdown
from .schema import ExtractionResult

SUPPORTED = {".txt", ".md"}
# Pausa entre documentos para respetar los límites por minuto (RPM) de los planes gratuitos.
DEFAULT_DELAY = {"gemini": 4.0, "openrouter": 3.0}


def load_documents(folder: Path) -> list[tuple[str, str]]:
    if not folder.is_dir():
        raise SystemExit(f"La carpeta {folder} no existe.")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED)
    if not files:
        raise SystemExit(f"No se encontraron documentos {sorted(SUPPORTED)} en {folder}")
    docs = []
    for p in files:
        try:
            docs.append((p.stem, p.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            docs.append((p.stem, ""))  # se reportará como empty_document en lugar de abortar el lote
    return docs


def process(args: argparse.Namespace) -> tuple[list[ExtractionResult], str, str]:
    client = create_client(args.provider, args.model, args.base_url, getattr(args, 'retries', None))
    label = f"{args.provider}:{client.model}"
    delay = args.delay if args.delay is not None else DEFAULT_DELAY.get(args.provider, 0.0)
    extractor = Extractor(client, max_attempts=args.max_attempts)
    print(f"Modelo: {label} | pausa entre documentos: {delay}s", file=sys.stderr)
    results = []
    for i, (doc_id, text) in enumerate(load_documents(Path(args.input))):
        if i and delay:
            time.sleep(delay)
        res = extractor.extract(doc_id, text)
        print(f"  {doc_id:<28} {res.status:<13} intentos={res.attempts}", file=sys.stderr)
        results.append(res)
    return results, label, client.model


def cmd_run(args: argparse.Namespace) -> int:
    results, label, _ = process(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = build_summary(results)
    (out / "extractions.json").write_text(
        json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(summary, results, label), encoding="utf-8")
    print(f"\nListo. Archivos generados en {out}/ (extractions.json, summary.json, report.md)")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    results, label, _ = process(args)
    report = evaluate(results, Path(args.expected))
    report["model"] = label
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", label)  # nombres válidos también en Windows
    path = out / f"eval_{safe}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nModelo: {label} | Accuracy global: {report['overall_accuracy']}")
    for t, fields in report["by_case_type"].items():
        print(f"  {t:<12} " + "  ".join(f"{f}={v['correct']}/{v['total']}" for f, v in fields.items()))
    print(f"Detalle en {path}")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    client = create_client(args.provider, args.model, args.base_url)
    if not hasattr(client, "list_models"):
        raise LLMError(f"El proveedor {args.provider} no soporta listar modelos desde esta herramienta.")
    names = client.list_models()
    if args.filter:
        names = [n for n in names if args.filter.lower() in n.lower()]
    print(f"Modelos disponibles en {args.provider} ({len(names)}):")
    for n in names:
        print(f"  {n}")
    print("\nUsalo con: doc-insight run <carpeta> --provider", args.provider, "--model <nombre>")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="doc-insight", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("input", help="Carpeta con documentos .txt/.md")
        sp.add_argument("--provider", default=os.getenv("DOC_INSIGHT_PROVIDER", "gemini"), choices=PROVIDERS)
        sp.add_argument("--model", help="Modelo a usar (por defecto, el del proveedor)")
        sp.add_argument("--base-url", help="Sólo para --provider custom (endpoint compatible con OpenAI)")
        sp.add_argument("--delay", type=float, help="Segundos de pausa entre documentos (límites RPM)")
        sp.add_argument("--max-attempts", type=int, default=3, help="Intentos por documento ante respuestas inválidas")
        sp.add_argument("--retries", type=int, help="Reintentos HTTP ante 429/503 (por defecto 6, con espera creciente de hasta 30s)")
        sp.add_argument("--out", default="out")

    r = sub.add_parser("run", help="Procesa una carpeta y genera reportes")
    common(r)
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("evaluate", help="Procesa y compara contra casos etiquetados")
    common(e)
    e.add_argument("expected", help="Carpeta con <doc_id>.json esperados")
    e.set_defaults(func=cmd_evaluate)

    m = sub.add_parser("models", help="Lista los modelos disponibles para tu API key")
    m.add_argument("--provider", default=os.getenv("DOC_INSIGHT_PROVIDER", "gemini"), choices=PROVIDERS)
    m.add_argument("--model", help=argparse.SUPPRESS)
    m.add_argument("--base-url", help="Sólo para --provider custom")
    m.add_argument("--filter", help="Texto para filtrar la lista (ej.: flash)")
    m.set_defaults(func=cmd_models)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        return args.func(args)
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
