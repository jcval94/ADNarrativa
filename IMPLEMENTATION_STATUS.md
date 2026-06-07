# Estado de Implementación

Fecha de corte: 2026-06-07

Versiones efectivas actuales:

- `taxonomy_version_effective`: `v1_0`
- `prompt_version_effective`: `v1_0`
- `validator_version_effective`: `v1_0`

## Resumen Ejecutivo

El proyecto ya tiene una base JSON-first sólida: arquitectura, paquete instalable, contratos Pydantic estrictos, taxonomía auditada, constitución estable v1.0, validadores determinísticos iniciales, compilador de notación derivada, loader/segmentador, extracción de heurísticas conservadoras, cliente OpenAI estructurado, clasificador JSON-first, árbitro conservador, auditoría por similitud semántica, construcción de review sets, workflow de revisión sintética por comité OpenAI, métricas de confiabilidad sintética, detector auditable de relaciones externas, detector de cadenas narrativas, evaluación con reportes JSON y pipeline/CLI end-to-end.

La decisión más importante sigue intacta: el JSON validado es la fuente de verdad. La notación compacta se compila desde JSON y no debe editarse manualmente.

Step 20 agrega fixtures golden de regresión con `synthetic_gold_high_confidence` y pruebas que bloquean cambios accidentales en la notación derivada. Step 21 cierra el plan maestro con una guía operativa para ejecutar, auditar, revisar sintéticamente, promover gold y evaluar sin romper el principio JSON-first.

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
| 15 | Completo | Métricas de confiabilidad sintética, buckets high/medium/rejected y elegibilidad de regresión. |
| 16 | Completo | Detector determinístico y auditable de relaciones con salida `relations.jsonl`. |
| 17 | Completo | Detector determinístico de cadenas por relaciones y secuencias multilabel con salida `chains.jsonl`. |
| 18 | Completo | Evaluación contra gold permitido, métricas unitarias/label y reportes JSON/MD derivados. |
| 19 | Completo | Pipeline y CLI end-to-end JSON-first con manifest, JSONL, audit report, secuencias y CSV derivados. |
| 20 | Completo | Fixtures y tests golden con `synthetic_gold_high_confidence` para estabilidad de notación. |
| 21 | En este commit | Guía de operación para anotaciones estables, auditables y revisadas sintéticamente. |

## Artefactos Clave

