from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import bling
import roteiro


DIA = date(2026, 10, 16)
HORA = datetime(2026, 10, 16, 13, 5)


def nota(identificador, **campos):
    return {"id": identificador, "numero": "000123", "tipo": 1, "situacao": 6,
            "dataEmissao": "2026-10-16 09:10:00", "loja": {"id": 123},
            "numeroPedidoLoja": "1234567890123456", **campos}


class DadosTests(unittest.TestCase):
    @patch("roteiro.consultar_notas", return_value=[nota(1)])
    def test_situacao_alterada_no_detalhe_so_mantem_emitida_danfe(self, _lista):
        for situacao in range(1, 12):
            with self.subTest(situacao=situacao):
                cliente = Mock(get=Mock(return_value={"data": nota(1, situacao=situacao)}))
                registros = roteiro.coletar_registros(cliente, DIA, {"123": "Shopee"}, progresso=None)
                self.assertEqual(len(registros), 1 if situacao == 6 else 0)

    @patch("roteiro.consultar_notas", return_value=[nota(1)])
    def test_detalhe_sem_situacao_interrompe_geracao(self, _lista):
        cliente = Mock(get=Mock(return_value={"data": nota(1, situacao=None)}))
        with self.assertRaises(bling.ErroBling):
            roteiro.coletar_registros(cliente, DIA, {}, progresso=None)

    @patch("roteiro.consultar_notas", return_value=[nota(1), nota(2, loja={"id": 456})])
    def test_loja_excluida_nao_entra_no_roteiro_nem_requer_detalhes(self, _lista):
        cliente = Mock(get=Mock(return_value={"data": nota(1)}))
        resultado = roteiro.coletar_registros(cliente, DIA, {"123": "Mercado Livre", "456": None}, progresso=None)
        self.assertEqual([r.id_nota for r in resultado], ["1"])
        cliente.get.assert_called_once_with("/nfe/1", {})

    @patch("roteiro.consultar_notas", return_value=[nota(1)])
    def test_exclusao_tambem_e_conferida_no_detalhe_atualizado(self, _lista):
        cliente = Mock(get=Mock(return_value={"data": nota(1, loja={"id": 456})}))
        self.assertEqual(roteiro.coletar_registros(cliente, DIA, {"456": None}, progresso=None), [])

    def test_configuracao_null_e_preservada_como_exclusao(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "lojas.json"
            arquivo.write_text('{"123":"Mercado Livre", "456":null}', encoding="utf-8")
            self.assertEqual(roteiro.carregar_lojas(arquivo), {"123": "Mercado Livre", "456": None})

    @patch("roteiro.consultar_notas", return_value=[nota(1), nota(2)])
    def test_detalhes_incluem_pedido_longo_e_cancelamento_posterior_e_excluido(self, _lista):
        cliente = Mock()
        cliente.get.side_effect = [{"data": nota(1)}, {"data": nota(2, situacao=2)}]
        resultado = roteiro.coletar_registros(cliente, DIA, {"123": "Mercado Livre"}, progresso=None)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].pedido, "1234567890123456")
        self.assertEqual(resultado[0].marketplace, "Mercado Livre")

    @patch("roteiro.consultar_notas", return_value=[nota(1)])
    def test_loja_desconhecida_e_numero_ausente_nao_omitem_nota(self, _lista):
        cliente = Mock(get=Mock(return_value={"data": nota(1, numeroPedidoLoja=None)}))
        resultado = roteiro.coletar_registros(cliente, DIA, {}, progresso=None)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].pedido, "")
        self.assertEqual(resultado[0].marketplace, "Loja 123")

    @patch("roteiro.consultar_notas", return_value=[nota(1)])
    def test_identificador_com_risco_de_arredondamento_nao_e_convertido(self, _lista):
        cliente = Mock(get=Mock(return_value={"data": nota(1, numeroPedidoLoja=1.234567890123456e15)}))
        with self.assertRaises(bling.ErroBling):
            roteiro.coletar_registros(cliente, DIA, {}, progresso=None)

    @patch("roteiro.consultar_notas", return_value=[nota(1)])
    def test_detalhe_de_outra_nota_nao_e_associado(self, _lista):
        cliente = Mock(get=Mock(return_value={"data": nota(999)}))
        with self.assertRaises(bling.ErroBling):
            roteiro.coletar_registros(cliente, DIA, {}, progresso=None)


