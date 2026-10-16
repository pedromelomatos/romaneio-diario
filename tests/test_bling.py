import copy
from datetime import date
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import bling


DIA = date(2026, 10, 16)


def nota(identificador, numero, **campos):
    return {"id": identificador, "numero": numero, "tipo": 1, "situacao": 6,
            "dataEmissao": "2026-10-16 09:10:00", **campos}


class ConsultaTests(unittest.TestCase):
    def test_consulta_todas_paginas_inclui_somente_emitida_danfe(self):
        cliente = Mock()
        cliente.get.side_effect = [
            {"data": [nota(1, "000123"), nota(2, "000124", situacao=2)]},
            {"data": [nota(3, "000122", situacao=5), nota(4, "000121", situacao=1),
                      nota(5, "002807", situacao=4)]},
            {"data": []},
        ]
        resultado = bling.consultar_notas(cliente, DIA)
        self.assertEqual([n["numero"] for n in resultado], ["000123"])
        for i, chamada in enumerate(cliente.get.call_args_list, 1):
            caminho, filtros = chamada.args
            self.assertEqual(caminho, "/nfe")
            self.assertEqual(filtros["pagina"], i)
            self.assertEqual(filtros["tipo"], 1)
            self.assertEqual(filtros["dataEmissaoInicial"], "2026-10-16 00:00:00")
            self.assertEqual(filtros["dataEmissaoFinal"], "2026-10-16 23:59:59")
            self.assertEqual(filtros["situacao"], 6)

    def test_demais_situacoes_sao_excluidas_mesmo_se_api_ignorar_filtro(self):
        cliente = Mock()
        cliente.get.side_effect = [
            {"data": [nota(i, str(i), situacao=i) for i in range(1, 12)]}, {"data": []},
        ]
        self.assertEqual([n["situacao"] for n in bling.consultar_notas(cliente, DIA)], [6])

    def test_nenhuma_nota_e_resultado_valido(self):
        self.assertEqual(bling.consultar_notas(Mock(get=Mock(return_value={"data": []})), DIA), [])

    def test_nao_omite_silenciosamente_notas_fora_dos_filtros(self):
        for mudanca in ({"dataEmissao": "2026-10-15 23:59:59"}, {"tipo": 0}, {"situacao": None}):
            with self.subTest(mudanca=mudanca):
                cliente = Mock()
                cliente.get.side_effect = [{"data": [nota(1, "001", **mudanca)]}, {"data": []}]
                with self.assertRaises(bling.ErroBling):
                    bling.consultar_notas(cliente, DIA)

    def test_resposta_invalida_nao_parece_lista_vazia(self):
        for resposta in ({}, {"data": {}}, {"data": [{}]}):
            with self.subTest(resposta=resposta), self.assertRaises(bling.ErroBling):
                bling.consultar_notas(Mock(get=Mock(return_value=resposta)), DIA)

    def test_pagina_repetida_nao_gera_loop_nem_conferencia_parcial(self):
        cliente = Mock(get=Mock(return_value={"data": [nota(1, "001")]}))
        with self.assertRaisesRegex(bling.ErroBling, "repetiu"):
            bling.consultar_notas(cliente, DIA)
        self.assertEqual(cliente.get.call_count, 2)

    def test_pagina_sobreposta_nao_duplica_nota(self):
        cliente = Mock()
        cliente.get.side_effect = [
            {"data": [nota(1, "001")]},
            {"data": [nota(1, "001"), nota(2, "002")]}, {"data": []},
        ]
        self.assertEqual(len(bling.consultar_notas(cliente, DIA)), 2)

    def test_mudanca_da_mesma_nota_interrompe_conferencia(self):
        cliente = Mock()
        cliente.get.side_effect = [
            {"data": [nota(1, "001")]}, {"data": [nota(1, "001", situacao=2)]},
        ]
        with self.assertRaisesRegex(bling.ErroBling, "mudaram"):
            bling.consultar_notas(cliente, DIA)


