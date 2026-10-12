# Spec 33: Pequenos defeitos — k-pontos do Resumo, "Abrir local de origem" e rótulo do cluster na barra superior

| | |
|---|---|
| **Prioridade** | 33 (três itens pequenos e independentes; R2 é um defeito que quebra a ação inteira e pode sair antes de tudo) |
| **Status** | Implementada |
| **Depende de** | spec 5 (menu de contexto: "Abrir local de origem"), spec 11 (`input_extract`: o chip `K_POINTS`), spec 12 (Resumo de saídas) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): três correções pequenas, cada uma com arquivo, linha e teste identificados. |

## Itens de origem (`Ideias.md`)

> - Na opção de gerar resumo, no menu do botão direito do mouse: Tem uma linha do resumo "k-points" que eroneamente soma as componentes kx, ky e kz, invez de exibir '5 5 5', mostra '15'
>
> - No menu do botão direito do mouse a opção 'Abrir local de origem' não funciona. Dá o erro:
> `File ".../ui/widgets/context_menu.py", line 295, in_on_reveal_finished: if watcher.isError() and paths:` →
> `AttributeError: 'QDBusPendingCallWatcher' object has no attribute 'isError'`
>
> - Na barra superior mosta o login do usario e o o endereço do cluter, ao lado de um circulo para indicar o estado de conexão com cluster. Quero que remova o endereço do cluster e o nome do usuario. Deixe apenas o circulo para indicar o estado.

## Situação atual

- **R1 (k-pontos do Resumo).** O código **não soma** nada: a regra `kpoints` de `core/qe/summary/scan.py:90-94` captura o número que o
  pw.x imprime em `number of k points=` (os pontos **irredutíveis** da zona de Brillouin) e `core/qe/summary/build.py:139-143` o escreve
  na linha "k-pontos". Na pasta `Documentation/Exemplo-bands-010-mehg-O1` o `scf.in:144-145` pede `K_POINTS automatic` / `5 1 5 0 0 0` e o
  `scf.out:434` diz `number of k points= 13`: a linha mostra `13`, não `11` (a soma) nem `5 1 5`. O "15" do usuário é, provavelmente, a
  contagem de pontos irredutíveis de uma malha 5×5×5 com a linha rotulada só "k-pontos" (**não verificado**: não há uma saída com malha
  `5 5 5` aqui). O pw.x **não imprime a malha** na saída (o `scf.out` do exemplo só traz a contagem e a lista `k(  1) = …`); ela está
  no input. O visualizador de input já a mostra (`core/qe/input_extract.py:91-101`, chip `automatic 5×5×5 (0 0 0)`). `summarize(path)`
  (`core/qe/summary/__init__.py:61-65`, chamado no worker por `ui/widgets/summary_view.py:109`) lê só a saída. Teste que fixa o rótulo:
  `tests/test_summary.py:66` (`system["k-pontos"].value == "47"`).
- **R2 (Abrir local de origem).** `ui/widgets/context_menu.py:274-291` (`_show_items_dbus`) cria um `QDBusPendingCallWatcher` (`:288`) e
  `_on_reveal_finished` (`:293-299`) chama `watcher.isError()` (`:295`) e `watcher.error().message()`. No PyQt6 o watcher herda
  `QObject` e `QDBusPendingCall` e **não tem** `isError` (medido: `hasattr(QDBusPendingCallWatcher, "isError")` é `False`; quem tem é
  `QDBusPendingReply(watcher)`). O erro vem em **toda** chamada terminada, com sucesso ou não: o fallback `_open_parent` nunca roda e o
  `watcher.deleteLater()` (`:299`) também não. O teste `tests/test_file_grid_menu.py:290-316` passa à função um `FailedCall` feito à mão,
  com `isError`, e por isso nunca encontra a classe real.
- **R3 (barra superior).** `ui/widgets/bars.py:187-189` cria o LED (`StatusLed`) e o `cluster_label` (`#clusterLabel`); `:198-199` os
  põe na barra; `TopBar.set_cluster(label, state)` (`:254-256`) escreve o texto e o estado. O texto é montado em
  `ui/sync_coordinator.py:189-193` (`"{user}@{host}"`, ou "cluster não configurado") e emitido por `cluster_changed(label, state)`, que
  `ui/main_window.py:254-255` liga ao `TopBar` e à `ActivityBar` (esta ignora o rótulo, `bars.py:150`). Estilo:
  `ui/resources/styles/layout/top_bar.qss:6-10`. O tooltip do LED (`LED_TIPS`, `bars.py:34-40`) diz só "Cluster acessível" etc.
  Teste: `tests/test_main_window.py:47` (`top_bar.cluster_label.text() == "cluster não configurado"`).

## Requisitos

### R1: Resumo com a malha de k-pontos

1. A linha "k-pontos" passa a se chamar **"k-pontos irredutíveis"** (o valor não muda: é o que o pw.x imprime).
2. Nova linha **"Malha k"** logo depois, com o texto do chip do input (`automatic 5×5×5 (0 0 0)`, `gamma`, `crystal_b 5 pontos`,
   `tpiba 47 pontos`). A origem é o input de **mesmo nome** ao lado da saída (`<saída>.with_suffix(".in")`, que `looks_like_input`), lido na
   thread do worker que já faz o Resumo.
3. Novo módulo Qt-free `core/qe/summary/mesh.py`: `k_mesh_of(output: Path) -> str | None` (nunca levanta: sem input, input ilegível ou sem
   card `K_POINTS` devolve `None`; lê só o início, até `INPUT_READ_LIMIT`, e usa `input_lint.lint` e o texto do chip). O chip de
   `input_extract.py` vira função pública (`k_points_text(card)`) para os dois usarem a mesma frase.
