"""Criar um ZIP independente de Python instalado, com uma lista explícita de arquivos."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile, ZIP_DEFLATED


BASE = Path(__file__).resolve().parents[1]
VERSAO = "3.13.16"
URL = "https://www.python.org/ftp/python/3.13.16/python-3.13.16-embeddable-win32.zip"
SHA256 = "9d6e5a436f8d417f70387b22e49b56f46dd6328423f8e759cee74c427aa1b6fc"
ARQUIVOS = (
    "app.py", "bling.py", "roteiro.py", "portatil.py", "modelo_roteiro.xlsx",
)


def verificar_zip_seguro(arquivo: ZipFile) -> None:
    for item in arquivo.infolist():
        caminho = PurePosixPath(item.filename.replace("\\", "/"))
        if caminho.is_absolute() or ".." in caminho.parts or ":" in str(caminho):
            raise RuntimeError("O runtime contém um caminho inválido.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--com-credenciais", action="store_true",
                        help="Incluir Client ID e Secret de tokens.json; nunca incluir tokens de acesso.")
    args = parser.parse_args()
    credenciais = None
    lojas = None
    if args.com_credenciais:
        sys.path.insert(0, str(BASE))
        import bling
        credenciais = bling.carregar_aplicacao(BASE / "tokens.json")
        if not credenciais:
            raise RuntimeError("Crie tokens.json com as credenciais do aplicativo antes de empacotar.")
        # Pacote interno da empresa: preservar nomes de lojas e exclusões já conferidos.
        if (BASE / "lojas.json").is_file():
            import roteiro
            lojas = roteiro.carregar_lojas(BASE / "lojas.json")
    build = BASE / ".build"
    downloads = build / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    download = downloads / f"python-{VERSAO}-win32.zip"
    if not download.exists():
        temporario = download.with_suffix(".download")
        with urlopen(URL, timeout=60) as entrada, temporario.open("wb") as saida:
            shutil.copyfileobj(entrada, saida)
        temporario.replace(download)
    digest = hashlib.sha256(download.read_bytes()).hexdigest()
    if digest != SHA256:
        raise RuntimeError("O SHA256 do Python não corresponde ao manifesto oficial. Pacote não criado.")

    # Pasta nova a cada build: não apaga nem incorpora arquivos de uma execução anterior.
    trabalho = Path(tempfile.mkdtemp(prefix="portatil_", dir=build)).resolve()
    if not trabalho.is_relative_to(build.resolve()):
        raise RuntimeError("Pasta de preparação fora do projeto.")
    raiz = trabalho / "RomaneioDiario"
    programa = raiz / "programa"
    runtime = programa / "_runtime"
    runtime.mkdir(parents=True)
    with ZipFile(download) as oficial:
        verificar_zip_seguro(oficial)
        oficial.extractall(runtime)
    # O programa e suas dependências pertencem somente ao pacote, sem site-packages
    # globais, variáveis PYTHONPATH, instalações do Windows ou caminhos do autor.
    arquivos_pth = list(runtime.glob("python*._pth"))
    if len(arquivos_pth) != 1:
        raise RuntimeError("Configuração inesperada no Python embutível.")
    arquivos_pth[0].write_text("python313.zip\n.\n..\n", encoding="ascii")
    for nome in ARQUIVOS:
        shutil.copy2(BASE / nome, programa / nome)
    (raiz / "LEIA-ME.txt").write_bytes((BASE / "LEIA-ME.txt").read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8-sig"))
    for nome, acao in (("1_CONFIGURAR.cmd", "configurar"), ("2_GERAR_ROTEIRO.cmd", "gerar")):
        atalho = f'''@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0programa\\_runtime\\python.exe" (
    echo Extraia a pasta inteira do ZIP antes de abrir este atalho.
    pause
    exit /b 1
)
"%~dp0programa\\_runtime\\python.exe" -X utf8 "%~dp0programa\\portatil.py" {acao} %*
set "resultado=%errorlevel%"
echo.
pause
exit /b %resultado%
'''
        (raiz / nome).write_bytes(atalho.replace("\n", "\r\n").encode("utf-8"))
    for nome in ("roteiros", "logs"):
        (raiz / nome).mkdir()
    componentes = f"Python {VERSAO}, Windows x86, distribuicao embutivel oficial.\nOrigem: {URL}\nSHA256: {SHA256}\nLicenca: _runtime/LICENSE.txt\n\nDocumentacao: https://docs.python.org/3/using/windows.html#the-embeddable-package\n"
    (programa / "COMPONENTES.txt").write_text(componentes, encoding="utf-8")
    if credenciais:
        # Só estes três campos saem do ambiente de desenvolvimento. Nunca distribuir
        # access_token, refresh_token, acesso.dat ou autorizações de outra máquina.
        (programa / "tokens.json").write_text(json.dumps(credenciais, indent=2) + "\n", encoding="utf-8")
    if lojas is not None:
        (programa / "lojas.json").write_text(json.dumps(lojas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Testar o Python fornecido com o ZIP. Não consulta a conta real nem agenda tarefas.
    resultado = subprocess.run([str(runtime / "python.exe"), "-X", "utf8", str(programa / "portatil.py"), "--diagnostico"],
                               cwd=trabalho, capture_output=True, text=True, encoding="utf-8", timeout=30)
    if resultado.returncode:
        raise RuntimeError("O ambiente portátil não passou na verificação: " + resultado.stderr[:1000])

    saidas = BASE / "outputs" / "distribuicao"
    saidas.mkdir(parents=True, exist_ok=True)
    nome = "RomaneioDiario_Portatil_Windows"
    if credenciais:
        nome += "_Configurado"
    destino_zip = saidas / (nome + ".zip")
    with ZipFile(destino_zip, "w", ZIP_DEFLATED, compresslevel=9) as pacote:
        for arquivo in sorted(raiz.rglob("*")):
            if arquivo.is_file() and "__pycache__" not in arquivo.parts:
                pacote.write(arquivo, arquivo.relative_to(trabalho).as_posix())
        for nome in ("roteiros", "logs"):
            pacote.writestr(f"RomaneioDiario/{nome}/", "")
    relatorio = {"zip": str(destino_zip), "bytes": destino_zip.stat().st_size,
                 "runtime_sha256": digest, "pasta_teste": str(raiz), "diagnostico": resultado.stdout.strip(),
                 "zip_sha256": hashlib.sha256(destino_zip.read_bytes()).hexdigest()}
    (saidas / ("verificacao_configurado.json" if credenciais else "verificacao.json")).write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(relatorio, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
