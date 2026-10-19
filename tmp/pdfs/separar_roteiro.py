from pathlib import Path
import openpyxl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from pypdf import PdfReader
import subprocess

root = Path(__file__).resolve().parents[2]
source = root / 'outputs/ROTEIRO_2026-10-19_133907_899688.xlsx'
out = root / 'output/pdf/ROTEIRO_2026-10-19_Mercado_Livre_Shopee.pdf'
out.parent.mkdir(parents=True, exist_ok=True)
sheet = openpyxl.load_workbook(source, data_only=True).active
groups = []
for row in sheet.iter_rows(values_only=True):
    if row[0] in ('MERCADO LIVRE', 'SHOPEE'):
        groups.append({'name': row[0], 'expected': int(row[2]), 'rows': []})
    elif groups and isinstance(row[0], (int, float)):
        groups[-1]['rows'].append([str(v) if v is not None else '' for v in row])
assert len(groups) == 2
assert sum(len(g['rows']) for g in groups) == 94
date = sheet['A2'].value.strftime('%d/%m/%Y')
time = str(sheet['A3'].value).split(': ', 1)[-1]
c = canvas.Canvas(str(out), pagesize=A4)
c.setTitle('Roteiro 19/10/2026 - Mercado Livre e Shopee')
w, h = A4
left, right = 30, w - 30
widths = [75, 130, right - left - 205]
for page, group in enumerate(groups, 1):
    assert len(group['rows']) == group['expected']
    c.setFillColor(colors.HexColor('#172B3A'))
    c.setFont('Helvetica-Bold', 18)
    c.drawString(left, h - 40, 'ROTEIRO')
    c.setFont('Helvetica', 10)
    c.drawRightString(right, h - 39, date + '  |  ' + time)
    c.setFont('Helvetica-Bold', 13)
    c.drawString(left, h - 66, group['name'])
    c.setFont('Helvetica-Bold', 10)
    c.drawRightString(right, h - 65, f"TOTAL DE PEDIDOS: {group['expected']}")
    top = h - 82
    header_h, row_h = 22, 12.3
    c.setFillColor(colors.HexColor('#172B3A'))
    c.rect(left, top - header_h, right - left, header_h, fill=1, stroke=0)
    x = left
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 9)
    for text, width in zip(['PEDIDO', 'NOTA FISCAL', 'VENDA NA LOJA VIRTUAL'], widths):
        c.drawCentredString(x + width / 2, top - 14, text)
        x += width
    y = top - header_h
    for index, row in enumerate(group['rows']):
        if index % 2 == 0:
            c.setFillColor(colors.HexColor('#F0F3F5'))
            c.rect(left, y - row_h, right - left, row_h, fill=1, stroke=0)
        c.setFillColor(colors.HexColor('#172B3A'))
        c.setFont('Helvetica', 9.5)
        x = left
        for text, width in zip(row, widths):
            assert c.stringWidth(text, 'Helvetica', 9.5) < width - 10
            c.drawCentredString(x + width / 2, y - 9.2, text)
            x += width
        y -= row_h
    assert y > 35
    c.setStrokeColor(colors.HexColor('#BCC7CD'))
    c.setLineWidth(0.4)
    c.rect(left, y, right-left, top-y, fill=0, stroke=1)
    c.setFillColor(colors.HexColor('#667780'))
    c.setFont('Helvetica', 8)
    c.drawRightString(right, 20, f'{page} / 2')
    c.showPage()
c.save()
pdf = PdfReader(out)
assert len(pdf.pages) == 2
for page, group in zip(pdf.pages, groups):
    text = page.extract_text()
    assert group['name'] in text
    other = 'SHOPEE' if group['name'] == 'MERCADO LIVRE' else 'MERCADO LIVRE'
    assert other not in text
    for row in group['rows']:
        assert row[1] in text and row[2] in text
subprocess.run(['pdftoppm', '-scale-to', '1200', '-png', str(out), str(root / 'tmp/pdfs/roteiro')], check=True)
print(str(out))
print('Validated: 2 pages; 55 Mercado Livre orders; 39 Shopee orders; all invoice and order identifiers preserved.')
