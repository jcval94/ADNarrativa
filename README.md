# narrative_dna

Sistema **JSON-first** para convertir transcripciones de discursos en una representación estable, interpretable y auditable de ADN narrativo.

> Implementar desde cero un MVP JSON-first para ADN narrativo estable, interpretable y auditable.

## Qué problema resuelve

Las transcripciones suelen analizarse con etiquetas subjetivas, prompts cambiantes o métricas agregadas difíciles de auditar. `narrative_dna` busca representar la estructura narrativa de cada unidad de texto con contratos JSON estrictos, validadores determinísticos y una notación compacta derivada.

La meta no es etiquetar todo agresivamente. La meta es producir anotaciones consistentes, explicables y comparables entre frases similares.

## Principios del proyecto

- JSON es la fuente de verdad.
- La notación compacta se deriva del JSON, nunca se edita manualmente.
- La precisión tiene prioridad sobre cobertura falsa.
- La revisión sintética con alta temperatura se usa para diversidad, no como decisión final.
- El agregador y el árbitro final son conservadores.
- Sólo synthetic_gold_high_confidence puede usarse para pruebas de regresión.
- CSV sólo existe como export derivado.

## Notación compacta

La notación es un resumen derivado del JSON:

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

Ejemplos:

```text
(P+V)_S1{0}
(K+Y)!_E2{-}
(S+I+U)_C1{+}
```

Interpretación rápida:

- `FUNCIONES`: funciones narrativas como pregunta, claim, evidencia, explicación, solución.
- `CERTEZA`: símbolo opcional de certeza.
- `EMOCIÓN`: emoción expresada.
- `INTENSIDAD`: intensidad emocional de 0 a 3.
- `POSTURA`: positiva, negativa, mixta o neutral.

La notación nunca se edita manualmente. Si cambia el JSON, se recompila.

## Estado del repo

Estado actual: Steps 0-20 completos.

El proyecto ya tiene arquitectura JSON-first, scaffolding Python, contratos Pydantic estrictos, JSON Schemas, constitución/taxonomía v1.0, validadores determinísticos, compilador de notación, loader/normalizador/segmentador, extracción de heurísticas conservadoras, cliente OpenAI Responses API con Structured Outputs estrictos, clasificador JSON-first por unidad/documento, árbitro conservador para casos de alto riesgo, auditoría por similitud semántica, review sets para comité sintético, workflow de revisión sintética OpenAI, métricas de confiabilidad sintética, detector auditable de relaciones, detector de cadenas narrativas, evaluación con reportes JSON y pipeline/CLI end-to-end.

La capa actual puede leer `.txt`, `.json`, `.jsonl` y `data/transcripts/videos` para producir `NarrativeDocument` con unidades candidatas sin LLM. Las unidades nacen como `N_N0{0}` y las heurísticas agregan sólo señales auditables (`locked_functions`, `candidate_functions`, certeza/emoción/postura candidata y `evidence_spans`); no cambian `functions` ni `final_notation`.

El cliente LLM vive únicamente en `src/narrative_dna/llm_client.py`: lee `OPENAI_API_KEY` del entorno, usa `configs/llm_config.json`, construye `text.format` con `json_schema` y `strict=true`, valida toda respuesta con Pydantic, cachea por hash versionado en `.cache/narrative_dna/`, soporta retries y `dry_run`, y devuelve errores controlados para permitir fallback a heurísticas.

El clasificador vive en `src/narrative_dna/unit_classifier.py`: construye el payload contextual para el modelo, usa `NarrativeUnitPartialClassification`, fusiona locks heurísticos con la salida LLM, ejecuta validadores determinísticos y recompila `final_notation` desde JSON validado.

El adjudicator vive en `src/narrative_dna/adjudicator.py`: se activa por baja confianza, flags críticos, sobre-etiquetado, emoción intensa, conflictos heuristic/LLM, funciones excesivas, primarias confundibles o conflictos de similitud. Su política reduce etiquetas débiles, limpia flags resueltos y vuelve a validar la unidad.

