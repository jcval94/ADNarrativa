# CLAUDE.md

Memoria de proyecto para Claude Code trabajando dentro de `narrative_dna`.

## Identidad del proyecto

`narrative_dna` es un sistema Python para convertir transcripciones de discursos en ADN narrativo auditable.

Objetivo central:

> Implementar desde cero un MVP JSON-first para ADN narrativo estable, interpretable y auditable.

La fuente de verdad es JSON validado por Pydantic/JSON Schema. La notación compacta sólo se deriva.

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

Ejemplos:

- `(P+V)_S1{0}`
- `(K+Y)!_E2{-}`
- `(S+I+U)_C1{+}`

## Principios operativos

- JSON es la fuente de verdad.
- La notación compacta se deriva del JSON, nunca se edita manualmente.
- La precisión tiene prioridad sobre cobertura falsa.
- La revisión sintética con alta temperatura se usa para diversidad, no como decisión final.
- El agregador y el árbitro final son conservadores.
- Sólo synthetic_gold_high_confidence puede usarse para pruebas de regresión.
- CSV sólo existe como export derivado.

## Cómo debes pensar el repo

Este proyecto no es sólo un clasificador. Es un sistema de contratos, auditoría y estabilidad.

Prioridades en orden:

1. Contratos JSON estrictos.
2. Taxonomía con fronteras claras.
3. Validadores determinísticos.
4. Notación derivada.
5. Auditoría de similitud.
6. Revisión sintética conservadora.
7. Evaluación y regresión.
8. Exports derivados.

No optimices por cobertura aparente. Optimiza por precisión, trazabilidad y consistencia.

## Arquitectura mental

```text
transcripts
  -> loader / normalizer / segmenter
  -> heuristic_candidates
  -> unit_classifier
  -> validators
  -> notation compiler
  -> adjudicator
  -> relation_detector
  -> chain_detector
  -> similarity_auditor
  -> review_set_builder
  -> synthetic_review committee
  -> reliability scoring
  -> evaluator
  -> JSON/JSONL outputs
  -> derived CSV/TXT exports
```

## Archivos críticos

- `src/narrative_dna/models.py`: contratos Pydantic. Si esto cambia, revisa schemas y tests.
- `src/narrative_dna/notation.py`: compilador de notación. No debe aceptar edición manual de `final_notation`.
- `src/narrative_dna/validators.py`: reglas determinísticas de estabilidad.
- `configs/taxonomy_v1_0.json`: taxonomía estable después de consolidación.
- `annotation_guidelines/*`: reglas de frontera, pares mínimos y criterios de decisión.
- `prompts/*.md`: prompts versionables.
- `outputs/{run_id}/run_manifest.json`: manifiesto de trazabilidad.
- `tests/fixtures/golden_units.jsonl`: regresión para evitar drift de notación.

## Reglas de edición para Claude Code

### Haz

- Prefiere cambios pequeños y verificables.
- Escribe tests junto con cada regla nueva.
- Usa validación Pydantic antes de cualquier output.
- Mantén compatibilidad con Python `>=3.11`.
- Usa Typer para CLI.
- Usa Rich para logs legibles.
- Usa Pandas sólo en exporters derivados.
- Mantén toda llamada OpenAI encapsulada en `llm_client.py`.
- Usa cache por hash cuando haya inferencia LLM.

### No hagas

- No edites `final_notation` manualmente.
- No uses CSV como input canónico.
- No promuevas synthetic gold de confiabilidad media o baja a regresión.
- No mezcles `human_gold` con `synthetic_gold`.
- No agregues nuevas etiquetas sin actualizar boundaries, minimal pairs y validators.
- No llames APIs externas fuera de OpenAI sin instrucción explícita.
- No hardcodees claves, rutas locales personales ni modelos fuera de configs.
- No borres `data/`, `outputs/` o `.git/`.

## Checklist antes de terminar cualquier tarea

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Además confirma:

- JSON/JSONL nuevo parsea.
- No hay campos extra no permitidos.
- Todos los artifacts relevantes tienen `run_id`.
- Toda anotación tiene `taxonomy_version`, `prompt_version`, `validator_version`.
- Todo output importante tiene versiones efectivas:
  - `taxonomy_version_effective`
  - `prompt_version_effective`
  - `validator_version_effective`
- La notación se recompila desde JSON.
- Los CSV, si existen, son derivados.
- Se actualizó documentación cuando cambió contrato o comando.

## Comandos de trabajo

Instalar:

```bash
python -m pip install -e ".[dev]"
```

Validar taxonomía:

```bash
narrative-dna validate-taxonomy
```

Exportar schemas:

```bash
narrative-dna export-schemas
```

Correr sin LLM:

```bash
narrative-dna run --input-dir data/transcripts --output-dir outputs --no-llm
```

Correr con LLM:

```bash
narrative-dna run --input-dir data/transcripts --output-dir outputs --use-llm --use-adjudicator
```

Auditar similitud:

```bash
narrative-dna audit-similarity --run-id <RUN_ID> --top-k 10 --threshold 0.82
```

Construir revisión:

```bash
narrative-dna build-review-set --run-id <RUN_ID>
```

Revisión sintética:

```bash
narrative-dna synthetic-review --run-id <RUN_ID>
narrative-dna promote-synthetic-gold --run-id <RUN_ID>
```

Evaluar:

```bash
narrative-dna evaluate --run-id <RUN_ID> --gold outputs/<RUN_ID>/synthetic_gold_high_confidence.jsonl
```

## Política de modelos runtime

Configuración recomendada:

| Componente | Modelo | Reasoning | Temperatura |
|---|---:|---:|---:|
| main_classifier | gpt-5.5 | medium | 0.1 |
| adjudicator | gpt-5.5 | high | 0.0 |
| divergent_reviewer_a | gpt-5.5 | high | 0.9 |
| divergent_reviewer_b | gpt-5.5 | high | 1.0 |
| taxonomy_strict_reviewer | gpt-5.5 | high | 0.7 |
| synthetic_aggregator | gpt-5.5 | high | 0.1 |
| synthetic_final_adjudicator | gpt-5.5 | xhigh | 0.0 |

Interpretación:

- Los reviewers pueden ser creativos para encontrar ambigüedad.
- El aggregator y final adjudicator no deben ser creativos.
- El final adjudicator debe rechazar antes que inventar certeza.

## Señales de alerta

Detente y corrige si ves:

- `N` coexistiendo con otra función.
- `K` y `A` simultáneamente en `functions` en vez de `A` heredado.
- `D` sin evidencia concreta.
- `R` sin anclaje de pregunta.
- emoción expresada inferida sólo porque el texto menciona una emoción.
- más de 5 funciones en una unidad sin `possible_overlabeling`.
- `final_notation` hardcodeada.
- outputs sin versionado efectivo.
- synthetic gold usado como humano.

## Plan de fases

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
