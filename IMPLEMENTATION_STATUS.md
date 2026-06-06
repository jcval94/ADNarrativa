# Estado de Implementación

Fecha de corte: 2026-06-06

Versiones efectivas actuales:

- `taxonomy_version_effective`: `v1_0`
- `prompt_version_effective`: `v1_0`
- `validator_version_effective`: `v1_0`

## Resumen Ejecutivo

El proyecto ya tiene una base JSON-first sólida: arquitectura, paquete instalable, contratos Pydantic estrictos, taxonomía auditada, constitución estable v1.0, validadores determinísticos iniciales, compilador de notación derivada, loader/segmentador, extracción de heurísticas conservadoras, cliente OpenAI estructurado, clasificador JSON-first, árbitro conservador, auditoría por similitud semántica, construcción de review sets, workflow de revisión sintética por comité OpenAI y métricas de confiabilidad sintética.

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
| 6 | Completo | Validadores determinísticos iniciales y compilador de notación. |
| 7 | Completo | Loader, normalizador y segmentador JSON-first para `.txt`, `.json`, `.jsonl` y `data/transcripts/videos`. |
| 8 | Completo | Heurísticas conservadoras como candidatos auditables, sin cambiar clasificación final. |
| 9 | Completo | Cliente OpenAI Responses API con Structured Outputs estrictos, cache versionado, retries, dry-run y validación Pydantic. |
| 10 | Completo | Clasificador por unidad/documento con contexto, heurísticas, salida parcial estricta y postproceso con validadores. |
| 11 | Completo | Árbitro conservador para casos de alto riesgo, con salida estructurada, reducción de etiquetas débiles y validación posterior. |
| 12 | Completo | Auditoría por similitud semántica con embeddings cacheados, conflicto de notación y explicación auditable. |
| 13 | Completo | Review set sintético priorizado por flags, needs_review, conflictos de similitud, grupos confundibles, pares mínimos y QA de alta confianza. |
| 14 | Completo | Comité sintético OpenAI con reviewers diversos, aggregator conservador, adjudicator final, candidatos y reportes JSON/MD. |
| 15 | En este commit | Métricas de confiabilidad sintética, buckets high/medium/rejected y elegibilidad de regresión. |

## Artefactos Clave

- `ARCHITECTURE.md`: diseño del sistema y pipeline objetivo.
- `PROJECT_CHARTER.md`: alcance MVP y no-alcance.
- `src/narrative_dna/models.py`: contratos Pydantic estrictos.
- `annotation_guidelines/taxonomy_v1_0.json`: taxonomía estable.
- `annotation_guidelines/validator_rules_v1_0.json`: reglas esperadas v1.0.
- `annotation_guidelines/minimal_pairs_v1_0.jsonl`: pares mínimos consolidados.
- `src/narrative_dna/validators.py`: validadores determinísticos iniciales.
- `src/narrative_dna/notation.py`: compilador de notación derivada.
- `src/narrative_dna/loader.py`: carga de transcripts individuales, JSONL multi-documento y árboles de videos.
- `src/narrative_dna/normalizer.py`: normalización determinística de espacios, comillas, saltos e invisibles.
- `src/narrative_dna/segmenter.py`: segmentación semántica conservadora con timestamps, offsets y unidades no clasificadas.
- `src/narrative_dna/heuristic_candidates.py`: extracción de señales candidatas con evidencia auditable.
- `src/narrative_dna/llm_client.py`: frontera única para OpenAI Responses API y salidas estructuradas.
- `configs/llm_config.json`: perfiles LLM, cache y retry policy.
- `src/narrative_dna/unit_classifier.py`: clasificación JSON-first con contexto, heurísticas y validadores.
- `prompts/unit_classifier.md`: prompt operativo v1.0 para salida JSON estricta.
- `src/narrative_dna/adjudicator.py`: adjudicación conservadora para casos de alto riesgo.
- `prompts/adjudicator.md`: prompt operativo v1.0 para resolución conservadora.
- `src/narrative_dna/similarity_auditor.py`: auditoría semántica de inconsistencias de notación.
- `configs/similarity_audit_config.json`: umbral, top-k y proveedor de embeddings configurable.
- `src/narrative_dna/review_set_builder.py`: construcción de `review/review_items.jsonl` y manifest para comité sintético.
- `schemas/synthetic_review_item.schema.json`: contrato estricto del review item enriquecido con contexto, reglas y versiones efectivas.
- `schemas/synthetic_review_manifest.schema.json`: contrato del manifest del review set.
- `src/narrative_dna/synthetic_reviewer.py`: orquestación del comité sintético, carga de review items y escritura de outputs.
- `src/narrative_dna/review_aggregator.py`: agregación conservadora y conversión segura a candidatos sintéticos.
- `prompts/synthetic_reviewer.md`: prompt operativo v1.0 para reviewers sintéticos.
- `prompts/synthetic_aggregator.md`: prompt operativo v1.0 para consenso conservador.
- `prompts/synthetic_adjudicator.md`: prompt operativo v1.0 para adjudicación final sintética.
- `schemas/synthetic_final_adjudication.schema.json`: contrato del árbitro final sintético.
- `schemas/synthetic_review_report.schema.json`: contrato del reporte de revisión sintética.
- `src/narrative_dna/synthetic_reliability.py`: scoring determinístico de confiabilidad sintética.
- `schemas/synthetic_reliability_metrics.schema.json`: contrato ampliado de métricas de confiabilidad.

