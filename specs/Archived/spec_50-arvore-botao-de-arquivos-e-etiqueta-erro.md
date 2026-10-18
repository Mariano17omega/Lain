# Spec 50: Árvore de pastas — botão "Mostrar arquivos" e etiqueta ERRO nas pastas com erro de simulação

| | |
|---|---|
| **Prioridade** | 50 (dois ajustes independentes do painel da árvore; R2 é o mais útil no dia a dia, R1 é pequeno) |
| **Status** | Implementada. Desempenho (`-m perf -s tests/test_perf_detection.py`, nesta máquina, antes → depois): `detect_folder` nas 520 pastas, a frio 583 → 600–860 ms e a quente 77 → 78–110 ms (ruído da máquina: o teste chama `detect_folder`, que a spec não mudou; orçamentos 1500 e 180 ms); o custo novo é `run_error`, medido à parte: **10–15 ms nas 520 pastas** (uma `scandir` cada); `F5 + detect 50 folders` (passa por `detect_now`, logo por `run_error`) 36 → 8–12 ms, dentro de 48 ms.<br>- **Corrigido em 18/10/2026** (revisão de código): um `job.o<id>` que contém uma saída do QE terminada (`JOB DONE`, a linha da grade diz OK/AVISO) não liga mais o ERRO da pasta; um truncado continua ERRO. Só os logs com conteúdo são farejados, pelo cache do serviço (`run_error(pasta, sniff)`), o que ajusta o "nunca lê o conteúdo" do R2.1. E o ERRO é calculado antes da detecção, por isso fica mesmo quando ela falha (`_DetectionFailed` em `ui/services.py`), ao contrário do "`_on_error` guarda `None`" do R2.2. |
| **Depende de** | spec 37 (`ui.tree_show_files`, `FileFilterProxy.set_dirs_only`), spec 4 (`.o<id>` como ERRO / SEM ERROS), spec 14/15 (`DetectionService`) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: P; R2: M) |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): R1 liga um filtro que já existe; R2 segue o desenho dos selos (badges) e acrescenta um campo ao cache do serviço, sem física nem arquivo perto do limite. |

## Itens de origem (`Ideias.md`)

> - Adicione um botão para 'tree_show_files', isso já foi definido no arquivo de configuração 'config.yaml', quero que adicione um botão para o usuario mudar durante a execução do programa. Quero que o botão fique na aba da arvores de arquivos, entre o botão 'recoher tudo' e 'atualizar'.
> - Na aba da arvore de arquivos, se a pasta de uma unidade de simulação (Bands, PDOS, etc.) tiver algum erro de simulação, ou seja, se tiver o arquivo '_.o_' não vazio ou tiver o arquivo 'CRASH', o nome da pasta deve ficar com uma tag 'ERRO' vermelha, indicando que houve um erro.

"'_.o_'" é lido como o log de saída do job (`job.o12345`, `*.o<número>`), o mesmo arquivo que a grade já rotula "ERRO" quando não está vazio
(spec 4). "Aba da árvore" é o painel Explorador (`ExplorerPanel`).

## Situação atual

- **R1 (botão de arquivos).** `ui/widgets/explorer.py:186-188`: o cabeçalho do Explorador tem `collapse_button` ("Recolher tudo", `unfold_less`) e
  `refresh_button` ("Atualizar (F5)", `refresh`), em `PanelHeader.add_button` (`ui/widgets/common.py:103`, na ordem de chamada). A árvore lista só pastas
  quando `ui.tree_show_files` é `false` (padrão, `core/config.py:213`): `ExplorerPanel.__init__` passa `dirs_only=not ui.tree_show_files` ao
  `FileFilterProxy` (`explorer.py:205-211`) e `apply_config` (`:275-279`, "Recarregar config.yaml") chama `proxy.set_dirs_only(...)`.
  `FileFilterProxy.set_dirs_only` (`ui/widgets/fs_model.py:87-91`) já troca o filtro em execução (`invalidateFilter`). Não há controle na interface:
  só o `config.yaml` muda o valor. `tests/test_tree_show_files.py` cobre o filtro e `select_path` com a árvore só de pastas. A variante
  `headerButton` já tem o estilo `:checked` (`ui/resources/styles/navigation/panels.qss:31-34`), então um `IconButton` checável não precisa de QSS.
  O ícone `draft` (arquivo) existe em `ui/resources/icons/`.
