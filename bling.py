"""Conexão local e conferência de notas do Bling. Python 3.10+, Windows."""

from __future__ import annotations

import argparse
import base64
import ctypes
from contextlib import contextmanager
from datetime import date, datetime
import getpass
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser


API = "https://api.bling.com.br/Api/v3"
AUTHORIZE = "https://www.bling.com.br/Api/v3/oauth/authorize"
CALLBACK = "http://localhost:8765/callback"
SITUACAO_EMITIDA_DANFE = 6
SITUACAO_AUTORIZADA = 5  # Situação de aprovação da NF-e na API do Bling.
SITUACOES_ROTEIRO = frozenset({str(SITUACAO_AUTORIZADA), str(SITUACAO_EMITIDA_DANFE)})


class ErroBling(Exception):
    """Mensagem que pode ser exibida sem expor credenciais ou dados da API."""


class ErroHTTP(ErroBling):
    def __init__(self, status: int, limite_diario: bool = False):
        self.status = status
        self.limite_diario = limite_diario
        mensagem = {
            400: "O Bling recusou os parâmetros ou a autorização. Confira o cadastro do aplicativo.",
            401: "O acesso foi recusado. Execute novamente a opção conectar.",
            403: "Permissão insuficiente. Confira os escopos Notas Fiscais e Pedidos de Venda.",
            429: "Limite de consultas do Bling atingido. Tente novamente mais tarde.",
        }.get(status, f"O Bling retornou HTTP {status}. A operação não foi concluída.")
        super().__init__(mensagem)


