Ajustes, correções e novas funcionalidades:


- Quando o usuario iniciar um projeto pela primeira vez, a aba de visualização de graficos e inputs não deve ser iniciada quando abir o programa.

- Quando o usuario clicar duas vezes em um input ou em alguma figura, a aba de visualização de graficos e inputs deve ser iniciada.

- Quando uma aba é ativada ou desativada, o layout do programa muda, a divisoria entre as areas muda. Por exemplo, se eu fechar a aba de visualização de graficos e inputs, a outras duas abas, de visualização de arquivos e arvore de pastas, são redimensionadas para ocupar meio a meio, preenchendo o espaço que a aba de visualização de graficos e inputs ocupava. Quero que a divisoria entre as areas mantenha a proporção após fechar ou abrir alguma aba.

- Remova o botão 'Ajuste' da barra lateral esquerda. Ele não tem função nenhuma por enquanto.

- Na visualização dos arquivos da pasta no formato de grade de icones, além dos nomes, é exibido o tamanho do arquivo, quero que remova a exibição do tamanho do arquivo. Mantenha as labels 'OK', 'icompleto', etc. que informam os estados dos arquivos.

- No botão 'Plot' na barra de ferramentas, na lateral do lado esquerdo, atualmente, quando clicar nele, é gerado o plot automaticamente. Não quero que esse botão gere o plot automaticamente porque já tem um botão 'Gerar Gráfico' na aba de visualização de graficos e inputs. A função do botão 'Plot' deveria ser apenas abrir a aba de visualização de graficos e inputs, se ela não estiver aberta, e abrir a aba esquerda de configurações de plotagem. A aba já existe, só quero que não gere o plot toda vez que cliclo nele, só abra e deixe as configurações para o usuario ajustar.

- Quando cliclo com o botão direito do mouse em um arquivo ou pasta, deve abrir algumas opções: 'Abrir local de origem', 'Abrir com' (Para escolher um programa para abrir), 'Copiar', 'Renomear'. Apenas essas opções. No futuro será implementado mais, por enquando só essas.

- Na visualização de arquivos em grade, adicione um atalho para voltar para voltar para a pasta anterior, seria um equivalente ao "cd ..", Deve ser sempre o primeiro elemento da grande. è apenas um atalho visual para facilitar a navegação.

- Após fazer a plotagem de bandas, as informações da plotagem que ficam no rotapé, barra inferior, devem ser atualizadas. Atualmente, após fazer a plotagem e fechar fechar a aba de visualizaçao de graficos e inputs, e sair da pasta onde estão os arquivos, as informações no rotapé não são atualizadas, permanecem as da plotagem anterior. Quero que as informações do rodapé sejam atualizadas.

- Os arquivos do tipo '*.o*' são arquivos de saida de informações de erro da simulação. Trate eles como arquivos de texto, permitindo que o usuario veja o conteúdo deles na aba de visualização de inputs. Se o arquivo estiver vazio, significa que não houve erro na simulação, se tiver conteúdo, significa que houve erro na simulação.

- O fundo das figuras de grafico geradas no plot possuem fundo transparente. Quero que o fundo seja branco. Atualmente quando o tema é escuro, o fundo da imagem é transparente, aparecendo aparecendo um fundo escuro no tema escuro e um fundo brando no tema claro. Deixe o fundo sempre branco, tanto no tema escuro quanto no tema claro.

- Adicione um novo parametro na aba "Ajustes" que permite ao usuario escolher a cor de fundo do gráfico, o padrão é fundo branco.

- Atualmente, quando fecha o programa, todas as informações do programa são perdidas. O usuário pode abrir a mesma pasta novamente e o programa não guarda nenhuma informação sobre o estado anterior. Quero que as mudanças em runtime que o usuario fizer sejam persistidas após fechar o app. 


- Os arquivos com extenção '.qsub' são scripts de submissão de tarefas para o cluster. O Lain deve ser capaz de identificar esses arquivos e tratá-los como arquivos de texto, permitindo que o usuario veja o conteudo deles na aba de visualização de inputs. Não deve ser possivel editar o conteudo desses arquivos dentro dolain, apenas visualizar.

- No caso de simulações de relaxamento, 'relax' e 'vc-relax', quero que faça o plot do progresso de relaxamento. Em 'Documentation/Relax-Viewer-' tem um pequeno app que ler outputs do relaxamento e gerar o plot, em escala linear e escala log, do |ΔE| vs passos BFGS, e Força total vs Passos BFGS. Esse o 'Relax-Viewer-' como referencia para implementar esses dois plots. O Lain deve ser capaz de identificar se é um relaxamento e gerar os dois plots quando clicar no botão plot, iqual como é bom bandas e PDOS. 

- As informações que quero que pesistam são:

-- Possição dos divisores verticais das abas.

-- As mudanças de parametros feitas na aba de configuraçõe de plot (AJUSTE DO GRÁFICO). Deve ser salvos as configurações de plot em um arquivo .plot na pasta da simulação, de forma que quando abrir a past novamente, o programa vai carregar as ultimas configurações de plot usadas na simulação.  




