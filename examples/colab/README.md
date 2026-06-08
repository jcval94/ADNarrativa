# Colab Examples

Estos ejemplos están pensados para ejecutar `narrative_dna` desde cero en
Google Colab: clonan el repo desde GitHub, instalan el paquete, importan los
módulos principales y corren el pipeline JSON-first desde texto general.

## Notebook Principal

[Abrir en Colab](https://colab.research.google.com/github/jcval94/ADNarrativa/blob/main/examples/colab/narrative_dna_quickstart.ipynb)

Archivo:

```text
examples/colab/narrative_dna_quickstart.ipynb
```

Incluye:

- descarga del repo con `git clone`;
- instalación editable con `pip install -e ".[dev]"`;
- imports de `load_text_document`, `run_pipeline_from_text`, `run_pipeline` y `load_gold_units`;
- ejecución conservadora sin LLM desde un string en memoria;
- ejecución alternativa desde un archivo `.txt`;
- lectura de outputs JSON/JSONL;
- visualización de `heuristic_candidates`, ya que sin LLM la clasificación final permanece como `N_N0{0}`;
- regresión golden local;
- celda opcional para usar `OPENAI_API_KEY` desde Colab Secrets.

## Uso Rápido En Una Celda

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

En modo sin LLM, `final_notation` seguirá siendo `N_N0{0}` por diseño. Mira
`heuristic_candidates` para ver señales determinísticas auditables, o usa
`use_llm=True` para clasificación final.
