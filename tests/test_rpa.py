import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.rpa_jucesc import consultar, validar_e_normalizar_cnpjs


class RpaFacadeTests(unittest.IsolatedAsyncioTestCase):
    def test_valida_normaliza_e_remove_cnpjs_duplicados(self):
        self.assertEqual(
            validar_e_normalizar_cnpjs(
                ["12345678000195", "12.345.678/0001-95"]
            ),
            ["12.345.678/0001-95"],
        )

    def test_rejeita_cnpj_com_digito_verificador_invalido(self):
        with self.assertRaisesRegex(ValueError, "CNPJ inválido"):
            validar_e_normalizar_cnpjs(["12345678000196"])

    async def test_delega_ao_motor_existente_sem_print_de_erro(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pasta_saida = Path(temp_dir)
            with patch(
                "src.rpa_jucesc.consultar_cnpj_jucesc",
                new_callable=AsyncMock,
                return_value=[],
            ) as motor:
                resultado = await consultar(
                    ["12.345.678/0001-95"],
                    "529.982.247-25",
                    "Nome Sobrenome",
                    "nome@example.com",
                    pasta_saida,
                )

        self.assertEqual(resultado, [])
        motor.assert_awaited_once_with(
            ["12.345.678/0001-95"],
            "529.982.247-25",
            "Nome Sobrenome",
            "nome@example.com",
            pasta_saida,
            salvar_print_erro=False,
        )


if __name__ == "__main__":
    unittest.main()
