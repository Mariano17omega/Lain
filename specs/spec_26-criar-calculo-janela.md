# Spec 26: Criar cálculo — botão e janela

| | |
|---|---|
| **Prioridade** | 26 |
| **Status** | Implementada. Desvios:<br>- **Toast sem o lembrete de "Enviar ao cluster"** (decisão do usuário): a ação é da spec 27, que acrescenta o lembrete junto com ela (R5.3 adiado; feito na spec 27).<br>- **Sem tokens novos** (decisão do usuário): as linhas alteradas usam `diff_change_bg` (o âmbar do diff de inputs, via `CodeView.set_row_backgrounds`) e o `ShellHighlighter` usa os `syn_*`. Um fundo `hl_changed` quebraria `test_theme_contrast`, que mede todo `hl_*` como texto.<br>- **Abas = arquivos do plano:** não há abas "k-points"/"Bandas" à parte; a rede (`kmesh`) fica na aba do arquivo do seu grupo (NSCF na PDOS, o input no SCF/Relax) e o caminho na de `bands.in`.<br>- O erro do SCF é `ScfInputError` (backend da spec 25), não `ScfError`.<br>- O botão é `ActivityBar.new_calc` (`create` é método de `QWidget`); ícone `add_circle`; o tipo começa vazio ("Escolha o tipo").<br>- Habilitar botão e ação: `FirstRunController.refreshed` (na abertura e a cada config aplicada) → `CalcCreateController.update_available`; `main_window.py` ganhou 2 linhas.<br>- Core: `validate_target` = `validate_suffix` + `validate_parent` (mensagem sob cada campo); `types.field_problems` marca cada campo; `core/calc_create/preview.py` tem o que a janela mostra (`changed_lines`, `field_text`, `file_rows`, `target_text`, `created_notice`, `outside_project`, `mesh_summary`).<br>- Caminho: na primeira visita a sugestão só preenche tabela vazia; "Sugerir" substitui. Números aceitam vírgula; valor inválido volta ao anterior. Coluna "Pontos" (dica: até o próximo).<br>- Sem `_grow`: a janela abre em 960×640 e as páginas escondidas têm política `Ignored`. |
| **Depende de** | spec 18 (registro de ações, paleta, `for_window`), spec 25 (backend de geração) |
| **Usada por** | nenhuma (spec 27 envia a pasta criada) |
| **Esforço** | G |

## Itens de origem (`Ideias.md`)

> - crie um modulo para criar scripts e inputs de calculos (relax, vc-relax, scf, dos, bandas, etc) de forma grafica. Crie um botão "Criar calculo" na barra lateral esquerda. Esse botão abre uma janela para o usurio configurar e criar os scripts e inputs de calculos.
> -- O usuario pode editar as configurações do input e do script, preenchedo campos definidos na interface grafica. [...] O usuario não editar texto manualmente.
> -- Essa janela de criação de calculos deve ser acessível a partir da barra lateral esquerda, por um botão "Criar calculo", aparece novas abas na janela de configuração de calculo. O usuario seleciona o tipo de calculo em um botão lista dropdown. Tem o botão para ele selecionar o scf inicial, nome da pasta, local onde a pasta com o calculo será criada. Quandoo usuario confirmar, a janela muda para uma janela com varias abas, uma abas para template usado para o tipo de calculo definido pelo usuario, por exemplo, se o usuario selecionou PDOS, então deve ter uma aba para o script qsub, para o SCF, para o NSCF e projwfc.in. Além disso, deve der uma aba com a lista de arquivos que serão gerados na pasta.
> -- Add uma aba extra para descrição, essa aba é apenas para o usuario escrever anotações e descrições sobre o que está calculando. O texto deve ser salvo em um arquivo .md na mesma pasta onde será criado o calculo. É apenas anotação para o proprio usuario.
> -- A pasta só é criada após o usuario preencher todas as informações obrigatorias e clicar em "Criar". Se o usuario cancelar, a janela é fechada sem criar nada.
> -- A criação desses calculos é feita localmente, o usuario deve enviar os arquivos gerados para o cluster usando a ferramenta de sincronização.

