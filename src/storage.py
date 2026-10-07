import uuid
from pathlib import Path

ARQUIVOS_RESULTADO = {".csv", ".pdf"}


def criar_pasta_consulta(pasta_resultados: Path) -> tuple[str, Path]:
    consulta_id = str(uuid.uuid4())
    pasta_consulta = (pasta_resultados / consulta_id).resolve()
    pasta_consulta.mkdir(parents=True, exist_ok=False)
    return consulta_id, pasta_consulta


def listar_arquivos(pasta_consulta: Path) -> list[Path]:
    return sorted(
        path
        for path in pasta_consulta.iterdir()
        if path.is_file() and path.suffix.casefold() in ARQUIVOS_RESULTADO
    )


def caminho_arquivo(pasta_consulta: Path, nome: str) -> Path | None:
    if Path(nome).name != nome:
        return None
    caminho = (pasta_consulta / nome).resolve()
    if (
        caminho.parent != pasta_consulta
        or not caminho.is_file()
        or caminho.suffix.casefold() not in ARQUIVOS_RESULTADO
    ):
        return None
    return caminho
