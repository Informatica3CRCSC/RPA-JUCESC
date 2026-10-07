import asyncio
import csv
import io
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from src.config import PASTA_RESULTADOS, TAMANHO_MAXIMO_UPLOAD
from src.models import (
    ArquivoConsulta,
    CriarConsultaRequest,
    CriarConsultaResponse,
    ResultadoItem,
)
from src.rpa_jucesc import consultar, validar_e_normalizar_cnpjs
from src.storage import caminho_arquivo, criar_pasta_consulta, listar_arquivos

logger = logging.getLogger(__name__)
Automation = Callable[
    [list[str], str, str, str, Path],
    Awaitable[list[dict[str, Any]]],
]


def _validar_solicitante(cpf: str, nome: str, email: str) -> tuple[str, str, str]:
    from consulta_fichas_jucesc import _validar

    cpf_formatado, erros = _validar(cpf, nome, email)
    if erros:
        raise ValueError(" ".join(erros))
    return cpf_formatado, nome.strip().upper(), email.strip()


def _cnpjs_do_arquivo(conteudo: str, extensao: str) -> list[str]:
    if extensao == ".txt":
        return [
            linha.split("#", 1)[0].strip()
            for linha in conteudo.splitlines()
            if linha.split("#", 1)[0].strip()
        ]

    try:
        dialeto = csv.Sniffer().sniff(conteudo[:4096], delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    linhas = list(csv.reader(io.StringIO(conteudo), dialect=dialeto))
    if not linhas:
        return []
    cabecalho = [celula.strip().casefold() for celula in linhas[0]]
    coluna_cnpj = next(
        (indice for indice, nome in enumerate(cabecalho) if nome == "cnpj"),
        None,
    )
    inicio = 1 if coluna_cnpj is not None else 0
    coluna = coluna_cnpj or 0
    cnpjs = []
    for numero_linha, linha in enumerate(linhas[inicio:], start=inicio + 1):
        if not linha or not any(celula.strip() for celula in linha):
            continue
        if coluna >= len(linha) or not linha[coluna].strip():
            raise ValueError(f"Arquivo CSV: CNPJ ausente na linha {numero_linha}.")
        cnpjs.append(linha[coluna].strip())
    return cnpjs


def criar_app(
    *,
    pasta_resultados: Path = PASTA_RESULTADOS,
    automation: Automation = consultar,
) -> FastAPI:
    app = FastAPI(title="API RPA JUCESC", version="1.0.0")
    app.state.consulta_lock = asyncio.Lock()
    app.state.pasta_resultados = pasta_resultados.resolve()
    app.state.automation = automation

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def processar_consulta(
        cnpjs: list[str],
        cpf: str,
        nome: str,
        email: str,
    ) -> CriarConsultaResponse:
        try:
            lote = validar_e_normalizar_cnpjs(cnpjs)
            solicitante = _validar_solicitante(cpf, nome, email)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        consulta_id, pasta_consulta = criar_pasta_consulta(
            app.state.pasta_resultados
        )
        async with app.state.consulta_lock:
            try:
                resultados = await app.state.automation(
                    lote, *solicitante, pasta_consulta
                )
            except Exception as exc:
                logger.exception("Falha ao executar consulta JUCESC %s", consulta_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Não foi possível executar a consulta JUCESC.",
                ) from exc

        itens = [
            ResultadoItem(
                cnpj=item["cnpj"],
                status=item["status"],
                arquivo=item.get("arquivo"),
                erro=item.get("erro"),
                pdf_url=(
                    f"/consultas/{consulta_id}/arquivos/{item['arquivo']}"
                    if item.get("status") == "success" and item.get("arquivo")
                    else None
                ),
            )
            for item in resultados
        ]
        return CriarConsultaResponse(
            consulta_id=consulta_id,
            total=len(itens),
            sucesso=sum(item.status == "success" for item in itens),
            erros=sum(item.status == "error" for item in itens),
            resultados=itens,
            csv_url=f"/consultas/{consulta_id}/arquivos/resultados_jucesc.csv",
        )

    @app.post(
        "/consultas",
        response_model=CriarConsultaResponse,
        status_code=status.HTTP_200_OK,
    )
    async def criar_consulta(payload: CriarConsultaRequest) -> CriarConsultaResponse:
        return await processar_consulta(
            payload.cnpjs,
            payload.cpf_solicitante,
            payload.nome_solicitante,
            payload.email_solicitante,
        )

    @app.post(
        "/consultas/arquivo",
        response_model=CriarConsultaResponse,
        status_code=status.HTTP_200_OK,
    )
    async def criar_consulta_por_arquivo(
        arquivo: UploadFile = File(...),
        cpf_solicitante: str = Form(...),
        nome_solicitante: str = Form(...),
        email_solicitante: str = Form(...),
    ) -> CriarConsultaResponse:
        extensao = Path(arquivo.filename or "").suffix.casefold()
        if extensao not in {".txt", ".csv"}:
            raise HTTPException(
                status_code=422,
                detail="Envie um arquivo .txt ou .csv.",
            )
        conteudo_bytes = await arquivo.read(TAMANHO_MAXIMO_UPLOAD + 1)
        if len(conteudo_bytes) > TAMANHO_MAXIMO_UPLOAD:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="O arquivo deve ter no máximo 1 MB.",
            )
        try:
            conteudo = conteudo_bytes.decode("utf-8-sig")
            cnpjs = _cnpjs_do_arquivo(conteudo, extensao)
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Não foi possível ler a lista de CNPJs: {exc}",
            ) from exc
        return await processar_consulta(
            cnpjs,
            cpf_solicitante,
            nome_solicitante,
            email_solicitante,
        )

    @app.get(
        "/consultas/{consulta_id}/arquivos",
        response_model=list[ArquivoConsulta],
    )
    async def obter_arquivos(consulta_id: UUID) -> list[ArquivoConsulta]:
        pasta_consulta = app.state.pasta_resultados / str(consulta_id)
        if not pasta_consulta.is_dir():
            raise HTTPException(status_code=404, detail="Consulta não encontrada.")
        return [
            ArquivoConsulta(
                nome=arquivo.name,
                url=f"/consultas/{consulta_id}/arquivos/{arquivo.name}",
            )
            for arquivo in listar_arquivos(pasta_consulta)
        ]

    @app.get("/consultas/{consulta_id}/arquivos/{nome_arquivo}")
    async def baixar_arquivo(consulta_id: UUID, nome_arquivo: str) -> FileResponse:
        pasta_consulta = app.state.pasta_resultados / str(consulta_id)
        if not pasta_consulta.is_dir():
            raise HTTPException(status_code=404, detail="Consulta não encontrada.")
        arquivo = caminho_arquivo(pasta_consulta, nome_arquivo)
        if arquivo is None:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        return FileResponse(arquivo, filename=arquivo.name)

    return app


app = criar_app()
