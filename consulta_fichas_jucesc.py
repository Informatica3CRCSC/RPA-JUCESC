# -*- coding: utf-8 -*-
"""Motor Playwright da JUCESC, reutilizado pelo serviço FastAPI.

Implementa a consulta da Ficha Cadastral Simplificada no site público da
JUCESC. A camada de integração HTTP está em ``src.rpa_jucesc``.
"""

import asyncio
import csv
import hashlib
import json
import os
import random
import re
import sys
from datetime import datetime
from getpass import getpass
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

VERSAO = "v19"
PASTA_ROBO = Path(__file__).resolve().parent
ARQUIVO_CNPJS = PASTA_ROBO / "cnpjs.txt"
PASTA_DADOS_USUARIO = Path(os.environ.get("APPDATA", Path.home())) / "RoboJUCESC"
ARQUIVO_SOLICITANTE = PASTA_DADOS_USUARIO / "solicitante.json"

DOMINIO_PERMITIDO = "jucesc.sc.gov.br"
MAX_CNPJS_POR_EXECUCAO = int(os.environ.get("RPA_MAX_CNPJS", "20"))
SALVAR_PRINT_RESULTADO = False   # True = guarda um print da tabela de cada CNPJ (pode conter dados)
MOSTRAR_NAVEGADOR = False        # True = abre o navegador visível (útil para investigar erros)


def impressao_digital():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def url_permitida(url):
    """True se a URL for do domínio da JUCESC (aceita também blob: e about:blank)."""
    if not url or url.startswith("about:blank"):
        return True
    if url.startswith("blob:"):
        url = url[5:]
    host = (urlparse(url).hostname or "").lower()
    return host == DOMINIO_PERMITIDO or host.endswith("." + DOMINIO_PERMITIDO)


async def abrir_navegador(p):
    """Usa o Google Chrome já instalado; se não houver, usa o Chromium do Playwright."""
    try:
        return await p.chromium.launch(channel="chrome", headless=not MOSTRAR_NAVEGADOR)
    except Exception:
        return await p.chromium.launch(headless=not MOSTRAR_NAVEGADOR)


# ---------------------------------------------------------------------------
# CNPJs
# ---------------------------------------------------------------------------
def formatar_cnpj(c):
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def _valor_caractere_cnpj(ch):
    """Dígito -> o próprio número; letra A-Z -> código ASCII menos 48
    (A=17 ... Z=42). É assim que a Receita Federal define o cálculo do
    dígito verificador do CNPJ alfanumérico (emitido desde 31/07/2026)."""
    if ch.isdigit():
        return int(ch)
    return ord(ch) - 48


