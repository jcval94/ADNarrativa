# AGENTS.md

Guía raíz para agentes de código que trabajen en `narrative_dna`.

Este repositorio implementa un MVP **JSON-first** para convertir transcripciones en una representación estable, interpretable y auditable de ADN narrativo.

## 1. Principios no negociables

- JSON es la fuente de verdad.
- La notación compacta se deriva del JSON, nunca se edita manualmente.
- La precisión tiene prioridad sobre cobertura falsa.
- La revisión sintética con alta temperatura se usa para diversidad, no como decisión final.
- El agregador y el árbitro final son conservadores.
- Sólo synthetic_gold_high_confidence puede usarse para pruebas de regresión.
- CSV sólo existe como export derivado.

La notación derivada del proyecto es:

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

Ejemplos: `(P+V)_S1{0}`, `(K+Y)!_E2{-}`, `(S+I+U)_C1{+}`.

## 2. Regla de oro para agentes

Antes de modificar código, identifica en qué capa estás trabajando:

1. **Contrato**: modelos Pydantic, JSON Schema, taxonomía, validadores.
2. **Ingesta**: loader, normalizer, segmenter.
3. **Candidatos**: heurísticas conservadoras.
4. **Inferencia**: cliente OpenAI, clasificador, adjudicator.
5. **Auditoría**: similitud, clusters, review sets.
6. **Revisión sintética**: reviewers, aggregator, final adjudicator, reliability.
7. **Outputs derivados**: exports, CSV, reportes, secuencias compactas.

No mezcles capas en un cambio si no es estrictamente necesario.

## 3. Reglas de edición

- No edites `final_notation` manualmente. Debe compilarse desde JSON validado.
- No uses CSV como fuente de verdad. CSV sólo puede existir en `outputs/{run_id}/exports/` como derivado.
- Todo output importante debe incluir `run_id`.
- Toda anotación debe conservar:
  - `taxonomy_version`
  - `prompt_version`
  - `validator_version`
- Todo output JSON/JSONL/MD importante debe incluir:
  - `taxonomy_version_effective`
  - `prompt_version_effective`
  - `validator_version_effective`
- Todo cambio en taxonomía debe actualizar pares mínimos, fronteras, validadores esperados y changelog.
- Toda regla que reduzca ambigüedad debe tener test.
- Si una decisión puede ser determinística, no la mandes al LLM.
- Si el modelo duda, baja confianza y marca `needs_review=true`.

## 4. Dependencias y stack esperado

Usa Python `>=3.11`.

Dependencias principales:

- `pydantic`
- `typer`
- `pandas` sólo para exports derivados
- `pyyaml`
- `pytest`
- `ruff`
- `rich`
- OpenAI Responses API sólo a través de `src/narrative_dna/llm_client.py`

No agregues dependencias pesadas sin justificarlo en el PR.

## 5. Comandos permitidos y recomendados

Instalación local:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Validación rápida:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Comandos CLI esperados:

- `narrative-dna validate-taxonomy`
- `narrative-dna run`
- `narrative-dna evaluate`
- `narrative-dna inspect`
- `narrative-dna audit-similarity`
- `narrative-dna build-review-set`
- `narrative-dna synthetic-review`
- `narrative-dna promote-synthetic-gold`
- `narrative-dna export-schemas`

Ejecución sin LLM:

```bash
narrative-dna run --input-dir data/transcripts --output-dir outputs --no-llm --no-adjudicator
```

Ejecución con LLM:

```bash
narrative-dna run --input-dir data/transcripts --output-dir outputs --use-llm --use-adjudicator
```

Auditoría:

```bash
narrative-dna audit-similarity --run-id <RUN_ID> --top-k 10 --threshold 0.82
narrative-dna build-review-set --run-id <RUN_ID>
narrative-dna synthetic-review --run-id <RUN_ID>
narrative-dna promote-synthetic-gold --run-id <RUN_ID>
narrative-dna evaluate --run-id <RUN_ID> --gold outputs/<RUN_ID>/synthetic_gold_high_confidence.jsonl
```

## 6. Comandos prohibidos o de alto riesgo

