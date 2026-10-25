Add no botão 'Tree' a função de mostrar e ocultar aba lateral com a arvore de pastas, igual ao botão 'Tree' que fica na barra superior.

Remover a sessão de 'Recents' da aba lateral de exibição da arvore de pastas.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

Quero quem em 'config.yaml' tem a opção de adicionar em 'paths' um caminho para a pasta 'data', para o usuario definir onde os arquivos de configuração do Lain serão salvos, tipo uma alternativa para os caminhos padrões tipo '~/.config/qe-studio/' de forma que se o usuario copiar a pasta, todas as configurações, incluindo as que foram salvas no 'data' sejam levadas junto.

Quando inicio o app pelo menu iniciar, é carregado pelo 'config.yaml', no terminal não carrega o arquivo de configurações.
Quando inicio pelo terminal, digitando 'lain' no terminal, fora da pasta do projeto, o programa inicia sem sem o 'config.yaml'.
Quero poder iniciar o programa em qualquer terminal, sempre lendo o arquivo 'config.yaml' que fica na raiz do projeto lain.



%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

Melhorar sincronização, add um novo botão de sincronização para quando clicado nele, a aba esqueda 'Tree' e a aba central 'Grid' mudam a cor de fundo, e passam e exibir as pastas e arquivos do cluster, e só voltam a exibir as pastas e arquivos locais quando o botão for clicado novamente. 

A mundança a cor do plano de fundo acontece apenas visualmente, para indicar que o Lain está exibindo os arquivos do cluster, e que o usuario não está visualizando os arquivos locais. 

No menu do botão direito do mouse, invez de aparecer a opção upload, tem a opção download, para baixar os arquivos do cluster para o computador local. 

Para lidar com o delay na interação quando está visualizando arquivos remotos, adicione uma animação para indicar que o Lain está processando a requisição.

As funções de plot continua funcionando na visualização de arquivos e pastas remotas, mas apenas para a leitura, ou seja, os arquivos são copiados para o computador local antes de serem plotados. Ou seja, plotar um grafico no ambiente remoto baixa automaticamente o conteudo necesario para a plotagem para o computador local.

Para a cor de fundo, no ambiente remoto, use a cor de fundo com tom vermelho.

Implementar checksum na sincronização.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
No terminal, uso o comando 'qstatus -a' para visualizar todos os jobs que estão sendo executados e a fila de jobs, e 'qstatus' para visualizar apenas os jobs do meus usuario, os que estão na espera e estão sendo executados. Por exemplo:

'''
mariano@lucci:~$ qstatus -a
Running jobs:
 job-ID  # name                      owner      start time          running in
------------------------------------------------------------------------------
  23538 32 Nd2Fe14B-4f-129           aercio     10/15/2026 17:53:02 physica.q  
  23591 32 hBN+Sm-1                  toliveira  10/20/2026 11:29:17 physica.q  
  23592 32 hBN+Eu-1                  toliveira  10/22/2026 08:34:47 physica.q  

Waiting jobs:
 job-ID  # name                      owner      submit time        
-------------------------------------------------------------------
  23542 32 Sm3NbO8-HP-130            aercio     10/15/2026 18:05:21 
  23543 32 BNNT90-S-375              aercio     10/15/2026 18:07:00 
'''

'''
mariano@lucci:~$ qstatus
Waiting jobs for user: mariano
 job-ID  # name                      submit time        
--------------------------------------------------------
  23644 32 Bands-kao-b               10/22/2026 23:39:04 
  23645 32 PDS-B                     10/22/2026 23:43:43 
  23646 32 Bands-kao-001-p           10/22/2026 23:46:20 

'''


Na barra superior, tem um ponto que ficar verde ou vermelho para indicar a conexão com cluster. O ponto que indicar a conexão com cluster, ficar verde se estiver conectado, e vermelho se não estiver.

Quero que do lado esquerdo desse botão apareça o 'name' do job, do meu usuario, que está sendo executado, com um formato 'Running: <name>', ou 'No job running' (Se o usuario não estiver rodando nenhum job). Se Tiver mais de um job rodando, o conteudo de Running fica variando entre os jobs que estão sendo executados, de 5 em 5 segundos (Podendo ser configurado em 'config.yaml'), por exemplo.

E quando clicar em cima de 'Running: <name>' ou 'No job running' abre uma lista suspensa com todos os jobs do cluster (qstatus -a), com um formato parecido com o do comando 'qstatus -a', onde vai mostrar o 'name', 'owner', 'submit time' e 'running in'. Como o conteudo da lista precisa ser consultada no cluster sempre, matenha o conteudo tela salva temporariamente durante cada sessão, atualizando a cada 5 min (Podendo ser configurado em 'config.yaml').

