"""Dados do romaneio e preenchimento do modelo XLSX, usando apenas a biblioteca padrão.

O modelo é o arquivo de referência formatado pelo usuário. Este módulo preenche
seu XML com strings literais, preservando estilos, bordas, alturas e impressão.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import json
import io
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from bling import Cliente, ErroBling, consultar_notas


BASE = Path(__file__).resolve().parent
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)


def tag(nome):
    return f"{{{NS}}}{nome}"


def _serializar(raiz: ET.Element, fonte: bytes) -> bytes:
    """Preservar também os namespaces opcionais usados pelo Excel."""
    namespaces = dict(par for _, par in ET.iterparse(io.BytesIO(fonte), events=("start-ns",)))
    for prefixo, uri in namespaces.items():
        ET.register_namespace(prefixo, uri)
    usados = {nome.split("}", 1)[0][1:] for elemento in raiz.iter()
              for nome in [elemento.tag, *elemento.attrib] if nome.startswith("{")}
    ignorable = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable"
    for elemento in raiz.iter():
        for prefixo in elemento.get(ignorable, "").split():
            uri = namespaces.get(prefixo)
            if uri and uri not in usados:
                raiz.set("xmlns:" + prefixo, uri)
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=True)


@dataclass(frozen=True)
class Registro:
    id_nota: str
    numero: str
    pedido: str
    loja_id: str
    marketplace: str


def carregar_lojas(arquivo: Path) -> dict[str, str | None]:
    try:
        mapa = json.loads(arquivo.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ErroBling("Não foi possível ler lojas.json. Copie lojas.exemplo.json para lojas.json e preencha os IDs das suas lojas.") from None
    if not isinstance(mapa, dict) or any(
        not isinstance(k, str) or not k.isdigit()
        or (v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 40))
        for k, v in mapa.items()
    ):
        raise ErroBling("lojas.json deve relacionar cada ID numérico a um nome (até 40 caracteres) ou null para excluir.")
    return {k: v.strip() if v is not None else None for k, v in mapa.items()}


def _loja_excluida(nota: dict, lojas: dict[str, str | None]) -> bool:
    loja_id = str((nota.get("loja") or {}).get("id") or "0")
    return loja_id in lojas and lojas[loja_id] is None


def coletar_registros(cliente: Cliente, dia: date, lojas: dict[str, str | None], progresso=print) -> list[Registro]:
    notas = [n for n in consultar_notas(cliente, dia) if not _loja_excluida(n, lojas)]
    registros = []
    for posicao, nota in enumerate(notas, 1):
        if progresso:
            progresso(f"Consultando detalhes das notas: {posicao}/{len(notas)}", end="\r", flush=True)
        detalhe = cliente.get(f"/nfe/{nota['id']}", {}).get("data")
        if not isinstance(detalhe, dict) or str(detalhe.get("id")) != str(nota["id"]):
            raise ErroBling("O Bling retornou detalhes incompatíveis com a nota consultada.")
        if str(detalhe.get("situacao")) == "2":
            continue  # Cancelamento ocorrido depois da listagem inicial.
        if _loja_excluida(detalhe, lojas):
            continue  # A loja pode ter mudado depois da listagem inicial.
        if (str(detalhe.get("tipo")) != "1" or detalhe.get("situacao") is None
                or str(detalhe.get("dataEmissao", ""))[:10] != dia.isoformat()
                or not str(detalhe.get("numero", "")).strip()):
            raise ErroBling("Uma nota mudou durante a geração. Execute gerar novamente.")
        pedido = detalhe.get("numeroPedidoLoja")
        if pedido is None:
            pedido = ""
        if not isinstance(pedido, str):
            # Não converter floats que podem já ter perdido dígitos de identificadores.
            raise ErroBling("O Bling retornou um número de venda que não é texto. A geração foi interrompida.")
        loja = detalhe.get("loja") or {}
        loja_id = str(loja.get("id") or "0")
        grupo = lojas.get(loja_id, f"Loja {loja_id}" if loja_id != "0" else "Sem loja")
        registros.append(Registro(str(nota["id"]), str(detalhe["numero"]), pedido.strip(), loja_id, grupo))
    if progresso and notas:
        progresso()
    return registros


def agrupar(registros: list[Registro]) -> list[tuple[str, list[Registro]]]:
    grupos = defaultdict(list)
    for registro in registros:
        grupos[registro.marketplace].append(registro)
    prioridade = {"Mercado Livre": 0, "Shopee": 1}
    return [
        (nome, sorted(grupos[nome], key=lambda r: (r.numero.zfill(20), r.id_nota), reverse=True))
        for nome in sorted(grupos, key=lambda nome: (prioridade.get(nome, 2), nome.casefold()))
    ]


def _celula(endereco, valor, estilo=None, formula=None):
    atributos = {"r": endereco}
    if estilo is not None:
        atributos["s"] = estilo
    elemento = ET.Element(tag("c"), atributos)
    if formula is not None:
        if isinstance(valor, str):
            elemento.set("t", "str")
        ET.SubElement(elemento, tag("f")).text = formula
        ET.SubElement(elemento, tag("v")).text = str(valor)
    elif valor is None:
        pass  # Célula vazia com estilo: preserva também as bordas dos espaços.
    elif isinstance(valor, (int, float)):
        ET.SubElement(elemento, tag("v")).text = str(valor)
    else:
        texto = str(valor)
        if len(texto) > 32767 or any(ord(c) < 32 and c not in "\t\n\r" for c in texto):
            raise ErroBling("Um campo contém texto incompatível com o Excel.")
        elemento.set("t", "inlineStr")
        node = ET.SubElement(ET.SubElement(elemento, tag("is")), tag("t"))
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = texto
    return elemento


def _estilo_alerta(conteudo: bytes, estilo_base: str) -> tuple[bytes, str]:
    """Destacar pedidos ausentes sem perder as bordas do modelo."""
    raiz = ET.fromstring(conteudo)
    fills, fonts, xfs = (raiz.find(tag(nome)) for nome in ("fills", "fonts", "cellXfs"))
    base = deepcopy(xfs[int(estilo_base)])
    fill = ET.SubElement(fills, tag("fill"))
    pattern = ET.SubElement(fill, tag("patternFill"), {"patternType": "solid"})
    ET.SubElement(pattern, tag("fgColor"), {"rgb": "FFFFF1C2"})
    fonte = deepcopy(fonts[int(base.get("fontId", "0"))])
    cor = fonte.find(tag("color"))
    if cor is not None:
        fonte.remove(cor)
    ET.SubElement(fonte, tag("color"), {"rgb": "FF714400"})
    if fonte.find(tag("b")) is None:
        ET.SubElement(fonte, tag("b"))
    fonts.append(fonte)
    base.attrib.update({"fillId": str(len(fills) - 1), "fontId": str(len(fonts) - 1),
                        "applyFill": "1", "applyFont": "1"})
    xfs.append(base)
    for colecao in (fills, fonts, xfs):
        colecao.set("count", str(len(colecao)))
    return _serializar(raiz, conteudo), str(len(xfs) - 1)


def salvar_excel(registros: list[Registro], dia: date, gerado: datetime, destino: Path,
                 modelo: Path = BASE / "modelo_roteiro.xlsx") -> Path:
    if destino.exists():
        raise ErroBling("O arquivo de saída já existe. Escolha outro nome ou gere novamente sem --saida.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(modelo) as original:
        raiz = ET.fromstring(original.read("xl/worksheets/sheet1.xml"))
        dados = raiz.find(tag("sheetData"))
        exemplos = {c.get("r"): c for row in dados for c in row}
        estilos = {end: c.get("s") for end, c in exemplos.items()}
        linhas_modelo = {int(row.get("r")): dict(row.attrib) for row in dados}
        estilos_xml = original.read("xl/styles.xml")
        if any(not r.pedido for r in registros):
            estilos_xml, estilos["alerta"] = _estilo_alerta(estilos_xml, estilos["C7"])
        dados.clear()

        def linha(numero, valores, estilos_ref, *, formulas=None):
            referencia = int("".join(c for c in estilos_ref[0] if c.isdigit()))
            atributos = {**linhas_modelo[referencia], "r": str(numero)}
            row = ET.SubElement(dados, tag("row"), atributos)
            for col, valor, ref in zip("ABC", valores, estilos_ref):
                row.append(_celula(f"{col}{numero}", valor, estilos.get(ref),
                                   (formulas or {}).get(col)))

        linha(1, ["ROTEIRO", None, None], ["A1", "B1", "C1"])
        # Data e horário são valores de Excel; IDs e números fiscais são strings literais.
        serial_data = (dia - date(1899, 12, 30)).days
        linha(2, [serial_data, None, None], ["A2", "B2", "C2"])
        linha(3, [f"HORÁRIO: {gerado:%H:%M:%S}", None, None], ["A3", "B3", "C3"])
        linha(4, [None, None, None], ["A4", "B4", "C4"])
        proxima = 5
        totais = []
        grupos = agrupar(registros) or [("SEM NOTAS", [])]
        for posicao, (nome, itens) in enumerate(grupos):
            inicio = proxima + 2
            fim = inicio + max(len(itens), 1) - 1
            totais.append(f"C{proxima}")
            linha(proxima, [nome.upper(), "TOTAL:", len(itens)], ["A5", "B5", "C5"],
                  formulas={"C": f"COUNTA(B{inicio}:B{fim})"})
            linha(proxima + 1, ["PEDIDO", "NOTA FISCAL", "VENDA NA LOJA VIRTUAL"],
                  ["A6", "B6", "C6"])
            for i, item in enumerate(itens, 1):
                linha(inicio + i - 1, [i, item.numero, item.pedido or "NÃO INFORMADO"],
                      ["A7", "B7", "C7" if item.pedido else "alerta"])
            if not itens:
                linha(inicio, [None, None, None], ["A7", "B7", "C7"])
            if posicao < len(grupos) - 1:
                linha(fim + 1, [None, None, None], ["A4", "B4", "C4"])
            proxima = fim + 2
        ultima = proxima - 2
        cabecalho = dados.find(f"{tag('row')}[@r='2']")
        total = cabecalho.find(f"{tag('c')}[@r='B2']")
        cabecalho.remove(total)
        cabecalho.insert(1, _celula("B2", f"TOTAL DE PEDIDOS:{len(registros)}", estilos["B2"],
                                   '"TOTAL DE PEDIDOS:"&SUM(' + ",".join(totais) + ")"))
        dimension = raiz.find(tag("dimension"))
        if dimension is not None:
            dimension.set("ref", f"A1:C{ultima}")
        # Mesclagens, larguras, margens e configuração de impressão vêm do modelo.

        workbook = ET.fromstring(original.read("xl/workbook.xml"))
        nomes = workbook.find(tag("definedNames"))
        if nomes is None:
            nomes = ET.Element(tag("definedNames"))
            existente_calc = workbook.find(tag("calcPr"))
            workbook.insert(list(workbook).index(existente_calc) if existente_calc is not None else len(workbook), nomes)
        for nome in list(nomes):
            if nome.get("name") in {"_xlnm.Print_Area", "_xlnm.Print_Titles"}:
                nomes.remove(nome)
        ET.SubElement(nomes, tag("definedName"), {"name": "_xlnm.Print_Area", "localSheetId": "0"}).text = f"'Roteiro'!$A$1:$C${ultima}"
        ET.SubElement(nomes, tag("definedName"), {"name": "_xlnm.Print_Titles", "localSheetId": "0"}).text = "'Roteiro'!$1:$3"
        calc = workbook.find(tag("calcPr"))
        if calc is None:
            calc = ET.SubElement(workbook, tag("calcPr"))
        calc.attrib.update({"fullCalcOnLoad": "1", "forceFullCalc": "1"})

        substituicoes = {
            "xl/worksheets/sheet1.xml": _serializar(raiz, original.read("xl/worksheets/sheet1.xml")),
            "xl/workbook.xml": _serializar(workbook, original.read("xl/workbook.xml")),
            "xl/styles.xml": estilos_xml,
        }
        # As células novas usam strings literais. Não carregar valores históricos
        # não utilizados, nem uma cadeia de cálculo com posições do exemplo antigo.
        if "xl/sharedStrings.xml" in original.namelist():
            sst = ET.Element(tag("sst"), {"count": "0", "uniqueCount": "0"})
            substituicoes["xl/sharedStrings.xml"] = _serializar(sst, original.read("xl/sharedStrings.xml"))
        if "xl/calcChain.xml" in original.namelist():
            for parte, atributo, valor in (
                ("xl/_rels/workbook.xml.rels", "Type", "/calcChain"),
                ("[Content_Types].xml", "PartName", "/xl/calcChain.xml"),
            ):
                fonte = original.read(parte)
                arvore = ET.fromstring(fonte)
                for elemento in list(arvore):
                    if elemento.get(atributo, "").endswith(valor):
                        arvore.remove(elemento)
                substituicoes[parte] = _serializar(arvore, fonte)
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=destino.parent, suffix=".xlsx", delete=False) as tmp:
                temporario = Path(tmp.name)
            with ZipFile(temporario, "w", compression=ZIP_DEFLATED) as saida:
                for item in original.infolist():
                    if item.filename == "xl/calcChain.xml":
                        continue
                    saida.writestr(item, substituicoes.get(item.filename, original.read(item.filename)))
            temporario.rename(destino)
        finally:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
    return destino


def gerar(cliente: Cliente, dia: date, destino: Path | None = None, lojas_arquivo: Path = BASE / "lojas.json") -> Path:
    lojas = carregar_lojas(lojas_arquivo)
    registros = coletar_registros(cliente, dia, lojas)
    gerado = datetime.now()
    destino = destino or BASE / "outputs" / f"ROTEIRO_{dia.isoformat()}_{gerado:%H%M%S_%f}.xlsx"
    arquivo = salvar_excel(registros, dia, gerado, destino.resolve())
    print(f"\nRoteiro gerado: {arquivo}")
    print(f"Total: {len(registros)} notas.")
    for grupo, quantidade in Counter(r.marketplace for r in registros).items():
        print(f"  {grupo}: {quantidade}")
    faltantes = [r.numero for r in registros if not r.pedido]
    if faltantes:
        print("ATENÇÃO: número da venda não informado nas notas: " + ", ".join(faltantes))
    desconhecidas = sorted({r.loja_id for r in registros if r.loja_id not in lojas})
    if desconhecidas:
        print("Confira o nome destas lojas em lojas.json: " + ", ".join(desconhecidas))
    return arquivo