- **R2 (etiqueta ERRO).** `ExplorerDelegate.paint` (`explorer.py:46-99`) pinta, para uma pasta, os selos da detecção da direita para a esquerda
  (`for result in reversed(self.service.results(path) or [])`, `paint_badge`, `ui/painting.py:62-86`) e, se um filtro de selo espera a detecção,
  "detectando…". `service.results(pasta)` agenda a detecção na primeira pintura (`ui/services.py:49-57`); a tarefa é `_detect` (`:19-22`) →
  `detect_folder`, que lê a pasta com `FolderListing.scan` (`core/calculations/listing.py:25-37`: `os.scandir`, só arquivos da pasta e os PDOS de um
  nível abaixo). **Nada olha por `CRASH` em lugar nenhum** (`grep -rn CRASH src` vazio). O ERRO de um log de job existe só **para arquivos**:
  `core/file_kinds.py:26,29-30,76-77` (`JOB_LOG = ^.+\.[oe]\d+(?:[.-]\d+)?$`, `status_label` → `("ERRO", "error")` se `size > 0`), pintado na linha
  do arquivo da grade/árvore com arquivos. A dica do selo vem de `ExplorerDelegate._tooltip_at` (`:144-162`) com `badge_layout`
  (`ui/painting.py:49-59`), a mesma conta da pintura. Tokens de cor: `badge_<token>_{bg,fg,border}` em `dark.yaml:39-56` / `light.yaml` (bands, pdos,
  relax, scf, calc, other); **não há `badge_error_*`**; `tests/test_theme_contrast.py:92` exige AA de todo `badge_*_fg` sobre o próprio fundo. O resultado
  da detecção fica em `DetectionService._results` (`:42`), esvaziado por `invalidate` (`:101-125`; F5, sync, renomear). Testes que montam o serviço:
  `tests/test_services.py` (vários), `test_perf_detection.py:126`, `test_load_cache.py:230`, `test_tree_show_files.py:100`; nenhum chama `_detect` ou lê
  `_results` direto (grep).
- Tamanhos: `ui/widgets/explorer.py` 354, `ui/services.py` 150, `ui/painting.py` ~90, `core/file_kinds.py` ~110.

## Requisitos

### R1: botão "Mostrar arquivos" no cabeçalho da árvore

1. `ExplorerPanel.files_button`: `IconButton(theme, "draft", …)`, `setCheckable(True)`, criado **entre** `collapse_button` e `refresh_button`
   (a ordem das chamadas a `header.add_button`). Marcado = a árvore lista os arquivos. Tooltip: "Mostrar arquivos na árvore" (desmarcado) /
   "Ocultar arquivos da árvore" (marcado).
2. Estado inicial: `ui.tree_show_files` (o botão nasce marcado ou não). Um clique faz `proxy.set_dirs_only(not checked)` e é só da sessão: **nada é
   gravado**; "Recarregar config.yaml" (`apply_config`) volta ao valor do arquivo e atualiza o botão (sem emitir `toggled`: um método
   `set_files_shown(bool)` que bloqueia o sinal, como `ProjectCombo.set_current`).
3. Bordas: com um arquivo selecionado na árvore e o botão desmarcado, a linha some; a pasta aberta na grade não muda (o `_on_current` ignora um
   índice inválido); `select_path(arquivo)` volta a funcionar como na spec 37 (R2.4) nos dois estados. Com o filtro do nome ativo, a troca
   reaplica o filtro (o `invalidateFilter` já o faz). O botão entra na ordem de Tab do painel pela variante `headerButton` (`controls/focus.qss`).
4. **Testes** (`tests/test_tree_show_files.py`, com `tree_files_window` / `main_window` e `grid_helpers.tree_names`): o botão existe, fica entre os
   dois (`header.buttons` na ordem `collapse, files, refresh`), nasce desmarcado com o padrão e marcado com `ui.tree_show_files: true`
   (`window_factory(ui=…)`); marcar mostra os arquivos e desmarcar os esconde sem mudar `current_folder()`; o tooltip troca; "Recarregar config" com
   o valor do arquivo reposiciona o botão; nada vai ao QSettings (`window.settings.allKeys()` sem chave nova).

### R2: etiqueta vermelha "ERRO" na pasta