El auditor de similitud vive en `src/narrative_dna/similarity_auditor.py`: construye texto contextual, usa embeddings locales o OpenAI configurable, cachea vectores, calcula vecinos por cosine similarity, mide distancia de notación y escribe `similarity_conflicts.jsonl` más `similarity_conflicts_summary.json` como outputs derivados.

El constructor de review sets vive en `src/narrative_dna/review_set_builder.py`: toma `documents.jsonl`, `similarity_conflicts.jsonl`, pares mínimos y reglas taxonómicas para priorizar unidades con `needs_review`, flags, grupos confundibles, emociones intensas, baja confianza, conflictos semánticos, pares similares con notación distinta y muestras de alta confianza para QA.

La revisión sintética vive en `src/narrative_dna/synthetic_reviewer.py` y `src/narrative_dna/review_aggregator.py`: consume `review/review_items.jsonl`, ejecuta reviewers configurados en `configs/llm_config.json`, agrega de forma conservadora, pasa por un adjudicator final y escribe outputs JSONL trazables.

La confiabilidad sintética vive en `src/narrative_dna/synthetic_reliability.py`: calcula acuerdo entre reviewers, acuerdo aggregator/final, confiabilidad final, buckets high/medium/rejected y elegibilidad de regresión sin volver a llamar al LLM.

El detector de relaciones vive en `src/narrative_dna/relation_detector.py`: aplica reglas determinísticas por funciones, distancia y marcadores textuales para producir `NarrativeRelation` con `run_id`, `evidence_spans`, relaciones rechazadas, flags de revisión y versiones efectivas.

El detector de cadenas vive en `src/narrative_dna/chain_detector.py`: compone relaciones y secuencias multilabel contiguas para producir `NarrativeChain` con `run_id`, secuencia de unidades, relaciones usadas, notación derivada, evidencia, flags y versiones efectivas.

La evaluación vive en `src/narrative_dna/evaluator.py`: compara `documents.jsonl` contra gold JSONL permitido, calcula métricas unitarias y por label, rechaza gold sintético que no sea high-confidence y escribe reportes JSON/MD derivados.

El pipeline vive en `src/narrative_dna/pipeline.py` y escribe outputs con `src/narrative_dna/exporter.py`: carga transcripciones, agrega heurísticas, clasifica/adjudica opcionalmente, detecta relaciones/cadenas, genera manifest, JSONL, `dna_sequences.txt`, `audit_report` y CSV derivados.

La regresión golden vive en `tests/fixtures/golden_regression/`: contiene sólo `synthetic_gold_high_confidence`, re-deriva `final_notation` desde JSON validado y evalúa el fixture con `regression_pass_rate=1.0`.

Siguiente paso natural: Step 21, documentación y guía de operación.

## Instalación

Requisitos:

- Python `>=3.11`
- Git
- Opcional: `OPENAI_API_KEY` para flujos con LLM

Instalación local:

```bash
git clone <REPO_URL>
cd narrative_dna
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Configura variables de entorno:

```bash
cp .env.example .env
```

Ejemplo mínimo:

```env
OPENAI_API_KEY=sk-...
```

## Estructura esperada

```text
narrative_dna/
  pyproject.toml
  README.md
  AGENTS.md
  CLAUDE.md
  .env.example
  PROJECT_CHARTER.md
  ARCHITECTURE.md

  configs/
    project_config.json
    llm_config.json
    synthetic_review_config.json
    taxonomy_v0_1.json
    taxonomy_v1_0.json
    validators_config_v0_1.json
    validators_config_v1_0.json
    similarity_audit_config.json
    relation_patterns.json
    chain_patterns.json
    version_migration_rules.json

  schemas/
    document.schema.json
    unit.schema.json
    relation.schema.json
    chain.schema.json
    audit.schema.json
    gold.schema.json
    taxonomy.schema.json

  annotation_guidelines/
    annotation_constitution_v0_1.md
    annotation_constitution_v1_0.md
    decision_trees_v1_0.md
    label_boundaries_v1_0.json
    minimal_pairs_v1_0.jsonl
    positive_negative_examples_v1_0.jsonl
    validator_rules_v1_0.json
    notation_contract_v1_0.md
    confusion_groups_v1_0.json

  data/
    transcripts/
    gold/
    review/

  outputs/

  prompts/
    unit_classifier.md
    adjudicator.md
    relation_adjudicator.md
    synthetic_reviewer.md
    synthetic_aggregator.md
    synthetic_adjudicator.md

  src/
    narrative_dna/

  tests/
    fixtures/
