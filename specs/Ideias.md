Ajustes, correções e novas funcionalidades:

- gride de graficos: Add um um botão na barra superior chamado "Grids" que abre uma janela para selecionar e configurar o gride de graficos;
  Nessa janela, o usuario cria uma grade NxM para unir os graficos. Cada quadrante da grade pode exibir um grafico.
  Para cada quadrante, o usuario escolhe um grafico que já foi plotado, define o posição (linha, coluna) e define um título.

- Na aba de configurações dos graficos, add um botão para incluir o grap de energia nas legedas do plot. Essa opção deve ser um checkbox e deve aparecer apenas nos graficos de bandas e PDOS.

- Add um botão 'Bandas com DOS' no meno do botão direito do mouse. Esse botão só apareve quando o usuario seleciona uma pasta com calculo de Bandas e uma pasta com calculo de DOS. O botão 'Bandas com DOS' plotar as bandas e a DOS no mesmo grafico, com o mesmo eixo de energia (eixo y).

- Na aba configurações dos graficos, para o caso de plot de PDOS, na sessão Projeções, inclua um botão "Atomos", que abre uma janela com a lista de todos atomos do composto. É exibido o rotulo do elemento, as coordenadas x, y, z, (com tabela), com uma coluna de checkbox. Nessa janela o usuario pode selecionar os atomos que deseja plotar (obtiais da PDOS) e salvar essa seleção. Essa seleção é salva por composto, então o usuario não precisa selecionar os atomos toda vez que for plotar PDOS do mesmo composto. Para cada composto existe uma lista de atomos selecionados. Por padrão todos os atomos estão selecionados. Ao iniciar o Lain, o usuario deve selecionar os atomos para cada composto. Quando o usuario seleciona uma pasta que contém um composto que já foi selecionado, o Lain deve carregar os atomos selecionados para esse composto. È util quando o usuario quer plotar apenas os orbitais de dois atomos, no caso de analize de ligações quimicas.

- No caso de relaxamento (relax e vc-relax), no caso do output desses calculos (convergidos!), e apenas neles, inclua a opção "Gerar SCF convergido" no menu do botão direito do mouse. Esse botão gera um scf usando os mesmos parametros usados no input, mas com as coodernadas e a celula já convergidas. O novo scf é salvo na mesma pasta do relaxante, mas com o nome 'scf_convergido<prefix>.in' e 'scf_convergido<prefix>.out', onde <prefix> é o prefix do input do calculo de relaxamento.

- crie um modulo para criar scripts e inputs de calculos (relax, vc-relax, scf, dos, bandas, etc) de forma grafica. Crie um botão "Criar calculo" na barra lateral esquerda. Esse botão abre uma janela para o usurio configurar e criar os scripts e inputs de calculos.

-- Crie uma pasta 'src/qe_studio/resources/templates/qsub/' e 'src/qe_studio/resources/templates/qe/' e organize os arquivos de templates por tipo de calculo usando a biblioteca Jinja2.

-- Em 'src/qe_studio/resources/templates/qe/' vão ficar os templates dos scripts do cluster.

-- Em 'Documentation/Referencia_de_scripts_QSUB' tem exemplos de scripts do cluster, que servirão de base para a criacao dos templates. Nos scripts a linha '#$ -N "name"' define o nome que será exibido no scheduler do cluster. A linha '#$ -pe physica NP' define o numero NP de nucleos usados no calculo. Além do nome, cada script deve ter os parametros NP (Numero de nucleos), nk (Numero de k-points). 'qsub' é a extenção dos scripts que enviam o calculo para o cluster. Os arquivos qsub devem ter um nome que descrevam o tipo de calculo e os parametros, por exemplo: 'relax.qsub', 'scf.qsub', 'pdos.qsub', 'bandas.qsub', etc.

-- Em 'src/qe_studio/resources/templates/qe/' vão ficar os templates dos inputs, por exemplo 'projwfc.in', 'bands_pp', 'pp_mehg_charge.in', etc.

-- Nessa janela de configuração de calculo, obrigadoriamente deve ser informado um input de SCF. A partir dele são extraidas as informações para gerar outros inputs, tipo o de NSCF (Só copiar e editar o "calculation = 'nscf'"), o prefix, etc. As informações que não podem ser obtidas do scf inicial, devem ser solicitadas na interface grafica. Por exemplo, pontos de simetria para o calculo de bandas. Se o calculo for de bandas, o usuario deve informar os pontos de simetria, usando a biblioteca Pymatgen. Caso contrário, o usuario pode informar uma rede de k-points manual. os pontos devem ser em K_POINTS crystal_b.

-- O usuario pode editar as configurações do input e do script, preenchedo campos definidos na interface grafica. Por padrão os valores são preenchidos com valores extraidos do input de SCF. Se o usuario não informar um valor para algum campo, o valor padrão do template será usado. O usuario não editar texto manualmente.

-- O usuario especifica o local onde será criado a pasta onde será salvo as coisas. O tipo de calculo define o prefixo da pasta, o nome da pasta que o usuario definir será o sufixo, por exemplo: "bandas_Al" ou "relax_Si"

-- A criação desses calculos não devem substituir os existentes. Caso já existam arquivos com o mesmo nome, os arquivos devem ser salvos com um sufixo, por exemplo: "bandas_Al_1", "relax_Si_1", etc.

-- A criação desses calculos é feita localmente, o usuario deve enviar os arquivos gerados para o cluster usando a ferramenta de sincronização.

-- Essa janela de criação de calculos deve ser acessível a partir da barra lateral esquerda, por um botão "Criar calculo", aparece novas abas na janela de configuração de calculo. O usuario seleciona o tipo de calculo em um botão lista dropdown. Tem o botão para ele selecionar o scf inicial, nome da pasta, local onde a pasta com o calculo será criada. Quandoo usuario confirmar, a janela muda para uma janela com varias abas, uma abas para template usado para o tipo de calculo definido pelo usuario, por exemplo, se o usuario selecionou PDOS, então deve ter uma aba para o script qsub, para o SCF, para o NSCF e projwfc.in. Além disso, deve der uma aba com a lista de arquivos que serão gerados na pasta.

-- Add uma aba extra para descrição, essa aba é apenas para o usuario escrever anotações e descrições sobre o que está calculando. O texto deve ser salvo em um arquivo .md na mesma pasta onde será criado o calculo. É apenas anotação para o proprio usuario.

-- A pasta só é criada após o usuario preencher todas as informações obrigatorias e clicar em "Criar". Se o usuario cancelar, a janela é fechada sem criar nada.