class OAuthTests(unittest.TestCase):
    @patch("builtins.print")
    def test_pacote_configurado_nao_pede_credenciais_nem_importa_tokens(self, _print):
        dados = {"client_id": "id-teste", "client_secret": "secret-teste", "tokens": {
            "access_token": "nao-copiar", "refresh_token": "nao-copiar"}}
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "tokens.json"
            arquivo.write_text(json.dumps(dados), encoding="utf-8-sig")
            carregado = bling.carregar_aplicacao(arquivo)
        self.assertEqual(carregado, {"client_id": "id-teste", "client_secret": "secret-teste",
                                     "redirect_uri": bling.CALLBACK})
        anterior = {"tokens": {"refresh_token": "acesso-anterior"}}
        with patch("bling.carregar_aplicacao", return_value=carregado), \
                patch("builtins.input") as entrada, patch("bling.getpass.getpass") as segredo, \
                patch("bling.autorizar") as autorizar:
            bling.conectar(Mock(), anterior)
        entrada.assert_not_called()
        segredo.assert_not_called()
        self.assertEqual(autorizar.call_args.args[0].config, carregado)
        self.assertEqual(anterior, {"tokens": {"refresh_token": "acesso-anterior"}})

    def test_arquivo_invalido_nao_expoe_conteudo(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "tokens.json"
            self.assertEqual(bling.carregar_aplicacao(arquivo), {})
            for conteudo in ('{"client_secret":"segredo-nao-expor",', '[]',
                             '{"client_id":"id","client_secret":123}',
                             '{"client_id":"id","client_secret":"segredo-nao-expor","redirect_uri":"http://exemplo.com:1/cb"}'):
                arquivo.write_text(conteudo, encoding="utf-8")
                with self.subTest(conteudo=conteudo), self.assertRaises(bling.ErroBling) as erro:
                    bling.carregar_aplicacao(arquivo)
                self.assertNotIn("segredo-nao-expor", str(erro.exception))

    @patch("builtins.print")
    def test_reconectar_aproveita_cadastro_local_sem_reutilizar_tokens(self, _print):
        config = {"client_id": "id", "client_secret": "secret", "tokens": {"refresh_token": "antigo"}}
        with patch("bling.carregar_aplicacao", return_value={}), patch("builtins.input") as entrada, \
                patch("bling.autorizar") as autorizar:
            bling.conectar(Mock(), config)
        entrada.assert_not_called()
        self.assertNotIn("tokens", autorizar.call_args.args[0].config)
        self.assertEqual(config["tokens"]["refresh_token"], "antigo")

    @patch("builtins.print")
    def test_sem_arquivo_nem_cadastro_mantem_configuracao_manual(self, _print):
        with patch("bling.carregar_aplicacao", return_value={}), \
                patch("builtins.input", side_effect=["id-manual", ""]), \
                patch("bling.getpass.getpass", return_value="secret-manual"), \
                patch("bling.autorizar") as autorizar:
            bling.conectar(Mock(), {})
        self.assertEqual(autorizar.call_args.args[0].config, {
            "client_id": "id-manual", "client_secret": "secret-manual", "redirect_uri": bling.CALLBACK})

    def test_autorizacao_com_retorno_http_local_e_troca_imediata_do_codigo(self):
        with socket.socket() as reserva:
            reserva.bind(("127.0.0.1", 0))
            porta = reserva.getsockname()[1]
        cliente = Mock()
        cliente.config = {"client_id": "id-de-teste", "redirect_uri": f"http://localhost:{porta}/callback"}
        threads, erros = [], []

        def abrir_navegador(url):
            state = parse_qs(urlsplit(url).query)["state"][0]

            def navegador_simulado():
                try:
                    destino = f"http://127.0.0.1:{porta}/callback?" + urlencode({"state": state, "code": "codigo-unico"})
                    with urlopen(destino, timeout=3) as resposta:
                        self.assertEqual(resposta.status, 200)
                        self.assertEqual(resposta.headers["Cache-Control"], "no-store")
                except Exception as exc:
                    erros.append(exc)

            thread = threading.Thread(target=navegador_simulado)
            threads.append(thread)
            thread.start()
            return True

        with patch("bling.webbrowser.open", side_effect=abrir_navegador), patch("builtins.print"):
            bling.autorizar(cliente, segundos=5)
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(erros, [])
        cliente.token.assert_called_once_with({"grant_type": "authorization_code", "code": "codigo-unico"})

    def test_callback_so_aceita_estado_e_caminho_corretos(self):
        for url in ("/callback?code=abc", "/callback?state=errado&code=abc",
                    "/outro?state=seguro&code=abc", "/callback?state=seguro&code=a&code=b",
                    "/callback?state=seguro&state=seguro&code=abc"):
            with self.subTest(url=url):
                self.assertEqual(bling.interpretar_callback(url, "/callback", "seguro"), ("ignorar", ""))
        self.assertEqual(bling.interpretar_callback("/callback?state=seguro&code=abc", "/callback", "seguro"),
                         ("codigo", "abc"))

    def test_recusa_de_autorizacao_nao_aceita_codigo(self):
        tipo, _ = bling.interpretar_callback("/callback?state=x&error=access_denied&code=abc", "/callback", "x")
        self.assertEqual(tipo, "erro")

    def test_retorno_fica_restrito_ao_computador_local(self):
        self.assertEqual(bling.validar_callback(bling.CALLBACK).port, 8765)
        for url in ("http://exemplo.com:8765/callback", "http://localhost/callback",
                    "http://localhost:8765/callback?code=a", "http://localhost:abc/callback",
                    "http://usuario@localhost:8765/callback", "https://localhost:8765/callback"):
            with self.subTest(url=url), self.assertRaises(bling.ErroBling):
                bling.validar_callback(url)

    def test_rotacao_de_tokens_grava_novo_refresh_e_respeita_validade(self):
        config = {"client_id": "id", "client_secret": "segredo", "tokens": {"refresh_token": "antigo"}}
        cofre = Mock()
        cliente = bling.Cliente(cofre, config)
        with patch("bling.requisicao", return_value={"access_token": "acesso", "refresh_token": "novo", "expires_in": 3600}), \
                patch("bling.time.time", return_value=100):
            cliente.renovar()
        self.assertEqual(config["tokens"], {"access_token": "acesso", "refresh_token": "novo", "expires_at": 3700})
        cofre.salvar.assert_called_once_with(config)

    def test_falha_na_troca_de_codigo_nao_repete_requisicao(self):
        cliente = bling.Cliente(Mock(), {"client_id": "id", "client_secret": "segredo"})
        with patch("bling.requisicao", side_effect=bling.ErroHTTP(500)) as chamada:
            with self.assertRaises(bling.ErroHTTP):
                cliente.token({"grant_type": "authorization_code", "code": "unico"})
        self.assertEqual(chamada.call_count, 1)

    def test_erro_http_nao_expoe_resposta_com_segredos(self):
        erro = HTTPError("https://exemplo", 400, "invalid", {}, io.BytesIO(b'{"segredo":"nao_expor"}'))
        with patch("bling.urlopen", side_effect=erro):
            with self.assertRaises(bling.ErroHTTP) as resultado:
                bling.requisicao("POST", "https://exemplo", {}, {"code": "tambem_secreto"})
        self.assertNotIn("nao_expor", str(resultado.exception))
        self.assertNotIn("tambem_secreto", str(resultado.exception))


class ClienteTests(unittest.TestCase):
    def cliente(self):
        return bling.Cliente(Mock(), {"tokens": {"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 3600}})

    @patch("bling.time.sleep")
    def test_renova_uma_vez_apos_401(self, _sleep):
        cliente = self.cliente()
        with patch.object(cliente, "renovar") as renovar, \
                patch("bling.requisicao", side_effect=[bling.ErroHTTP(401), {"data": []}]):
            self.assertEqual(cliente.get("/nfe", {}), {"data": []})
        renovar.assert_called_once()

    @patch("bling.time.sleep")
    def test_limite_diario_nao_e_repetido(self, _sleep):
        cliente = self.cliente()
        with patch("bling.requisicao", side_effect=bling.ErroHTTP(429, True)) as chamada:
            with self.assertRaises(bling.ErroHTTP):
                cliente.get("/nfe", {})
        self.assertEqual(chamada.call_count, 1)

    @patch("bling.time.sleep")
    def test_repeticoes_de_erro_temporario_sao_limitadas(self, _sleep):
        with patch("bling.requisicao", side_effect=bling.ErroHTTP(503)) as chamada:
            with self.assertRaises(bling.ErroHTTP):
                self.cliente().get("/nfe", {})
        self.assertEqual(chamada.call_count, 5)


@unittest.skipUnless(os.name == "nt", "DPAPI exige Windows")
class CofreTests(unittest.TestCase):
    def test_credenciais_protegidas_e_rotacao_preservada_em_disco(self):
        with tempfile.TemporaryDirectory() as pasta:
            cofre = bling.Cofre(Path(pasta))
            dados = {"client_id": "teste", "client_secret": "segredo-que-nao-pode-estar-em-texto"}
            cofre.salvar(dados)
            self.assertNotIn(dados["client_secret"].encode(), cofre.arquivo.read_bytes())
            self.assertEqual(cofre.ler(), dados)
            novo = copy.deepcopy(dados)
            novo["tokens"] = {"refresh_token": "novo-token"}
            cofre.salvar(novo)
            self.assertEqual(cofre.ler(), novo)
            self.assertEqual(list(Path(pasta).iterdir()), [cofre.arquivo])


if __name__ == "__main__":
    unittest.main()
