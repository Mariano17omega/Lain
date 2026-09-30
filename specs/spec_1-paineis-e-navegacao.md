# Spec 1: Painéis, barra de atividades e rodapé

| | |
|---|---|
| **Prioridade** | 1 (correções e ajustes de uso diário; base para a spec 3) |
| **Status** | Rascunho para revisão |
| **Depende de** | nenhuma |
| **Usada por** | spec 3 (persistência dos divisores) |
| **Esforço** | M |

## Itens de origem (`Ideias.md`)

> - Quando o usuario iniciar um projeto pela primeira vez, a aba de visualização de graficos e inputs não deve ser iniciada quando abir o programa.
> - Quando o usuario clicar duas vezes em um input ou em alguma figura, a aba de visualização de graficos e inputs deve ser iniciada.
> - Quando uma aba é ativada ou desativada, o layout do programa muda, a divisoria entre as areas muda. [...] Quero que a divisoria entre as areas mantenha a proporção após fechar ou abrir alguma aba.
> - Remova o botão 'Ajuste' da barra lateral esquerda. Ele não tem função nenhuma por enquanto.
> - No botão 'Plot' na barra de ferramentas, na lateral do lado esquerdo, [...] A função do botão 'Plot' deveria ser apenas abrir a aba de visualização de graficos e inputs, se ela não estiver aberta, e abrir a aba esquerda de configurações de plotagem.
> - Após fazer a plotagem de bandas, as informações da plotagem que ficam no rotapé, barra inferior, devem ser atualizadas. [...]

Decisão confirmada: o workspace começa **sempre oculto** ao abrir o Lain (as abas não são
restauradas, então ele abriria vazio). A largura dele é lembrada para quando for aberto.

## Vocabulário

A janela tem três painéis num `QSplitter` horizontal, à direita da barra de atividades:

| Painel | Widget | Toggle na barra superior |
|---|---|---|
| Painel esquerdo: árvore **ou** ajustes do gráfico | `MainWindow.left` (`QStackedWidget`: `ExplorerPanel` / `ParamsPanel`) | "Árvore" |
| Grade de arquivos | `MainWindow.files` (`FilePanel`) | "Grade" |
| Workspace: abas de gráficos, textos e imagens | `MainWindow.workspace` (`Workspace`) | "Gráficos" |

"Aba de visualização de gráficos e inputs" = **workspace**. "Aba esquerda de configurações de
plotagem" = `ParamsPanel` ("AJUSTE DO GRÁFICO").

## Situação atual

- `MainWindow._restore_state` (`src/qe_studio/ui/main_window.py:238`) restaura tamanhos do splitter e a
  visibilidade da grade; o workspace fica sempre visível, mostrando o estado vazio
  (`Workspace.empty`, `src/qe_studio/ui/widgets/workspace.py:154`).
- `MainWindow.open_file` (`main_window.py:279`) já chama `set_panel_visible("workspace", True)` após
  abrir um arquivo em aba. O duplo clique na árvore (`ExplorerPanel._on_double_click`) e a ativação na
  grade (`FilePanel._on_activated`) já chegam a `open_file`. **O item "duplo clique abre o workspace"
  já funciona**; só perde sentido hoje porque o workspace nunca está oculto no início. Falta teste.
- `MainWindow.set_panel_visible` (`main_window.py:301`) apenas faz `setVisible` no widget. O
  `QSplitter` dá o espaço liberado aos vizinhos conforme o stretch factor (só o workspace tem stretch
  1, `main_window.py:178`), e ao reexibir o painel volta com um tamanho arbitrário. Resultado: ao
  fechar o workspace, árvore e grade ficam meio a meio, e a proporção anterior se perde.
- Botão "Ajuste" na barra de atividades: `ActivityBar.params` (`src/qe_studio/ui/widgets/bars.py:109`),
  sinal `params_requested` (`bars.py:90`, conectado em `main_window.py:221`). Ele duplica o que o botão
  "Árvore" e o botão "Voltar à árvore" do `ParamsPanel` já fazem.
- Botão "Plot": `ActivityBar.plot` → `plot_requested` → `MainWindow.generate_plot`
  (`main_window.py:223`), que detecta, carrega, plota **e exporta** (`auto_export=True`) a pasta atual.
