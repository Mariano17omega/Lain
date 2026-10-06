- O botão para mostrar o gap de energia no grafico de bandas, na sessão 'LEGENDAS' da aba de configurações de grafico não funciona. O Sistema é um isolante com gap maior de 1 eV, mas quando clico no botão, aparece o aviso dizendo que ão é possivel calcular o gap porque o sistema é metalico.

- Na sessão 'LEGENDAS' da aba de configurações de grafico, add dois campos 'dx' e 'dy' para o usuario adicionar um deslocamento na posição da legenda para ajustar ela com mais libertade.

- Na opção de gerar resumo, no menu do botão direito do mouse: Tem uma linha do resumo "k-points" que eroneamente soma as componentes kx, ky e kz, invez de exibir '5 5 5', mostra '15'

- No menu do botão direito do mouse a opção 'Abrir local de origem' não funciona. Dá o erro: 
 
""" Traceback (most recent call last):
  File "/home/m/Área de trabalho/Lain/src/qe_studio/ui/widgets/context_menu.py", line 295, in_on_reveal_finished
    if watcher.isError() and paths:
       ^^^^^^^^^^^^^^^
AttributeError: 'QDBusPendingCallWatcher' object has no attribute 'isError'
"""

- Na barra superior mosta o login do usario e o o endereço do cluter, ao lado de um circulo para indicar o estado de conexão com cluster. Quero que remova o endereço do cluster e o nome do usuario. Deixe apenas o circulo para indicar o estado.

- Arquivos markdown, quando abertos na aba de visualização, deve ser rendezinados como markdown, não como texto puro.

- Os arquivos '.qsub' são visualizados como arquivo de texto puro na aba lateral. Os scripts '.qsub' devem ser visualizados como com realce, erros de escrita, e coisas do tipo igual como é com os arquivos de input.

- A Função de criar calculo da diferença de carga deu erro, não acontece nada depois de selecionar um scf e clicar no botão continuar.

- Na janela de criação de calculo, se o usuario clicar no botão de 'Avançado', deve ser permitido editar os inputs e o script na propria janela de visualização, mas ó no modo Avançado.


- Os outputs de calculo NSCF não tem a função de plotar no menu do botão direito do mouse. QUero que tenha um botão com a mesma função de plot que o outputs do scf tem.

- Nas pastas com calculo de relaxamento, quando é para fazer o plot do output do relaxamento, o grafico é feito clicando no botão "Gerar Gráfico" na barra superior. Isso não é muito pratico, porque pode ter mais de um output na pasta. Quero que no menu do botão direito do mouse, adicione a oção de plot para os aquivos de output de relaxamento, iqual como é feito para os outputs de scf. O botão na barra superior continuar funcionando como um atalho, util quando tiver apenas um output de calculo na pasta.

- Na visualização dos arquivos na grade, aba central, quando o nome é muito longo, não é exibido o nome completo. Quero que quando o nome for grande, quebre a linha, não use '...'.

- Na arvore de pastas na aba lateral esquerda, por padrão deve ser exibido apenas as pastas. Adicione um parametro em 'config.yaml' para o usuario ajustar isso e fazer com que exibam os arquivos também na arvore de pastas.

- 
