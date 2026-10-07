# Serviço RPA JUCESC

API HTTP simples para consultar CNPJs na JUCESC com FastAPI e Playwright. A automação continua sendo o fluxo já existente em `consulta_fichas_jucesc.py`; a API apenas valida a entrada, chama esse mesmo fluxo e disponibiliza os arquivos gerados. Não há fila, banco de dados, Redis, workers ou interface Web nesta versão.

## Instalação

Requer Python 3.10+ e acesso à Internet a partir do servidor.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Também é possível executar `instalar.bat` no Windows para instalar as dependências do serviço e o navegador do Playwright.

## Executar a API

```powershell
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

`iniciar_api.bat` executa o mesmo comando no Windows. A documentação interativa fica em `http://127.0.0.1:8000/docs`.

Por padrão, o servidor escuta apenas no próprio computador. Se outros computadores precisarem acessá-lo, configure a rede privada/firewall e inicie com `--host 0.0.0.0`. **Esta versão não tem autenticação**: não exponha a API diretamente à Internet. CPF, nome e e-mail são enviados à JUCESC durante cada execução, não são guardados no disco pela API. CSVs e PDFs são armazenados localmente e contêm dados que devem ter acesso restrito.

## Configuração

Copie `.env.example` como referência. O aplicativo não carrega arquivos `.env` automaticamente; configure as variáveis no ambiente do processo antes de iniciar:

- `RPA_OUTPUT_DIR`: diretório de saída (padrão `outputs`, relativo ao diretório de execução).
- `RPA_MAX_CNPJS`: máximo de CNPJs por consulta (padrão `20`).

No PowerShell, por exemplo:

```powershell
$env:RPA_OUTPUT_DIR = "C:\Dados\RPA-JUCESC"
$env:RPA_MAX_CNPJS = "20"
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

## Endpoints

### `GET /health`

Verifica se o processo está disponível:

```json
{"status":"ok"}
```

### `POST /consultas`

Consulta uma lista enviada como JSON. CPF, nome completo e e-mail do solicitante são os dados exigidos pela JUCESC:

```json
{
  "cnpjs": ["12.345.678/0001-95"],
  "cpf_solicitante": "529.982.247-25",
  "nome_solicitante": "Nome Sobrenome",
  "email_solicitante": "nome@example.com"
}
```

A chamada permanece aberta até o lote acabar. A API executa um lote por vez neste processo, limita cada lote a 20 CNPJs por padrão e normaliza/ignora CNPJs duplicados. O site pode demorar; configure timeout suficiente no cliente HTTP e em qualquer proxy reverso.

Exemplo de resposta:

```json
{
  "consulta_id": "e084fb3d-95ad-470b-bca3-59c41da2f214",
  "total": 1,
  "sucesso": 1,
  "erros": 0,
  "resultados": [
    {
      "cnpj": "12.345.678/0001-95",
      "status": "success",
      "arquivo": "jucesc_12.345.678-0001-95.pdf",
      "erro": null,
      "pdf_url": "/consultas/e084fb3d-95ad-470b-bca3-59c41da2f214/arquivos/jucesc_12.345.678-0001-95.pdf"
    }
  ],
  "csv_url": "/consultas/e084fb3d-95ad-470b-bca3-59c41da2f214/arquivos/resultados_jucesc.csv"
}
```

O campo `status` é `success` ou `error`; falhas individuais incluem a descrição em `erro`. O CSV contém todos os CNPJs processados e seus status.

### `POST /consultas/arquivo`

Envia `multipart/form-data` com:

- `arquivo`: `.txt` com um CNPJ por linha, ou `.csv` com os CNPJs na primeira coluna (opcionalmente com uma coluna chamada `CNPJ`). CSV separado por vírgula, ponto e vírgula ou tabulação é aceito.
- `cpf_solicitante`, `nome_solicitante`, `email_solicitante`: mesmos campos do JSON.

O upload tem limite de 1 MB. Ambas as formas de entrada usam as mesmas validações e o mesmo fluxo Playwright.

### Arquivos resultantes

- `GET /consultas/{consulta_id}/arquivos`: lista CSV e PDFs gerados.
- `GET /consultas/{consulta_id}/arquivos/{nome_arquivo}`: baixa um arquivo daquele identificador.

Os arquivos ficam em `RPA_OUTPUT_DIR/{consulta_id}/`. A limpeza/retention desses diretórios é responsabilidade de quem administra o servidor.

### Erros HTTP comuns

- `422`: JSON, CNPJ, solicitante ou arquivo inválido.
- `404`: identificador de consulta ou arquivo não encontrado.
- `413`: upload maior que 1 MB.
- `500`: falha inesperada na execução do motor, registrada no log do servidor.

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes usam uma automação simulada e não acessam a JUCESC nem iniciam navegador.

## Estrutura

```text
consulta_fichas_jucesc.py  # motor Playwright existente e CLI legado
src/
  api.py                   # endpoints síncronos FastAPI
  config.py                # diretório e limite configuráveis
  models.py                # contratos HTTP
  rpa_jucesc.py            # validação e fachada para o motor existente
  storage.py               # diretórios e acesso seguro aos artefatos
tests/
```

O CLI permanece disponível por `rodar.bat`; ele e a API chamam o mesmo fluxo de automação.