def _dv_cnpj(parcial, pesos):
    soma = sum(_valor_caractere_cnpj(ch) * p for ch, p in zip(parcial, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cnpj_valido(c):
    """Confere os dígitos verificadores de verdade (módulo 11), não só o
    formato. Aceita CNPJ só numérico (tradicional) e alfanumérico (letras
    A-Z só nas 12 primeiras posições; os 2 dígitos verificadores são
    sempre numéricos)."""
    if len(c) != 14 or not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c):
        return False
    if len(set(c)) == 1:
        return False
    dv1 = _dv_cnpj(c[0:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    dv2 = _dv_cnpj(c[0:12] + dv1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return c[12] == dv1 and c[13] == dv2


def ler_cnpjs(caminho):
    """Lê os CNPJs do arquivo (um por linha; linhas vazias e trechos depois de # são ignorados).
    Aceita com ou sem pontuação, numérico ou alfanumérico. Confere os dígitos
    verificadores de verdade. Se houver linha inválida, mostra quais são e não roda."""
    with open(caminho, encoding="utf-8-sig") as f:
        linhas = f.read().splitlines()
    cnpjs, problemas = [], []
    for n, linha in enumerate(linhas, 1):
        texto = linha.split("#")[0].strip()
        if not texto:
            continue
        c = re.sub(r"[^0-9A-Za-z]", "", texto).upper()
        if len(c) != 14:
            problemas.append(f"  linha {n}: {linha.strip()}  (tem {len(c)} caracteres, esperado 14)")
            continue
        if not cnpj_valido(c):
            problemas.append(f"  linha {n}: {linha.strip()}  (dígitos verificadores inválidos — confira se não há número trocado)")
            continue
        c = formatar_cnpj(c)
        if c in cnpjs:
            print(f"Aviso: CNPJ repetido ignorado (linha {n}): {c}")
            continue
        cnpjs.append(c)
    if problemas:
        print("Há linhas inválidas no arquivo. Corrija e rode de novo:")
        print("\n".join(problemas))
        return None
    if not cnpjs:
        print("Nenhum CNPJ encontrado no arquivo. Preencha e rode de novo.")
        return None
    print(f"{len(cnpjs)} CNPJ(s) lidos e validados:")
    for c in cnpjs:
        print(f"  {c}")
    return cnpjs


def ler_arquivo_cnpjs():
    if not ARQUIVO_CNPJS.exists():
        ARQUIVO_CNPJS.write_text("# Um CNPJ por linha. Linhas começando com # são ignoradas.\n", encoding="utf-8")
        print(f"Criei o arquivo {ARQUIVO_CNPJS.name}. Preencha com os CNPJs (um por linha) e rode de novo.")
        return None
    cnpjs = ler_cnpjs(ARQUIVO_CNPJS)
    if cnpjs and len(cnpjs) > MAX_CNPJS_POR_EXECUCAO:
        print(f"\nO limite por execução é {MAX_CNPJS_POR_EXECUCAO}. Serão consultados só os "
              f"{MAX_CNPJS_POR_EXECUCAO} primeiros; rode de novo com os demais.")
        cnpjs = cnpjs[:MAX_CNPJS_POR_EXECUCAO]
    return cnpjs


# ---------------------------------------------------------------------------
# Consulta (mesma lógica do notebook v17)
# ---------------------------------------------------------------------------
MAX_TENTATIVAS = 2          # 1 tentativa original + 1 nova tentativa
PAUSA_ENTRE_CNPJS = (1.5, 3.0)  # segundos (min, max) — pausa educada entre consultas


def nome_seguro(cnpj):
    return cnpj.replace("/", "-")


def salvar_linha_csv(caminho_csv, registro, escrever_cabecalho):
    with open(caminho_csv, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["cnpj", "status", "arquivo", "erro"],
            delimiter=";",
            extrasaction="ignore",
        )
        if escrever_cabecalho:
            w.writeheader()
        w.writerow(registro)


async def _aguardar_download_ou_popup(page, context, clique, timeout_ms=12000):
    download_task = asyncio.create_task(page.wait_for_event("download", timeout=timeout_ms))
    popup_task = asyncio.create_task(context.wait_for_event("page", timeout=timeout_ms))
    await clique()
    done, pending = await asyncio.wait(
        {download_task, popup_task}, timeout=timeout_ms/1000, return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()
    if download_task in done:
        try:
            return ("download", download_task.result())
        except Exception:
            pass
    if popup_task in done:
        try:
            return ("popup", popup_task.result())
        except Exception:
            pass
    return (None, None)


async def _localizar_icone_ficha(frame):
    """Tenta, em ordem, algumas formas específicas de achar o botão/ícone
    que abre a Ficha Cadastral Simplificada. Se nenhuma funcionar, levanta
    um erro claro em vez de clicar "no último elemento visível da tela"
    (que podia baixar a coisa errada sem avisar, como na v15)."""
    candidatos = [
        lambda: frame.locator("[title='Ficha Cadastral Simplificada']"),
        lambda: frame.locator("[title*='Ficha' i]"),
        lambda: frame.locator("a[href*='ficha' i], a[href*='pdf' i]"),
        lambda: frame.get_by_role("link", name=re.compile("ficha|pdf|cadastral", re.I)),
        lambda: frame.locator("img[alt*='ficha' i], img[alt*='pdf' i]"),
    ]
    for construir in candidatos:
        try:
            loc = construir()
            if await loc.count() > 0:
                return loc.first
        except Exception:
            continue
    raise Exception(
        "Não encontrei o botão/ícone da Ficha Cadastral Simplificada com nenhuma das "
        "formas conhecidas. O site da JUCESC provavelmente mudou — ajuste a lista de "
        "candidatos em _localizar_icone_ficha()."
    )


URL_JUCESC = "https://cop.jucesc.sc.gov.br/externo/servicos/?bnire"


async def _iniciar_busca(page, campo_cnpj, cpf, nome, email):
    """Abre a página da JUCESC, identifica o solicitante e deixa pronta a tela de busca por CNPJ."""
    # Não espera "networkidle": no computador (rede da instituição, antivírus, proxy)
    # a página da JUCESC pode nunca ficar 100% ociosa, e isso dava "Timeout 45000ms".
    # Agora espera só o carregamento básico e o campo de CPF aparecer, com 1 nova tentativa.
    for tentativa in (1, 2):
        try:
            await page.goto(URL_JUCESC, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector('#cpf', state='visible', timeout=60000)
            break
        except Exception:
            if tentativa == 2:
                raise Exception(
                    "A página da JUCESC não abriu (o campo de CPF não apareceu em 2 tentativas). "
                    "Abra https://cop.jucesc.sc.gov.br/externo/servicos/?bnire no Chrome: se também "
                    "não abrir, o site está fora do ar ou bloqueado pela rede da instituição (fale com a TI).")
            print("  (a JUCESC demorou para responder; tentando abrir de novo...)")

    await page.fill('#cpf', cpf)
    await page.click('#botao')
    await page.wait_for_selector('#nome', state='visible', timeout=20000)

    await page.fill('#nome', nome)
    await page.fill('#email', email)
    await page.fill('#email2', email)
    await page.locator('#botao2').last.click()

    await campo_cnpj.wait_for(state="visible", timeout=20000)


async def _voltar_para_busca(page, frame, campo_cnpj):
    """Clica em 'Nova Busca' e confirma que o campo de CNPJ voltou. Procura o botão dentro do
    iframe E na página principal (antes só se procurava no iframe, e quando o botão não estava
    lá o clique era pulado em silêncio). Devolve True se voltou para a busca."""
    nome = re.compile(r"nova\s+busca", re.I)
    candidatos = [
        lambda: frame.locator("#nova_busca"),
        lambda: frame.get_by_role("button", name=nome),
        lambda: frame.get_by_text(nome),
        lambda: page.locator("#nova_busca"),
        lambda: page.get_by_role("button", name=nome),
        lambda: page.get_by_text(nome),
    ]
    for construir in candidatos:
        try:
            loc = construir()
            if await loc.count() == 0:
                continue
            botao = loc.first
            try:
                await botao.click(timeout=8000)
            except Exception:
                await botao.click(timeout=8000, force=True)
            await campo_cnpj.wait_for(state="visible", timeout=10000)
            return True
        except Exception:
            continue
    return False


async def _garantir_tela_de_busca(page, frame, campo_cnpj, cpf, nome, email):
    """Antes de cada CNPJ: confere que o campo de CNPJ está na tela. Se não estiver, tenta
    'Nova Busca'; se isso não resolver, recarrega a JUCESC e refaz a identificação do zero.
    Devolve 'ok', 'nova busca' ou 'recarregou'."""
    try:
        await campo_cnpj.wait_for(state="visible", timeout=3000)
        return "ok"
    except Exception:
        pass
    if await _voltar_para_busca(page, frame, campo_cnpj):
        return "nova busca"
    await _iniciar_busca(page, campo_cnpj, cpf, nome, email)
    return "recarregou"


async def _consultar_um_cnpj(page, context, frame, campo_cnpj, cnpj, pasta_saida):
    """Faz a busca de UM CNPJ já dentro da sessão/iframe aberto e devolve
    o caminho do PDF salvo. Lança exceção em caso de erro (quem chama
    decide se tenta de novo)."""
    await campo_cnpj.fill(cnpj)
    await frame.get_by_text("Buscar", exact=True).click()

    # Espera aparecer na tabela a linha DESTE CNPJ. Assim nunca se clica na ficha do CNPJ
    # anterior, que pode continuar na tela por um instante.
    digitos = re.sub(r"[^0-9A-Za-z]", "", cnpj).upper()
    padrao = re.compile(r"[.\s/\-]*".join(re.escape(ch) for ch in digitos), re.I)
    linha = frame.locator("tr", has_text=padrao).first
    try:
        await linha.wait_for(state="visible", timeout=15000)
    except Exception:
        raise Exception(
            f"Sem resultado para o CNPJ {cnpj}: ele não apareceu na tabela da JUCESC "
            "(sem registro lá, ou a página não respondeu)."
        )
    await page.wait_for_timeout(500)
    if SALVAR_PRINT_RESULTADO:
        await page.screenshot(
            path=str(pasta_saida / f"jucesc_{nome_seguro(cnpj)}_resultado.png"),
            full_page=True,
        )

    icone = await _localizar_icone_ficha(linha)

    async def clicar():
        await icone.click()

    tipo, resultado = await _aguardar_download_ou_popup(page, context, clicar)
    caminho = pasta_saida / f"jucesc_{nome_seguro(cnpj)}.pdf"

    if tipo == "download":
        await resultado.save_as(caminho)
    elif tipo == "popup":
        nova_pagina = resultado
        await nova_pagina.wait_for_load_state("load", timeout=15000)
        await nova_pagina.wait_for_timeout(1500)
        if not url_permitida(nova_pagina.url):
            await nova_pagina.close()
            raise Exception(f"A ficha abriu fora do domínio da JUCESC ({nova_pagina.url}); não foi salva por segurança.")
        await nova_pagina.pdf(path=str(caminho))
        await nova_pagina.close()
    else:
        raise Exception("Não foi possível capturar o PDF (nem download nem nova aba)")

    return caminho.name


async def consultar_cnpj_jucesc(
    cnpjs,
    cpf_solicitante,
    nome_solicitante,
    email_solicitante,
    pasta_saida,
    salvar_print_erro=True,
):
    resultados = []
    csv_tem_cabecalho = False
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    caminho_csv = pasta_saida / "resultados_jucesc.csv"
    browser = None
    try:
        async with async_playwright() as p:
            browser = await abrir_navegador(p)
            try:
                context = await browser.new_context(accept_downloads=True, viewport={"width":1366,"height":900})
                page = await context.new_page()
                frame = page.frame_locator("#b_nire iframe")
                campo_cnpj = frame.locator("input[placeholder='CNPJ' i]")
                await _iniciar_busca(page, campo_cnpj, cpf_solicitante, nome_solicitante, email_solicitante)

                for indice, cnpj in enumerate(cnpjs):
                    registro = None
                    for tentativa in range(1, MAX_TENTATIVAS + 1):
                        try:
                            como = await _garantir_tela_de_busca(
                                page, frame, campo_cnpj, cpf_solicitante, nome_solicitante, email_solicitante)
                            if como != "ok":
                                print(f"  (voltou para a tela de busca: {como})")
                            caminho = await _consultar_um_cnpj(
                                page, context, frame, campo_cnpj, cnpj, pasta_saida
                            )
                            registro = {
                                "cnpj": cnpj,
                                "status": "success",
                                "arquivo": caminho,
                                "erro": None,
                            }
                            break
                        except Exception as e:
                            print(f"[tentativa {tentativa}/{MAX_TENTATIVAS}] Erro no CNPJ {cnpj}: {e}")
                            if salvar_print_erro:
                                try:
                                    await page.screenshot(
                                        path=str(pasta_saida / f"jucesc_{nome_seguro(cnpj)}_erro.png"),
                                        full_page=True,
                                    )
                                except Exception:
                                    pass
                            if tentativa == MAX_TENTATIVAS:
                                registro = {
                                    "cnpj": cnpj,
                                    "status": "error",
                                    "arquivo": None,
                                    "erro": str(e),
                                }

                    resultados.append(registro)
                    print(f"{cnpj} -> {registro['status']}")
                    salvar_linha_csv(caminho_csv, registro, escrever_cabecalho=not csv_tem_cabecalho)
                    csv_tem_cabecalho = True

                    # clica em "Nova Busca" para o próximo CNPJ; se não conseguir, a verificação
                    # no início do próximo CNPJ recarrega a página do zero
                    if indice < len(cnpjs) - 1:
                        try:
                            if not await _voltar_para_busca(page, frame, campo_cnpj):
                                print("  (botão 'Nova Busca' não achado; vou recarregar a JUCESC no próximo CNPJ)")
                        except Exception:
                            pass

                    # pausa educada entre consultas (não dispara tudo em sequência direta)
                    if indice < len(cnpjs) - 1:
                        await page.wait_for_timeout(int(random.uniform(*PAUSA_ENTRE_CNPJS) * 1000))
            finally:
                if browser is not None:
                    await browser.close()
    except Exception as e:
        print(f"Erro geral na JUCESC (fluxo inicial): {e}")
        print("Confira a conexão com a internet e os dados do solicitante.")
        for cnpj in cnpjs:
            if any(r["cnpj"] == cnpj for r in resultados):
                continue
            registro = {
                "cnpj": cnpj,
                "status": "error",
                "arquivo": None,
                "erro": f"ERRO GERAL: {e}",
            }
            resultados.append(registro)
            salvar_linha_csv(caminho_csv, registro, escrever_cabecalho=not csv_tem_cabecalho)
            csv_tem_cabecalho = True
    return resultados


# ---------------------------------------------------------------------------
# Solicitante (CPF, nome, e-mail): guardado só neste computador
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def formatar_cpf(texto):
    """Devolve o CPF no formato 000.000.000-00 se for válido (confere os dígitos); senão None."""
    d = re.sub(r"\D", "", texto)
    if len(d) != 11 or len(set(d)) == 1:
        return None
    for i in (9, 10):
        soma = sum(int(d[k]) * (i + 1 - k) for k in range(i))
        if (soma * 10) % 11 % 10 != int(d[i]):
            return None
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"



def _validar(cpf_txt, nome_txt, email_txt):
    cpf = formatar_cpf(cpf_txt or "")
    erros = []
    if not cpf:
        erros.append("CPF inválido: use os 11 números.")
    if len((nome_txt or "").split()) < 2:
        erros.append("Nome incompleto: informe nome e sobrenome.")
    if not EMAIL_RE.match(email_txt or ""):
        erros.append("E-mail inválido. Exemplo: nome@dominio.com")
    return cpf, erros


def _pedir_solicitante():
    print("\nDados do SOLICITANTE exigidos pela JUCESC (são os seus dados, não os da empresa).")
    while True:
        cpf_txt = getpass("CPF (não aparece enquanto digita): ").strip()
        nome_txt = input("Nome completo: ").strip()
        email_txt = input("E-mail: ").strip()
        cpf, erros = _validar(cpf_txt, nome_txt, email_txt)
        if not erros:
            break
        print("Corrija:")
        for e in erros:
            print(" -", e)
    dados = {"cpf": cpf, "nome": nome_txt.upper(), "email": email_txt}
    if input("Guardar estes dados NESTE computador para as próximas vezes? (S/N): ").strip().lower().startswith("s"):
        PASTA_DADOS_USUARIO.mkdir(parents=True, exist_ok=True)
        ARQUIVO_SOLICITANTE.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        print(f"Dados guardados em {ARQUIVO_SOLICITANTE} (fora da pasta do robô).")
    return dados


def obter_solicitante(trocar=False):
    if trocar and ARQUIVO_SOLICITANTE.exists():
        ARQUIVO_SOLICITANTE.unlink()
        print("Dados do solicitante anteriores apagados.")
    dados = None
    if ARQUIVO_SOLICITANTE.exists():
        try:
            dados = json.loads(ARQUIVO_SOLICITANTE.read_text(encoding="utf-8"))
            _, erros = _validar(dados.get("cpf"), dados.get("nome"), dados.get("email"))
            if erros:
                print("Os dados guardados do solicitante estão incompletos ou inválidos.")
                dados = None
        except Exception:
            dados = None
    if dados is None:
        dados = _pedir_solicitante()
    usuario, dominio = dados["email"].split("@", 1)
    print(f"Solicitante: {dados['nome'].split()[0]} | CPF ***.***.***-{dados['cpf'][-2:]} | e-mail {usuario[0]}***@{dominio}")
    return dados["cpf"], dados["nome"], dados["email"]


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def main():
    print("=" * 64)
    print(f"ROBÔ DE FICHAS DA JUCESC {VERSAO} — impressão digital: {impressao_digital()[:16]}...")
    print("=" * 64)

    trocar = "--trocar-solicitante" in sys.argv
    if trocar:
        obter_solicitante(trocar=True)
        print("Pronto. Rode o robô normalmente.")
        return

    cnpjs = ler_arquivo_cnpjs()
    if not cnpjs:
        return
    cpf, nome, email = obter_solicitante()

    input(f"\nConfira a lista acima. Aperte ENTER para consultar {len(cnpjs)} CNPJ(s) (ou feche a janela para cancelar)... ")

    pasta = PASTA_ROBO / f"fichas_jucesc_{datetime.now():%Y-%m-%d_%H%M}"
    pasta.mkdir(exist_ok=True)
    print(f"\n== Consultando JUCESC ({len(cnpjs)} CNPJs) ==")
    resultados = asyncio.run(consultar_cnpj_jucesc(cnpjs, cpf, nome, email, pasta))

    ok = sum(1 for r in resultados if r["status"] == "success")
    print("\n== Resumo ==")
    print(f"{ok} de {len(cnpjs)} fichas geradas.")
    print(f"Resultados em: {pasta}")
    print("Abra primeiro o resultados_jucesc.csv (status de cada CNPJ).")
    print("As fichas podem conter dados pessoais (LGPD): guarde em pasta restrita e apague quando não precisar.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompido. O que já foi consultado está no resultados_jucesc.csv da pasta da execução.")
    except Exception:
        import traceback
        print("\n[ERRO] O robô parou por um problema inesperado:")
        traceback.print_exc()
    input("\nPressione ENTER para fechar...")
