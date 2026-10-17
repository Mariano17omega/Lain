Os botões "Gerar Gráfico" e "Grid" que ficam na barra superior, jundo dos botões das abas, não combinam com a UX do projeto, quero fazer as seguintes musanças:

- Mover os botões "Gerar Gráfico" e "Grid" para barra lateral onde já exitem outros botões.
- Na barra lateral já tem um botão "Plot" com a função parecida com "Gerar Gráfico", pode remover o botão 'Plot'.
- Quero que espaço destinado ao endereço da pasta seja fixo, não quero que os itens do lado direito se desloquem toda vez que entrar ou sair de pasta (O endereço da pasta muda).
- Adicione um botão para 'tree_show_files', isso já foi definido no arquivo de configuração 'config.yaml', quero que adicione um botão para o usuario mudar durante a execução do programa. Quero que o botão fique na aba da arvores de arquivos, entre o botão 'recoher tudo' e 'atualizar'.
- Na aba da arvore de arquivos, se a pasta de uma unidade de simulação (Bands, PDOS, etc.) tiver algum erro de simulação, ou seja, se tiver o arquivo '_.o_' não vazio ou tiver o arquivo 'CRASH', o nome da pasta deve ficar com uma tag 'ERRO' vermelha, indicando que houve um erro.

Além disso, quero que na criação de um calculo, tenha um botão Checkbox, 'Numerar', quando ele for marcado, ele vai adicionar uma numeração no prefixo do nome da pasta criada. Essa numeração é opcional, e vai seguir a ordem de numeração se já tiver outras pastas com o mesmo prefixo. A numeração considera todas as pastas presentes dentro da pasta onde vai ser criado o calculo, ou seja, não é restrido ao tipo de calculo, por exemplo: "0_Relax", "1_Bands", "PDOS".
