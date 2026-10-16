"""Menu para o pacote Windows portátil; não requer pacotes adicionais."""

from collections import defaultdict
from argparse import ArgumentTypeError
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import bling
import roteiro


BASE = Path(__file__).resolve().parent


def pedir_data() -> date:
    while True:
        valor = input(f"Data das notas [Enter = hoje, {date.today():%d/%m/%Y}]: ").strip()
        if not valor:
            return date.today()
        try:
            return bling.data_argumento(valor)
        except ArgumentTypeError:
            print("Data inválida. Digite como 15/10/2026.")


def escolher_nome(atual: str | None, *, existente: bool) -> tuple[bool, str | None]:
    """Retornar (alterar, valor), distinguindo exclusão de manter a escolha."""
    while True:
        if existente:
            print("Atual: " + (atual if atual is not None else "Não incluir nos roteiros"))
        print("  1 Mercado Livre  |  2 Shopee  |  3 Outro nome  |  4 Não incluir")
        escolha = input("Escolha [Enter = manter]: ").strip()
        if not escolha:
            return False, atual
        if escolha in {"1", "2", "4"}:
            return True, {"1": "Mercado Livre", "2": "Shopee", "4": None}[escolha]
        if escolha == "3":
            nome = input("Nome da loja ou marketplace: ").strip()
            if nome and len(nome) <= 40:
                return True, nome
            print("Digite um nome com até 40 caracteres.")


def salvar_lojas(arquivo: Path, mapa: dict) -> None:
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(dir=arquivo.parent, suffix=".tmp", delete=False, mode="w", encoding="utf-8") as tmp:
            temporario = Path(tmp.name)
            json.dump(mapa, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
        os.replace(temporario, arquivo)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def configurar_lojas(cliente: bling.Cliente, dia: date, arquivo: Path = BASE / "lojas.json") -> None:
    mapa = roteiro.carregar_lojas(arquivo) if arquivo.exists() else {}
    notas = bling.consultar_notas(cliente, dia)
    lojas = defaultdict(list)
    for nota in notas:
        identificador = str((nota.get("loja") or {}).get("id") or "0")
        lojas[identificador].append(str(nota["numero"]))
    if not lojas:
        print("Não há notas nessa data para identificar as lojas. Você pode tentar outra data.")
    for identificador, numeros in sorted(lojas.items()):
        print(f"\nLoja {identificador}: {len(numeros)} notas. Exemplo: NF {numeros[0]}.")
        alterar, nome = escolher_nome(mapa.get(identificador), existente=identificador in mapa)
        if alterar:
            mapa[identificador] = nome
        elif identificador not in mapa:
            mapa[identificador] = f"Loja {identificador}" if identificador != "0" else "Sem loja"
    salvar_lojas(arquivo, mapa)
    print("\nConfiguração das lojas salva neste computador.")


def abrir_pasta():
    pasta = BASE / "outputs"
    pasta.mkdir(exist_ok=True)
    os.startfile(str(pasta))


def executar_acao(acao: str) -> None:
    if acao == "5":
        abrir_pasta()
        return
    if acao == "6":
        with bling.sessao_local() as (_cofre, config):
            if not config:
                raise bling.ErroBling("Conecte ao Bling pela opção 1 antes de agendar.")
        if not (BASE / "lojas.json").is_file():
            raise bling.ErroBling("Configure as lojas pela opção 2 antes de agendar.")
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        resultado = subprocess.run([str(shell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BASE / "agendar_roteiro.ps1")])
        if resultado.returncode:
            print("O agendamento não foi criado. Consulte a mensagem acima.")
        return
    dia = pedir_data() if acao in {"2", "4", "7"} else date.today()
    with bling.sessao_local() as (cofre, config):
        if acao == "1":
            bling.conectar(cofre, config)
            print("Depois da conexão, escolha a opção 2 para identificar as lojas.")
            return
        if not config:
            raise bling.ErroBling("Conecte ao Bling pela opção 1 antes de continuar.")
        cliente = bling.Cliente(cofre, config)
        if acao == "2":
            configurar_lojas(cliente, dia)
        elif acao in {"3", "4"}:
            if not (BASE / "lojas.json").exists():
                print("\nVamos identificar as lojas antes do primeiro roteiro.")
                configurar_lojas(cliente, dia)
            roteiro.gerar(cliente, dia)
            print("\nO arquivo está na pasta de resultados (opção 5 do menu).")
        elif acao == "7":
            notas = bling.consultar_notas(cliente, dia)
            print(f"Notas de saída de {dia:%d/%m/%Y}, situação Emitida DANFE: {len(notas)}")
            print("Esta conferência mostra todas as lojas, inclusive as excluídas do roteiro.")


def main() -> int:
    if "--diagnostico" in sys.argv:
        import ssl
        ssl.create_default_context()
        if not (BASE / "modelo_roteiro.xlsx").is_file():
            print("Modelo ausente. Extraia novamente o ZIP completo.")
            return 1
        print("Ambiente portátil pronto.")
        return 0
    try:
        # Verificar a pasta escolhida antes de iniciar a configuração da conta.
        pasta = BASE / "outputs"
        pasta.mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=pasta):
            pass
    except OSError:
        print("Extraia a pasta completa do ZIP para Documentos ou para a Área de Trabalho e tente novamente.")
        return 1
    while True:
        print("\nROMANEIO DIÁRIO\n")
        print("1  Conectar ao Bling")
        print("2  Configurar lojas e exclusões")
        print("3  Gerar roteiro de hoje")
        print("4  Gerar roteiro de outra data")
        print("5  Abrir pasta dos roteiros")
        print("6  Agendar todos os dias às 13h")
        print("7  Conferir quantidade de notas no Bling")
        print("0  Sair\n")
        try:
            escolha = input("Escolha uma opção: ").strip()
            if escolha == "0":
                return 0
            if escolha not in {str(i) for i in range(1, 8)}:
                print("Escolha uma opção de 0 a 7.")
                continue
            executar_acao(escolha)
        except (bling.ErroBling, OSError) as exc:
            print(f"\n{exc}" if isinstance(exc, bling.ErroBling) else "Não foi possível acessar um arquivo ou programa. Confira se o ZIP foi extraído por completo.")
        except (EOFError, KeyboardInterrupt):
            print("\nOperação interrompida.")
            return 0
        try:
            input("\nPressione Enter para voltar ao menu...")
        except (EOFError, KeyboardInterrupt):
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
