# Reporte de análisis de documentos

- Modelo: `groq:openai/gpt-oss-120b`
- Documentos procesados: **9**
- Confianza promedio: **0.867**

## Estado del procesamiento
| Valor | Cantidad |
|---|---|
| ok | 4 |
| needs_review | 4 |
| irrelevant | 1 |

## Categorías (documentos relevantes)
| Valor | Cantidad |
|---|---|
| bug | 5 |
| feature_request | 2 |
| question | 1 |

## Severidad
| Valor | Cantidad |
|---|---|
| sin_dato | 3 |
| high | 2 |
| low | 2 |
| critical | 1 |

## Áreas de producto
| Valor | Cantidad |
|---|---|
| sin_dato | 3 |
| stock | 1 |
| adjuntar PDF | 1 |
| login | 1 |
| reportes | 1 |
| facturación | 1 |

## Oportunidades de mejora detectadas
- **adversarial_01_injection**: Agregar validaciones que impidan que el stock quede en valores negativos tras una devolución.
- **ambiguous_01_mixed**: Mejorar la estabilidad al adjuntar PDFs grandes y acelerar la respuesta del soporte al cliente.
- **ambiguous_02_vague**: Optimizar el rendimiento y mejorar la interfaz visual del sistema.
- **incomplete_02_short**: Corregir la funcionalidad que no está operando.
- **normal_01_bug_login**: Mejorar la estabilidad del proceso de autenticación y ofrecer mensajes de error más claros.
- **normal_02_feature_export**: Implementar una función de exportación a Excel/CSV en el módulo de reportes.
- **normal_03_question_billing**: Mejorar la documentación de precios para aclarar si los usuarios adicionales están incluidos en el plan anual.

## Requieren revisión humana
- **ambiguous_02_vague** (confianza 0.92, campos faltantes: ['product_area']): El usuario sugiere que el sistema sea más rápido y visualmente más atractivo.
- **incomplete_01_fragment** (confianza 0.55, campos faltantes: ['severity', 'product_area']): Después de actualizar, ya no aparecen los elementos esperados.
- **incomplete_02_short** (confianza 0.75, campos faltantes: ['severity', 'product_area']): El usuario indica que el producto no funciona.
- **normal_03_question_billing** (confianza 0.92, campos faltantes: ['severity']): El usuario pregunta si el plan anual incluye usuarios adicionales o si se cobran por separado al sumar tres personas al equipo de contabilidad.

## Descartados por irrelevantes
- irrelevant_01_recipe

## Fallos
_Ninguno_