- `tests/fixtures/golden_regression/synthetic_gold_high_confidence.jsonl`: fixtures de regresión elegibles, todos high-confidence y sin flags.
- `tests/fixtures/golden_regression/expected_notation_sequences.json`: secuencia esperada para comprobar estabilidad de notación derivada.
- `tests/test_golden_regression.py`: pruebas de elegibilidad, derivación de notación, evaluación perfecta y rechazo de synthetic gold medium/rejected.
- `OPERATING_GUIDE.md`: guía de instalación, ejecución, auditoría, revisión sintética, promoción gold, evaluación, regresión y checklist.

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
- `src/narrative_dna/relation_detector.py`: detección determinística de relaciones externas con evidencia, flags y versiones efectivas.
- `configs/relation_patterns.json`: reglas declarativas base para tipos de relación y distancias conservadoras.
- `schemas/relation.schema.json`: contrato actualizado con `run_id` y versiones efectivas.
- `src/narrative_dna/chain_detector.py`: detección determinística de cadenas narrativas por grafo de relaciones y secuencias multilabel.
- `configs/chain_patterns.json`: patrones declarativos de cadenas por relaciones y pasos funcionales.
- `schemas/chain.schema.json`: contrato actualizado con `run_id`, evidencia, flags y versiones efectivas.
- `src/narrative_dna/evaluator.py`: evaluación JSON-first contra gold permitido y escritura de reportes derivados.
- `schemas/evaluation_metrics.schema.json`: contrato ampliado de métricas de evaluación con conteos, outputs y versiones efectivas.
- `src/narrative_dna/pipeline.py`: orquestación end-to-end de loader, heurísticas, clasificación/adjudicación opcional, relaciones, cadenas y exports.
- `src/narrative_dna/exporter.py`: escritura de outputs JSON/JSONL, audit report, secuencias compactas y CSV derivados.

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
- `narrative-dna detect-relations --run-id <RUN_ID>` lee `documents.jsonl`, adjunta relaciones por documento y escribe `relations.jsonl`.
- El detector cubre `ANS`, `SUP`, `EXPL`, `ELAB`, `EXMP`, `ANLG`, `CONTR`, `REFUT`, `RISK`, `SOLV`, `SEQ`, `SUM`, `CALL`, `CAUSE` y `COND` con reglas auditables.
- `narrative-dna detect-chains --run-id <RUN_ID>` lee `documents.jsonl`, usa relaciones adjuntas o `relations.jsonl`, adjunta cadenas por documento y escribe `chains.jsonl`.
- El detector de cadenas cubre patrones por relación como pregunta-respuesta, claim-soporte-explicación, riesgo-solución, contraste-resolución y ejemplo/analogía; también cubre secuencias multilabel contiguas sin LLM.
- `narrative-dna evaluate --run-id <RUN_ID> --gold <GOLD_JSONL>` escribe `evaluation_metrics.json`, `label_metrics.json`, `confusion_groups_report.json`, `audit_report.json` y `audit_report.md`.
- La evaluación acepta gold humano, `synthetic_gold_high_confidence` y unidades JSONL explícitas; rechaza candidatos sintéticos medium/rejected.
- `narrative-dna run --input-dir <DIR> --output-dir outputs --no-llm --no-adjudicator` escribe un run completo conservador con `run_manifest.json`, `documents.jsonl`, `units.jsonl`, `relations.jsonl`, `chains.jsonl`, `dna_sequences.txt`, `audit_report` y CSV derivados.
- `narrative-dna inspect --run-id <RUN_ID>` resume manifest y conteos de outputs principales.

- Los fixtures golden de `tests/fixtures/golden_regression/` fuerzan que `final_notation` se rederive desde JSON validado y que `regression_pass_rate` permanezca en `1.0` para el set estable.
- La regresión rechaza explícitamente candidatos sintéticos que no sean `synthetic_gold_high_confidence`.
- La guía operativa describe el orden recomendado: run conservador sin LLM, run con LLM/adjudicator, auditoría de similitud, review set, comité sintético, promoción, evaluación y regresión golden.

## Refuerzos Pendientes

- Implementar validadores v1.0 adicionales: certeza epistémica, postura con target, C/B/X, E/H/G y T/M/L/Z.
- Reforzar segmentación y heurísticas con más casos de habla oral real antes de congelar regression fixtures.
- Ampliar fixtures golden con más casos reales promovidos por revisión sintética high-confidence.
- Validar schemas generados contra ejemplos reales de outputs en más rutas del pipeline.
- Encapsular OpenAI únicamente en `llm_client.py` antes de cualquier llamada LLM.

## Observaciones Críticas

- Hay archivos untracked ajenos al plan actual: `generated/`, `html_builder.py`, `tests/test_html_builder.py`. No los he tocado ni incluido en commits.
- La suite completa pasa usando `--basetemp .pytest_tmp`; el directorio temporal global de Windows puede dar permisos denegados en este entorno.
- Ruff global falla por los archivos untracked `html_builder.py` y `tests/test_html_builder.py`; Ruff sobre archivos versionados pasa.
- El pipeline end-to-end ya existe; el modo con LLM depende de `OPENAI_API_KEY` y de perfiles configurados en `configs/llm_config.json`.

## Próximo Step Natural

Plan maestro 0-21 completo. Próximo trabajo recomendado: endurecer validadores v1.0 pendientes y ampliar fixtures golden con casos reales promovidos high-confidence.
