Ajustes, correções e novas funcionalidades:

- gride de graficos: Add um um botão na barra superior chamado "Grids" que abre uma janela para selecionar e configurar o gride de graficos;
  Nessa janela, o usuario cria uma grade NxM para unir os graficos. Cada quadrante da grade pode exibir um grafico.
  Para cada quadrante, o usuario escolhe um grafico que já foi plotado, define o posição (linha, coluna) e define um título.

- Na aba de configurações dos graficos, add um botão para incluir o grap de energia nas legedas do plot. Essa opção deve ser um checkbox e deve aparecer apenas nos graficos de bandas e PDOS.

- Add um botão 'Bandas com DOS' no meno do botão direito do mouse. Esse botão só apareve quando o usuario seleciona uma pasta com calculo de Bandas e uma pasta com calculo de DOS. O botão 'Bandas com DOS' plotar as bandas e a DOS no mesmo grafico, com o mesmo eixo de energia (eixo y).

- Na aba configurações dos graficos, para o caso de plot de PDOS, na sessão Projeções, inclua um botão "Atomos", que abre uma janela com a lista de todos atomos do composto. É exibido o rotulo do elemento, as coordenadas x, y, z, (com tabela), com uma coluna de checkbox. Nessa janela o usuario pode selecionar os atomos que deseja plotar (obtiais da PDOS) e salvar essa seleção. Essa seleção é salva por composto, então o usuario não precisa selecionar os atomos toda vez que for plotar PDOS do mesmo composto. Para cada composto existe uma lista de atomos selecionados. Por padrão todos os atomos estão selecionados. Ao iniciar o Lain, o usuario deve selecionar os atomos para cada composto. Quando o usuario seleciona uma pasta que contém um composto que já foi selecionado, o Lain deve carregar os atomos selecionados para esse composto. È util quando o usuario quer plotar apenas os orbitais de dois atomos, no caso de analize de ligações quimicas.

- No caso de relaxamento (relax e vc-relax), no caso do output desses calculos (convergidos!), e apenas neles, inclua a opção "Gerar SCF convergido" no menu do botão direito do mouse. Esse botão gera um scf usando os mesmos parametros usados no input, mas com as coodernadas e a celula já convergidas. O novo scf é salvo na mesma pasta do relaxante, mas com o nome 'scf_convergido<prefix>.in' e 'scf_convergido<prefix>.out', onde <prefix> é o prefix do input do calculo de relaxamento.
