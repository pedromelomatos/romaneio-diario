"""Dois comandos para uso diário: configurar uma vez e gerar o roteiro de hoje."""

import argparse
from datetime import date, datetime
import logging
from pathlib import Path
import tempfile

import app
import bling
import roteiro


BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent if BASE.name == "programa" else BASE


def preparar_pastas() -> None:
    for nome in ("roteiros", "logs"):
        pasta = RAIZ / nome
        pasta.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=pasta):
            pass


def configurar(cofre: bling.Cofre, config: dict) -> None:
    print("CONFIGURAÇÃO INICIAL\n")
    bling.conectar(cofre, config)
    if not (BASE / "lojas.json").is_file():
        print("\nIdentifique as lojas uma única vez.")
        app.configurar_lojas(bling.Cliente(cofre, cofre.ler()), date.today(), BASE / "lojas.json")
    print("\nTudo pronto! Para gerar o roteiro de hoje, abra 2_GERAR_ROTEIRO.cmd.")


def executar(acao: str) -> Path | None:
    with bling.sessao_local() as (cofre, config):
        if acao == "configurar":
            configurar(cofre, config)
            return None
        if not config.get("tokens", {}).get("refresh_token"):
            print("Este é o primeiro uso. Vamos autorizar o acesso ao Bling.\n")
            configurar(cofre, config)
            config = cofre.ler()
        if not (BASE / "lojas.json").is_file():
            raise bling.ErroBling("Finalize a configuração pelo 1_CONFIGURAR.cmd antes de gerar.")
        agora = datetime.now()
        destino = RAIZ / "roteiros" / f"ROTEIRO_{agora:%d_%m_%Y_%H%M%S_%f}.xlsx"
        print(f"\nGerando roteiro de hoje ({date.today():%d/%m/%Y}). Aguarde...")
        arquivo = roteiro.gerar(bling.Cliente(cofre, config), date.today(), destino, BASE / "lojas.json")
    print("\nConcluído! O arquivo está na pasta roteiros, ao lado dos atalhos.")
    return arquivo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=("configurar", "gerar"), nargs="?", default="gerar")
    parser.add_argument("--diagnostico", action="store_true")
    args = parser.parse_args()
    if args.diagnostico:
        import ssl
        ssl.create_default_context()
        if not (BASE / "modelo_roteiro.xlsx").is_file():
            print("Modelo ausente. Extraia o ZIP completo novamente.")
            return 1
        bling.carregar_aplicacao()
        print("Pacote pronto para configurar e gerar roteiros.")
        return 0
    handler = None
    logger = logging.getLogger("romaneio.portatil")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        preparar_pastas()
        log = RAIZ / "logs" / "execucao.log"
        # Um único arquivo de log, sem pilhas de arquivos antigos.
        handler = logging.FileHandler(log, mode="w" if log.exists() and log.stat().st_size > 1_000_000 else "a",
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.info("Início: %s", args.acao)
        arquivo = executar(args.acao)
        logger.info("Concluído: %s", arquivo.name if arquivo else "configuração inicial")
        return 0
    except (bling.ErroBling, OSError) as exc:
        mensagem = str(exc) if isinstance(exc, bling.ErroBling) else (
            "Não foi possível acessar os arquivos. Extraia o ZIP completo para Documentos e tente novamente.")
        print("\n" + mensagem)
        if handler:
            logger.error("%s", mensagem)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nOperação interrompida. Você pode abrir o atalho novamente.")
        if handler:
            logger.info("Operação interrompida pelo usuário.")
        return 1
    finally:
        if handler:
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
