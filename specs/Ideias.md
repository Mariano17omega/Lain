Quero implementar a visualização 3D das estruturas a partir do scf.

Primeiro pedir um relatorio, @Documentation/Relatorios/Relatorio_visualizacao_3D_da_estrutura.md para o Claude analizar possiveis formas de implementar.
A partir do relatorio, foi feito um teste isolado, foi criado um programa simples para visualizar a estrutura a partir do scf. Esse programa está salvo em @Documentation/Exemplo-visualizador_3d

Gostei desse resultado, e quero implementar uma visualização 3D no projeto Lain. Quero que seja implementado da seguinte forma:

- No menu do botão direito do mouse, adicione a opção 'Visualização 3D'

- Esse Botão deve abrir uma nova janela independente da janela principal do Lain. Nessa janela o usuario visualiza a estrutura atomica 3D do scf.

- O usuario poderá abrir quantas janelas de visualização 3D quiser. Para cada vez que abir um scf usado o botão 'Visualização 3D', cria-se uma nova janela de visualização 3D. Um exemplo é quando temos varios scf no banco de dados, cada scf tem sua própria janela 3D independente. Cada janela deve ter suas proprias configuracoes, como zoom, cor dos atomos, etc.

- Dentro dessa nova janela, vai ter um painel do lado esquerdo e um painel do lado direito. Igual como foi feito em @Documentation/Exemplo-visualizador_3d .

Quando implementar a visualização 3D, faça as seguintes correções que não gostei do @Documentation/Exemplo-visualizador_3d :

- No painel direito, a parte de metrica ( distancias e angulos). Quero que tenha um botão 'Distancia' e um botão 'Angulos' para selecionar o tipo de calculo.

- Quando o 'Distancia' está ativo, o usuario seleciona dois atomos, e o programa mostra a distancia entre eles.

- Quando o usuario selecionar o 'Angulos', quando o usuario seleciona tres atomos, e o programa mostre o angulo entre eles, igual como é feito no xcrysden.

- O botão 'Distancia' e o botão 'Angulos' devem ser mutually exclusive. O usuario deve selecionar um deles para realizar o calculo.

- A distancia sempre será calculada para um par de atomos.

- As distancias devem ser calculadas automaticamente e mostradas em uma tabela, por exemplo: O usuario sleciona dois atomos, é calculado a distancia deles. Depois seleciona mais dois atomos, e é calculado a distancia entre eles, e é add uma nova linha na tabela dos resutados, por exemplo

O1 - O2 1.5 Å
O1 - O3 2.1 Å
O2 - O3 1.8 Å

- Os angulos devem ser calculadas automaticamente e mostradas em uma tabela, por exemplo: O usuario sleciona tres atomos, é calculado o angulo entre eles. Depois seleciona mais tres atomos, e é calculado o angulo entre eles, e é add uma nova linha na tabela dos resutados, por exemplo

O1 - O2 - O3 120.0°
O1 - O2 - O4 135.0°

- Na visualização 3D, as arestas entram dentro dos atomos, fica estranho, porque dá para vê as arestas dentro dos atomos. Quero que as arestas não entrem dentro das esferas dos atomos. E independende da possição que olho, as arestas parecem retangulos, não parecem cilindros, como são na realidade, melhore isso.

- Quando dou zoom e seleciono um atomo, o zoom é desfeito. Quero que mantenha o zoom quando clicar nos atomos.

- Melhore a UI da aba do lado esquerdo do visualizado 3D, a forma como foi feita no Exemplo-visualizador_3d não ficou boa.
