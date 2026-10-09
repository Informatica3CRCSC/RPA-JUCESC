const form = document.querySelector("#form-consulta");
const manualPanel = document.querySelector("#painel-manual");
const filePanel = document.querySelector("#painel-arquivo");
const cnpjsInput = document.querySelector("#lista-cnpjs");
const fileInput = document.querySelector("#arquivo-cnpjs");
const fileName = document.querySelector("#nome-arquivo");
const submitButton = document.querySelector("#botao-consultar");
const statusMessage = document.querySelector("#mensagem-status");
const resultsSection = document.querySelector("#secao-resultados");
const resultsBody = document.querySelector("#linhas-resultados");
const csvLink = document.querySelector("#baixar-csv");

function modoEntrada() {
  return form.querySelector('input[name="modo-entrada"]:checked').value;
}

function atualizarModoEntrada() {
  const manual = modoEntrada() === "manual";
  manualPanel.hidden = !manual;
  filePanel.hidden = manual;
  cnpjsInput.disabled = !manual;
  cnpjsInput.required = manual;
  fileInput.disabled = manual;
  fileInput.required = !manual;
}

function mostrarStatus(mensagem, estado = "info") {
  statusMessage.textContent = mensagem;
  statusMessage.dataset.state = estado;
  statusMessage.hidden = false;
}

function criarCelula(texto) {
  const cell = document.createElement("td");
  cell.textContent = texto;
  return cell;
}

function renderizarResultados(consulta) {
  document.querySelector("#total-consultado").textContent = consulta.total;
  document.querySelector("#total-sucesso").textContent = consulta.sucesso;
  document.querySelector("#total-erros").textContent = consulta.erros;
  resultsBody.replaceChildren();

  for (const resultado of consulta.resultados) {
    const row = document.createElement("tr");
    row.append(criarCelula(resultado.cnpj));

    const statusCell = document.createElement("td");
    const statusLabel = document.createElement("span");
    statusLabel.className = "result-status";
    if (resultado.status === "success") {
      statusLabel.textContent = "Documento encontrado";
    } else {
      statusLabel.classList.add("is-error");
      statusLabel.textContent = "Não foi possível consultar";
      if (resultado.erro) {
        const detail = document.createElement("span");
        detail.className = "error-detail";
        detail.textContent = resultado.erro;
        statusLabel.append(detail);
      }
    }
    statusCell.append(statusLabel);
    row.append(statusCell);

    const documentCell = document.createElement("td");
    if (resultado.pdf_url) {
      const link = document.createElement("a");
      link.className = "document-link";
      link.href = resultado.pdf_url;
      link.download = "";
      link.textContent = "Baixar PDF ↓";
      documentCell.append(link);
    } else {
      documentCell.textContent = "—";
    }
    row.append(documentCell);
    resultsBody.append(row);
  }

  if (consulta.csv_url) {
    csvLink.href = consulta.csv_url;
    csvLink.hidden = false;
  } else {
    csvLink.hidden = true;
  }
  resultsSection.hidden = false;
}

async function lerResposta(response) {
  if (response.ok) {
    return response.json();
  }

  let detail;
  try {
    const body = await response.json();
    detail = body.detail;
    if (Array.isArray(detail)) {
      detail = detail.map((item) => item.msg).filter(Boolean).join(" ");
    }
  } catch {
    detail = null;
  }
  throw new Error(
    typeof detail === "string" && detail
      ? detail
      : `O servidor respondeu com erro (HTTP ${response.status}).`,
  );
}

async function requisitar(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        "Não foi possível conectar ao serviço. Verifique se a API está em execução e tente novamente.",
      );
    }
    throw error;
  }
  return lerResposta(response);
}

async function enviarConsulta() {
  const solicitante = {
    cpf_solicitante: form.elements.cpf_solicitante.value.trim(),
    nome_solicitante: form.elements.nome_solicitante.value.trim(),
    email_solicitante: form.elements.email_solicitante.value.trim(),
  };

  if (modoEntrada() === "arquivo") {
    const payload = new FormData();
    payload.append("arquivo", fileInput.files[0]);
    Object.entries(solicitante).forEach(([campo, valor]) => {
      payload.append(campo, valor);
    });
    return requisitar(
      "/consultas/arquivo",
      { method: "POST", body: payload },
    );
  }

  const cnpjs = cnpjsInput.value
    .split(/\r?\n/)
    .map((cnpj) => cnpj.trim())
    .filter(Boolean);
  return requisitar(
    "/consultas",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...solicitante, cnpjs }),
    },
  );
}

form.querySelectorAll('input[name="modo-entrada"]').forEach((option) => {
  option.addEventListener("change", atualizarModoEntrada);
});

fileInput.addEventListener("change", () => {
  fileName.textContent = fileInput.files.length
    ? `Arquivo selecionado: ${fileInput.files[0].name}`
    : "Nenhum arquivo selecionado.";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) {
    return;
  }

  resultsSection.hidden = true;
  statusMessage.hidden = true;
  submitButton.disabled = true;
  submitButton.textContent = "Consultando...";
  form.setAttribute("aria-busy", "true");
  mostrarStatus(
    "Sua consulta está em andamento. Isso pode levar alguns minutos; mantenha esta página aberta.",
  );

  try {
    const consulta = await enviarConsulta();
    renderizarResultados(consulta);
    mostrarStatus("Consulta concluída. Baixe os documentos encontrados ou o relatório CSV.");
  } catch (error) {
    mostrarStatus(
      error instanceof Error
        ? error.message
        : "Não foi possível concluir a consulta. Tente novamente ou peça ajuda ao responsável pelo sistema.",
      "error",
    );
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = 'Consultar CNPJs <span aria-hidden="true">→</span>';
    form.removeAttribute("aria-busy");
  }
});

atualizarModoEntrada();