4. `summarize(path)` chama `k_mesh_of` e entrega o resultado à montagem das seções; `summarize_lines(lines, pw=None)` mantém a assinatura
   (os testes de propriedade): sem malha, nenhuma linha "Malha k". A linha não tem `line` (a origem é outro arquivo).
5. **Testes** (`tests/test_summary.py`): `si_bands/si.scf.out` com `si.scf.in` ao lado mostra "Malha k" igual ao chip do input
   (`test_input_extract` já fixa o formato) e "k-pontos irredutíveis" igual a antes; saída sem input ao lado não tem "Malha k"; input
   ilegível (bytes inválidos) não derruba o Resumo; o rótulo antigo `"k-pontos"` do `:66` passa a `"k-pontos irredutíveis"`.

### R2: "Abrir local de origem" lê o resultado da chamada D-Bus

1. `_on_reveal_finished(watcher)` usa `reply = QDBusPendingReply(watcher)`: com `reply.isError()` registra `reply.error().message()` e abre
   a pasta pai (`_open_parent`); sem erro, não faz mais nada. `watcher.deleteLater()` roda sempre.
2. **Testes** (`tests/test_file_grid_menu.py`): trocar o `FailedCall` à mão por um watcher **real**, sem barramento de sessão (o teste
   nunca toca o D-Bus de verdade): `QDBusPendingCallWatcher(QDBusPendingCall.fromCompletedCall(call.createErrorReply("org.freedesktop.DBus.Error.ServiceUnknown",
   "sem FileManager1")))` com `call = QDBusMessage.createMethodCall(...)` (verificado: termina e `QDBusPendingReply(watcher).isError()` é
   verdadeiro). Dois casos: erro abre `QUrl.fromLocalFile(pai)`; `call.createReply()` não abre nada. `qtbot.capture_exceptions()` volta vazio.

### R3: Só o LED na barra superior

1. Remover `TopBar.cluster_label` (widget, `addWidget`, `setObjectName`) e o bloco `#clusterLabel` de `top_bar.qss`.
2. `TopBar.set_cluster(label, state)` mantém a assinatura (o sinal `cluster_changed` não muda): o `label` entra no **tooltip** do LED
   (`"Cluster acessível\nusuario@host"`); "cluster não configurado" não repete o que o tooltip de `disabled` já diz.
3. **Testes:** `tests/test_main_window.py:47` passa a afirmar que `top_bar` não tem `cluster_label` e que o tooltip do LED diz que o
   cluster não está configurado; um teste em `TopBar` sozinho (`top_bar.set_cluster("usuario@host", "online")`) vê o `usuario@host` só no
   tooltip do LED; os testes de `tests/test_sync_coordinator.py:42,129` já fixam que `cluster_changed` carrega o texto e não mudam.

## Fora de escopo
- Mostrar a malha para saídas sem input de mesmo nome (o `relax_in` da detecção, como `scf_from_relax.pair_input` faz): fica de fora para o
  Resumo continuar sem depender da detecção.
- Malha efetiva de um NSCF/bandas por caminho (`crystal_b`): o chip mostra "N pontos", sem expandir.
- Outro gerenciador de arquivos que não implemente `org.freedesktop.FileManager1`: continua o fallback `_open_parent`.
- O ponto do botão "Rsync" na `ActivityBar` (já é só o ponto).

## Decisões assumidas (confirmar na revisão)
1. O "15" do relatório é a contagem de pontos irredutíveis, **não** uma soma: o código não soma. O que o usuário quer ver (`5 5 5`) entra
   como linha nova, e o rótulo antigo passa a dizer o que é.
2. A malha vem só do input de mesmo nome ao lado da saída (a mesma regra de nomes do pw.x: `pw.x -i x.in > x.out`).
3. O `usuario@host` sai da barra mas continua no tooltip do LED (a informação não se perde); se o usuário quer o tooltip sem o endereço,
   basta tirar a segunda linha de R3.2.

## Notas de implementação
- Novos: `core/qe/summary/mesh.py` (entra em `QT_FREE` de `tests/test_architecture.py`, que já cobre `core/qe/summary/`).
- Alterados: `core/qe/summary/build.py` (273 linhas; a linha nova), `core/qe/summary/__init__.py`, `core/qe/input_extract.py`
  (`_k_points` → `k_points_text`), `ui/widgets/context_menu.py` (`_on_reveal_finished`), `ui/widgets/bars.py` (`TopBar`),
  `ui/resources/styles/layout/top_bar.qss`, `tests/test_summary.py`, `tests/test_file_grid_menu.py`, `tests/test_main_window.py`.
- Limites: nenhum arquivo perto de 500 linhas.
- Documentação ao implementar: `CLAUDE.md`, seção "Output summary (spec 12)": a linha "Malha k" e de onde vem; seção "Context menu (spec 5)":
  `QDBusPendingReply(watcher)`.

## Critérios de aceite e testes
- [x] `tests/test_summary.py`: com `si.scf.in` ao lado, "Malha k" = chip do input e "k-pontos irredutíveis" = `47`/valor de hoje; sem
      input, sem "Malha k"; `summarize_lines` e os testes de propriedade do `test_properties.py` passam sem mudança.
- [x] `tests/test_file_grid_menu.py`: watcher real com erro abre a pasta pai; resposta sem erro não abre; nenhuma exceção capturada.
- [x] `tests/test_main_window.py`: sem `cluster_label` na barra; LED com o `usuario@host` só no tooltip.
- [x] `test_architecture.py` (QT_FREE, FS_ALLOWED: `ui/` não ganha chamada de disco), `ruff check`, `ruff format --check`, `pyright` e a suíte
      `-m "not realdata and not perf"` verdes.