No ejecutes sin permiso explícito:

```bash
rm -rf data/
rm -rf outputs/
rm -rf .git/
git push --force
git reset --hard
```

No imprimas ni guardes secretos:

- `OPENAI_API_KEY`
- tokens personales
- credenciales locales
- dumps de `.env`

No llames APIs externas excepto OpenAI cuando el flujo lo requiera y esté configurado por `llm_config.json`.

## 7. Política de modelos y razonamiento

Modelo Codex por defecto: `GPT-5.5`.

Guía de reasoning:

| Tipo de tarea | Reasoning |
|---|---|
| Arquitectura y taxonomía | `xhigh` |
| Auditoría y estabilidad | `xhigh` |
| Schemas y validadores | `high` |
| Implementación mecánica | `medium` |
| Documentación | `medium` |

Regla práctica:

- Usa razonamiento alto para contratos, validadores, taxonomía, auditoría y regresión.
- Usa razonamiento medio para scaffolding, documentación y cambios mecánicos.
- No reduzcas reasoning en decisiones críticas de adjudicación final.

## 8. Política de revisión sintética

La revisión sintética reemplaza una revisión humana exhaustiva, pero no debe presentarse como gold humano.

Nombres correctos:

- `synthetic_review`
- `synthetic_gold_candidate`
- `synthetic_gold_high_confidence`
- `synthetic_gold_medium_confidence`
- `synthetic_gold_rejected`

Reglas:

- Alta temperatura se usa sólo para diversidad de reviewers.
- El aggregator debe ser conservador.
- El final adjudicator debe ser aún más conservador.
- Sólo `synthetic_gold_high_confidence` puede usarse para pruebas de regresión.
- `medium` sirve para análisis, no para congelar reglas.
- `rejected` nunca se promueve como gold.

## 9. Estructura esperada del repo

```text
configs/
schemas/
annotation_guidelines/
data/
  transcripts/
  gold/
  review/
outputs/
prompts/
src/
  narrative_dna/
tests/
```

Archivos raíz esperados:

```text
README.md
AGENTS.md
CLAUDE.md
PROJECT_CHARTER.md
ARCHITECTURE.md
pyproject.toml
.env.example
```

## 10. Convenciones de outputs

Todo run debe escribir:

```text
outputs/{run_id}/run_manifest.json
outputs/{run_id}/documents.jsonl
outputs/{run_id}/units.jsonl
outputs/{run_id}/relations.jsonl
outputs/{run_id}/chains.jsonl
outputs/{run_id}/audit_report.json
outputs/{run_id}/audit_report.md
outputs/{run_id}/dna_sequences.txt
outputs/{run_id}/exports/units.csv
outputs/{run_id}/exports/relations.csv
outputs/{run_id}/exports/chains.csv
```

Los CSV deben ser reconstruibles desde JSON/JSONL.

## 11. Política de commits

Usa commits pequeños, auditables y con Conventional Commits.

Ejemplos:

```bash
git commit -m "feat: define strict pydantic models and json schemas"
git commit -m "test: add golden regression fixtures for notation stability"
git commit -m "docs: add operating guide for stable auditable synthetic-reviewed annotations"
```

No hagas commit si:

- fallan tests relevantes;
- agregaste JSON inválido;
- hay outputs importantes sin versión efectiva;
- el cambio rompe el contrato JSON-first;
- promoviste gold sintético no high-confidence.

## 12. Checklist antes de entregar

- [ ] `python -m pytest` pasa o se documentan fallos no relacionados.
- [ ] `python -m ruff check .` pasa.
- [ ] JSON/JSONL modificado parsea correctamente.
- [ ] No hay CSV como fuente de verdad.
- [ ] `final_notation` se deriva desde JSON.
- [ ] Nuevas reglas tienen tests.
- [ ] Cambios de taxonomía actualizan pares mínimos/fronteras/changelog.
- [ ] Outputs incluyen `run_id` y versiones efectivas.
- [ ] No se expusieron secretos.
- [ ] El commit message refleja la fase trabajada.

## 13. Plan maestro de implementación

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
