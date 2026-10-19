# Romaneio diário

Automação do roteiro dos motoristas da distribuidora com a API v3 do Bling.

## Pacote portátil para compartilhar

O ZIP `RomaneioDiario_Portatil_Windows.zip` inclui seu próprio Python. O destinatário
extrai a pasta completa e abre `1_CONFIGURAR.cmd` na primeira vez. Depois, basta
abrir `2_GERAR_ROTEIRO.cmd` para gerar o roteiro de hoje, sem instalar Python ou bibliotecas.
A raiz contém os dois atalhos e o `LEIA-ME.txt`; código e runtime ficam em `programa/`.
Os arquivos Excel e PDF ficam em `roteiros/`, e o único log fica em `logs/execucao.log`.
Não há menus, seleção de data nem agendamento no pacote simplificado.

O pacote comum não inclui credenciais, `lojas.json`, notas, logs ou arquivos de testes.
O pacote com sufixo `_Configurado` inclui `programa/tokens.json` com **Client ID, Client Secret
e redirect_uri**, além de `programa/lojas.json` com os nomes e exclusões da empresa.
Nele, basta abrir o atalho de configuração e autorizar no navegador, sem digitar
as credenciais do aplicativo. Esse JSON é legível: distribua o pacote configurado
apenas a pessoas de confiança. Não publique o arquivo nem esse ZIP no GitHub.
Cada usuário autoriza a conexão na primeira utilização. O pacote configurado já
leva as lojas e exclusões conferidas; o pacote comum pede essa configuração uma vez.
Veja `LEIA-ME.txt` para o passo a passo e os requisitos de Windows.

Para reconstruir o ZIP em um Windows com Python de desenvolvimento:

```powershell
py -3 tools/empacotar_portatil.py
```

Para gerar o pacote configurado, mantenha `tokens.json` junto ao código, com os
campos `client_id`, `client_secret` e `redirect_uri`, e execute:

```powershell
py -3 tools/empacotar_portatil.py --com-credenciais
```

O empacotador seleciona somente esses três campos. Mesmo que o JSON de origem tenha
outros campos, tokens de acesso e renovação não são incluídos. O `tokens.json` local
e os ZIPs ficam ignorados pelo Git. O pacote comum continua disponível sem segredos.

O empacotador baixa a distribuição embutível oficial do Python, confere o SHA256
publicado no manifesto e inclui uma lista explícita de arquivos. O ambiente Python
portátil acompanha o pacote simplificado. As bibliotecas de PDF também são incluídas,
com versões e hashes fixados em `tools/dependencias_pdf.json`, e suas licenças acompanham
o pacote. O runtime e o ZIP ficam em pastas
ignoradas pelo Git; a licença oficial acompanha o pacote.

## Funcionalidades

Conexão OAuth e conferência das notas fiscais de saída por data de emissão,
de todas as lojas, nas situações **Emitida DANFE** ou **Autorizada (Aprovado)**. Geração de Excel com sequência,
número da nota e número da venda, agrupados por marketplace, com totais.
As notas e os pedidos não são alterados no Bling.

## Conectar pela primeira vez

Requisitos para executar pelo código: Windows e Python 3.10 ou superior, com
`py -3 -m pip install -r requirements-pdf.txt`. O ZIP portátil já inclui tudo.
Os atalhos também aproveitam o Python incluído no Codex quando disponível.
O relógio e o fuso do computador devem estar corretos; a data padrão é a data local.

1. No cadastro do aplicativo Bling, confira:
   - Visibilidade: **Privado**.
   - Link de redirecionamento: `http://localhost:8765/callback`.
   - Escopos: **Notas Fiscais** e **Pedidos de Venda**, para visualização.
2. Abra as informações do aplicativo e localize **Client ID** e **Client Secret**.
3. Dê dois cliques em `conectar_bling.cmd`.
4. Com `tokens.json`, as credenciais são preenchidas automaticamente. Sem ele, o
   programa aproveita o cadastro local existente ou pede Client ID e Client Secret.
   O secret fica oculto durante a digitação.
5. Na configuração manual, pressione Enter para confirmar o endereço de retorno.
6. No navegador, confira a conta e autorize o aplicativo.
7. Volte à janela e verifique a mensagem de conexão autorizada.

O programa aguarda até cinco minutos pela autorização e troca o código por tokens
assim que recebe o retorno. A porta 8765 deve estar livre. O receptor escuta apenas
no próprio computador e é fechado ao terminar.

As credenciais e os tokens são protegidos pela DPAPI do Windows em
`%LOCALAPPDATA%\RomaneioDiario\acesso.dat`, fora desta pasta de código.
Somente o mesmo usuário Windows pode abrir esse arquivo. O `tokens.json` opcional
contém uma cópia legível das credenciais do aplicativo para facilitar a instalação.
Os tokens de acesso ficam apenas no cofre local, nunca no JSON distribuído. Não
compartilhe tokens de acesso nem URLs de retorno com `code`.

