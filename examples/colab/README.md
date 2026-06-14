# Colab Examples

Estos ejemplos están pensados para ejecutar `narrative_dna` desde cero en
Google Colab: clonan el repo desde GitHub, instalan el paquete, importan los
módulos principales y corren el pipeline JSON-first desde texto general.

## Notebook Principal

[Abrir en Colab, rama main](https://colab.research.google.com/github/jcval94/ADNarrativa/blob/main/examples/colab/narrative_dna_quickstart.ipynb)

[Abrir en Colab, rama con timing LLM](https://colab.research.google.com/github/jcval94/ADNarrativa/blob/codex/add-llm-timing-logs/examples/colab/narrative_dna_quickstart.ipynb)

Archivo:

```text
examples/colab/narrative_dna_quickstart.ipynb
```

Incluye:

- descarga del repo con `git clone` y selección de rama;
- instalación editable con `pip install -e ".[dev]"`;
- imports de `load_text_document`, `run_pipeline_from_text` y `run_pipeline`;
- un caso de prueba exigente con analogía, tesis, evidencia simulada, riesgo, recomendación, instrucciones y preguntas;
- ejecución conservadora sin LLM desde un string en memoria;
- ejecución alternativa desde un archivo `.txt`;
- lectura de outputs JSON/JSONL sin usar CSV como fuente de verdad;
- utilidades para imprimir `ADN -> frase`, evidencia, confianza, revisión, relaciones, cadenas y auditoría;
- regresión golden local;
- celda opcional para usar `OPENAI_API_KEY` desde Colab Secrets;
- timing por etapa en modo LLM, incluyendo cada `openai.api_call` y su `api_call_purpose`.

## Uso Rápido En Una Celda

```python
import os
import subprocess
from pathlib import Path

repo_url = "https://github.com/jcval94/ADNarrativa.git"
repo_branch = os.environ.get("ADNARRATIVA_BRANCH", "codex/add-llm-timing-logs")
repo_dir = Path("/content/ADNarrativa")

if not repo_dir.exists():
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", repo_branch, repo_url, str(repo_dir)],
        check=True,
    )
os.chdir(repo_dir)
```

Después:

```python
%pip install -q -e ".[dev]"

from narrative_dna.pipeline import run_pipeline_from_text

transcript_text = "\n".join(
    [
        "Imagina un hospital pequeño que quiere usar IA para priorizar llamadas de pacientes.",
        "El director cree que el sistema debe ser una brújula, no un piloto automático.",
        "Pero hay un riesgo serio: si los datos históricos tienen sesgos, la IA puede repetirlos.",
        "Primero define qué decisión se automatiza; después mide falsos positivos y negativos.",
        "¿A quién ayuda este sistema? ¿Qué evidencia necesitarías antes de confiar en él?",
    ]
)

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

En modo sin LLM, `final_notation` ya no queda fijo en `N_N0{0}` cuando hay
señales determinísticas fuertes: el pipeline promueve un baseline heurístico
conservador, conserva `heuristic_candidates` como evidencia auditable y marca
revisión para señales candidatas o multietiqueta. Usa `use_llm=True`,
`use_adjudicator=True` y `log_timings=True` cuando necesites inferencia
estructurada y tiempos por etapa.
