from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader

import bling
import roteiro
from pdf_roteiro import salvar_pdf


DIA = date(2026, 10, 19)
HORA = datetime(2026, 10, 19, 13, 39, 7)


def itens(quantidade, grupo="Mercado Livre", inicio=1):
    return [roteiro.Registro(str(i), f"{i:06}", f"200001525855{i:04}", "1", grupo)
            for i in range(inicio, inicio + quantidade)]


def dados_pdf(arquivo):
    resultado = []
    for pagina in PdfReader(arquivo).pages:
        linhas = pagina.extract_text().splitlines()
        grupo = linhas[2]
        primeiro = linhas.index("VENDA NA LOJA VIRTUAL") + 1
        i = primeiro
        while i < len(linhas) and linhas[i].isdigit():
            resultado.append((grupo, int(linhas[i]), linhas[i + 1], linhas[i + 2]))
            i += 3
    return resultado


class PdfTests(unittest.TestCase):
    def test_94_pares_mesmos_dados_do_excel_com_uma_pagina_por_marketplace(self):
        registros = itens(55) + itens(39, "Shopee", 101)
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            roteiro.salvar_excel(registros, DIA, HORA, base / "roteiro.xlsx")
            salvar_pdf(roteiro.agrupar(registros), DIA, HORA, base / "roteiro.pdf")
            reader = PdfReader(base / "roteiro.pdf")
            self.assertEqual(len(reader.pages), 2)
            self.assertIn("TOTAL DE PEDIDOS: 55", reader.pages[0].extract_text())
            self.assertNotIn("SHOPEE", reader.pages[0].extract_text())
            self.assertIn("TOTAL DE PEDIDOS: 39", reader.pages[1].extract_text())
            esperado = [(nome.upper(), seq, item.numero, item.pedido)
                        for nome, grupo in roteiro.agrupar(registros)
                        for seq, item in enumerate(grupo, 1)]
            self.assertEqual(dados_pdf(base / "roteiro.pdf"), esperado)
            with ZipFile(base / "roteiro.xlsx") as z:
                root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            pares_excel = []
            for row in root.findall(f"{roteiro.tag('sheetData')}/{roteiro.tag('row')}"):
                vals = {c.get("r")[0]: "".join(t.text or "" for t in c.iter(roteiro.tag("t"))) for c in row}
                if vals.get("B", "").isdigit():
                    pares_excel.append((vals["B"], vals["C"]))
            self.assertEqual([(r[2], r[3]) for r in esperado], pares_excel)

    def test_mais_de_55_continua_o_grupo_sem_perder_registros_ou_misturar_lojas(self):
        registros = itens(56) + itens(1, "Shopee", 100)
        with tempfile.TemporaryDirectory() as pasta:
            pdf = salvar_pdf(roteiro.agrupar(registros), DIA, HORA, Path(pasta) / "roteiro.pdf")
            reader = PdfReader(pdf)
            self.assertEqual(len(reader.pages), 3)
            self.assertIn("Registros 56 a 56 de 56", reader.pages[1].extract_text())
            self.assertNotIn("SHOPEE", reader.pages[1].extract_text())
            self.assertIn("SHOPEE", reader.pages[2].extract_text())
            self.assertEqual(len(dados_pdf(pdf)), 57)
            self.assertEqual([r[1] for r in dados_pdf(pdf)[:56]], list(range(1, 57)))

    def test_sem_notas_e_pedido_ausente_ficam_explicitos(self):
        with tempfile.TemporaryDirectory() as pasta:
            vazio = salvar_pdf([], DIA, HORA, Path(pasta) / "vazio.pdf")
            self.assertEqual(len(PdfReader(vazio).pages), 1)
            self.assertIn("TOTAL DE PEDIDOS: 0", PdfReader(vazio).pages[0].extract_text())
            registro = roteiro.Registro("1", "000123", "", "1", "Shopee")
            pdf = salvar_pdf([("Shopee", [registro])], DIA, HORA, Path(pasta) / "ausente.pdf")
            self.assertIn("NÃO INFORMADO", PdfReader(pdf).pages[0].extract_text())

    def test_pdf_existente_e_preservado(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "roteiro.pdf"
            destino.write_bytes(b"anterior")
            with self.assertRaises(bling.ErroBling):
                salvar_pdf([], DIA, HORA, destino)
            self.assertEqual(destino.read_bytes(), b"anterior")

    @patch("roteiro.carregar_lojas", return_value={"1": "Mercado Livre"})
    @patch("roteiro.coletar_registros", return_value=itens(2))
    def test_gerar_automaticamente_publica_os_dois_arquivos_com_mesma_base(self, coleta, _lojas):
        with tempfile.TemporaryDirectory() as pasta, patch("builtins.print"):
            destino = Path(pasta) / "resultado.xlsx"
            self.assertEqual(roteiro.gerar(Mock(), DIA, destino), destino.resolve())
            self.assertTrue(destino.is_file())
            self.assertEqual(len(dados_pdf(destino.with_suffix(".pdf"))), 2)
            coleta.assert_called_once()

    @patch("roteiro.carregar_lojas", return_value={})
    @patch("roteiro.coletar_registros", return_value=itens(1))
    def test_falha_no_pdf_nao_deixa_excel_publicado_ou_sobrescreve_pdf(self, _coleta, _lojas):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "resultado.xlsx"
            with patch("pdf_roteiro.salvar_pdf", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError):
                    roteiro.gerar(Mock(), DIA, destino)
            self.assertEqual(list(Path(pasta).iterdir()), [])
            destino.with_suffix(".pdf").write_bytes(b"anterior")
            with self.assertRaises(bling.ErroBling):
                roteiro.gerar(Mock(), DIA, destino)
            self.assertFalse(destino.exists())
            self.assertEqual(destino.with_suffix(".pdf").read_bytes(), b"anterior")


if __name__ == "__main__":
    unittest.main()
