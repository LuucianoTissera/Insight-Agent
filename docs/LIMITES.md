# Límites del agente

Documentar lo que el sistema **no** hace es parte del resultado de una PoC.

## Alcance
- **Entrada:** texto plano (`.txt`, `.md`) en UTF-8. Sin PDF, imágenes ni adjuntos.
- **Dominio:** tickets / feedback de usuarios de software. Otros tipos de documento se descartan como irrelevantes.
- **Idioma:** pensado y probado en español; otros idiomas no están evaluados.
- **Tamaño:** se truncan documentos de más de 20.000 caracteres (queda marcado en el reporte).

## Calidad
- **Conjunto de prueba pequeño** (9 documentos sintéticos): sirve para detectar regresiones y comparar modelos de forma orientativa, **no** para afirmar una precisión estadística.
- **Etiquetas esperadas subjetivas**, sobre todo severidad y casos ambiguos (por eso admiten listas de valores aceptables).
- **Grounding limitado:** verifica que las citas existan en el documento, no que la interpretación sea correcta.
- **Confianza autodeclarada:** el valor de `confidence` lo reporta el propio modelo y no está calibrado formalmente.
- **Resultados no comparables entre proveedores sin cuidado:** cada modelo interpreta distinto la severidad y la confianza; comparar sólo con el mismo conjunto de prueba y el mismo prompt.
- **No determinismo:** aun con `temperature=0`, distintas versiones del modelo pueden dar resultados distintos. Por eso se registra el modelo usado en cada reporte.

## Seguridad
- Hay mitigación frente a *prompt injection* (documento tratado como dato + caso adversarial), pero **no es una garantía**. Para uso real harían falta controles adicionales.
- Los documentos se envían a una API externa. En varios planes gratuitos (por ejemplo, Google AI Studio) el proveedor puede usar los datos enviados para mejorar sus productos: **no usar con datos personales o confidenciales**. Las muestras del repo son sintéticas.

## Operación
- Procesamiento secuencial (sin paralelismo ni caché), con pausa fija entre documentos.
- Los planes gratuitos tienen límites por minuto y por día que cambian sin aviso; si se agota el cupo diario, el lote falla (los documentos afectados quedan como `failed` con el error del proveedor).
- Los modelos gratuitos varían en su capacidad de seguir un esquema JSON: se compensa con validación y reintentos, pero modelos pequeños pueden agotar los intentos.
- Sin registro de latencia ni tokens.
- El agente **asiste**, no decide: los casos `needs_review` requieren una persona.

## Cuándo NO usarlo
Decisiones automáticas con impacto económico o legal, documentos sensibles, o volúmenes donde el costo por llamada no esté evaluado.