## Conferir o resultado

Dê dois cliques em `conferir_notas.cmd` para listar as notas do dia.
Compare os números e o total com a tela **Notas Fiscais de Saída** do Bling,
usando a mesma data e as situações **Emitida DANFE** e **Autorizada (Aprovado)**.

Pelo terminal, na pasta deste projeto:

```powershell
py -3 bling.py conectar
py -3 bling.py conferir
py -3 bling.py conferir --data 16/10/2026
py -3 bling.py gerar
py -3 bling.py gerar --data 16/10/2026
```

A consulta percorre todas as páginas, elimina repetições por ID e valida tipo,
data de emissão e situação. A consulta lista as notas do dia sem restringir a uma
única situação na API e seleciona os códigos `6` (**Emitida DANFE**) e `5`
(**Autorizada**, correspondente a **Aprovado**) na resposta e nos detalhes de cada nota.
Notas rejeitadas, canceladas ou pendentes ficam fora do roteiro.
Se a situação mudar durante a geração, a nota só permanece se ainda estiver em
uma dessas duas situações. Alterações posteriores são refletidas em uma nova consulta.
Não há filtro pela data de criação da venda.

O acesso é renovado automaticamente durante a conferência quando necessário.
Se o Bling revogar a autorização ou expirar o refresh token, execute conectar
novamente. A gravação dos tokens é atômica; duas execuções locais não podem usar
a mesma conexão simultaneamente. Consultas GET têm tentativas limitadas para
erros temporários. A troca de tokens não é repetida automaticamente.

## Usar em outros computadores

Envie o ZIP portátil e peça para extrair e abrir `1_CONFIGURAR.cmd`. Com o pacote
configurado, o atalho abre a autorização sem pedir Client ID ou Secret. Depois,
`2_GERAR_ROTEIRO.cmd` gera o Excel e o PDF de hoje na pasta `roteiros`.
Autorize em cada computador/usuário. Não copie a pasta de credenciais do Windows. Este aplicativo
privado atende à própria conta Bling; para outra empresa, configure um aplicativo
e uma autorização apropriados àquela conta.

## Gerar o roteiro

Dê dois cliques em `gerar_roteiro.cmd`. O programa consulta os detalhes de cada
nota e grava o Excel e o PDF na pasta `outputs`, ao lado do código. Cada execução cria
um par de arquivos com o mesmo nome, data e horário; roteiros anteriores não são substituídos.
Os dois formatos usam exatamente os mesmos registros da mesma consulta ao Bling.
O PDF segue o modelo A4 enviado: Mercado Livre primeiro e Shopee em uma página própria,
com as mesmas notas, pedidos, sequência e totais do Excel. Cada página comporta até
55 notas. Quando um marketplace ultrapassa esse limite, continua em novas páginas,
sem misturar os grupos e sem cortar registros. Outros marketplaces também ganham
páginas próprias. Pedidos ausentes aparecem como **NÃO INFORMADO** nos dois formatos.
O PDF fica ao lado do Excel também quando se usa `--saida`.

Para atualizar um computador que já usa o pacote portátil, extraia
`outputs/distribuicao/Atualizacao_Excel_e_PDF.zip` dentro da pasta `RomaneioDiario`
existente e aceite substituir os arquivos de `programa/`, incluindo a pasta `_vendor`.
A atualização não contém credenciais ou configurações de lojas. Não é necessário
reautorizar a conexão. O empacotador gera esse ZIP junto com o pacote completo.
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
py -3 -m pip install -r requirements-dev.txt
py -3 -m unittest discover -s tests -v
```

Os testes utilizam respostas simuladas e não acessam a conta Bling.

## Arquivos no GitHub

Versione o código, os testes, os atalhos, `lojas.exemplo.json` e
`modelo_roteiro.xlsx`. O modelo distribuído contém apenas a estrutura e a
formatação; os pedidos são preenchidos durante cada geração.

O `.gitignore` exclui `lojas.json`, credenciais, ambientes Python, logs, arquivos
temporários do Excel e a pasta `outputs`. O `tokens.json` local também é ignorado.
Os tokens de uso ficam fora do repositório, protegidos pelo Windows. Os valores presentes nos testes e no
arquivo de configuração de exemplo são fictícios.

Antes de enviar alterações, confira os arquivos que serão incluídos:

```powershell
git status --short
git add --dry-run .
```

Referências: [cadastro e OAuth](https://developer.bling.com.br/aplicativos),
[referência da API](https://developer.bling.com.br/referencia),
[limites de consultas](https://developer.bling.com.br/limites).
