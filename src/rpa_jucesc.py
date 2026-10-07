import re
from collections.abc import Iterable
from pathlib import Path

from consulta_fichas_jucesc import (
    MAX_CNPJS_POR_EXECUCAO,
    cnpj_valido,
    consultar_cnpj_jucesc,
    formatar_cnpj,
)


def validar_e_normalizar_cnpjs(cnpjs: Iterable[str]) -> list[str]:
    normalizados: list[str] = []
    invalidos: list[str] = []

    for indice, cnpj in enumerate(cnpjs, start=1):
        valor = re.sub(r"[^0-9A-Za-z]", "", cnpj).upper()
        if len(valor) != 14 or not cnpj_valido(valor):
            invalidos.append(f"item {indice}: {cnpj!r}")
            continue
        formatado = formatar_cnpj(valor)
        if formatado not in normalizados:
            normalizados.append(formatado)

    if invalidos:
        raise ValueError("CNPJ inválido: " + "; ".join(invalidos))
    if not normalizados:
        raise ValueError("Informe ao menos um CNPJ válido.")
    if len(normalizados) > MAX_CNPJS_POR_EXECUCAO:
        raise ValueError(
            f"O limite por consulta é {MAX_CNPJS_POR_EXECUCAO} CNPJs."
        )
    return normalizados


async def consultar(
    cnpjs: list[str],
    cpf: str,
    nome: str,
    email: str,
    pasta_saida: Path,
) -> list[dict[str, str | None]]:
    return await consultar_cnpj_jucesc(
        cnpjs,
        cpf,
        nome,
        email,
        pasta_saida,
        salvar_print_erro=False,
    )
