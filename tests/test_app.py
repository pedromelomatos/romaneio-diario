from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app


class ConfiguracaoPortatilTests(unittest.TestCase):
    @patch("builtins.print")
    def test_usuario_escolhe_exclusao_sem_editar_json(self, _print):
        with patch("builtins.input", return_value="4"):
            self.assertEqual(app.escolher_nome(None, existente=False), (True, None))

    @patch("builtins.print")
    def test_enter_preserva_exclusao_existente(self, _print):
        with patch("builtins.input", return_value=""):
            self.assertEqual(app.escolher_nome(None, existente=True), (False, None))

    @patch("builtins.print")
    @patch("app.bling.consultar_notas", return_value=[
        {"numero": "000001", "loja": {"id": 111}},
        {"numero": "000002", "loja": {"id": 222}},
    ])
    def test_primeira_configuracao_salva_nome_e_exclusao(self, _notas, _print):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "lojas.json"
            with patch("builtins.input", side_effect=["1", "4"]):
                app.configurar_lojas(Mock(), date(2026, 10, 16), arquivo)
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8")), {"111": "Mercado Livre", "222": None})
            self.assertEqual([p.name for p in Path(pasta).iterdir()], ["lojas.json"])

    @patch("builtins.print")
    @patch("app.bling.consultar_notas", return_value=[])
    def test_dia_sem_notas_preserva_configuracao_anterior(self, _notas, _print):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "lojas.json"
            arquivo.write_text('{"111":null}', encoding="utf-8")
            app.configurar_lojas(Mock(), date(2026, 10, 16), arquivo)
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8")), {"111": None})

    @patch("builtins.print")
    def test_data_invalida_pede_novamente(self, _print):
        with patch("builtins.input", side_effect=["31/02/2026", "15/10/2026"]):
            self.assertEqual(app.pedir_data(), date(2026, 10, 15))


if __name__ == "__main__":
    unittest.main()
