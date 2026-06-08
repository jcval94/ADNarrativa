# Guía de Operación

Esta guía describe cómo ejecutar `narrative_dna` como MVP JSON-first para
obtener anotaciones estables, interpretables y auditables desde transcripciones.
La regla central no cambia: JSON validado es la fuente de verdad y la notación
compacta se deriva desde ese JSON.

## Principios Operativos

- No edites `final_notation` manualmente.
- No uses CSV como entrada ni como fuente de verdad.
- Mantén `run_id`, `taxonomy_version_effective`, `prompt_version_effective` y
  `validator_version_effective` en todo output importante.
- Ejecuta primero el flujo sin LLM para revisar carga, normalización,
  segmentación, heurísticas, relaciones y cadenas.
- Activa LLM sólo cuando quieras clasificación de unidades o revisión sintética.
- Trata `synthetic_gold_high_confidence` como gold de regresión sintético, no
  como gold humano.
- No uses `synthetic_gold_medium_confidence` ni `synthetic_gold_rejected` para
  congelar comportamiento.

## Preparación Local

Instala el paquete y dependencias de desarrollo:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Para flujos con OpenAI, define `OPENAI_API_KEY` en el entorno o en `.env` según
tu forma habitual de cargar variables locales. No imprimas ni guardes el valor
del secreto en outputs, logs o commits.

Verifica que los contratos y la suite base pasan:

```bash
python -m pytest --basetemp .pytest_tmp
python -m ruff check .
python -m ruff format --check .
```

## Ejecución En Google Colab

El repo incluye un notebook que clona GitHub, instala el paquete e importa los
módulos principales:

```text
examples/colab/narrative_dna_quickstart.ipynb
```

Ábrelo directamente en Colab:

```text
https://colab.research.google.com/github/jcval94/ADNarrativa/blob/main/examples/colab/narrative_dna_quickstart.ipynb
```

El flujo mínimo dentro de Colab es:

```python
from pathlib import Path
import os
import subprocess

repo_url = "https://github.com/jcval94/ADNarrativa.git"
repo_dir = Path("/content/ADNarrativa")
if not repo_dir.exists():
    subprocess.run(["git", "clone", repo_url, str(repo_dir)], check=True)
os.chdir(repo_dir)
```

Después:

```python
%pip install -q -e ".[dev]"

from narrative_dna.loader import load_text_document
from narrative_dna.pipeline import run_pipeline_from_text

transcript_text = """
Te propongo algo simple. Crea tu propia caja negra emocional.
¿Qué aprendiste este año? ¿Qué quieres dejar registrado?
""".strip()

document = load_text_document(transcript_text, document_id="colab_text_demo", language="es")
result = run_pipeline_from_text(
    transcript_text,
    document_id="colab_text_demo",
    output_dir="outputs",
    run_id="colab_text_no_llm_demo",
    use_llm=False,
    use_adjudicator=False,
)
print(result.run_dir)
```

En este workspace puede haber archivos untracked ajenos al MVP que hagan fallar
Ruff global. Para validar sólo el proyecto versionado:

```bash
$files = @(git ls-files '*.py')
python -m ruff check $files
python -m ruff format --check $files
```

## Flujo Conservador Sin LLM

Empieza por el dataset real disponible:

```bash
narrative-dna run ^
  --input-dir data/transcripts/videos ^
  --output-dir outputs ^
  --no-llm ^
  --no-adjudicator
```

Para una prueba rápida:

```bash
narrative-dna run ^
  --input-dir data/transcripts/videos ^
  --output-dir outputs ^
  --no-llm ^
  --no-adjudicator ^
  --limit 1
```

El modo sin LLM produce unidades `N_N0{0}` como clasificación final, agrega
heurísticas como señales candidatas auditables en `heuristic_candidates` y
detecta relaciones/cadenas con reglas determinísticas. Esto sirve para comprobar
que la ingesta y los outputs están sanos antes de pagar o confiar en inferencia.
Si necesitas etiquetas finales distintas de `N_N0{0}`, ejecuta el clasificador
con `--use-llm` o usa `run_pipeline_from_text(..., use_llm=True)`.

Después inspecciona el run:

```bash
narrative-dna inspect --run-id <RUN_ID>
```

Revisa estos archivos primero:

```text
outputs/<RUN_ID>/run_manifest.json
outputs/<RUN_ID>/documents.jsonl
outputs/<RUN_ID>/units.jsonl
outputs/<RUN_ID>/relations.jsonl
outputs/<RUN_ID>/chains.jsonl
outputs/<RUN_ID>/audit_report.md
outputs/<RUN_ID>/dna_sequences.txt
```