1. **Núcleo** (`core/run_errors.py`, novo, Qt-free, em `QT_FREE` do `test_architecture.py`): `RunError(kind: "crash" | "job_log", name: str)` com
   `tooltip` ("Erro de simulação: arquivo CRASH" / "Erro de simulação: <nome> não está vazio") e
   `run_error(folder: Path) -> RunError | None`. Uma única `os.scandir(folder)` (só os arquivos da própria pasta, nenhuma subpasta), nunca raise
   (`OSError` → `None`), nunca lê o conteúdo: um arquivo regular chamado exatamente `CRASH` (qualquer tamanho; o pw.x só o cria numa parada com
   erro) → `crash`; senão o primeiro, em ordem de nome, que casa o log de saída do job com `st_size > 0` → `job_log`. Sem `stat` dos demais.
   O log de saída é `file_kinds.is_job_stdout(path)`, novo, `^.+\.o\d+(?:[.-]\d+)?$` sem diferenciar maiúsculas (a metade `o` do `JOB_LOG`; o
   `.e<id>`, stderr do SGE, **não** conta aqui, como o pedido). `JOB_LOG` e `status_label` não mudam. `cancel.check()` não é preciso (uma
   `scandir`).
2. **Serviço** (`ui/services.py`): `_detect` devolve `(resultados, run_error(pasta))`; `_on_done` guarda os dois (`_errors: dict[str, RunError | None]`
   ao lado de `_results`, sob o mesmo `_lock`); `detect_now` também; `invalidate` apaga de `_errors` as mesmas chaves que apaga de `_results`;
   `_on_error` guarda `None`. Novo `peek_error(pasta) -> RunError | None` (só o cache, como `peek_results`: não agenda nada). O erro é da pasta, por
   isso não depende de a detecção achar um módulo: uma pasta cujo job caiu antes de escrever a saída (sem selo de cálculo) também recebe a etiqueta.
3. **Pintura** (`ExplorerDelegate.paint`, só pastas): se `service.peek_error(path)` não for `None`, o selo "ERRO" é pintado **primeiro**, encostado na
   borda direita (`paint_badge(painter, right, center, "ERRO", theme, "error")`), e os selos da detecção seguem à esquerda dele. A dica
   (`_tooltip_at`): o item "ERRO" é o primeiro de `badge_layout` e devolve `RunError.tooltip`. A pintura não toca o disco.
4. **Cores:** `badge_error_{bg,fg,border}` nos **dois** temas — escuro: `bg rgba(244, 63, 94, 0.20)`, `fg #fda4af`, `border rgba(244, 63, 94, 0.45)`
   (a família do `error` `#f43f5e`); claro: tons vermelhos escolhidos para passar AA em `test_theme_contrast.py::test_badges_pass_aa_on_their_own_background`.
   O token `"error"` de `paint_badge` casa `badge_error_*` (`ui/painting.py:75`).
5. **Atualização:** a etiqueta aparece quando a detecção da pasta termina (`detected` já repinta a viewport) e some/volta com F5, sync e renomear
   (`invalidate`). O `refresh_folder` de um pull (`MainWindow.refresh_folder`) já invalida a pasta sincronizada: um `job.o…` baixado liga a etiqueta.
6. **Desempenho:** o custo é uma `scandir` a mais por pasta detectada; `tests/test_perf_detection.py` (520 pastas) não pode passar do orçamento
   escrito na spec 14 (conferir o número antes e depois com `-m perf -s` e anotá-lo no "Status" ao implementar).
7. **Testes:** `tests/test_run_errors.py` (core, `tmp_path`): pasta limpa → `None`; `CRASH` → `crash` (vazio também); `job.o123` vazio → `None`, com
   byte → `job_log`; `job.e123` não vazio → `None`; `job.o123.1` (array) conta; `CRASH` vence um `.o`; subpasta com `CRASH` → `None`; `CRASH` como
   pasta → `None`; pasta inexistente → `None`; `.o` com várias → o primeiro por nome. `tests/test_services.py`: `peek_error` vazio antes da detecção,
   preenchido depois de `detected`, apagado por `invalidate(pasta)` e refeito (um `job.o` criado depois aparece após o `invalidate`). Janela
   (`test_tree_error_tag.py`, `main_window`): numa cópia de `demo_project`, a pasta com `CRASH` mostra o selo (`grab()` da viewport numa região à
   direita do nome tem a cor do token; ou o `badge_layout` dado pelo delegate) e a vizinha limpa não; a dica da pasta com `.o` não vazio é a do
   `RunError`. `test_theme_contrast.py` cobre as cores novas. `test_architecture.py`: `run_errors` sem PyQt6, `ui/` sem chamada de disco nova (`FS_ALLOWED`).

