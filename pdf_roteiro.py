"""PDF A4 do roteiro, com cada marketplace começando em uma página própria."""

from datetime import date, datetime
from pathlib import Path
import sys
import tempfile

from bling import ErroBling


LINHAS_POR_PAGINA = 55


def biblioteca_pdf():
    # O pacote portátil leva as bibliotecas; não depende de instalações no PC.
    vendor = Path(__file__).resolve().parent / "_vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white
    except ImportError:
        raise ErroBling("Biblioteca de PDF ausente. Extraia a atualização completa ou instale requirements-pdf.txt.") from None
    return canvas, A4, HexColor, white


def salvar_pdf(grupos: list[tuple[str, list]], dia: date, gerado: datetime, destino: Path) -> Path:
    if destino.exists():
        raise ErroBling("O PDF de saída já existe. Escolha outro nome ou gere novamente sem --saida.")
    canvas, A4, HexColor, white = biblioteca_pdf()
    destino.parent.mkdir(parents=True, exist_ok=True)
    paginas = []
    for nome, itens in grupos or [("SEM NOTAS", [])]:
        for inicio in range(0, max(1, len(itens)), LINHAS_POR_PAGINA):
            paginas.append((nome, itens, inicio, itens[inicio:inicio + LINHAS_POR_PAGINA]))

    temporario = None
    try:
        with tempfile.NamedTemporaryFile(dir=destino.parent, suffix=".pdf", delete=False) as tmp:
            temporario = Path(tmp.name)
        c = canvas.Canvas(str(temporario), pagesize=A4, pageCompression=1)
        c.setTitle(f"Roteiro {dia:%d/%m/%Y}")
        c.setAuthor("Romaneio Diário")
        largura, altura = A4
        esquerda, direita = 30, largura - 30
        larguras = [75, 130, direita - esquerda - 205]
        tinta = HexColor("#172B3A")

        def texto_central(texto, x, y, espaco):
            tamanho = min(9.5, 9.5 * (espaco - 10) / max(c.stringWidth(texto, "Helvetica", 9.5), 1))
            if tamanho < 6:
                raise ErroBling("Um identificador é longo demais para o PDF. Confira os dados da nota.")
            c.setFont("Helvetica", tamanho)
            c.drawCentredString(x + espaco / 2, y, texto)

        for pagina, (nome, todos, inicio, itens) in enumerate(paginas, 1):
            c.setFillColor(tinta)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(esquerda, altura - 40, "ROTEIRO")
            c.setFont("Helvetica", 10)
            c.drawRightString(direita, altura - 39, f"{dia:%d/%m/%Y}  |  {gerado:%H:%M:%S}")
            total = f"TOTAL DE PEDIDOS: {len(todos)}"
            espaco_nome = direita - esquerda - c.stringWidth(total, "Helvetica-Bold", 10) - 12
            tamanho_nome = min(13, 13 * espaco_nome / max(c.stringWidth(nome.upper(), "Helvetica-Bold", 13), 1))
            c.setFont("Helvetica-Bold", tamanho_nome)
            c.drawString(esquerda, altura - 66, nome.upper())
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(direita, altura - 65, total)
            topo, cabecalho, linha = altura - 82, 22, 12.3
            c.rect(esquerda, topo - cabecalho, direita - esquerda, cabecalho, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 9)
            x = esquerda
            for titulo, espaco in zip(("PEDIDO", "NOTA FISCAL", "VENDA NA LOJA VIRTUAL"), larguras):
                c.drawCentredString(x + espaco / 2, topo - 14, titulo)
                x += espaco
            y = topo - cabecalho
            for indice, item in enumerate(itens):
                if indice % 2 == 0:
                    c.setFillColor(HexColor("#F0F3F5"))
                    c.rect(esquerda, y - linha, direita - esquerda, linha, fill=1, stroke=0)
                if not item.pedido:
                    c.setFillColor(HexColor("#FFF1C2"))
                    c.rect(esquerda + sum(larguras[:2]), y - linha, larguras[2], linha, fill=1, stroke=0)
                c.setFillColor(tinta)
                x = esquerda
                for texto, espaco in zip((str(inicio + indice + 1), item.numero, item.pedido or "NÃO INFORMADO"), larguras):
                    texto_central(texto, x, y - 9.2, espaco)
                    x += espaco
                y -= linha
            if not itens:
                c.setFillColor(tinta)
                c.setFont("Helvetica", 9.5)
                c.drawString(esquerda + 8, y - 16, "Nenhuma nota nesta data.")
                y -= 26
            c.setStrokeColor(HexColor("#BCC7CD"))
            c.setLineWidth(0.4)
            c.rect(esquerda, y, direita - esquerda, topo - y, fill=0, stroke=1)
            c.setFillColor(HexColor("#667780"))
            c.setFont("Helvetica", 8)
            if len(todos) > LINHAS_POR_PAGINA:
                c.drawString(esquerda, 20, f"Registros {inicio + 1} a {inicio + len(itens)} de {len(todos)}")
            c.drawRightString(direita, 20, f"{pagina} / {len(paginas)}")
            c.showPage()
        c.save()
        temporario.rename(destino)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
    return destino