Los CSV de `outputs/<RUN_ID>/exports/` son derivados reconstruibles. Úsalos para
inspección externa, no para reanotar ni corregir verdad.

## Flujo Con Clasificación LLM

Cuando la ingesta conservadora se vea correcta, ejecuta clasificación
estructurada:

```bash
narrative-dna run ^
  --input-dir data/transcripts/videos ^
  --output-dir outputs ^
  --use-llm ^
  --use-adjudicator ^
  --audit-similarity
```

Este flujo carga, normaliza y segmenta transcripciones; agrega heurísticas
candidatas; llama a OpenAI sólo a través de `src/narrative_dna/llm_client.py`;
valida cada respuesta con Pydantic; recompila `final_notation`; pasa casos de
riesgo al adjudicator conservador; detecta relaciones/cadenas; y escribe
outputs JSON/JSONL con derivados reconstruibles.

Si el modelo duda, la política correcta es bajar confianza y marcar
`needs_review=true`. Una anotación incompleta pero honesta es preferible a una
cobertura falsa.

## Auditoría De Similitud

Si no activaste `--audit-similarity` en el run principal, puedes ejecutarla
después:

```bash
narrative-dna audit-similarity --run-id <RUN_ID> --top-k 10 --threshold 0.82
```

La auditoría produce:

```text
outputs/<RUN_ID>/similarity_conflicts.jsonl
outputs/<RUN_ID>/similarity_conflicts_summary.json
```

Interpreta los conflictos como candidatos de revisión, no como errores
automáticos. Dos frases similares pueden tener notación distinta si el contexto,
el target, la postura o el acto de habla lo justifican.

## Review Set Sintético

Construye un set de revisión antes de llamar al comité:

```bash
narrative-dna build-review-set --run-id <RUN_ID>
```

Salida esperada:

```text
outputs/<RUN_ID>/review/review_items.jsonl
outputs/<RUN_ID>/review/review_manifest.json
```

El review set prioriza unidades con `needs_review`, flags, conflictos de
similitud, grupos confundibles, emociones intensas, baja confianza, pares
similares con notación distinta y muestras de alta confianza para QA.

Antes de gastar llamadas reales, prueba el workflow:

```bash
narrative-dna synthetic-review --run-id <RUN_ID> --dry-run --max-items 3
```

Cuando el dry run esté sano:

```bash
narrative-dna synthetic-review --run-id <RUN_ID>
```

Outputs principales:

```text
outputs/<RUN_ID>/synthetic_reviews.jsonl
outputs/<RUN_ID>/synthetic_review_aggregated.jsonl
outputs/<RUN_ID>/synthetic_final_adjudications.jsonl
outputs/<RUN_ID>/synthetic_gold_candidates.jsonl
outputs/<RUN_ID>/synthetic_review_report.json
outputs/<RUN_ID>/synthetic_review_report.md
```

El comité sintético no reconstruye contexto desde cero; consume
`review/review_items.jsonl`. Esto mantiene trazabilidad y evita que cada etapa
invente su propio problema.

## Promoción A Synthetic Gold

Promueve candidatos sólo después de calcular confiabilidad:

```bash
narrative-dna promote-synthetic-gold --run-id <RUN_ID>
```

Salida esperada:

```text
outputs/<RUN_ID>/synthetic_reliability_report.json
outputs/<RUN_ID>/synthetic_gold_high_confidence.jsonl
outputs/<RUN_ID>/synthetic_gold_medium_confidence.jsonl
outputs/<RUN_ID>/synthetic_gold_rejected.jsonl
```

Reglas de uso:

- `synthetic_gold_high_confidence`: puede usarse para regresión.
- `synthetic_gold_medium_confidence`: sirve para análisis y refinamiento, no
  para congelar comportamiento.
- `synthetic_gold_rejected`: nunca se promueve ni se usa como gold.

Un candidato high-confidence debe ser limpio, conservador, sin flags críticos,
sin `needs_review` y con confiabilidad suficiente.

## Evaluación

Evalúa un run contra gold permitido:

```bash
narrative-dna evaluate ^
  --run-id <RUN_ID> ^
  --gold outputs/<RUN_ID>/synthetic_gold_high_confidence.jsonl
```

También puedes evaluar contra gold humano si existe:

```bash
narrative-dna evaluate --run-id <RUN_ID> --gold data/gold/gold_units.jsonl
```

El evaluador rechaza candidatos sintéticos medium/rejected. Reportes:

```text
outputs/<RUN_ID>/evaluation_metrics.json
outputs/<RUN_ID>/label_metrics.json
outputs/<RUN_ID>/confusion_groups_report.json
outputs/<RUN_ID>/audit_report.json
outputs/<RUN_ID>/audit_report.md
```

Lecturas recomendadas:

- `regression_pass_rate`: estabilidad exacta de notación y ausencia de review en
  unidades esperadas.
- `functions_exact_match`: coincidencia multilabel estricta.
- `primary_function_accuracy`: estabilidad de función principal.
- `validator_violation_rate`: densidad de flags.
- `needs_review_rate`: proporción de casos que el sistema no debe fingir como
  resueltos.
- `similarity_conflict_rate`: posible inconsistencia entre frases similares.

## Regresión Golden

El repo incluye fixtures mínimos de regresión:

```text
tests/fixtures/golden_regression/
```

Ejecuta:

```bash
python -m pytest tests/test_golden_regression.py
```

Estas pruebas aseguran que:

- sólo `synthetic_gold_high_confidence` entra a regresión;
- `final_notation` se re-deriva desde JSON validado;
- un intento de editar manualmente la notación es reparado por validadores;
- el fixture estable evalúa con `regression_pass_rate=1.0`.

Cuando agregues nuevos casos golden, usa únicamente outputs promovidos como
`synthetic_gold_high_confidence` y conserva las versiones efectivas.

## Checklist Antes De Congelar Un Run

- `run_manifest.json` existe e incluye `run_id`, versiones y config snapshot.
- `documents.jsonl`, `units.jsonl`, `relations.jsonl` y `chains.jsonl` parsean.
- No hay CSV usado como input.
- `final_notation` coincide con la derivación desde JSON.
- Los flags críticos tienen explicación o review set.
- Los conflictos de similitud fueron revisados o preservados como deuda
  auditable.
- Sólo high-confidence entra en evaluación de regresión.
- `python -m pytest --basetemp .pytest_tmp` pasa o los fallos ajenos quedan
  documentados.
- Ruff pasa en los archivos versionados del proyecto.
- No hay secretos en outputs, logs o commits.

## Diagnóstico Rápido

Si faltan outputs principales, revisa `run_manifest.json`, la ruta `--input-dir`
y si `load_documents` encontró transcripciones soportadas.

Si muchas unidades quedan como `N_N0{0}`, confirma si ejecutaste `--no-llm`. En
ese modo es esperado: las heurísticas no cambian la clasificación final.

Si aparecen demasiados `needs_review`, revisa flags, baja confianza, conflictos
heurística/LLM y grupos confundibles. No reduzcas review artificialmente para
mejorar métricas.

Si `synthetic-review` falla, prueba `--dry-run --max-items 3`, revisa
`review/review_items.jsonl`, confirma `OPENAI_API_KEY` y valida
`configs/llm_config.json`.

Si Ruff global falla por archivos no versionados, valida el alcance versionado
con `git ls-files '*.py'` y documenta los untracked ajenos.

## Mantenimiento De Taxonomía, Prompts Y Validadores

Cuando cambie una regla taxonómica:

1. Actualiza la constitución y el changelog.
2. Ajusta pares mínimos, fronteras y ejemplos esperados.
3. Actualiza validadores determinísticos si la regla puede resolverse sin LLM.
4. Regenera o valida schemas si cambian contratos.
5. Añade pruebas antes de promover nuevos fixtures golden.
6. Sube la versión efectiva correspondiente.

Cuando cambie un prompt:

1. Mantén el JSON Schema estricto.
2. Preserva el principio de baja cobertura falsa.
3. Ajusta `prompt_version_effective`.
4. Re-ejecuta review set, revisión sintética y evaluación.

Cuando cambie un validador:

1. Añade o actualiza tests de borde.
2. Comprueba que `final_notation` se sigue derivando.
3. Re-ejecuta regresión golden.
4. Actualiza `validator_version_effective` si el comportamiento cambia.

## Criterio De Listo

Un run está listo para análisis cuando sus JSON/JSONL validan, los outputs
derivados son reconstruibles, las inconsistencias están auditadas y cualquier
gold sintético usado para regresión proviene exclusivamente de
`synthetic_gold_high_confidence`.
