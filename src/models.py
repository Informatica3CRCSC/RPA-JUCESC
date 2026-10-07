from typing import Literal

from pydantic import BaseModel, Field


class CriarConsultaRequest(BaseModel):
    cnpjs: list[str] = Field(min_length=1)
    cpf_solicitante: str
    nome_solicitante: str
    email_solicitante: str


class ResultadoItem(BaseModel):
    cnpj: str
    status: Literal["success", "error"]
    arquivo: str | None = None
    erro: str | None = None
    pdf_url: str | None = None


class CriarConsultaResponse(BaseModel):
    consulta_id: str
    total: int
    sucesso: int
    erros: int
    resultados: list[ResultadoItem]
    csv_url: str


class ArquivoConsulta(BaseModel):
    nome: str
    url: str