## Qué Ya Está Bien Encaminado

- JSON-first está reforzado por modelos, schemas y tests.
- v1.0 resolvió los issues críticos/altos de auditoría.
- Hay tests para assets v0.1, auditoría y v1.0.
- La notación se deriva desde JSON con orden taxonómico estable.
- Los validadores reparan casos como `N+K`, `A+K`, `D` sin evidencia y `R` sin ancla.
- El loader ya usa `data/transcripts/videos` sistemáticamente y prefiere segmentos temporizados.
- Las heurísticas detectan señales fuertes para P, Z, D, Y, E, H, G, C, B, X, S, I, U, V, O, F, L, M y Q, además de certeza, postura y emociones mencionadas/expresadas.
- El cliente OpenAI no acepta texto libre: exige JSON Schema `strict=true` y valida la respuesta con Pydantic antes de devolverla.
- El hash de cache incluye modelo, reasoning, temperatura, versiones efectivas, schema, prompt e input payload.
- El clasificador usa `NarrativeUnitPartialClassification`, nunca acepta notación compacta como input editable, y delega `final_notation` a validadores/compilador.
- Los casos `P+V`, `K` que hereda `A`, emoción mencionada, `R` sin pregunta y `D` sin evidencia están cubiertos con mocks.
- El adjudicator detecta baja confianza, flags críticos, sobre-etiquetado, emoción intensa, conflictos heurística/LLM y primarias confundibles.
- La adjudicación vuelve a pasar por validadores, limpia flags resueltos y mantiene `needs_review=true` si dos lecturas siguen siendo plausibles.
- El auditor distingue `likely_inconsistency`, `context_explains_difference`, `allowed_by_taxonomy` y `needs_human_review`.
- Los conflictos incluyen `similarity`, `notation_distance`, `conflict_score`, campos divergentes y versiones efectivas en el summary.
- El review set ya no es aleatorio: integra `needs_review`, flags, conflictos de similitud, grupos confundibles, emoción intensa, emociones mencionadas, >3 funciones, baja/media confianza, muestra QA high-confidence y pares mínimos v1.0.
- `narrative-dna build-review-set --run-id <RUN_ID>` escribe `outputs/{run_id}/review/review_items.jsonl` y `review_manifest.json`.
- `narrative-dna synthetic-review --run-id <RUN_ID>` consume exclusivamente `review/review_items.jsonl`, no reconstruye contexto desde cero.
- El comité escribe `synthetic_reviews.jsonl`, `synthetic_review_aggregated.jsonl`, `synthetic_final_adjudications.jsonl`, `synthetic_gold_candidates.jsonl`, `synthetic_review_report.json` y `synthetic_review_report.md`.
- Si aggregator o final adjudicator fallan, el flujo cae a decisiones conservadoras y no promueve gold.
- `narrative-dna promote-synthetic-gold --run-id <RUN_ID>` calcula acuerdo entre reviewers, acuerdo aggregator/final, confiabilidad final, buckets gold sintéticos y elegibilidad de regresión.
- Sólo candidatos `synthetic_gold_high_confidence` sin flags ni `needs_review` y con score >= 0.90 cuentan como elegibles para regresión.

## Refuerzos Pendientes

- Integrar loader, segmenter, heurísticas y validadores en el pipeline end-to-end.
- Integrar classifier y adjudicator en el pipeline end-to-end cuando se cablee `pipeline.py`.
- Implementar validadores v1.0 adicionales: certeza epistémica, postura con target, C/B/X, E/H/G y T/M/L/Z.
- Implementar detector auditable de relaciones del Step 16.
- Reforzar segmentación y heurísticas con más casos de habla oral real antes de congelar regression fixtures.
- Agregar pruebas golden de notación cuando exista `synthetic_gold_high_confidence`.
- Validar schemas generados contra ejemplos reales de outputs cuando el pipeline escriba `outputs/{run_id}`.
- Encapsular OpenAI únicamente en `llm_client.py` antes de cualquier llamada LLM.

## Observaciones Críticas

- Hay archivos untracked ajenos al plan actual: `generated/`, `html_builder.py`, `tests/test_html_builder.py`. No los he tocado ni incluido en commits.
- La suite completa pasa usando `--basetemp .pytest_tmp`; el directorio temporal global de Windows puede dar permisos denegados en este entorno.
- Ruff sobre `src tests` falla por el archivo untracked `tests/test_html_builder.py`; Ruff sobre archivos versionados pasa.
- Aún no existe pipeline end-to-end, por lo que documentos, heurísticas, clasificaciones, adjudicaciones y auditorías mockeadas se validan en memoria; el auditor ya puede escribir outputs derivados si existe `outputs/{run_id}/documents.jsonl`.

## Próximo Step Natural

Step 16: detector auditable de relaciones externas entre unidades.
