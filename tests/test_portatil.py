from contextlib import contextmanager
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import bling
import portatil


class FluxoSimplesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.base = self.raiz / "programa"
        self.base.mkdir()
        (self.base / "lojas.json").write_text('{"111":"Mercado Livre","222":null}', encoding="utf-8")
        self.cofre = Mock()
        self.config = {"client_id": "teste", "tokens": {"refresh_token": "teste"}}

    @contextmanager
    def sessao(self):
        yield self.cofre, self.config

    def fluxo(self, acao):
        with patch.multiple(portatil, BASE=self.base, RAIZ=self.raiz), \
                patch("bling.sessao_local", self.sessao), patch("builtins.print"):
            return portatil.executar(acao)

    def test_configuracao_da_empresa_so_pede_autorizacao(self):
        with patch("bling.conectar") as conectar, patch("app.configurar_lojas") as lojas:
            self.fluxo("configurar")
        conectar.assert_called_once_with(self.cofre, self.config)
        lojas.assert_not_called()

    def test_uso_diario_gera_hoje_fora_da_pasta_de_codigo_sem_perguntas(self):
        with patch("roteiro.gerar", side_effect=lambda c, d, p, m: p) as gerar, \
                patch("builtins.input", side_effect=AssertionError("Não deve perguntar")), \
                patch("bling.conectar") as conectar:
            arquivo = self.fluxo("gerar")
        conectar.assert_not_called()
        self.assertEqual(gerar.call_args.args[1], date.today())
        self.assertEqual(arquivo.parent, self.raiz / "roteiros")
        self.assertEqual(gerar.call_args.args[3], self.base / "lojas.json")

    def test_gerar_no_primeiro_uso_autoriza_e_usa_novos_tokens(self):
        self.config = {}
        novo = {"client_id": "teste", "tokens": {"refresh_token": "novo"}}
        self.cofre.ler.return_value = novo
        with patch("bling.conectar") as conectar, \
                patch("roteiro.gerar", side_effect=lambda c, d, p, m: p) as gerar:
            self.fluxo("gerar")
        conectar.assert_called_once()
        self.assertEqual(gerar.call_args.args[0].config, novo)

    def test_cancelar_configuracao_nao_inicia_relatorio(self):
        self.config = {}
        with patch("bling.conectar", side_effect=bling.ErroBling("Autorização recusada")), \
                patch("roteiro.gerar") as gerar:
            with self.assertRaises(bling.ErroBling):
                self.fluxo("gerar")
        gerar.assert_not_called()

    def test_erro_salva_um_log_sem_traceback_ou_credenciais(self):
        with patch.multiple(portatil, BASE=self.base, RAIZ=self.raiz), \
                patch("sys.argv", ["portatil.py", "gerar"]), patch("builtins.print"), \
                patch("portatil.executar", side_effect=bling.ErroBling("Acesso expirou; reconecte.")):
            self.assertEqual(portatil.main(), 1)
        logs = list((self.raiz / "logs").iterdir())
        self.assertEqual([p.name for p in logs], ["execucao.log"])
        self.assertIn("Acesso expirou", logs[0].read_text(encoding="utf-8"))
        self.assertNotIn("Traceback", logs[0].read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in self.raiz.iterdir()), ["logs", "programa", "roteiros"])


if __name__ == "__main__":
    unittest.main()