- Rodapé: `StatusBar.readout` (`bars.py:209`) só é escrito em `MainWindow._on_rendered`
  (`main_window.py:506`) e nunca é limpo. `_on_tab_changed(None)` (`main_window.py:490`) só
  desvincula o `ParamsPanel`. Por isso, ao fechar a aba do gráfico e trocar de pasta, o rodapé continua
  mostrando E_F, gap e px do gráfico anterior.

## Requisitos

### R1: Workspace oculto ao iniciar
1. Ao abrir o Lain, o workspace começa oculto em toda execução, e o toggle "Gráficos" da barra superior
   começa desmarcado.
2. Árvore e grade ocupam o espaço disponível na proporção lembrada (R3/spec 3).
3. A largura que o workspace teria continua guardada (R3) e é usada quando ele for aberto.

### R2: Abrir o workspace automaticamente
O workspace é exibido (se estiver oculto) quando:
1. o usuário dá duplo clique, ou Enter, num arquivo que o Lain visualiza internamente
   (`viewer_kind` = `text`, `image` ou `svg`), tanto na árvore quanto na grade;
2. um gráfico é gerado ("Gerar Gráfico", Ctrl+G, menu Gráficos). Esse caminho já passa por
   `_on_loaded`, que exibe o workspace;
3. o usuário clica no botão "Plot" (R5).

Arquivos `external` (abertos pelo sistema) **não** exibem o workspace.

### R3: Divisores mantêm a proporção
1. O `MainWindow` guarda a largura "de trabalho" de cada painel (`_panel_widths: dict[str, int]`
   com chaves `tree`, `grid`, `workspace`), atualizada quando o usuário arrasta um divisor
   (`QSplitter.splitterMoved`), redimensiona a janela ou antes de um painel ser ocultado.
2. **Ocultar** um painel: o espaço dele é dividido entre os painéis que continuam visíveis
   **proporcionalmente às larguras atuais deles**. Exemplo: árvore 280, grade 320, workspace 840.
   Ao fechar o workspace, a árvore fica com 280 + 840 × 280/600 = 672 e a grade com
   320 + 840 × 320/600 = 768, mantendo a razão 280:320.
3. **Reexibir** um painel: ele volta com a largura lembrada, e os demais encolhem proporcionalmente
   para liberar o espaço. Se nada foi arrastado entre fechar e reabrir, o layout volta exatamente
   ao anterior.
4. Nenhum painel fica menor que o seu mínimo atual (árvore 200, grade 170, workspace 320). Se não
   couber, a largura restaurada é reduzida até caber.
5. A regra vale para qualquer origem da mudança de visibilidade: toggles da barra superior, botão
   "Grade" da barra de atividades, abertura automática (R2) e botão Plot (R5).
6. Redimensionar a janela mantém o comportamento atual (o workspace absorve a diferença quando está
   visível; senão, os visíveis dividem proporcionalmente).

### R4: Remover o botão "Ajuste"
1. Remover `ActivityBar.params` e o sinal `params_requested`, com a conexão correspondente no
   `MainWindow`.
2. A troca árvore ⇄ ajustes continua disponível pelo botão "Árvore" (→ árvore), pelo botão "Plot"
   (→ ajustes, R5), pelo botão "Voltar à árvore" no cabeçalho do `ParamsPanel` e automaticamente ao
   gerar um gráfico (`_on_loaded` já chama `set_left_mode("params")`).
3. `ActivityBar.set_left_mode` passa a marcar "Árvore" no modo `tree` e "Plot" no modo `params`
   (Plot vira botão checkable que indica o painel de ajustes ativo).

### R5: Botão "Plot" só abre, não gera
Ao clicar em "Plot":
1. exibe o workspace, se estiver oculto;
2. exibe o painel esquerdo, se estiver oculto, no modo ajustes (`set_left_mode("params")`);
3. se a aba atual do workspace não é um gráfico mas existe alguma aba de gráfico aberta, ativa a
   aba de gráfico usada por último, para que o painel de ajustes mostre os parâmetros dela;
4. **não** detecta, não carrega, não plota e não exporta nada.

Ctrl+G, o menu "Gráficos → Gerar gráfico" e o botão "Gerar Gráfico" da barra superior continuam
gerando e exportando como hoje. O tooltip do Plot passa a ser "Gráficos e ajuste do gráfico". Sem
gráfico aberto, o `ParamsPanel` mostra o placeholder atual, que ganha um botão "Gerar gráfico"
(mesma ação do botão da barra superior).

### R6: Rodapé sempre coerente com o que está na tela
1. O `readout` do rodapé mostra o resumo do gráfico (`RenderInfo.summary` · px · DPI) **somente**
   quando a aba atual do workspace é um `PlotView` e o workspace está visível.
