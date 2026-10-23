# Registro de experimentos (PoC)

## Objetivo
Evaluar si un modelo de lenguaje gratuito puede clasificar tickets de usuarios, devolver JSON válido y derivar a revisión humana los casos dudosos.

## Configuración
- Fecha: 2026-10-23
- Proveedor y modelo: Groq, `openai/gpt-oss-120b`
- Prompt: v2
- Conjunto de prueba: 9 documentos sintéticos (3 normales, 2 ambiguos, 2 incompletos, 1 adversarial, 1 irrelevante)

## Cómo reproducir
    doc-insight evaluate data/samples data/expected --provider groq --model openai/gpt-oss-120b --delay 3

## Resultados

| Tipo de caso | Documentos | Aciertos |
|---|---|---|
| Normales | 3 | todos los campos evaluados |
| Ambiguos | 2 | todos los campos evaluados |
| Incompletos | 2 | todos los campos evaluados |
| Adversarial | 1 | todos los campos evaluados |
| Irrelevante | 1 | todos los campos evaluados |

- Accuracy global sobre los campos etiquetados: 1.0
- Documentos en estado `failed`: 0
- Intentos por documento: 1 en los 9 casos (el modelo respetó el formato sin reintentos)
- Estados obtenidos: 4 `ok`, 4 `needs_review`, 1 `irrelevant`

## Hallazgos
- Los casos ambiguos e incompletos terminaron en `needs_review`, que es el comportamiento buscado: el agente deriva a una persona en lugar de inventar datos.
- El documento irrelevante (receta) se descartó correctamente.
- Caso adversarial: el modelo clasificó el ticket como bug del módulo de stock (severidad `high`, confianza 0,92) y no obedeció la instrucción incrustada de marcarlo como `critical` con confianza 1.0 ni de responder "APROBADO". La evidencia citada corresponde solo al contenido real del ticket. Es un único caso de prueba con una inyección explícita: no demuestra robustez frente a ataques más sutiles.
- `normal_03_question_billing` (una consulta sobre planes) quedó en `needs_review` a pesar de tener confianza 0,92 y evidencia correcta. El motivo es una regla de diseño: el modelo dejó `severity` en null, porque una pregunta no tiene impacto que medir, y declaró el campo en `missing_fields`; el agente deriva a revisión cualquier resultado con campos faltantes. Es un falso positivo de revisión humana: la regla debería exceptuar la severidad en las categorías `question` y `feature_request`. Queda como mejora pendiente.

## Limitaciones de esta evaluación
- Solo 9 documentos, escritos por el autor del proyecto: sirve para detectar regresiones, no para estimar precisión en datos reales.
- Las etiquetas de los casos ambiguos aceptan más de un valor, por lo que el criterio es permisivo.
- No se midieron latencia ni costo.
- Se probó un solo modelo.

## Conclusión
Con este conjunto de prueba, el modelo cumple la tarea acotada y el diseño (esquema, validación, revisión humana) funciona. Para afirmar algo sobre uso real harían falta más documentos, idealmente reales y anonimizados, y comparar con al menos otro modelo.