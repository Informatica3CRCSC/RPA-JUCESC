import tempfile
import unittest
from pathlib import Path

import httpx

from src.api import _cnpjs_do_arquivo, criar_app


class FakeAutomation:
    async def __call__(self, cnpjs, cpf, nome, email, pasta_saida):
        pasta_saida = Path(pasta_saida)
        (pasta_saida / "resultados_jucesc.csv").write_text(
            "cnpj;status;arquivo;erro\n"
            f"{cnpjs[0]};success;jucesc_teste.pdf;\n",
            encoding="utf-8-sig",
        )
        (pasta_saida / "jucesc_teste.pdf").write_bytes(b"%PDF-test")
        (pasta_saida / "jucesc_erro.png").write_bytes(b"private screenshot")
        return [
            {
                "cnpj": cnpj,
                "status": "success" if indice == 0 else "error",
                "arquivo": "jucesc_teste.pdf" if indice == 0 else None,
                "erro": None if indice == 0 else "Sem resultado.",
            }
            for indice, cnpj in enumerate(cnpjs)
        ]


class ArquivoCnpjTests(unittest.TestCase):
    def test_le_txt_ignora_comentarios_e_linhas_vazias(self):
        self.assertEqual(
            _cnpjs_do_arquivo(
                "# lista\n12.345.678/0001-95 # comentário\n\n", ".txt"
            ),
            ["12.345.678/0001-95"],
        )

    def test_le_csv_com_cabecalho_e_delimitador_ponto_e_virgula(self):
        self.assertEqual(
            _cnpjs_do_arquivo(
                "nome;CNPJ\nEmpresa;12.345.678/0001-95\n", ".csv"
            ),
            ["12.345.678/0001-95"],
        )


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app = criar_app(
            pasta_resultados=Path(self.temp_dir.name),
            automation=FakeAutomation(),
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.temp_dir.cleanup()

    @staticmethod
    def payload(cnpjs):
        return {
            "cnpjs": cnpjs,
            "cpf_solicitante": "529.982.247-25",
            "nome_solicitante": "Nome Sobrenome",
            "email_solicitante": "nome@example.com",
        }

    async def test_health(self):
        response = await self.client.get("/health")
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_consulta_json_retorna_resultados_e_downloads(self):
        response = await self.client.post(
            "/consultas",
            json=self.payload(["12345678000195", "11222333000181"]),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["sucesso"], 1)
        self.assertEqual(body["erros"], 1)
        self.assertEqual(body["resultados"][0]["status"], "success")
        self.assertEqual(body["resultados"][1]["status"], "error")

        csv_response = await self.client.get(body["csv_url"])
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("jucesc_teste.pdf", csv_response.text)

        pdf_response = await self.client.get(body["resultados"][0]["pdf_url"])
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.content, b"%PDF-test")

        arquivos_response = await self.client.get(
            f"/consultas/{body['consulta_id']}/arquivos"
        )
        arquivos = arquivos_response.json()
        self.assertEqual(
            {arquivo["nome"] for arquivo in arquivos},
            {"resultados_jucesc.csv", "jucesc_teste.pdf"},
        )
        self.assertEqual(
            (
                await self.client.get(
                    f"/consultas/{body['consulta_id']}/arquivos/jucesc_erro.png"
                )
            ).status_code,
            404,
        )

    async def test_upload_txt_chama_mesma_automacao(self):
        response = await self.client.post(
            "/consultas/arquivo",
            data={
                "cpf_solicitante": "529.982.247-25",
                "nome_solicitante": "Nome Sobrenome",
                "email_solicitante": "nome@example.com",
            },
            files={
                "arquivo": (
                    "cnpjs.txt",
                    b"12.345.678/0001-95\n",
                    "text/plain",
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)

    async def test_upload_csv_e_valida_cnpjs(self):
        response = await self.client.post(
            "/consultas/arquivo",
            data={
                "cpf_solicitante": "529.982.247-25",
                "nome_solicitante": "Nome Sobrenome",
                "email_solicitante": "nome@example.com",
            },
            files={
                "arquivo": (
                    "cnpjs.csv",
                    b"cnpj\n12.345.678/0001-96\n",
                    "text/csv",
                )
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("CNPJ inválido", response.json()["detail"])

    async def test_rejeita_solicitante_invalido(self):
        response = await self.client.post(
            "/consultas",
            json={
                **self.payload(["12345678000195"]),
                "cpf_solicitante": "00000000000",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("CPF inválido", response.json()["detail"])

    async def test_rejeita_arquivo_nao_suportado_e_travessia_de_diretorio(self):
        response = await self.client.post(
            "/consultas/arquivo",
            data={
                "cpf_solicitante": "529.982.247-25",
                "nome_solicitante": "Nome Sobrenome",
                "email_solicitante": "nome@example.com",
            },
            files={"arquivo": ("lista.xlsx", b"contents")},
        )
        self.assertEqual(response.status_code, 422)

        consulta_response = await self.client.post(
            "/consultas",
            json=self.payload(["12345678000195"]),
        )
        consulta = consulta_response.json()
        response = await self.client.get(
            f"/consultas/{consulta['consulta_id']}/arquivos/..%2F..%2Fsecret"
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
