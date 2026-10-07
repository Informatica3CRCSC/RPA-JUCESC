import os
from pathlib import Path


PASTA_RESULTADOS = Path(
    os.environ.get("RPA_OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs")
).resolve()
TAMANHO_MAXIMO_UPLOAD = 1024 * 1024
