# Colab Examples

Estos ejemplos están pensados para ejecutar `narrative_dna` desde cero en
Google Colab: clonan el repo desde GitHub, instalan el paquete, importan los
módulos principales y corren el pipeline JSON-first.

## Notebook Principal

[Abrir en Colab](https://colab.research.google.com/github/jcval94/ADNarrativa/blob/main/examples/colab/narrative_dna_quickstart.ipynb)

Archivo:

```text
examples/colab/narrative_dna_quickstart.ipynb
```

Incluye:

- descarga del repo con `git clone`;
- instalación editable con `pip install -e ".[dev]"`;
- imports de `load_documents`, `run_pipeline` y `load_gold_units`;
- ejecución conservadora sin LLM sobre `data/transcripts/videos`;
- lectura de outputs JSON/JSONL;
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

from narrative_dna.loader import load_documents
from narrative_dna.pipeline import run_pipeline

documents = load_documents("data/transcripts/videos", limit=1)
result = run_pipeline(
    input_dir="data/transcripts/videos",
    output_dir="outputs",
    run_id="colab_no_llm_demo",
    use_llm=False,
    use_adjudicator=False,
    limit=1,
)
print(result.run_dir)
```
