# Serviço RPA JUCESC

Serviço HTTP com uma interface Web para consultar CNPJs no site da Junta Comercial do Estado de Santa Catarina (JUCESC) e disponibilizar os documentos encontrados. A API também pode ser consumida por outros clientes HTTP, como o n8n.

### ACESSO PELO LINK: http://192.168.2.210:8000 

## 1. O que é

A aplicação recebe dados do solicitante e uma lista de CNPJs, executa a automação existente com Playwright e retorna o resultado de cada empresa. Os arquivos resultantes são armazenados localmente, organizados por identificador da consulta (`consulta_id`), e ficam disponíveis para download.

## 2. Arquitetura

[![Architecture diagram](https://gitdiagram.com/diagram-badge.svg)](https://gitdiagram.com/informatica3crcsc/rpa-jucesc?utm_source=readme&utm_medium=badge)

## 3. Como funciona

1. O usuário utiliza a interface Web ou um cliente HTTP envia uma solicitação à API.
2. A FastAPI valida os dados do solicitante e os CNPJs.
3. `rpa_jucesc.py` normaliza os CNPJs e encaminha a consulta ao motor Playwright.
4. `consulta_fichas_jucesc.py` consulta a JUCESC e gera os resultados.
5. A API retorna um resumo com um `consulta_id`, os resultados individuais e URLs para listar ou baixar os arquivos.

## 4. Requisitos

- Windows, com Python 3.10 ou superior.
- Acesso à Internet para o servidor e para a consulta ao site da JUCESC.
- Google Chrome instalado ou Chromium instalado pelo Playwright.
- Dependências Python de `requirements.txt`.

## 5. Instalação

Na raiz do projeto, crie e ative um ambiente virtual e instale as dependências:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

No Windows, `instalar.bat` instala as dependências e o Chromium usando o Python disponível no `PATH`.

## 6. Como executar

Inicie o serviço a partir da raiz do repositório:

```powershell
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

No Windows, também é possível executar `iniciar_api.bat`. Com o serviço ativo:

- Interface Web: <http://127.0.0.1:8000/>
- Documentação interativa da API: <http://127.0.0.1:8000/docs>
- Verificação de disponibilidade: <http://127.0.0.1:8000/health>

## 7. Interface Web

Abra <http://127.0.0.1:8000/> no navegador. Informe nome, CPF e e-mail do solicitante e escolha como fornecer os CNPJs:

- **Digitar ou colar:** um CNPJ por linha.
- **Enviar arquivo:** arquivo `.txt` com um CNPJ por linha ou `.csv` com os CNPJs na primeira coluna; a coluna pode ter o cabeçalho `CNPJ`.

A interface mostra o resultado individual de cada CNPJ e oferece os PDFs encontrados e o relatório CSV para download. Durante a consulta, mantenha a página aberta: o processamento é síncrono e a solicitação HTTP permanece em andamento até terminar.

## 8. API HTTP

A API é a entrada HTTP comum à interface Web, ao n8n e a outros clientes:

| Método | Rota | Finalidade |
| --- | --- | --- |
| `GET` | `/health` | Informa se o processo da API está disponível. |
| `POST` | `/consultas` | Executa uma consulta a partir de uma lista JSON de CNPJs. |
| `POST` | `/consultas/arquivo` | Executa uma consulta a partir de arquivo TXT ou CSV. |
| `GET` | `/consultas/{consulta_id}/arquivos` | Lista os CSVs e PDFs disponíveis para uma consulta. |
| `GET` | `/consultas/{consulta_id}/arquivos/{nome_arquivo}` | Baixa um arquivo permitido daquela consulta. |

A API não oferece um endpoint separado para consultar novamente um `consulta_id`; o identificador organiza os arquivos da solicitação concluída.

## 9. Entrada por JSON

Envie `POST /consultas` com `Content-Type: application/json`. Os campos do solicitante são obrigatórios; `cnpjs` deve conter pelo menos um CNPJ. O exemplo abaixo usa valores de teste aceitos pela validação local:

```json
{
  "cnpjs": ["12.345.678/0001-95"],
  "cpf_solicitante": "529.982.247-25",
  "nome_solicitante": "Nome Sobrenome",
  "email_solicitante": "nome@example.com"
}
```

Quando a solicitação é processada, a resposta `200 OK` tem este formato:

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

`consulta_id` identifica a pasta dos arquivos daquela consulta. Cada item de `resultados` tem status `success` ou `error`; falhas individuais podem incluir a descrição em `erro`. `sucesso` e `erros` são as quantidades de resultados em cada estado. O conteúdo efetivo depende da resposta da JUCESC.

Exemplo com `curl.exe` no PowerShell:

```powershell
$body = @{
  cnpjs = @("12.345.678/0001-95")
  cpf_solicitante = "529.982.247-25"
  nome_solicitante = "Nome Sobrenome"
  email_solicitante = "nome@example.com"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/consultas" `
  -ContentType "application/json" `
  -Body $body
```

## 10. Entrada por arquivo

Envie `POST /consultas/arquivo` como `multipart/form-data` com os campos `arquivo`, `cpf_solicitante`, `nome_solicitante` e `email_solicitante`. São aceitos `.txt` e `.csv` até 1 MB. O CSV pode usar vírgula, ponto e vírgula ou tabulação; se houver um cabeçalho `CNPJ`, essa coluna será usada; sem cabeçalho reconhecido, será usada a primeira coluna.

Exemplo de arquivo `cnpjs.txt`:

```text
12.345.678/0001-95
```

Exemplo no PowerShell:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/consultas/arquivo" `
  -F "arquivo=@cnpjs.txt" `
  -F "cpf_solicitante=529.982.247-25" `
  -F "nome_solicitante=Nome Sobrenome" `
  -F "email_solicitante=nome@example.com"
```

A resposta usa o mesmo contrato da entrada JSON: `consulta_id`, contadores, resultados e URLs dos arquivos.

## 11. Arquivos gerados

Os arquivos de cada consulta ficam em `RPA_OUTPUT_DIR/{consulta_id}/`. A API permite listar somente os CSVs e PDFs reconhecidos como resultados:

```http
GET /consultas/e084fb3d-95ad-470b-bca3-59c41da2f214/arquivos
```

Exemplo de resposta:

```json
[
  {
    "nome": "resultados_jucesc.csv",
    "url": "/consultas/e084fb3d-95ad-470b-bca3-59c41da2f214/arquivos/resultados_jucesc.csv"
  },
  {
    "nome": "jucesc_12.345.678-0001-95.pdf",
    "url": "/consultas/e084fb3d-95ad-470b-bca3-59c41da2f214/arquivos/jucesc_12.345.678-0001-95.pdf"
  }
]
```

Use a URL de cada arquivo para baixá-lo. Os nomes são verificados pela API e somente arquivos `.csv` e `.pdf` da pasta daquela consulta podem ser servidos. A retenção e a limpeza das pastas locais são responsabilidade do administrador do serviço.

## 12. Integração com n8n

No n8n, use o nó **HTTP Request** para chamar os endpoints da FastAPI; não é necessária nem prevista uma integração direta do n8n com o processo Python:

```text
n8n ── HTTP Request ──► FastAPI ──► RPA
```

Para uma lista estruturada, configure `POST /consultas` com corpo JSON e os campos documentados acima. Para um arquivo, use `POST /consultas/arquivo` com corpo multipart/form-data. A resposta fornece o `consulta_id` e os URLs dos arquivos. Como a chamada espera a automação terminar, configure no n8n e em eventuais proxies um timeout adequado à duração observada das consultas.

## 13. Configuração

As variáveis são lidas do ambiente do processo. O serviço **não carrega automaticamente** um arquivo `.env`; `.env.example` é apenas uma referência.

| Variável | Padrão | Efeito |
| --- | --- | --- |
| `RPA_OUTPUT_DIR` | Diretório `outputs` na raiz do projeto | Diretório local em que a API cria uma pasta por consulta. |
| `RPA_MAX_CNPJS` | `20` | Número máximo de CNPJs distintos por consulta, aplicado pelo motor de automação. |

Configure-as antes de iniciar o processo. Exemplo no PowerShell:

```powershell
$env:RPA_OUTPUT_DIR = "C:\Dados\RPA-JUCESC"
$env:RPA_MAX_CNPJS = "20"
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

O limite de upload é atualmente fixo em 1 MB. As variáveis de ambiente devem ser definidas no mesmo ambiente que inicia o serviço; editá-las depois que o processo começou não altera a configuração já carregada.

## 14. Acesso pela rede

Por padrão, `iniciar_api.bat` inicia o servidor em `127.0.0.1`, acessível somente no próprio computador. Para disponibilizá-lo numa rede privada, pode ser necessário iniciar com `--host 0.0.0.0` e configurar firewall e regras de rede adequadas.

**Esta versão não tem autenticação própria. Não exponha a API diretamente à Internet.** Restrinja o acesso ao serviço pela rede e proteja os CSVs e PDFs, que podem conter dados sensíveis.

## 15. Processamento atual

A versão atual mantém uma arquitetura deliberadamente simples:

- cada consulta é síncrona e mantém a requisição HTTP aberta durante o processamento;
- uma instância de API executa um lote por vez;
- os resultados são armazenados no disco local;
- não há banco de dados, fila, Redis ou workers;
- não há autenticação própria.

Essas são características do modelo atual de execução. O navegador deve permanecer aberto até a resposta chegar; clientes HTTP devem prever um timeout suficiente.

## 16. Limitações atuais e respostas HTTP

Uma consulta pode levar vários minutos, pois depende da disponibilidade e do tempo de resposta do site da JUCESC. A lista de CNPJs e os dados do solicitante são validados pela API; CNPJs duplicados são normalizados e ignorados.

Erros HTTP comuns:

| Código | Situação |
| --- | --- |
| `422 Unprocessable Entity` | JSON, CNPJ, dados do solicitante ou arquivo inválido/não suportado. |
| `404 Not Found` | Consulta ou arquivo não encontrado. |
| `413 Request Entity Too Large` | Upload acima de 1 MB. |
| `500 Internal Server Error` | Falha inesperada durante a execução do motor; o detalhe técnico é registrado no log do servidor. |

Uma falha individual de consulta pode ser retornada como item com status `error` em uma resposta `200`; isso não significa necessariamente que o lote inteiro falhou.

## 17. Testes

Execute na raiz do repositório:

```powershell
python -m unittest discover -s tests -v
```

Os testes usam uma automação simulada para verificar validações, API, arquivos estáticos e downloads. Eles não consultam o site da JUCESC nem iniciam um navegador.

## 18. Estrutura do projeto

```text
RPA-JUCESC/
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── config.py
│   ├── models.py
│   ├── rpa_jucesc.py
│   ├── storage.py
│   └── static/
│       ├── app.js
│       ├── index.html
│       └── styles.css
├── tests/
│   ├── test_api.py
│   └── test_rpa.py
├── consulta_fichas_jucesc.py
├── iniciar_api.bat
├── instalar.bat
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Responsabilidade de cada parte:

- **FastAPI (`src/api.py`):** porta de entrada HTTP, serve a interface Web e implementa os endpoints.
- **Interface Web (`src/static/`):** formulário do navegador, apresentação dos resultados e acesso aos downloads.
- **`src/rpa_jucesc.py`:** valida e normaliza CNPJs e encaminha a consulta ao motor.
- **`consulta_fichas_jucesc.py`:** motor existente de automação Playwright que navega no site da JUCESC.
- **`src/storage.py`:** cria e consulta as pastas e os arquivos de resultado.
- **`src/models.py`:** define os modelos de entrada e as respostas usadas pela API.
- **`src/config.py`:** centraliza o diretório de resultados e o limite fixo de upload.
- **`tests/`:** testes automatizados da API e da camada RPA.
- **`iniciar_api.bat` e `instalar.bat`:** inicialização do serviço e instalação de dependências no Windows.

## 19. Site da JUCESC

A automação consulta o serviço público de fichas da JUCESC em <https://cop.jucesc.sc.gov.br/externo/servicos/?bnire>. A disponibilidade e o funcionamento do serviço externo podem afetar o tempo e o resultado das consultas.

## 20. Resumo da arquitetura

```text
Navegador ou cliente HTTP (incluindo n8n)
                    │
                    ▼
                  FastAPI
                    │
                    ▼
         RPA Python + Playwright
                    │
                    ▼
                  JUCESC
                    │
                    ▼
              CSV e PDFs locais
```