## Situação atual

- **Barra lateral esquerda** = `ActivityBar` (`ui/widgets/bars.py:93-144`): sinais `explorer_requested`,
  `grid_toggled`, `plot_requested`, `sync_requested`, `theme_requested`; botões `ActivityButton(theme, icon, text,
  tooltip, checkable)` (l.66-90, 46×44 px, rótulo de 9 px) criados em l.109-115 e dispostos pela tupla
  `(tree, grid, plot, rsync)` + `addStretch(1)` + tema (l.116-119); cada `clicked` liga a um sinal (l.123-127).
  `tests/test_main_window.py:213-215` afirma a forma da barra. Não há ícone `calculate`; os ícones são Material
  Symbols em `ui/resources/icons/*.svg`, atualizados por `scripts/fetch_assets.py`.
- **Ações:** `ui/actions.py:ACTIONS` (`ActionSpec(id, menu, text, slot, shortcut, separator_before)`, l.17-54)
  com `slot` um caminho de atributo da janela (`attrgetter`, l.74). Menus: Arquivo, Navegar, Cluster, Gráficos,
  Ferramentas, Ajuda. A paleta (`palette_controller.py:148-159`) e o diálogo de atalhos (`help_controller.py:66-76`)
  leem `ACTIONS` sozinhos. A ordem em `MainWindow.__init__` é `_build`, `_build_controllers`, `_build_menus`,
  `_connect`: o controlador precisa existir antes de `_build_menus`.
- **Controladores `for_window`:** `HelpController` (`help_controller.py:46-63`), `PaletteController`
  (`palette_controller.py:59-73`), `FirstRunController` (`first_run.py:57-69`): a classe recebe callables e
  widgets, `for_window` os monta, emitem `message(str, str, int)` ligado ao rodapé. `main_window.py` tem
  **475/500 linhas** (`test_architecture.py`).
- **Diálogos:** padrão modal `ask_*` (`ui/dialogs/mapping.py`: `QGridLayout`, `QLineEdit` + "…" + `QFileDialog`,
  habilitar OK por validação, `exec()` + `deleteLater()`); não modal com `WA_DeleteOnClose`
  (`shortcuts.py`, `help_controller.py:78-90`: um por vez, re-levanta o aberto); janela em páginas
  (`ui/dialogs/sync_dialog.py:35-172`: `QStackedWidget`, `_show_page`, `_grow`, `WindowModal`, Esc/X cancelam).
  **Nenhum diálogo usa `QTabWidget`/`QFormLayout`**; `QTabWidget` só em `DocumentTabs`
  (`workspace_tabs.py:47-53`, `#workspaceTabs`): uma aba em diálogo recebe o QSS genérico de `QTabBar`
  (`workspace/tabs.qss:9-33`) e precisa de `objectName` e regra de painel próprios.
- **Blocos de formulário:** `ui/widgets/param_widgets.py` (`Section` recolhível com grade 40/60 rótulo/campo,
  `add_row(label, widget, tooltip)`, `add_full`; `ColorButton`, `SeriesList`), `flow_layout.py` (chips), estilos
  de `QLineEdit`, `QSpinBox`, `QDoubleSpinBox`, `QComboBox`, `QCheckBox` em `controls/inputs.qss`.
- **Prévia somente leitura com realce:** `CodeView(theme)` (`ui/widgets/code_view.py:56-81`: `QPlainTextEdit`
  somente leitura com margem de linhas) + `highlighters.InputHighlighter(document, theme, issues=None)`
  (l.102-138, tokens `syn_*`), que funciona sem `issues`. `TextViewer` é preso a arquivo (`read_preview` em
  worker) e **não** serve para texto em memória. **Não há realce para `.qsub`/shell** (`.qsub` é `TEXT_SUFFIXES`
  e `SKIP_SUFFIXES`); realce novo = subclasse de `ThemedHighlighter` + tokens em `dark.yaml` **e** `light.yaml`.