def requisicao(method: str, url: str, headers: dict, campos: dict | None = None) -> dict:
    dados = urlencode(campos).encode() if campos is not None else None
    request = Request(url, data=dados, headers={"Accept": "application/json", **headers}, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            resultado = json.load(response)
    except HTTPError as exc:
        diario = False
        if exc.code == 429:
            try:
                diario = '"day"' in exc.read(65536).decode("utf-8")
            except (OSError, UnicodeError):
                pass
        raise ErroHTTP(exc.code, diario) from None
    except (URLError, TimeoutError, OSError):
        raise ErroBling("Falha de conexão com o Bling. Verifique a internet e tente novamente.") from None
    except (ValueError, UnicodeError):
        raise ErroBling("O Bling não retornou um JSON válido. Tente novamente mais tarde.") from None
    if not isinstance(resultado, dict):
        raise ErroBling("Resposta inesperada do Bling.")
    return resultado


def proteger(dados: bytes, *, abrir: bool = False) -> bytes:
    """DPAPI: o arquivo de acesso só pode ser aberto pelo mesmo usuário Windows."""
    if os.name != "nt":
        raise ErroBling("Esta versão do assistente utiliza a proteção de credenciais do Windows.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(dados)).from_buffer_copy(dados)
    entrada, saida = Blob(len(dados), buffer), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    operation = crypt.CryptUnprotectData if abrir else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
    operation.restype = ctypes.c_int
    if not operation(ctypes.byref(entrada), None, None, None, None, 1, ctypes.byref(saida)):
        raise ErroBling("Não foi possível acessar as credenciais protegidas deste usuário Windows.")
    try:
        return ctypes.string_at(saida.data, saida.size)
    finally:
        kernel.LocalFree(ctypes.cast(saida.data, ctypes.c_void_p))


class Cofre:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        self.arquivo = pasta / "acesso.dat"

    def ler(self) -> dict:
        if not self.arquivo.exists():
            return {}
        try:
            return json.loads(proteger(self.arquivo.read_bytes(), abrir=True))
        except (ValueError, OSError):
            raise ErroBling("Não foi possível ler a configuração local. Execute conectar novamente.") from None

    def salvar(self, dados: dict) -> None:
        conteudo = proteger(json.dumps(dados).encode("utf-8"))
        self.pasta.mkdir(parents=True, exist_ok=True)
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.pasta, delete=False) as arquivo:
                temporario = Path(arquivo.name)
                arquivo.write(conteudo)
            os.replace(temporario, self.arquivo)
        finally:
            if temporario is not None:
                temporario.unlink(missing_ok=True)


def validar_callback(url: str):
    partes = urlsplit(url)
    try:
        porta = partes.port
    except ValueError:
        porta = None
    if (partes.scheme != "http" or partes.hostname not in {"localhost", "127.0.0.1"}
            or porta is None or not partes.path or partes.username or partes.password
            or partes.query or partes.fragment):
        raise ErroBling("Use um retorno HTTP local com porta e caminho, como " + CALLBACK)
    return partes


def interpretar_callback(caminho: str, esperado: str, estado: str) -> tuple[str, str]:
    partes = urlsplit(caminho)
    if partes.path != esperado:
        return "ignorar", ""
    params = parse_qs(partes.query)
    states = params.get("state", [])
    if len(states) != 1 or not secrets.compare_digest(states[0], estado):
        return "ignorar", ""
    if "error" in params:
        return "erro", "A autorização foi recusada ou interrompida no Bling."
    codes = params.get("code", [])
    if len(codes) != 1 or not codes[0]:
        return "ignorar", ""
    return "codigo", codes[0]


class Cliente:
    def __init__(self, cofre: Cofre, config: dict):
        self.cofre, self.config = cofre, config
        self.ultima_consulta = 0.0

    def token(self, campos: dict) -> None:
        basic = base64.b64encode(
            f"{self.config['client_id']}:{self.config['client_secret']}".encode()
        ).decode("ascii")
        # Não repetir automaticamente: o code é de uso único e o refresh token pode ser rotacionado.
        retorno = requisicao("POST", API + "/oauth/token", {
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
        }, campos)
        if not retorno.get("access_token") or not retorno.get("refresh_token"):
            raise ErroBling("O Bling não retornou os tokens esperados. Execute conectar novamente.")
        try:
            validade = int(retorno["expires_in"])
            if validade <= 0:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ErroBling("O Bling não informou a validade do acesso. Execute conectar novamente.") from None
        self.config["tokens"] = {
            "access_token": retorno["access_token"],
            "refresh_token": retorno["refresh_token"],
            "expires_at": time.time() + validade,
        }
        self.cofre.salvar(self.config)

    def renovar(self) -> None:
        refresh = self.config.get("tokens", {}).get("refresh_token")
        if not refresh:
            raise ErroBling("O computador ainda não foi autorizado. Execute conectar.")
        self.token({"grant_type": "refresh_token", "refresh_token": refresh})

    def get(self, caminho: str, parametros: dict) -> dict:
        tokens = self.config.get("tokens", {})
        if not tokens.get("access_token") or time.time() >= tokens.get("expires_at", 0) - 60:
            self.renovar()
        renovado = False
        for tentativa in range(5):
            # Menos de três chamadas por segundo; o limite do Bling é compartilhado pela conta.
            time.sleep(max(0, self.ultima_consulta + 0.4 - time.monotonic()))
            self.ultima_consulta = time.monotonic()
            try:
                return requisicao("GET", API + caminho + "?" + urlencode(parametros), {
                    "Authorization": "Bearer " + self.config["tokens"]["access_token"],
                })
            except ErroHTTP as exc:
                if exc.status == 401 and not renovado:
                    self.renovar()
                    renovado = True
                elif ((exc.status == 429 and not exc.limite_diario) or exc.status in {500, 502, 503, 504}) and tentativa < 4:
                    time.sleep(2 ** tentativa)
                else:
                    raise
        raise ErroBling("Não foi possível concluir a consulta após as tentativas.")


def autorizar(cliente: Cliente, *, segundos: float = 300) -> None:
    partes = validar_callback(cliente.config["redirect_uri"])
    estado = secrets.token_urlsafe(32)
    resultado: dict[str, str] = {}

    class Retorno(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # O callback contém o código de acesso: nunca registrar a URL.

        def do_GET(self):
            tipo, valor = interpretar_callback(self.path, partes.path, estado)
            if tipo == "ignorar":
                self.send_error(400, "Retorno invalido")
                return
            resultado[tipo] = valor
            mensagem = "Retorno recebido. Volte ao programa para verificar o resultado."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(mensagem.encode("utf-8"))

    try:
        servidor = HTTPServer(("127.0.0.1", partes.port), Retorno)
    except OSError:
        raise ErroBling(f"Não foi possível abrir a porta {partes.port}. Feche outra execução do programa.") from None
    with servidor:
        servidor.timeout = 0.5
        url = AUTHORIZE + "?" + urlencode({
            "response_type": "code", "client_id": cliente.config["client_id"], "state": estado,
        })
        print("Autorize o aplicativo na página do Bling que será aberta no navegador.")
        if not webbrowser.open(url):
            raise ErroBling("Não foi possível abrir o navegador padrão. Configure-o e tente novamente.")
        prazo = time.monotonic() + segundos
        while not resultado and time.monotonic() < prazo:
            servidor.handle_request()
        if "erro" in resultado:
            raise ErroBling(resultado["erro"])
        if "codigo" not in resultado:
            raise ErroBling("Tempo de autorização encerrado. Execute conectar para tentar novamente.")
        cliente.token({"grant_type": "authorization_code", "code": resultado["codigo"]})
    print("Conexão autorizada. O acesso foi salvo com proteção do usuário Windows.")


def consultar_notas(cliente: Cliente, dia: date) -> list[dict]:
    notas = {}
    pagina = 1
    while True:
        resposta = cliente.get("/nfe", {
            "tipo": 1, "dataEmissaoInicial": f"{dia.isoformat()} 00:00:00",
            "dataEmissaoFinal": f"{dia.isoformat()} 23:59:59", "pagina": pagina, "limite": 100,
            # Consultar todas as situações e selecionar as aceitas abaixo: a API
            # aceita somente uma situação por chamada.
        })
        registros = resposta.get("data")
        if not isinstance(registros, list):
            raise ErroBling("A lista de notas retornada pelo Bling não possui o formato esperado.")
        if not registros:
            break
        novos = 0
        for nota in registros:
            if not isinstance(nota, dict) or not nota.get("id"):
                raise ErroBling("Foi retornada uma nota sem identificador. A conferência foi interrompida.")
            identificador = str(nota["id"])
            if identificador in notas:
                if notas[identificador] != nota:
                    raise ErroBling("As notas mudaram durante a consulta. Execute conferir novamente.")
                continue
            notas[identificador] = nota
            novos += 1
        if not novos:
            raise ErroBling("O Bling repetiu uma página de notas. A conferência foi interrompida.")
        pagina += 1
    selecionadas = []
    for nota in notas.values():
        if nota.get("situacao") is None:
            raise ErroBling("Não foi possível confirmar a situação de uma nota. A conferência foi interrompida.")
        if str(nota["situacao"]) not in SITUACOES_ROTEIRO:
            continue
        if (str(nota.get("tipo")) != "1" or str(nota.get("dataEmissao", ""))[:10] != dia.isoformat()
                or nota.get("numero") is None):
            raise ErroBling("Uma nota não corresponde aos filtros esperados. Confira os dados antes de continuar.")
        selecionadas.append(nota)
    return sorted(selecionadas, key=lambda n: (str(n["numero"]).zfill(20), str(n["id"])), reverse=True)


def credenciais_aplicacao(dados: dict) -> dict:
    """Selecionar apenas o cadastro do app, nunca copiar tokens de uma conexão."""
    if not isinstance(dados, dict):
        raise ErroBling("Configuração do aplicativo inválida no tokens.json.")
    novo = {}
    for campo in ("client_id", "client_secret", "redirect_uri"):
        valor = dados.get(campo, CALLBACK if campo == "redirect_uri" else None)
        if not isinstance(valor, str) or not valor.strip():
            raise ErroBling(f"Preencha o campo {campo} no tokens.json.")
        novo[campo] = valor.strip()
    validar_callback(novo["redirect_uri"])
    return novo


def carregar_aplicacao(arquivo: Path | None = None) -> dict:
    arquivo = arquivo if arquivo is not None else Path(__file__).resolve().parent / "tokens.json"
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError, OSError):
        raise ErroBling("Não foi possível ler tokens.json. Confira o arquivo do aplicativo.") from None
    return credenciais_aplicacao(dados)


def conectar(cofre: Cofre, config: dict) -> None:
    novo = carregar_aplicacao()
    if novo:
        print("Aplicativo configurado pelo tokens.json. Basta autorizar no navegador.")
    elif config.get("client_id") and config.get("client_secret"):
        novo = credenciais_aplicacao(config)
        print("Usando o aplicativo já configurado neste usuário Windows.")
    else:
        print("No Bling, abra o aplicativo e localize Client ID e Client Secret.")
        print("Digite as credenciais aqui. O Client Secret não aparecerá durante a digitação.")
        client_id = input("Client ID: ").strip()
        client_secret = getpass.getpass("Client Secret: ").strip()
        if not client_id or not client_secret:
            raise ErroBling("Preencha o Client ID e o Client Secret.")
        retorno = input(f"Link de redirecionamento [{CALLBACK}]: ").strip() or CALLBACK
        novo = credenciais_aplicacao({"client_id": client_id, "client_secret": client_secret,
                                      "redirect_uri": retorno})
    # Preservar o acesso anterior até uma nova autorização ser concluída com sucesso.
    autorizar(Cliente(cofre, novo))


def data_argumento(valor: str) -> date:
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("Informe a data como DD/MM/AAAA ou AAAA-MM-DD.")


@contextmanager
def sessao_local():
    """Uma única operação por usuário Windows, inclusive no menu portátil."""
    raiz = os.environ.get("LOCALAPPDATA")
    if not raiz or os.name != "nt":
        raise ErroBling("Execute este assistente em uma conta de usuário do Windows.")
    cofre = Cofre(Path(raiz) / "RomaneioDiario")
    cofre.pasta.mkdir(parents=True, exist_ok=True)
    import msvcrt
    with (cofre.pasta / "execucao.lock").open("a+b") as trava:
        if trava.seek(0, 2) == 0:
            trava.write(b"0")
            trava.flush()
        trava.seek(0)
        try:
            msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise ErroBling("Outra execução está usando a conexão do Bling. Aguarde a conclusão.") from None
        try:
            yield cofre, cofre.ler()
        finally:
            trava.seek(0)
            msvcrt.locking(trava.fileno(), msvcrt.LK_UNLCK, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Conexão e conferência de notas de saída do Bling.")
    parser.add_argument("acao", choices=("conectar", "conferir", "gerar"))
    parser.add_argument("--data", type=data_argumento, help="Data de emissão; padrão: hoje no computador.")
    parser.add_argument("--saida", type=Path, help="Caminho do novo Excel (somente para gerar).")
    args = parser.parse_args()
    try:
        with sessao_local() as (cofre, config):
            if args.acao == "conectar":
                conectar(cofre, config)
            else:
                if not config:
                    raise ErroBling("Execute conectar antes da primeira conferência.")
                dia = args.data or date.today()
                if args.acao == "gerar":
                    from roteiro import gerar
                    gerar(Cliente(cofre, config), dia, args.saida)
                else:
                    notas = consultar_notas(Cliente(cofre, config), dia)
                    print(f"Notas de saída de {dia:%d/%m/%Y}, situações Emitida DANFE ou Autorizada (Aprovado): {len(notas)}")
                    for nota in notas:
                        print(f"  NF {nota['numero']}")
                    print("Conferência concluída.")
        return 0
    except (ErroBling, OSError) as exc:
        print(f"Erro: {exc}" if isinstance(exc, ErroBling) else "Erro ao acessar os arquivos locais. Verifique as permissões.")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nOperação interrompida.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
