# Romaneio diário

Automação do roteiro dos motoristas da distribuidora com a API v3 do Bling.

## Funcionalidades

Conexão OAuth e conferência das notas fiscais de saída por data de emissão,
de todas as lojas, excluindo canceladas. Geração de Excel com sequência,
número da nota e número da venda, agrupados por marketplace, com totais.
As notas e os pedidos não são alterados no Bling.

## Conectar pela primeira vez

Requisitos: Windows e Python 3.10 ou superior. Não é necessário instalar pacotes.
Os atalhos também aproveitam o Python incluído no Codex quando disponível.
O relógio e o fuso do computador devem estar corretos; a data padrão é a data local.

1. No cadastro do aplicativo Bling, confira:
   - Visibilidade: **Privado**.
   - Link de redirecionamento: `http://localhost:8765/callback`.
   - Escopos: **Notas Fiscais** e **Pedidos de Venda**, para visualização.
2. Abra as informações do aplicativo e localize **Client ID** e **Client Secret**.
3. Dê dois cliques em `conectar_bling.cmd`.
4. Digite o Client ID e o Client Secret na janela local. O secret fica oculto.
5. Pressione Enter para confirmar o endereço de retorno cadastrado.
6. No navegador, confira a conta e autorize o aplicativo.
7. Volte à janela e verifique a mensagem de conexão autorizada.

O programa aguarda até cinco minutos pela autorização e troca o código por tokens
assim que recebe o retorno. A porta 8765 deve estar livre. O receptor escuta apenas
no próprio computador e é fechado ao terminar.

As credenciais e os tokens são protegidos pela DPAPI do Windows em
`%LOCALAPPDATA%\RomaneioDiario\acesso.dat`, fora desta pasta de código.
Somente o mesmo usuário Windows pode abrir esse arquivo. Não envie credenciais,
tokens nem URLs de retorno com `code` por chat, email ou capturas de tela.

## Conferir o resultado

Dê dois cliques em `conferir_notas.cmd` para listar as notas do dia.
Compare os números e o total com a tela **Notas Fiscais de Saída** do Bling,
usando a mesma data e desconsiderando as canceladas.

Pelo terminal, na pasta deste projeto:

```powershell
py -3 bling.py conectar
py -3 bling.py conferir
py -3 bling.py conferir --data 16/10/2026
py -3 bling.py gerar
py -3 bling.py gerar --data 16/10/2026
```

A consulta percorre todas as páginas, elimina repetições por ID e valida tipo,
data de emissão e situação. A API exclui canceladas por padrão e o programa
também as remove caso apareçam na resposta. Todas as demais situações são mantidas,
conforme a regra solicitada. Notas novas ou cancelamentos posteriores só são
refletidos em uma nova consulta. Não há filtro pela data de criação da venda.

O acesso é renovado automaticamente durante a conferência quando necessário.
Se o Bling revogar a autorização ou expirar o refresh token, execute conectar
novamente. A gravação dos tokens é atômica; duas execuções locais não podem usar
a mesma conexão simultaneamente. Consultas GET têm tentativas limitadas para
erros temporários. A troca de tokens não é repetida automaticamente.

## Usar em outros computadores

Copie o código, `modelo_roteiro.xlsx`, `lojas.json` e os arquivos `.cmd`/`.ps1`, instale Python e execute a conexão em cada
computador/usuário. Não copie a pasta de credenciais do Windows. Este aplicativo
privado atende à própria conta Bling; para outra empresa, configure um aplicativo
e uma autorização apropriados àquela conta.

## Gerar o roteiro

Dê dois cliques em `gerar_roteiro.cmd`. O programa consulta os detalhes de cada
nota e grava o Excel na pasta `outputs`, ao lado do código. Cada execução cria
um arquivo com data e horário; roteiros anteriores não são substituídos.
Se a nota não tiver número de venda, a célula fica destacada como **NÃO INFORMADO**
e o programa mostra quais notas precisam de conferência. A nota continua no total.

O modelo tem uma folha, com os marketplaces em blocos. Nota e venda são gravadas
como texto, preservando zeros e todos os dígitos. Os totais têm fórmulas com valores
calculados salvos para aparecerem mesmo antes de abrir no Excel. A impressão é
herdada do arquivo de referência. As bordas, cores, fontes, larguras, alturas e
posições seguem o modelo formatado pelo usuário: total geral com o texto em B2,
horário completo em A3 e bordas também nos espaços entre os marketplaces.
As fórmulas e a área de impressão acompanham a quantidade de notas geradas.

`lojas.json` relaciona os IDs das lojas aos nomes dos marketplaces. O mapeamento
é uma configuração local da empresa e não é enviado ao GitHub. Ao clonar o projeto,
copie `lojas.exemplo.json` para `lojas.json` e substitua os IDs fictícios pelos IDs
das lojas na sua conta Bling. Duas lojas podem ter o mesmo nome de marketplace.
Para excluir uma loja do roteiro, use `null` como valor do respectivo ID,
conforme o exemplo fictício em `lojas.exemplo.json`. A exclusão vale para qualquer
data consultada, inclusive nos agendamentos; as notas dessa loja não entram nos totais.
Uma loja nova é incluída como
**Loja ID**, sem omitir suas notas; edite esse arquivo para nomeá-la.
O número da venda vem de `numeroPedidoLoja` no detalhe da NF-e, sem exigir
permissão de configuração das integrações.

Para escolher um caminho específico (o arquivo não pode existir):

```powershell
py -3 bling.py gerar --data 16/10/2026 --saida "C:\Relatorios\roteiro.xlsx"
```

## Agendar diariamente às 13h

Depois de conferir o Excel, execute `agendar_roteiro.cmd` no computador responsável.
Ele cadastra uma tarefa diária às 13h no Agendador de Tarefas do Windows, no
usuário conectado. O script não altera uma tarefa existente com o mesmo nome.
O computador precisa estar ligado e o usuário precisa estar conectado; a janela
fica oculta. Uma execução perdida é iniciada quando o Windows permitir.

Resultados ficam em `outputs` e os registros de execução em `outputs\logs`.
Para alterar horário ou excluir o agendamento, use o Agendador de Tarefas e procure
**RomaneioDiario-GerarRoteiro**. Mantenha o código nesta pasta após agendar.
O comando de agendamento pode ser copiado para outro computador, mas deve ser
executado somente onde a geração diária deve ocorrer.

## Verificação do código

```powershell
py -3 -m unittest discover -s tests -v
```

Os testes utilizam respostas simuladas e não acessam a conta Bling.

## Arquivos no GitHub

Versione o código, os testes, os atalhos, `lojas.exemplo.json` e
`modelo_roteiro.xlsx`. O modelo distribuído contém apenas a estrutura e a
formatação; os pedidos são preenchidos durante cada geração.

O `.gitignore` exclui `lojas.json`, credenciais, ambientes Python, logs, arquivos
temporários do Excel e a pasta `outputs`. As credenciais de uso ficam fora do
repositório, protegidas pelo Windows. Os valores presentes nos testes e no
arquivo de configuração de exemplo são fictícios.

Antes de enviar alterações, confira os arquivos que serão incluídos:

```powershell
git status --short
git add --dry-run .
```

Referências: [cadastro e OAuth](https://developer.bling.com.br/aplicativos),
[referência da API](https://developer.bling.com.br/referencia),
[limites de consultas](https://developer.bling.com.br/limites).