```

## Formatos de entrada

Se soportan estos formatos:

### `.txt`

```text
Texto completo de la transcripción.
```

### `.json` con transcript

```json
{
  "document_id": "video_001",
  "transcript": "Texto completo...",
  "metadata": {"channel": "demo"}
}
```

### `.json` con segmentos

```json
{
  "document_id": "video_001",
  "segments": [
    {"start_ms": 0, "end_ms": 1000, "text": "Primera frase."}
  ],
  "metadata": {"channel": "demo"}
}
```

### `.jsonl`

Un documento por línea.

## Comandos principales

Validar taxonomía:

```bash
narrative-dna validate-taxonomy
```

Exportar JSON Schemas:

```bash
narrative-dna export-schemas
```

Correr pipeline sin LLM:

```bash
narrative-dna run \
  --input-dir data/transcripts \
  --output-dir outputs \
  --no-llm \
  --no-adjudicator
```

Correr pipeline con LLM:

```bash
narrative-dna run \
  --input-dir data/transcripts \
  --output-dir outputs \
  --use-llm \
  --use-adjudicator \
  --audit-similarity
```

Inspeccionar un run:

```bash
narrative-dna inspect --run-id <RUN_ID>
```

Auditar similitud:

```bash
narrative-dna audit-similarity --run-id <RUN_ID> --top-k 10 --threshold 0.82
```

Detectar relaciones:

```bash
narrative-dna detect-relations --run-id <RUN_ID>
```

Detectar cadenas narrativas:

```bash
narrative-dna detect-chains --run-id <RUN_ID>
```

Construir review set:

```bash
narrative-dna build-review-set --run-id <RUN_ID>
```

Revisión sintética:

```bash
narrative-dna synthetic-review --run-id <RUN_ID>
narrative-dna synthetic-review --run-id <RUN_ID> --dry-run --max-items 3
narrative-dna promote-synthetic-gold --run-id <RUN_ID>
```

Evaluar:

```bash
narrative-dna evaluate --run-id <RUN_ID> --gold data/gold/gold_units.jsonl
narrative-dna evaluate --run-id <RUN_ID> --gold outputs/<RUN_ID>/synthetic_gold_high_confidence.jsonl
```

`evaluate` escribe `evaluation_metrics.json`, `label_metrics.json`, `confusion_groups_report.json`, `audit_report.json` y `audit_report.md`.

Regresión golden local:

```bash
python -m pytest tests/test_golden_regression.py
```

Los fixtures viven en `tests/fixtures/golden_regression/` y usan exclusivamente `synthetic_gold_high_confidence`.

## Pipeline

Flujo end-to-end:

1. Crear `run_id`.
2. Guardar `ProjectRunManifest`.
3. Cargar transcripciones.
4. Normalizar texto.
5. Segmentar en unidades.
6. Aplicar heurísticas conservadoras.
7. Clasificar unidades con o sin LLM.
8. Validar y compilar notación.
9. Adjudicar casos críticos.
10. Detectar relaciones.
11. Detectar cadenas narrativas.
12. Auditar similitud semántica.
13. Construir review set para comité sintético.
14. Ejecutar revisión sintética por comité OpenAI.
15. Exportar JSON/JSONL.
16. Generar reportes y exports derivados.

## Outputs

Cada ejecución escribe en:

```text
outputs/{run_id}/
```

Outputs obligatorios:

```text
run_manifest.json
documents.jsonl
units.jsonl
relations.jsonl
chains.jsonl
audit_report.json
audit_report.md
dna_sequences.txt
exports/units.csv
exports/relations.csv
exports/chains.csv
```

Cuando aplique:

```text
similarity_conflicts.jsonl
similarity_conflicts_summary.json
review/review_items.jsonl
review/review_manifest.json
synthetic_reviews.jsonl
synthetic_review_aggregated.jsonl
synthetic_final_adjudications.jsonl
synthetic_gold_candidates.jsonl
synthetic_review_report.json
synthetic_review_report.md
synthetic_reliability_report.json
synthetic_gold_high_confidence.jsonl
synthetic_gold_medium_confidence.jsonl
synthetic_gold_rejected.jsonl
evaluation_metrics.json
label_metrics.json
confusion_groups_report.json
```

## Campos obligatorios por unidad narrativa

Cada unidad debe preservar, como mínimo:

- `functions`
- `primary_function`
- `secondary_functions`
- `inherited_functions`
- `certainty`
- `emotion_expressed`
- `emotion_intensity`
- `emotions_mentioned`
- `stance`
- `target`
- `speech_act`
- `logic`
- `evidence_spans`
- `rejected_labels`
- `validator_flags`
- `review_status`
- `final_notation`
- `taxonomy_version`
- `prompt_version`
- `validator_version`

## Relaciones externas

Relaciones contempladas:

```text
ANS, SUP, EXPL, ELAB, EXMP, ANLG, CONTR, REFUT, RISK, SOLV, SEQ, SUM, CALL, CAUSE, COND
```

## Taxonomía inicial de funciones

Funciones candidatas:

| Código | Función |
|---|---|
| A | afirmación simple |
| K | claim fuerte |
| O | opinión/interpretación |
| F | definición |
| Y | explicación causal |
| D | dato/evidencia |
| Q | cita/voz externa |
| P | pregunta |
| R | respuesta |
| E | ejemplo |
| H | historia/anécdota |
| G | analogía/comparación |
| C | contraste/giro |
| B | objeción/refutación |
| X | advertencia/riesgo |
| T | transición |
| M | metacomentario |
| L | lista/enumeración |
| Z | cierre/conclusión |
| S | solución/recomendación |
| I | instrucción/paso operativo |
| U | utilidad/aprendizaje |
| V | llamada al espectador |
| N | no clasificado |

## Validadores determinísticos clave

- `N_exclusive`: `N` no coexiste con otras funciones.
- `K_inherits_A`: `K` hereda `A`; `A` pasa a `inherited_functions`.
- `D_requires_evidence`: `D` requiere evidencia concreta.
- `R_requires_anchor`: `R` requiere pregunta cercana o relación `ANS`.
- `emotion_mentioned_vs_expressed`: emoción mencionada no equivale a emoción expresada.
- `overlabeling`: más de 5 funciones activa revisión.
- `primary_function_required`: toda unidad clasificada requiere función primaria.
- `notation_derivation`: `final_notation` siempre se deriva.

## Revisión sintética

El flujo usa un comité de modelos para sustituir revisión humana exhaustiva de forma auditada.

Componentes:

- `divergent_reviewer_a`
- `divergent_reviewer_b`
- `taxonomy_strict_reviewer`
- `synthetic_aggregator`
- `synthetic_final_adjudicator`

Reglas:

- Alta temperatura se usa para diversidad.
- El aggregator es conservador.
- El final adjudicator es el más conservador.
- No se llama `human_gold` a resultados sintéticos.
- Sólo `synthetic_gold_high_confidence` puede usarse en regresión.
- El comando `synthetic-review` consume exclusivamente `review/review_items.jsonl`; no reconstruye contexto desde cero.
- Si falla un reviewer, aggregator o adjudicator final, el flujo registra el fallo y degrada de forma conservadora.
- `promote-synthetic-gold` calcula confiabilidad y escribe buckets derivados; sólo high-confidence limpio y con score suficiente queda elegible para regresión.

## Métricas de evaluación

Métricas esperadas:

- `functions_exact_match`
- `primary_function_accuracy`
- `multilabel_jaccard`
- `micro_precision_recall_f1`
- `macro_precision_recall_f1`
- `f1_by_function`
- `emotion_expressed_accuracy`
- `emotion_intensity_mae`
- `stance_accuracy`
- `certainty_accuracy`
- `overlabeling_rate`
- `N_rate`
- `validator_violation_rate`
- `needs_review_rate`
- `rejected_labels_rate`
- `similarity_conflict_rate`
- `relation_precision_recall_f1`
- `regression_pass_rate`
- `synthetic_gold_reliability_distribution`

## Desarrollo

Tests:

```bash
python -m pytest
```

Lint:

```bash
python -m ruff check .
```

Formato:

```bash
python -m ruff format .
```

Smoke test esperado:

```bash
narrative-dna run --input-dir tests/fixtures/golden_documents --output-dir outputs --no-llm
```

## Versionado

Versiones base:

- `v0_1`: semilla inicial de scaffold y taxonomía.
- `v1_0`: primera taxonomía estable después de auditoría adversarial y consolidación.

Todo cambio en taxonomía debe registrar:

- `from_version`
- `to_version`
- `migration_notes`

Archivo esperado:

```text
configs/version_migration_rules.json
```

## Roadmap de implementación

| Step | Fase | Reasoning | Commit esperado |
| --- | --- | --- | --- |
| 0 | Arquitectura JSON-first y principios del proyecto | xhigh | init: define narrative dna architecture and json-first principles |
| 1 | Scaffolding del repositorio | medium | chore: scaffold json-first narrative dna package |
| 2 | Modelos Pydantic y JSON Schemas estrictos | high | feat: define strict pydantic models and json schemas |
| 3 | Constitución de Anotación v0.1 | xhigh | feat: create annotation constitution v0.1 with boundaries and minimal pairs |
| 4 | Auditoría adversarial de la Constitución v0.1 | xhigh | audit: adversarially review annotation constitution v0.1 |
| 5 | Consolidar Constitución v1.0 estable | xhigh | feat: consolidate stable annotation constitution v1.0 |
| 6 | Validadores determinísticos y compilador de notación | high | feat: implement deterministic validators and notation compiler |
| 7 | Loader, normalizador y segmentador JSON-first | medium | feat: add transcript loading normalization and segmentation |
| 8 | Heurísticas conservadoras como candidatos | high | feat: add conservative heuristic candidate extraction |
| 9 | Cliente OpenAI con Structured Outputs, cache y versiones | high | feat: add structured openai client with cache and schema validation |
| 10 | Clasificador de unidades JSON-first | high | feat: implement json-first unit classifier |
| 11 | Árbitro conservador de precisión | xhigh | feat: add conservative adjudicator for high-risk classifications |
| 12 | Auditoría por similitud semántica | high | feat: add semantic similarity auditor for notation consistency |
| 13 | Construir review set para comité sintético | medium | feat: build synthetic review set with boundary and similarity cases |
| 14 | Revisión sintética por comité OpenAI | high | feat: add synthetic openai committee review workflow |
| 15 | Métricas de confiabilidad sintética | high | feat: add reliability scoring for synthetic review outputs |
| 16 | Detector auditable de relaciones | high | feat: implement auditable relation detection |
| 17 | Detector de cadenas narrativas | medium | feat: detect narrative chains over multilabel sequences |
| 18 | Evaluación, métricas y reportes JSON | high | feat: add evaluation and audit metrics |
| 19 | Pipeline y CLI end-to-end JSON-first | high | feat: wire end-to-end json-first pipeline and cli |
| 20 | Golden regression tests con synthetic high-confidence | high | test: add golden regression fixtures for notation stability |
| 21 | Documentación y guía de operación | medium | docs: add operating guide for stable auditable synthetic-reviewed annotations |

## Reglas para contribuir

Antes de abrir PR:

- Corre tests.
- Corre lint.
- Valida JSON/JSONL.
- Explica cambios en contratos.
- Incluye tests para validadores.
- No mezcles cambios de taxonomía con refactors grandes.
- No promociones gold sintético sin confiabilidad alta.
- No incluyas secretos.

## Licencia

Pendiente de definir.
