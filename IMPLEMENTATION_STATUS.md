# Estado de Implementación

Fecha de corte: 2026-05-26

Versiones efectivas actuales:

- `taxonomy_version_effective`: `v1_0`
- `prompt_version_effective`: `v1_0`
- `validator_version_effective`: `v1_0`

## Resumen Ejecutivo

El proyecto ya tiene una base JSON-first sólida: arquitectura, paquete instalable, contratos Pydantic estrictos, taxonomía auditada, constitución estable v1.0, validadores determinísticos iniciales y compilador de notación derivada.

La decisión más importante sigue intacta: el JSON validado es la fuente de verdad. La notación compacta se compila desde JSON y no debe editarse manualmente.

## Avance Por Step

| Step | Estado | Resultado |
| --- | --- | --- |
| 0 | Completo | Arquitectura y charter JSON-first definidos. |
| 1 | Completo | Scaffolding Python instalable, CLI base, configs, schemas y tests mínimos. |
| 2 | Completo | Modelos Pydantic estrictos y exportador de JSON Schema. |
| 3 | Completo | Constitución v0.1 con taxonomía, fronteras, validadores esperados y 143 pares mínimos. |
| 4 | Completo | Auditoría adversarial v0.1 con 12 issues y 120 casos ambiguos usando transcripciones reales. |
| 5 | Completo | Constitución estable v1.0, 263 pares mínimos, changelog y tests de assets. |
| 6 | En este commit | Validadores determinísticos iniciales y compilador de notación. |

## Artefactos Clave

- `ARCHITECTURE.md`: diseño del sistema y pipeline objetivo.
- `PROJECT_CHARTER.md`: alcance MVP y no-alcance.
- `src/narrative_dna/models.py`: contratos Pydantic estrictos.
- `annotation_guidelines/taxonomy_v1_0.json`: taxonomía estable.
- `annotation_guidelines/validator_rules_v1_0.json`: reglas esperadas v1.0.
- `annotation_guidelines/minimal_pairs_v1_0.jsonl`: pares mínimos consolidados.
- `src/narrative_dna/validators.py`: validadores determinísticos iniciales.
- `src/narrative_dna/notation.py`: compilador de notación derivada.

## Qué Ya Está Bien Encaminado

- JSON-first está reforzado por modelos, schemas y tests.
- v1.0 resolvió los issues críticos/altos de auditoría.
- Hay tests para assets v0.1, auditoría y v1.0.
- La notación se deriva desde JSON con orden taxonómico estable.
- Los validadores reparan casos como `N+K`, `A+K`, `D` sin evidencia y `R` sin ancla.

## Refuerzos Pendientes

- Integrar los validadores con el pipeline cuando exista loader/segmenter.
- Implementar validadores v1.0 adicionales: certeza epistémica, postura con target, C/B/X, E/H/G y T/M/L/Z.
- Agregar pruebas golden de notación cuando exista `synthetic_gold_high_confidence`.
- Validar schemas generados contra ejemplos reales de outputs cuando el pipeline escriba `outputs/{run_id}`.
- Encapsular OpenAI únicamente en `llm_client.py` antes de cualquier llamada LLM.

## Observaciones Críticas

- Hay archivos untracked ajenos al plan actual: `generated/`, `html_builder.py`, `tests/test_html_builder.py`. No los he tocado ni incluido en commits.
- La suite completa pasa usando `--basetemp .pytest_tmp`; el directorio temporal global de Windows puede dar permisos denegados en este entorno.
- Aún no existe pipeline end-to-end, por lo que los validadores se prueban sobre payloads de unidad y no sobre runs reales.

## Próximo Step Natural

Step 7: loader, normalizador y segmentador JSON-first. Ahí conviene empezar a usar `data/transcripts/videos` de forma más sistemática para producir `documents` y unidades candidatas sin LLM.