## Fora de escopo

- A etiqueta na **grade** (cartões de pasta) e um filtro "ERRO" no menu "Filtrar ▾": não foram pedidos; ficam para outra spec se fizerem falta.
- Ler o conteúdo do `CRASH` ou do `.o` para dizer o motivo: a dica só diz qual arquivo causou a etiqueta.
- Contar `*.e<id>` não vazio: o pedido cita o `.o`; a grade já mostra o ERRO dos dois arquivos, individualmente.
- Distinguir um `.o` com avisos de MPI de uma falha real: a regra é a do pedido (não vazio), a mesma da grade.
- Persistir o botão de arquivos: ver decisão 2.

## Decisões assumidas (confirmar na revisão)

1. **O que é "unidade de simulação":** qualquer pasta da árvore, tenha ou não selo de cálculo; uma pasta de Bandas que caiu sem saída é justamente
   a que precisa da etiqueta. A alternativa (só pastas com selo) esconderia as falhas mais graves.
2. **O botão vale na sessão:** parte do `ui.tree_show_files` e não grava nada, para o `config.yaml` continuar mandando no início e no
   "Recarregar config". Se quiser que o programa lembre a escolha, é uma chave QSettings `explorer/show_files` e uma regra de qual vence.
3. **Só `.o`:** o `.e` (stderr) não liga a etiqueta, como no pedido. É uma linha trocar por `JOB_LOG` se quiser os dois.
4. **`CRASH` vale vazio:** o arquivo existir é o sinal.
5. **Posição:** "ERRO" fica na ponta direita da linha, antes dos selos BANDS/PDOS, para continuar visível com o nome da pasta cortado.

## Notas de implementação

- Novos: `src/qe_studio/core/run_errors.py`, `tests/test_run_errors.py`, `tests/test_tree_error_tag.py`.
- Alterados: `ui/widgets/explorer.py` (R1; pintura e dica de R2), `ui/services.py` (`_errors`, `peek_error`), `core/file_kinds.py`
  (`is_job_stdout`), `ui/resources/themes/dark.yaml` e `light.yaml` (`badge_error_*`), `tests/test_architecture.py` (`QT_FREE`),
  `tests/test_tree_show_files.py`, `tests/test_services.py`, `tests/test_theme_contrast.py` (se a lista de tokens for explícita).
- Limites: nenhum arquivo perto de 500 (`explorer.py` 354 → ~385). `ui/main_window.py` não é tocado.
- Documentação ao implementar: `CLAUDE.md` (seção "Detection pipeline" ou "Context menu"/painéis: `run_errors`, `peek_error`; a de `ui.tree_show_files`
  na spec 37: o botão), `config.example.yaml` **nas duas cópias** (o comentário de `tree_show_files` cita o botão; `tests/test_config.py` exige que
  sejam idênticas).

## Critérios de aceite e testes

- [ ] Com o padrão (`tree_show_files: false`) a árvore abre só com pastas e o botão está desmarcado, entre "Recolher tudo" e "Atualizar"
      (`test_tree_show_files.py`).
- [ ] O botão mostra e esconde os arquivos na hora, sem mudar a pasta da grade e sem gravar nada (`test_tree_show_files.py`).
- [ ] "Recarregar config.yaml" repõe o estado do arquivo e do botão (`test_tree_show_files.py`).
- [ ] Uma pasta com `CRASH`, ou com `job.o<id>` não vazio, mostra o selo vermelho "ERRO" na árvore; uma com `.o` vazio, só `.e`, ou limpa, não
      (`test_run_errors.py`, `test_tree_error_tag.py`).
- [ ] A dica do selo diz qual arquivo causou o erro (`test_tree_error_tag.py`).
- [ ] O selo some depois de apagar o arquivo e atualizar (F5), e um `.o` baixado por um pull o liga (`test_services.py`, `test_tree_error_tag.py`).
- [ ] Contraste AA do `badge_error_fg` nos dois temas (`test_theme_contrast.py`); a pintura não lê o disco (`test_architecture.py`).
- [ ] Detecção dentro do orçamento da spec 14 (`-m perf -s tests/test_perf_detection.py`, número anotado).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
