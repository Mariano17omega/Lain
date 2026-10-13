A pasta @Documentation/Exemplo-SLAB/ é um conjunto de scripts que fiz em Python para criar inputs do quantum espresso, eles fazem:

1. Cria uma estrutura SLAB a partir do SCF do bulk.
2. Cria uma Supercelula a partir do scf feito da estrutura do SLAB relaxada.
3. Possiciona uma molecula na superficie da supercelula (usando o a supercelula relaxada)

Fiz esses scripts focando na estrutura cristalina da caulinita.

Quero adaptar esses scripts para criar os inputs de calculos de superficie (slab, supercelula, e molecula na superficie) do Lain.

Já existe um botão e uma janela para criar calculos. Quero que adicione esses novos tipos de calculos no Lain.

- Slab
- Supercelula
- Molécula na superficie

São 3 tipos de calculos diferentes, mas que dependem um dos outros. O cálculo da supercelula pode (não necessariamente) depender do cálculo do slab, e o cálculo da molécula na superficie depender do cálculo da supercelula.

Para o cálculo da molécula na superficie, considere que o usuario está usando um scf de uma superficie relaxada (slab ou supercelula), mas adicione uma validação para caso o usuario confunda e selecione o scf de um bulk.

Nos scripts, para a criação da slab, tem a opção de usar o scf da molecula para obter o seu tamanho só pra calcular altura de vácuo. Adicione isso como algo opcional.

Os scripts possuem varios parametros que podem ser ajustados para diferentes casos, como bidentados, monodentados, Remove átomos H da superfície para adicionar a molécula, adicionar em um local especificando as coordenadas ou a partir de uma lista de canditados. Adicione todos os parametros dos scripts como parametros configuraveis nas janelas de criação de calculos.