class ExcelTests(unittest.TestCase):
    def gerar(self, pasta, registros):
        destino = Path(pasta) / "roteiro.xlsx"
        roteiro.salvar_excel(registros, DIA, HORA, destino)
        return destino

    def celulas(self, arquivo):
        with ZipFile(arquivo) as z:
            raiz = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        return {c.get("r"): c for c in raiz.iter(roteiro.tag("c"))}

    def texto(self, celula):
        return celula.find(roteiro.tag("is")).find(roteiro.tag("t")).text

    def test_identificadores_preservados_como_texto_literal_e_contagens_em_cache(self):
        itens = [
            roteiro.Registro("1", "000123", "1234567890123456", "123", "Mercado Livre"),
            roteiro.Registro("2", "000321", "TESTE123ABC456", "456", "Shopee"),
        ]
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = self.gerar(pasta, itens)
            celulas = self.celulas(arquivo)
            self.assertEqual(celulas["C7"].get("t"), "inlineStr")
            self.assertEqual(self.texto(celulas["C7"]), "1234567890123456")
            self.assertEqual(self.texto(celulas["B7"]), "000123")
            self.assertEqual(self.texto(celulas["C11"]), "TESTE123ABC456")
            self.assertEqual(celulas["B2"].find(roteiro.tag("v")).text, "TOTAL DE PEDIDOS:2")
            self.assertEqual(celulas["B2"].get("t"), "str")
            self.assertIsNone(celulas["C2"].find(roteiro.tag("v")))
            self.assertEqual(celulas["C5"].find(roteiro.tag("f")).text, "COUNTA(B7:B7)")
            self.assertEqual(celulas["B2"].find(roteiro.tag("f")).text, '"TOTAL DE PEDIDOS:"&SUM(C5,C9)')
            self.assertEqual(self.texto(celulas["A3"]), "HORÁRIO: 13:05:00")
            self.assertIsNone(celulas["B3"].find(roteiro.tag("v")))

    def test_conteudo_iniciado_com_igual_nao_vira_formula(self):
        item = roteiro.Registro("1", "001", '=HYPERLINK("x")', "123", "Mercado Livre")
        with tempfile.TemporaryDirectory() as pasta:
            celula = self.celulas(self.gerar(pasta, [item]))["C7"]
            self.assertEqual(celula.get("t"), "inlineStr")
            self.assertIsNone(celula.find(roteiro.tag("f")))

    def test_sem_notas_exibe_total_zero(self):
        with tempfile.TemporaryDirectory() as pasta:
            celulas = self.celulas(self.gerar(pasta, []))
            self.assertEqual(celulas["B2"].find(roteiro.tag("v")).text, "TOTAL DE PEDIDOS:0")
            self.assertEqual(self.texto(celulas["A5"]), "SEM NOTAS")

    def test_nao_sobrescreve_roteiro_anterior(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = self.gerar(pasta, [])
            antes = arquivo.read_bytes()
            with self.assertRaises(bling.ErroBling):
                roteiro.salvar_excel([], DIA, HORA, arquivo)
            self.assertEqual(antes, arquivo.read_bytes())

    def test_numero_ausente_fica_visivel_no_excel(self):
        item = roteiro.Registro("1", "001", "", "123", "Mercado Livre")
        with tempfile.TemporaryDirectory() as pasta:
            celula = self.celulas(self.gerar(pasta, [item]))["C7"]
            self.assertEqual(self.texto(celula), "NÃO INFORMADO")

    def test_bordas_e_alturas_do_modelo_se_estendem_a_quantidades_diferentes(self):
        itens = [roteiro.Registro(str(i), str(i), str(i), "1", "Mercado Livre") for i in range(50)]
        itens.append(roteiro.Registro("51", "051", "pedido", "2", "Shopee"))
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = self.gerar(pasta, itens)
            with ZipFile(roteiro.BASE / "modelo_roteiro.xlsx") as modelo, ZipFile(arquivo) as saida:
                self.assertEqual(modelo.read("xl/styles.xml"), saida.read("xl/styles.xml"))
                self.assertNotIn("xl/calcChain.xml", saida.namelist())
                self.assertNotIn(b"/calcChain", saida.read("xl/_rels/workbook.xml.rels"))
                self.assertNotIn(b"calcChain.xml", saida.read("[Content_Types].xml"))
                referencia = ET.fromstring(modelo.read("xl/worksheets/sheet1.xml"))
                gerada = ET.fromstring(saida.read("xl/worksheets/sheet1.xml"))
            cells = self.celulas(arquivo)
            ref_cells = {c.get("r"): c for c in referencia.iter(roteiro.tag("c"))}
            for linha, ref_linha in ((56, 7), (57, 4), (58, 5), (59, 6), (60, 7)):
                for coluna in "ABC":
                    self.assertEqual(cells[f"{coluna}{linha}"].get("s"), ref_cells[f"{coluna}{ref_linha}"].get("s"))
            self.assertEqual(gerada.find(f"{roteiro.tag('sheetData')}/{roteiro.tag('row')}[@r='56']").get("ht"),
                             referencia.find(f"{roteiro.tag('sheetData')}/{roteiro.tag('row')}[@r='7']").get("ht"))
            self.assertEqual(cells["B2"].find(roteiro.tag("v")).text, "TOTAL DE PEDIDOS:51")
            self.assertEqual(cells["B2"].find(roteiro.tag("f")).text, '"TOTAL DE PEDIDOS:"&SUM(C5,C58)')

    def test_impressao_cobre_todos_os_registros(self):
        itens = [roteiro.Registro(str(i), str(i), str(i), "1", "Mercado Livre") for i in range(150)]
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = self.gerar(pasta, itens)
            with ZipFile(arquivo) as z:
                workbook = ET.fromstring(z.read("xl/workbook.xml"))
                sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            nomes = {n.get("name"): n.text for n in workbook.find(roteiro.tag("definedNames"))}
            self.assertEqual(nomes["_xlnm.Print_Area"], "'Roteiro'!$A$1:$C$156")
            self.assertEqual(sheet.find(roteiro.tag("pageSetup")).get("fitToHeight"), "0")


if __name__ == "__main__":
    unittest.main()