- **Validação de SCF:** `core/sniff.py:looks_like_input(path)` (só cabeça, sem ASE, seguro na GUI); o que a spec 25
  exige (`calculation == 'scf'`) vem de `scf_info.read_scf`, que roda em worker.
- **Tarefas e ocupado:** `core/tasks.py` (`run_task`, `TaskGroup`) e `ui/busy.py:BusyTracker`; callbacks na GUI.
- **Aviso de fim:** `ui/widgets/toast.py:Toast`/`show_message(text, level, details)` (spec 17).
- **Seleção no explorador:** `ExplorerPanel.select_path` (como clique na árvore).

## Requisitos

### R1: Botão, ação e controlador
1. `ActivityBar` ganha o botão **"Criar cálculo"** (rótulo curto "Criar" no botão de 46×44, tooltip "Criar
   cálculo (scripts e inputs)"), não checkável, abaixo de "Rsync" na tupla de `bars.py:116`; sinal
   `create_requested`. Ícone novo (`add_circle` ou `calculate`) vendorizado por `scripts/fetch_assets.py`
   (conferir que o arquivo é commitado como os demais).
2. Ação `calc.create` em `ACTIONS` (menu "Ferramentas ▸ Criar cálculo…", sem atalho de teclado por padrão; se a
   spec 18 tiver convenção, usar Ctrl+Shift+N) → `calc_create.open`. A paleta lista a ação sem código novo.
3. `ui/calc_create_controller.py:CalcCreateController.for_window(window)`: recebe `root()` (`local_root` atual),
   `current_folder()` (pasta do explorador), `select_path(path)`, `refresh(folder)`, e o toast (`show_message`). Abre
   `CalcCreateDialog`; **um por vez** (re-levanta o aberto). `MainWindow`: registro do controlador e o `connect`
   do botão (≤ 3 linhas; o arquivo não pode passar de 500).
4. O botão e a ação ficam desabilitados com tooltip "Defina `paths.local_root` para criar cálculos" enquanto
   `local_root` não é uma pasta (estado `missing_root` da spec 18).

### R2: Janela em duas etapas
1. `ui/dialogs/calc_create/dialog.py:CalcCreateDialog` (`QDialog`, não modal para a janela principal mas único,
   `WA_DeleteOnClose`, tamanho inicial ~ 960×640, redimensionável): um `QStackedWidget` com a **Etapa 1
   (Configuração)** e a **Etapa 2 (Arquivos)**, `_show_page`/`_grow` como `sync_dialog.py`. Título "Criar cálculo".
2. Esc, o X da janela e "Cancelar" fecham **sem criar nada** (nenhuma chamada a `writer.create_folder` antes de
   "Criar"). Se a Etapa 2 tem campos editados ou notas, perguntar "Descartar o que foi preenchido?" (Sim/Não).
3. "Voltar" na Etapa 2 retorna à Etapa 1 **sem perder** o que foi preenchido; trocar o tipo ou o SCF na Etapa 1
   reconstrói a Etapa 2 (a janela avisa que os campos voltam aos padrões).

### R3: Etapa 1 — Configuração
Campos (linhas de `QGridLayout`, rótulo à esquerda):
1. **Tipo de cálculo:** `QComboBox` com os `CalcType` do registro da spec 25 (SCF, Relax, VC-Relax, Bandas, PDOS).
2. **Input de SCF** (obrigatório): `QLineEdit` somente leitura + "Escolher…" (`QFileDialog.getOpenFileName`, pasta
   inicial = a do explorador). Ao escolher: `looks_like_input` (GUI) e `read_scf` em worker (spinner "Lendo
   SCF…"); se não é SCF (`ScfError`) mostra a mensagem em vermelho sob o campo. O arquivo escolhido nunca é
   alterado.
3. **Nome da pasta** (obrigatório): sufixo; validação ao vivo de `validate_target` (vazio, caracteres inválidos)
   com mensagem sob o campo.
4. **Local:** `QLineEdit` somente leitura + "Escolher…" (`getExistingDirectory`); padrão = pasta atual do
   explorador (ou `local_root`). O local pode ser qualquer pasta gravável (ver "Decisões assumidas").
5. **Prévia do nome:** linha "Será criada: `bandas_Al`" (ou "`bandas_Al_1` — já existe `bandas_Al`") por
   `preview_name`, atualizada a cada mudança.
6. "Continuar" fica **desabilitado** até: tipo escolhido, SCF válido (já lido), sufixo válido, local gravável. Ao
   continuar, `CalcType.fields(scf)` e `plan` rodam (sem I/O de rede; o k-path do pymatgen roda em worker, R5).

### R4: Etapa 2 — abas
`QTabWidget` (`objectName "calcTabs"`, QSS próprio em `ui/resources/styles/dialogs/calc_create.qss`, domínio já
listado em `STYLE_DOMAINS`) com uma aba por arquivo gerado, na ordem do `CalcPlan.files` da spec 25, mais duas
fixas:
1. **Uma aba por arquivo** (ex.: PDOS → "Script (pdos.qsub)", "SCF (scf.in)", "NSCF (nscf.in)", "projwfc.in"; Bandas →
   "Script", "SCF", "Bandas (bands.in)", "bands_pp.in"). Cada aba é um `QSplitter`: **formulário à esquerda**
   (campos do `CalcType` do grupo daquele arquivo, em `Section`s de `param_widgets`: rótulo, widget, tooltip, marca
   de obrigatório) e **prévia somente leitura à direita** (`CodeView` + `InputHighlighter` para `.in`,
   `ShellHighlighter` para `.qsub`). **O usuário não edita texto**: só preenche campos; a prévia é renderizada de
   novo, debounced (250 ms), a cada edição, por `CalcType.plan` (Jinja + `InputEditor`; sem leitura de
   arquivo, rápido), e destaca em amarelo-claro (`ExtraSelection`, token `hl_changed`) as linhas que diferem do
   SCF original nos inputs derivados.
2. **Padrões:** cada campo abre preenchido com o valor extraído do SCF (spec 25 R3.3); campo apagado volta ao
   padrão do tipo, com a dica "vazio = <padrão>" como `placeholderText`. Campos obrigatórios sem valor
   (vazios sem padrão) ficam marcados e bloqueiam "Criar".
3. **Aba "Bandas" (k-path):** `ui/widgets/kpath_editor.py:KPathEditor` — tabela (rótulo, k1, k2, k3, pontos até o
   próximo), botões adicionar, remover, subir, descer, "Marcar quebra de segmento" e "Sugerir (pymatgen)". Na
   entrada da aba, as sugestões vêm de `kpath.suggest_path` **em worker** (spinner "Calculando caminho de alta
   simetria…" pelo `BusyTracker`); falha ou `KPathUnavailable` → mensagem na aba e tabela vazia para digitação
   manual. O usuário pode alterar tudo. Sem ao menos 2 pontos, "Criar" fica bloqueado.
4. **Aba "k-points" (demais tipos com NSCF, ex. PDOS):** campos `n1 n2 n3` e deslocamentos (spec 25 R5.3), com o
   resumo "N k-points na rede" só como aviso aproximado.
5. **Aba "Script":** `job_name`, `np`, `nk` (e nada do cluster: isso é do `config.yaml`, spec 25 R6.3), com os avisos
   de `np % nk` (rótulo âmbar, nunca bloqueia).
6. **Aba "Arquivos":** lista (`QTreeWidget` ou lista simples) de **tudo que será criado** na pasta final, com
   nome, tipo e tamanho aproximado, mais o caminho completo (`<local>/<pasta final>`), a nota "Se já existir, será
   criada como `<pasta>_1`" e os **avisos** acumulados (`CalcPlan.notes` e validações: `np % nk`, `outdir`
   absoluto, SCF sem estrutura legível, k-path indisponível). `descricao.md` aparece só quando há texto na aba
   Descrição.
7. **Aba "Descrição":** única área de texto livre (`QPlainTextEdit`, placeholder "Anotações sobre este cálculo
   (opcional)"); o texto vai para `descricao.md` na pasta criada, só se não vazio. É anotação do usuário; nada
   interpreta o conteúdo.

### R5: Criar
1. Botões da Etapa 2: "Voltar", "Cancelar" e "**Criar**" (padrão). "Criar" só é habilitado com **todos** os
   obrigatórios preenchidos e sem erro de validação; o tooltip do botão desabilitado diz o que falta
   ("Defina ao menos 2 pontos do caminho"). Avisos (âmbar) não bloqueiam.
2. "Criar" chama `writer.create_folder` em **worker** (`run_task`, spinner "Criando <pasta>…", janela
   desabilitada). Sucesso: fecha a janela, seleciona a pasta nova no explorador (`select_path`), atualiza a pasta
   mãe e mostra toast `success` ("Pasta bandas_Al_1 criada com 4 arquivos") com "Detalhes" (lista dos arquivos e,
   se houve sufixo, o motivo). Falha: `QMessageBox.critical` com o motivo, a janela permanece aberta e nada fica
   pela metade (a limpeza é do writer).
3. Lembrete: o toast termina com "Use ‘Enviar ao cluster’ para levar a pasta ao cluster" quando a sincronização
   está configurada (`config.sync_enabled`); o envio é a spec 27, e **não** é feito aqui.

### R6: Realce de `.qsub`
1. `ui/widgets/highlighters.py:ShellHighlighter(ThemedHighlighter)` com regras para comentários (`#`),
   diretivas `#$ …`, strings, variáveis `${…}`/`$X`, palavras reservadas do shell e `export`/`.`: tokens novos
   `sh_*` (ou reaproveitar `syn_*`) nos **dois** arquivos de tema (`dark.yaml`, `light.yaml`).
2. Escopo: só a prévia da janela. O visualizador de texto de arquivos `.qsub` (spec 4, somente leitura) pode usar o
   mesmo realce, mas isso é opcional nesta spec.

## Fora de escopo
- Editar inputs/scripts como texto, salvar modelos próprios ou criar templates pela interface.
- Tipos de cálculo além dos da spec 25 (dos.x, cargas, ELF).
- Enviar ao cluster ou submeter o job (spec 27 e o próprio cluster).
- Abrir automaticamente os arquivos criados no workspace.
- Atalho global e histórico de cálculos criados.

## Decisões assumidas (confirmar na revisão)
1. A janela é única (uma por vez), com duas etapas no mesmo `QDialog` (como o diálogo de sync), em vez de duas janelas.
2. **Local da pasta:** pode ser qualquer pasta gravável, com padrão na pasta atual do explorador. Se ficar
   fora de `local_root`, a pasta funciona mas a sincronização e a detecção só a enxergam dentro do projeto;
   a Etapa 1 mostra um aviso âmbar nesse caso.
3. A prévia é **somente leitura**: o usuário só mexe nos campos (pedido: "não editar texto manualmente").
4. "Descartar o que foi preenchido?" só aparece com edições ou notas; um cancelamento sem edição fecha direto.
5. Campos vazios → padrão do tipo (pedido), mesmo os extraídos do SCF (apagar o campo volta ao valor do SCF,
   não ao padrão "de fábrica").
6. Botão "Criar cálculo" **abaixo de Rsync** na barra. Em janelas muito baixas a barra já corta pelo fim
   (o botão do tema fica ao fundo); não há rolagem nova.
7. Ícone e rótulo curtos ("Criar") por causa do botão de 46×44 px.

## Notas de implementação
- Novos: `ui/calc_create_controller.py`, `ui/dialogs/calc_create/{__init__,dialog,setup_page,tabs_page,form,preview}.py`
  (cada um < 500 linhas; `form.py` gera widgets a partir de `FormField`, como `params_body.py` faz com
  `ParamField`), `ui/widgets/kpath_editor.py`, `ui/resources/styles/dialogs/calc_create.qss`,
  `ShellHighlighter` em `highlighters.py` (hoje ~140 linhas).
- Alterados: `ui/widgets/bars.py` (botão e sinal), `ui/actions.py` (`calc.create`), `ui/main_window.py` (≤ 3
  linhas), `ui/resources/themes/{dark,light}.yaml` (tokens `sh_*` e `hl_changed`, nos dois), `ui/resources/icons/` + `scripts/fetch_assets.py`,
  `tests/test_main_window.py` (forma da barra).
- Nenhum `open(`/`read_text` em `ui/` (teste de arquitetura): toda leitura (SCF, k-path) e escrita (criar) passa
  por `run_task` + `core/calc_create`; a validação síncrona só usa `looks_like_input` e `preview_name`/
  `validate_target`, que fazem `stat`, não leitura de conteúdo.
- `ui/` não conhece tipos: a lista de tipos, os campos e os arquivos vêm do registro de `core/calc_create`.
- Como em `sync_dialog.py`, páginas escondidas usam política de tamanho `Ignored` para a janela não crescer.

## Critérios de aceite e testes
- [ ] Barra: o botão "Criar" existe e emite `create_requested`; `test_main_window.py` ajustado; ação `calc.create`
      aparece na paleta e no menu Ferramentas; com `local_root` inválido, botão e ação desabilitados.
- [ ] Etapa 1: "Continuar" desabilitado até tipo + SCF válido + sufixo válido + local gravável; SCF que não é SCF
      (`calculation = 'relax'`) mostra o erro e mantém "Continuar" desabilitado; prévia do nome mostra o sufixo
      `_1` quando a pasta já existe.
- [ ] Etapa 2: abas por tipo — PDOS: Script, SCF, NSCF, projwfc.in + Arquivos + Descrição; Bandas: Script, SCF,
      Bandas, bands_pp.in + Arquivos + Descrição; SCF/Relax/VC-Relax: Script, input + Arquivos + Descrição.
- [ ] Campos: abrem com valores do SCF (prefix, nbnd…); apagar volta ao padrão; a prévia muda ao editar (debounce
      injetável); linhas alteradas em relação ao SCF são destacadas; a prévia não é editável.
- [ ] K-path: mock do `suggest_path` povoa a tabela; adicionar, remover, reordenar, quebra de segmento;
      `KPathUnavailable` → tabela vazia e mensagem; menos de 2 pontos → "Criar" desabilitado.
- [ ] "Criar" desabilitado com obrigatório faltando e com tooltip do motivo; avisos de `np % nk` não bloqueiam.
- [ ] Cancelar/Esc/X: a árvore de diretórios fica idêntica (nada criado); com edições, pergunta antes (patch do
      `QMessageBox`).
- [ ] Criar: pasta e arquivos corretos (conteúdo igual ao `CalcPlan`); segunda criação com o mesmo nome → `_1`;
      `descricao.md` só com texto; toast `success`; pasta nova selecionada no explorador; falha simulada →
      `QMessageBox.critical` patchado, janela aberta, nada no disco.
- [ ] Voltar da Etapa 2 preserva a Etapa 1; trocar o tipo reconstrói a Etapa 2.
- [ ] `ShellHighlighter`: `#$ -N`, `#`, `${VAR}` coloridos; tokens existem nos dois temas (teste de temas).
- [ ] `test_architecture.py`: sem `open(`/`read_text` em `ui/`, arquivos < 500 linhas (incluindo `main_window.py`).