2. O texto passa a começar pelo nome da pasta do gráfico (ex.: `si_bands · E_F = 6.25 eV · gap
   0.61 eV · 1800×1350 px (300 DPI)`), para ficar claro a que simulação ele se refere.
3. O `readout` é limpo quando a aba de gráfico é fechada, quando a aba atual passa a ser texto ou
   imagem, quando o workspace fica sem abas e quando o workspace é ocultado.
4. Ao reexibir o workspace com uma aba de gráfico atual, o resumo volta.
5. Mudar de pasta não altera o `readout` enquanto o gráfico continuar visível. Com o prefixo do R6.2
   fica claro que ele se refere a outra pasta. O campo de caminho (`StatusBar.path`) continua sendo
   atualizado na seleção, como hoje.

## Fora de escopo
- Restaurar as abas abertas entre execuções.
- Persistir larguras e visibilidade em disco: fica na spec 3 (esta spec cria a estrutura em memória).
- Mudanças no "Gerar Gráfico" (detecção, escolha de tipo, auto-export).

## Decisões assumidas (confirmar na revisão)
1. Fechar a última aba **não** oculta o workspace, que mostra o estado vazio. O usuário oculta pelo
   toggle "Gráficos".
2. O botão Plot fica "marcado" enquanto o painel de ajustes está ativo (R4.3).
3. O placeholder do painel de ajustes ganha o botão "Gerar gráfico" (R5).
4. O rodapé não mostra informação da pasta selecionada quando não há gráfico (ex.: tipo detectado).
   Ele apenas fica vazio.

## Notas de implementação
- Arquivos: `src/qe_studio/ui/main_window.py` (`_build`, `_connect`, `_restore_state`,
  `set_panel_visible`, `set_left_mode`, `_on_tab_changed`, `_on_rendered`, novo slot para o Plot),
  `src/qe_studio/ui/widgets/bars.py` (`ActivityBar`), `src/qe_studio/ui/widgets/plot_params.py`
  (`_placeholder` + sinal `generate_requested`).
- Centralizar a lógica de tamanhos num único método (ex.: `_apply_panel_layout(changed: str)`) chamado
  por `set_panel_visible`. `QSplitter.sizes()` devolve 0 para widgets ocultos, então as larguras de
  trabalho não podem vir só de `sizes()`.
- `set_panel_visible("workspace", ...)` deve atualizar o `readout` (R6.3/R6.4). A troca de aba já passa
  por `_on_tab_changed`; aproveitar para limpar o `readout` quando `widget` não é `PlotView`.
- "Última aba de gráfico usada" (R5.3): guardar a ordem de ativação em `Workspace` (ex.: lista de chaves
  `plot:*` atualizada em `_on_current`).
- Sinais de longa duração conectados a métodos, não a lambdas (regra do CLAUDE.md).

## Critérios de aceite e testes
Em `tests/test_main_window.py` / `tests/test_plot_workflow.py` (headless, fixture `main_window`):
- [ ] Janela recém-criada: `workspace.isVisible()` é falso e o toggle "Gráficos" está desmarcado.
- [ ] `open_file` num `.in` e num `.png` exibe o workspace. Num arquivo `external`, o workspace
      continua oculto (monkeypatch em `QDesktopServices.openUrl`).
- [ ] Com tamanhos iniciais conhecidos, ocultar o workspace mantém a razão árvore/grade (tolerância
      ±2 px), e reexibir restaura os três tamanhos originais.
- [ ] Ocultar e reexibir a grade com o workspace visível preserva a razão árvore/workspace.
- [ ] A `ActivityBar` não tem mais o atributo `params` nem o sinal `params_requested`.
- [ ] Clicar em Plot numa pasta com bandas: nenhuma detecção pedida (`_detecting` vazio), nenhum
      arquivo novo em `plots/`, workspace visível, `left.currentIndex() == 1`.
- [ ] Com uma aba de gráfico e uma de texto abertas (texto atual), Plot ativa a aba de gráfico.
- [ ] Depois de gerar um gráfico, fechar a aba limpa `status.readout`. Trocar para uma aba de texto
      também limpa, e voltar para a aba do gráfico restaura o texto.
- [ ] O `readout` começa com o nome da pasta do gráfico.
- [ ] Atualizar `test_panel_toggles` e `test_close_saves_state` para o novo comportamento.
