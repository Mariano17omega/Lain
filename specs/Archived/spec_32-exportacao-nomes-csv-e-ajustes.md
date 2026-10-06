# Spec 32: Exportação — nomes com o caminho do projeto, CSV dos dados, roda do mouse no painel de ajustes e botão "Átomos…" da PDOS

| | |
|---|---|
| **Prioridade** | 32 (R1 é um defeito: pode ser implementado e entregue antes do resto) |
| **Status** | Implementada. Desvios:<br>- **`k (2π/alat)`, não `k (Å⁻¹)` (R4.3):** o `x` de `BandData` é o do bands.x, em unidades de 2π/alat, e o dataset não guarda o `alat` para converter; o cabeçalho diz a unidade que o dado tem.<br>- **`core/calculations/listing.py`, não `neighbours.py` (R4.2):** `feeds_parent` usa `IGNORED_SUBDIRS` e os nomes de PDOS, então o que saiu de `base.py` foi `FolderListing` com eles (`base.py` 499 → 454 linhas, reexportando).<br>- **Dez algarismos significativos, não `repr` (R4.1):** `repr` escrevia `-4,7357000000000005` para `E − E_F`; o QE imprime no máximo 8 dígitos, então `.10g` limpa o ruído sem perder dado.<br>- **`plan_export(session, root=None)`:** sem raiz, sem prefixo; só o `PlotExporter` passa a raiz, e os testes de `plan_export` sem raiz não mudaram.<br>- **`join_stem` tira também o `-` inicial** (um prefixo só de pontos deixaria `-bands`); a regra de R3.4 é a mesma.<br>- **O aceite manual (roda real, LibreOffice) não foi feito pelo agente:** o offscreen não o prova (R2.5); fica para o usuário.<br>- **`ruff format --check .` falha em `specs/report-04-10-26.md`**, que já falhava no HEAD (o ruff 0.16.9 formata o bloco de código do Markdown); fora desta spec. |
| **Depende de** | spec 15 (`PlotExporter`, exportação em worker), spec 21 (átomos da PDOS), spec 22 (bandas com DOS), spec 31 (projetos: `local_root` e `project_of`) |
| **Usada por** | nenhuma |
| **Esforço** | G (R1 e R2: P; R3: M; R4: G) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): R3 e R4 mudam contratos usados em vários lugares (`CalculationModule` ganha um hook, `plan_export` / `ExportPlan` / `PlotExporter` mudam de assinatura) e `core/calculations/base.py` está em 499 de 500 linhas. R1 e R2, sozinhos, seriam Sonnet 5.5. |

## Itens de origem (ideias de 06/10/2026)

> - Atualmente os gráficos são salvos com o nome do tipo de gráfico, tipo 'bands.png' e 'pdos.png'. Quero definir um padrão para a
>   geração dos nomes dos gráficos: quero que inclua como prefixo nos nomes dos arquivos a estrutura de pastas partindo da raiz da
>   pasta do projeto, por exemplo:
>   -- Para uma pasta '/projeto_ilita/bulk/bandas/', a imagem gerada é salva com o nome 'projeto_ilita-bulk-bandas-bands.png'.
>
> - Quero que quando os gráficos de Bandas, PDOS, bandas com PDOS forem salvos, seja gerado um arquivo '.CSV' com os dados de todos
>   os eixos dos gráficos e seus respectivos dados, seguindo o padrão abaixo do software origem, com vírgula como separador
>   decimal. O arquivo é salvo na mesma pasta onde fica o gráfico gerado. O nome deve seguir o mesmo padrão de nomeação dos
>   arquivos de imagem, apenas com a extensão '.CSV' em vez de '.png'. O arquivo '.CSV' deve incluir os nomes das colunas.
>   -- Para uma pasta '/projeto_ilita/bulk/bandas/', o arquivo CSV gerado é salvo com o nome 'projeto_ilita-bulk-bandas-bands.csv'.
>
> - Na aba esquerda de configurações do gráfico, quando rolo para baixo ou para cima, se o mouse passar por cima de um dos campos,
>   a rolagem começa a rolar os valores do campo onde o mouse está passando em vez de rolar a tela. Quero que não seja possível
>   rolar os valores dos campos dos parâmetros. Quando rolar com o mouse, quero que role apenas a tela.
>
> - No plot de curvas PDOS, na seção 'PROJEÇÕES', tem o botão 'Átomos' […]. Após marcar os átomos e clicar em salvar, a filtragem não
>   funciona, não acontece nada, e aparece esse erro: `File ".../ui/widgets/params_body.py", line 250, in pick` →
>   `File ".../ui/dialogs/atoms.py", line 114, in ask_atoms: return dialog.answer() if accepted else None`
>   […] Corrija o erro de plotagem do gráfico de PDOS.

Decisões do usuário nesta rodada (06/10/2026): o CSV tem o **layout largo** (x + uma coluna por série), colunas separadas por
**`;`** (a vírgula é o decimal) e a roda do mouse é bloqueada **só no painel de ajustes do gráfico**. O trecho "seguindo o padrão
abaixo do software origem" chegou sem o padrão: o layout acima o substitui.

## Situação atual

- **R1 (átomos da PDOS).** `ui/dialogs/atoms.py:38` liga `WA_DeleteOnClose` em `AtomsDialog`; `ask_atoms` (`:108-114`) roda
  `dialog.exec()` e só **depois** lê `dialog.answer()`. `QDialog::exec` apaga o objeto C++ ao voltar quando o atributo está ligado,
  então `answer()` → `AtomsDialog.checked` (`:83`) → `AtomTable.checked` (`ui/widgets/atom_table.py:141`) → `check.isChecked()` levanta
  `RuntimeError: wrapped C/C++ object of type QCheckBox has been deleted` (reproduzido com `exec` real e um `QTimer.singleShot` que marca
  os átomos e clica "Salvar"; o traceback do usuário está cortado na linha 114). A exceção sai do slot `pick` (`ui/widgets/params_body.py:250`):
  `self._set(name, answer.atoms)` nunca roda, então a seleção não é aplicada, salva no `compounds.json` nem replotada, e o `ExceptionReporter`
  (spec 27-5) mostra o erro. Os testes não pegam: `test_ask_atoms_returns_the_answer_or_none` (`tests/test_atoms_dialog.py:110-124`)
  troca `AtomsDialog.exec` por uma função que clica e volta (sem `exec` real) e os testes do painel (`:153-174`,
  `test_module_contract.py:415`) trocam o `ask_atoms` inteiro. É o único par `exec()` + `WA_DeleteOnClose` de `src/`: os outros modais
  (`rename.py:70-75`, `new_project.py:85`, `open_with.py:84`) não usam o atributo e chamam `dialog.deleteLater()` depois de ler o resultado.
- **R2 (roda do mouse).** Nenhum `wheelEvent`, filtro de roda ou `NoWheel` no repositório. Os campos do painel são criados em
  `ui/widgets/params_body.py`: `QSpinBox` (`:188`, tipo `int`, sem uso hoje), `QComboBox` (`:203`, `choice`) e `QDoubleSpinBox` (`:296`,
  `float`); os demais (`QCheckBox`, `QLineEdit`, `ColorButton`, `SeriesList`, o botão "Átomos…") não reagem à roda. Nada é criado depois:
  `refreshes=True` só reempurra valores por `_setters` (`:354-355`) e `ParamsPanel.bind` reconstrói um `ParamsBody` inteiro
  (`plot_params.py:81-89`). O `QScrollArea` por plot nasce em `plot_params.py:132-137`. Os três widgets têm `focusPolicy`
  `WheelFocus` (medido): a roda também lhes dá foco, e dali em diante Up/Down muda o valor. `Section` (`param_widgets.py:82`, `:96`) é
  compartilhada com o formulário de "Criar cálculo", que tem o mesmo problema (`calc_create/form.py:125`, `kmesh.py:30`,
  `kpath_editor.py:114`), assim como a tabela de células do grid (`dialogs/grid_cells.py:114`, `:121`): fora de escopo (ver abaixo).
- **R3 (nomes).** `CalculationModule.export_stem(params)` (`core/calculations/base.py:413-415`) devolve `self.kind` (`bands`, `pdos`,
  `bands_dos`, `scf`); `relax.py:55-60` devolve `relax`, `relax_energia`, `relax_forca` ou `relax_todos`; `grid/module.py:52-53` devolve
  `grid_<nome>`. O único chamador é `core/plotting/export.py:plan_export` (`:56-71`, na thread da GUI, que também faz `existing_targets` e
  `next_free_stem`: `<stem>_2`, `_3`…). `export_figure` (`:98-130`) escreve `plots/<stem>.<fmt>` por arquivo temporário + `os.replace`.
  O export **não conhece a raiz**: `PlotSession` (`core/plotting/session.py:34-41`) não guarda `local_root`, `PlotExporter(busy,
  dialog_parent, parent)` (`ui/plot_export.py:30`) não recebe config; `PlotWorkflow` tem `self._config()` (`plot_workflow.py:95`) e o
  constrói em `:116`. `core/projects.py:project_of` (`:75-82`) é puro (`relative_to`, sem resolver). A pasta de cada módulo: bandas, PDOS e
  relax = a pasta detectada; SCF = a pasta da saída; bandas + DOS = a pasta das bandas (`bands_dos/pair.py:54`); grid = a **raiz**
  (`grid/data.py:36-42`, `<local_root>/plots/grid_<nome>.*`). Arquivos de `plots/` nunca entram na detecção (`IGNORED_SUBDIRS`,
  `base.py:43`), nunca sobem no push (`DEFAULT_PUSH_EXCLUDES`) e `plots` não é projeto (`projects.py:29`).
- **R4 (CSV).** Não existe escritor de CSV nem função das "séries plotadas": o que a figura desenha está nos closures de
  `pdos/render.py` (`draw`, `channel`) e em `bands/render.py` (`draw_plain`, `_draw_channel`, que subtraem a referência). Os dados:
  `BandsDataset` (`bands/data.py:88-109`: `bands: BandData` com `x[k]` e `energies[banda, k]` em eV absoluto, `bands_down`,
  `reference(mode)` em `:124-131`, `shown_channels` em `bands/render.py:35-39`); `PdosDataset` (`pdos/data.py:16-34`) com
  `projwfc.aggregate(data, grouping, atoms)`, `selected_total`, `spin_mode` (`pdos/render.py:65-69`), `series_label` (`:25-27`),
  `hidden_series`, `show_total` e `shift_to_fermi`; `BandsDosDataset` (`bands_dos/data.py:16-22`) usa **uma** referência, a das bandas
  (`bands_dos/render.py:43`). Em bandas + DOS o x das bandas (k) e o da DOS (E) têm comprimentos diferentes: uma tabela retangular
  só serve com dois blocos. Convenção do repo: ponto decimal em todo lugar (`QLocale.c()` no painel, `LC_ALL=C.UTF-8` no rsync); a vírgula
  decimal é uma exceção deliberada deste CSV. `core/appdirs.py:atomic_write_text` (`:63-81`) não controla `newline=`. `base.py` tem 499
  linhas (`PER_FILE_LIMIT` 500); `plot_workflow.py` 476 e `main_window.py` 447 (limite 450).

## Requisitos

### R1: O botão "Átomos…" da PDOS aplica a seleção (defeito)

1. Tirar `WA_DeleteOnClose` de `AtomsDialog`. `ask_atoms` lê o resultado e só então `dialog.deleteLater()`, como `ask_rename`
   (`rename.py:70-75`): o objeto vive até a resposta ser lida. O diálogo continua com `setModal(True)` e dono (`parent`), então não vaza.
2. O botão "Salvar" aceita a seleção, o painel chama `self._set(name, answer.atoms)` (`params_body.py:251-253`) e o plot é refeito
   com os átomos escolhidos; o `compounds.json` grava a seleção (`PlotSession.persist`, spec 21). Nada mais muda no fluxo: com o
   `ask_atoms` trocado, o caminho `_set` → `persist` → `replot` já tem testes que passam.
3. **Teste com `exec` real** (a lacuna que escondeu o defeito): um `QTimer.singleShot` acha `QApplication.activeModalWidget()`, marca
   átomos e clica em "Salvar" enquanto o `exec()` verdadeiro roda. Dois testes: `ask_atoms` devolve `AtomsAnswer([...])` / `None`
   (Cancelar) com `exec` real, e o clique no botão "Átomos…" do painel (só o diálogo é real) deixa `session.params.atoms` com a escolha,
   o `compounds.json` com ela e a figura com menos séries; `qtbot.capture_exceptions()` volta vazio nos dois.
4. Regra para o `CLAUDE.md` ao implementar: *um modal rodado com `exec()` não usa `WA_DeleteOnClose`: o `exec` apaga o objeto antes de o
   chamador ler a resposta; leia, depois `deleteLater()`*.

### R2: A roda do mouse só rola o painel de ajustes

1. Novo módulo `ui/widgets/no_wheel.py` com `NoWheelSpinBox(QSpinBox)`, `NoWheelDoubleSpinBox(QDoubleSpinBox)` e
   `NoWheelComboBox(QComboBox)`. Cada um liga `setFocusPolicy(Qt.FocusPolicy.StrongFocus)` no `__init__` (a roda deixa de dar foco; Tab e clique
   continuam) e sobrescreve `wheelEvent(event)` com `event.ignore()`: o evento sobe até o `QScrollArea` do painel, que rola. Docstring com o
   "Reusable:" do repo (CLAUDE.md); sem lógica de `core/`.
2. `params_body.py` passa a criar essas subclasses nos três pontos (`:188`, `:203`, `:296`); o import troca as classes `Q…`. Sem mudança de
   QSS (os seletores de tipo `QSpinBox`/`QDoubleSpinBox`/`QComboBox` casam as subclasses: `inputs.qss:2`, `:69-76`, `:32`).
3. Continuam valendo: digitar no campo, setas e Page Up/Down com o campo focado, arrastar nas setas do spin, o clique que abre o combo e
   a **lista aberta** do combo (uma janela de popup própria, que não passa pelo `wheelEvent` do combo), Tab e a ordem de foco
   (`FocusController` só pergunta `focusPolicy != NoFocus` e `TabFocus`, `StrongFocus` os tem).
4. Nenhuma roda altera um valor do painel, sobre qualquer posição do campo (a área de texto do spin repassa ao spin, que ignora).
5. **Limite dos testes:** o offscreen só entrega `QWheelEvent` por `QApplication.sendEvent` (evento não espontâneo, que o Qt não propaga ao
   pai); a propagação até o `QScrollArea` com a roda real fica num **passo manual de aceite** (abaixo). Se falhar na prática, o plano B é o
   `wheelEvent` reenviar o evento ao `viewport()` do `QScrollArea` ancestral (o primeiro `QAbstractScrollArea` da cadeia de pais) em vez de só
   ignorá-lo: o contrato do R2.4 é o mesmo e os testes não mudam.

### R3: Nome das figuras com o caminho a partir da raiz

1. **Padrão.** `stem = <prefixo>-<sufixo do módulo>`, em que o prefixo são os componentes de `folder.relative_to(local_root)` unidos por
   `-` e o sufixo é o `export_stem(params)` de hoje. Com `local_root = ~/sim`, a pasta `~/sim/projeto_ilita/bulk/bandas` exporta
   `plots/projeto_ilita-bulk-bandas-bands.png` (e `.svg`, `.pdf`, `.csv`, R4). Relax: `…-relax_energia.png`; SCF: `…-scf.png`
   (redundante, mas é a regra); bandas + DOS: o prefixo da pasta das bandas, `…-bands_dos.png`.
2. **Onde mora.** Novo `core/plotting/names.py` (Qt-free, em `QT_FREE` do `test_architecture.py`): `export_prefix(folder, root) -> str` e
   `join_stem(prefix, suffix) -> str`. Puro: nada é resolvido nem lido do disco (como `project_of`). `plan_export(session, root)` recebe a
   raiz e compõe o stem; `ExportPlan.stem` já é o nome completo, então `existing_targets`, `next_free_stem` (`<stem>_2`) e o diálogo de
   sobrescrever não mudam.
3. **De onde vem a raiz.** `PlotExporter(busy, dialog_parent, parent=None, *, root: Callable[[], Path])` chama `root()` a cada export (um
   "Recarregar config.yaml" e o `use_session_root` valem na hora); o `PlotWorkflow` passa `lambda: self._config().paths.local_root` (duas
   linhas: `plot_workflow.py` e `main_window.py` não têm folga, a lógica fica em `core/`). `PlotSession` não ganha campo.
4. **Casos de borda** (tudo em `names.py`):
   - pasta igual à raiz: **sem prefixo** (`bands`, como hoje). O grid, cuja `folder` é a raiz, fica `grid_<nome>` sem tratamento especial;
   - pasta fora da raiz (`relative_to` falha): só o **nome da pasta** (`dummy_sim-dummy`);
   - componente com ponto inicial: perde os pontos iniciais do **stem inteiro** (nada de arquivo oculto nem colisão com os temporários
     `.<nome>.tmp`);
   - tamanho: o stem tem no máximo `MAX_STEM_BYTES = 180` bytes UTF-8 (sobram `_NN`, `.svg`/`.csv` e o `.….tmp` dentro dos 255 do
     sistema de arquivos): corta **componentes inteiros pela esquerda** (a pasta da simulação e o sufixo sobrevivem); se um só componente
     ainda estourar, é truncado pelo fim (em fronteira de caractere);
   - `_remove_orphans` (`export.py:91-95`) passa a usar `glob.escape(stem)`: o stem agora carrega nomes de pasta do usuário
     (`[`, `]`, `*`, `?`);
   - o `-` dentro de um nome (`VC-Relax_Si`) deixa o stem ambíguo, e isso é inofensivo: cada arquivo mora no `plots/` da **sua** pasta.
5. **Sobrescrever.** O conjunto (imagens + CSV) é uma unidade: `existing` lista qualquer um que já exista; "Nova versão" dá
   `<stem>_2.png/.svg/.pdf/.csv`; "Sobrescrever" troca todos. O texto do diálogo (`ui/dialogs/overwrite.py:35`) passa de "Figuras com
   este nome já existem em plots/" para "Arquivos com este nome já existem em plots/".
6. **Arquivos antigos** (`plots/bands.png`) não são migrados, renomeados nem apagados; renomear uma pasta também não renomeia os
   exports dela (como hoje). Ao implementar: atualizar `README.md:19`, `spec_0-PRD.md` §4.4 (`plots/` e o padrão de nomes) e o
   `CLAUDE.md` ("`core/plotting/export.py` writes into `<simulation>/plots/`…").

### R4: CSV com os dados dos gráficos de Bandas, PDOS e Bandas + DOS

1. **Núcleo** `core/plotting/table.py` (Qt-free, em `QT_FREE`): `Column(name: str, values: Sequence[float])`, `PlotTable(columns)` e
   `to_csv(table) -> str`. Formato: **primeira linha = nomes das colunas**; colunas separadas por `;`; decimal com vírgula; fim de linha `\n`;
   UTF-8 **com BOM** (o Excel e o LibreOffice em pt-BR leem `π` e `↑` certo; ver "Decisões assumidas"); número = `format(v, ".10g")` com
   `.` → `,` (10 algarismos significativos: o QE imprime no máximo 8, e o ruído de 1e-16 da subtração `E − E_F` não vira dígitos; `1.5e-07` → `1,5e-07`); `NaN`/`inf` e o fim de uma coluna mais curta que as
   outras = **célula vazia**; nome com `;`, `"` ou quebra de linha entre aspas (módulo `csv` do stdlib com `delimiter=";"`). Sem
   cabeçalho de comentário (quebraria a importação): a referência de energia vai no nome das colunas.
2. **Hook** em `CalculationModule`: `table(self, dataset: D, params: P) -> PlotTable | None`, padrão `None` (SCF, relax, grid e o
   `DummyModule` do contrato não têm CSV). Só `bands`, `pdos` e `bands_dos` o implementam. **Sem kind na UI nem em `export.py`**: quem exporta
   pergunta ao módulo. Para o hook caber em `base.py` (499 linhas), extrair para `core/calculations/listing.py` o `FolderListing`, os ajudantes de
   nomes de PDOS e o `IGNORED_SUBDIRS` (~55 linhas) e reexportá-los de `base`, para os importadores atuais (`detection.py`, os módulos) não
   mudarem. (A spec propunha as funções de vizinhança; `feeds_parent` depende de `IGNORED_SUBDIRS` e dos nomes de PDOS, que ficariam presos.)
3. **Conteúdo: o que a figura desenha, sem recortar pela janela.** Valores como plotados (energia menos a referência); `emin/emax/xmin/xmax`
   são só vista: o CSV tem a série inteira (o `.plot` guarda a vista). Rótulo da referência pelo modo: `E−E_F`, `E−VBM`, `E−gap médio`, `E`
   (absoluta).
   - **Bandas** (`bands/table.py`): `k (2π/alat)` (a unidade do bands.x: o dataset não guarda o `alat` para converter para Å⁻¹), depois `Banda 1 (E−E_F, eV)` … `Banda N (E−E_F, eV)`. Com spin, `Banda n ↑ (…)` e
     `Banda n ↓ (…)` só dos canais mostrados (`shown_channels`, ou seja `spin_channels` `both`/`up`/`down`); se o x do ↓ não for igual ao do
     ↑ (a spec 13 os supõe iguais, mas não o garante), o ↓ ganha a coluna `k ↓ (2π/alat)` própria antes das suas bandas.
   - **PDOS** (`pdos/table.py`): `E − E_F (eV)` (ou `E (eV)` com `shift_to_fermi` desligado) e uma coluna por série **desenhada**:
     `aggregate(data, grouping, atoms)` sem as `hidden_series`, mais "Total" / "Soma dos átomos selecionados" quando `show_total` (o mesmo
     `_total` do render, `pdos/render.py:194-199`); nome = `series_label` mais ` ↑`/` ↓` e `(estados/eV)`; os modos de spin como
     desenhados: `mirror` (↓ **negativo**), `overlay`, `up`, `down`, `sum`. A orientação (horizontal/vertical) não muda o CSV.
   - **Bandas + DOS** (`bands_dos/table.py`, `bands_view` / `dos_view` de `bands_dos/params.py:83-90`): os dois blocos lado a lado, o das
     bandas (`k` + bandas) e o da PDOS (`E` + séries), cada um com o **seu** x e a referência única das bandas; o bloco mais curto fica em
     branco até o fim da tabela. Sem coluna separadora (cada bloco começa pelo seu x).
4. **Funções paralelas, não refatoração.** `bands/table.py`, `pdos/table.py` e `bands_dos/table.py` reusam os ajudantes que já existem
   (`reference`, `shown_channels`, `aggregate`, `_total`, `spin_mode`, `series_label`) em vez de extrair as séries dos closures de
   `pdos/render.py` (os goldens de `test_figure_regression.py` ficam como estão). O risco é a tabela e o desenho divergirem: um teste de
   **consistência** (R4.8) compara as colunas com os dados dos artistas da figura renderizada.
5. **Escrita.** `export_figure` e seus testes **ficam intactos** (`tests/test_plotting.py:187-202` fixam a listagem de `plots/` e o
   `ValueError` de formato inválido). Novo em `core/plotting/export.py`: `table_path(folder, stem)` (`plots/<stem>.csv`, `.csv`
   minúsculo), `write_table(path, table)` (temp `.<nome>.tmp` + `os.replace`, como as imagens; o `to_csv` roda fora do `MPL_LOCK`, pois não
   toca no matplotlib) e `export_files(module, dataset, params, style, folder, stem, formats, tables)`: chama `export_figure` e depois
   escreve o CSV se `module.table(dataset, params)` não for `None`, devolvendo as imagens + o CSV. É o que o worker do `PlotExporter` roda
   no lugar de `export_figure`.
6. **Plano.** `ExportPlan` ganha `table: bool` (o módulo tem CSV: `plan_export` pergunta a um método barato do módulo, ver nota de
   implementação) e o `.csv` entra em `existing` e em `next_free_stem` (R3.5). Sem formato de imagem selecionado continua o erro "Selecione ao
   menos um formato de exportação." (`export.py:65-68`): o CSV acompanha o salvamento, não o substitui. O CSV **não é** um valor de
   `export_formats` / `ExportFormat` (`core/config.py:43`), nem tem checkbox nem chave no `config.yaml`: é sempre gerado nos três
   módulos, como o pedido diz.
7. **UI.** `export_finished` passa a trazer também o `.csv` (`written`); a mensagem "Salvo em plots/: a.png, a.svg, a.pdf, a.csv" vem do
   mesmo `_on_done`. O `.csv` já abre no visualizador de texto (`file_kinds.py:17`) e a grade o mostra sem mudança.
8. **Testes de consistência** com a figura (`tests/figure_structure.py` como base): bandas — cada coluna `Banda n` é igual ao `y` do
   segmento correspondente do `LineCollection`, no modo de referência `fermi` e `vbm`; PDOS — cada coluna é igual ao `ydata` de um `Line2D`
   de série (com átomos filtrados, série oculta, `mirror` e `overlay` de uma fixture de spin); bandas + DOS — os dois blocos contra os dois
   eixos.

## Fora de escopo

- CSV de SCF, relax e grid (o pedido cita Bandas, PDOS e bandas com PDOS); o hook `table` os deixa abertos (módulo novo = implementar o hook).
- A linha de Fermi, as posições e rótulos dos pontos de alta simetria e a janela de energia no CSV: só as séries das curvas.
- Colunas ou linhas recortadas pela vista do gráfico.
- Migrar, renomear ou apagar exports antigos (`bands.png`), renomear exports junto com a pasta, e o prefixo no grid (`grid_<nome>` fica).
- A roda do mouse nos formulários de "Criar cálculo" e na tabela do grid: o `ui/widgets/no_wheel.py` é reutilizável, o escopo da decisão do
  usuário é o painel de ajustes.
- CSV como formato de exportação do `config.yaml`, checkbox "CSV" no painel e escolha do separador ou do decimal.
- Localização do texto das colunas (spec `end`, internacionalização): os nomes saem em português como o resto da interface.

## Decisões assumidas (confirmar na revisão)

1. **Layout largo** (x + uma coluna por série) e **`;`** como separador de colunas: decisões do usuário. O "padrão do software de origem" não
   chegou na mensagem; se for outro (por exemplo, o formato do `.gnu` do bands.x ou das colunas `pdos_atm#…` do projwfc.x), muda só os
   `table.py` e os testes de consistência.
2. **UTF-8 com BOM.** Faz o Excel pt-BR abrir `π`, `↑` e acentos sem pedir codificação; o preço é um U+FEFF no primeiro nome de coluna
   para quem lê com `encoding="utf-8"` (com `utf-8-sig` não há). Sem BOM é uma linha em `to_csv`.
3. **Como plotado e sem recorte** pela janela de energia e de k; o ↓ da PDOS no modo espelho sai **negativo**, como no desenho.
4. **`-` como separador** mesmo com `-` nos nomes (`VC-Relax_Si`): a ambiguidade não gera colisão (cada `plots/` é de uma pasta).
5. **Fora da raiz** o prefixo é só o nome da pasta; **pasta = raiz** não tem prefixo.
6. **O CSV acompanha as imagens**: não há exportação só de CSV, não há checkbox e ele não é um valor de `export_formats`.
7. **`.csv` minúsculo**, como no exemplo do pedido (`…-bands.csv`), apesar do `.CSV` do texto.
8. **R1 corrige no diálogo** (sem `WA_DeleteOnClose`) e não no chamador, para a regra valer para o próximo modal.

## Notas de implementação

- **Ordem sugerida:** R1 (um commit pequeno, independente), R2, R3, R4 (o CSV usa o stem de R3 e o worker de R3.3). R1 e R2 também podem
  ir antes da 28/29.
- **Arquivos novos:** `ui/widgets/no_wheel.py`, `core/plotting/names.py`, `core/plotting/table.py`, `core/calculations/listing.py`,
  `core/calculations/bands/table.py`, `core/calculations/pdos/table.py`, `core/calculations/bands_dos/table.py`.
- **Alterados:** `ui/dialogs/atoms.py`; `ui/widgets/params_body.py` (três construtores; 368 linhas); `core/plotting/export.py`
  (`plan_export(session, root)`, `table_path`, `write_table`, `export_files`, `_remove_orphans`; 130 → ~190 linhas);
  `ui/plot_export.py` (`root=`, `export_files` no lugar de `export_figure`; 101 linhas); `ui/plot_workflow.py` (a linha do
  `PlotExporter(…, root=…)`: 476 → ~478); `core/calculations/base.py` (extração + hook: 499 → ~470); `bands/module.py`, `pdos/module.py`,
  `bands_dos/module.py` (o hook `table`, uma linha cada); `ui/dialogs/overwrite.py` (texto). Nenhum arquivo passa de 500 linhas
  (`test_architecture.py`); `ui/main_window.py` não muda.
- **`ExportPlan.table`:** `plan_export` roda na GUI e não pode calcular a tabela (custa leitura de arrays). Um método barato do módulo diz se
  ele tem CSV sem calcular: `has_table: ClassVar[bool] = False` na base, `True` nos três módulos (como `render_in_worker`, `selectable`, outros
  ClassVars do contrato). `table()` só roda no worker.
- **Hook e UI:** nenhum arquivo de `ui/` sabe qual módulo tem CSV: `PlotExporter` passa o módulo da sessão a `export_files`.
- **Testes a alterar** (nomes que mudam de `bands.png` para `<prefixo>-bands.png`, ou que ganham o `.csv`): `test_plot_workflow.py`
  (`:67-94`, `:267-296`, `:579`, as listagens de `:524-531`), `test_export_worker.py` (`:57-61`, `:100-104`), `test_plot_workflow_unit.py`
  (`:107-119`; o `Rig` tem `local_root=demo_project`, então `03_bands` vira o prefixo), `test_bands_dos_ui.py` (`:125-128`),
  `test_module_contract.py` (`:163-193`: o `dummy_folder` está fora da raiz, prefixo = nome da pasta; o `DummyModule` fica sem `table`),
  `test_plot_session.py` (`:140-157`: `plan_export(session, root)`), `test_dialogs.py:52-66` (texto do diálogo). `test_grid_workflow.py:125`
  e `test_grid_render.py:204-212` não mudam (pasta = raiz). `test_plotting.py` não muda (`export_figure` intacto).
- **Documentação ao implementar:** `CLAUDE.md` (Plotting: o stem e o CSV; Threading: o worker do export; a regra do `exec()` sem
  `WA_DeleteOnClose`; "Focus": `no_wheel`), `README.md:19`, `spec_0-PRD.md` §4.4; mover esta spec para `Archived/` e ajustar o link do roadmap.

## Critérios de aceite e testes

- [x] **R1:** `ask_atoms` com `exec` real devolve `AtomsAnswer([..])` ao salvar e `None` ao cancelar; o clique em "Átomos…" no painel de PDOS
  deixa `session.params.atoms` com a escolha, grava o `compounds.json` e refaz a figura com menos séries; `qtbot.capture_exceptions()` vazio.
  `AtomsDialog` não liga `WA_DeleteOnClose` (`tests/test_atoms_dialog.py`).
- [x] **R2:** `tests/test_no_wheel.py`: um `QWheelEvent` enviado a cada `QAbstractSpinBox` e `QComboBox` de um painel de bandas e de PDOS (por
  `findChildren` do `window.params.body`) não muda `value()` nem `currentIndex()`, deixa `isAccepted()` falso, e o campo tem
  `focusPolicy() == StrongFocus`; um teste varre o corpo e falha se achar `QSpinBox`/`QDoubleSpinBox`/`QComboBox` que não seja a subclasse;
  `qtbot.keyClick(spin, Key_Up)` e `setValue` ainda mudam o valor.
- [x] **R3:** `tests/test_export_names.py`: `~/sim/projeto_ilita/bulk/bandas` → `projeto_ilita-bulk-bandas`; pasta = raiz → vazio e stem `bands`;
  fora da raiz → nome da pasta; `.oculta/x` sem ponto inicial; stem acima de `MAX_STEM_BYTES` corta componentes pela esquerda; `glob.escape` (pasta
  `a[1]` não apaga temporário de outra); `plan_export(session, root)` com `existing`/`new_stem` (`…-bands_2`). `tests/test_export_csv_ui.py`
  (janela sobre a fixture `raiz`): uma pasta de bandas em `ilita/Analise_1/Bandas` exporta `plots/ilita-Analise_1-Bandas-bands.png` e
  `.csv`; um segundo export pergunta, "Nova versão" dá `…-bands_2.*`; "Recarregar config.yaml" com outra raiz muda o prefixo no export seguinte.
- [x] **R4:** `tests/test_plot_table.py`: `to_csv` (`;`, vírgula decimal, BOM, primeira linha de nomes, `NaN` e coluna curta vazios, aspas num nome com
  `;`, `1.5e-07` → `1,5e-07`); bandas sem spin, com spin (`↑`/`↓`, `spin_channels` `up`) e com x do ↓ diferente; PDOS com `atoms`,
  `hidden_series`, `show_total`, `shift_to_fermi` desligado e os cinco `spin_mode` (fixtures `qe731_ni_spin_*`); bandas + DOS com os dois blocos e
  colunas de comprimentos diferentes; **consistência com a figura** (R4.8); SCF, relax e grid: `module.table(...)` é `None` e nenhum `.csv`
  aparece. `export_figure` continua sem escrever CSV (`test_plotting.py` sem mudança).
- [x] **Arquitetura:** `base.py` ≤ 500 linhas depois do hook; `names.py`, `table.py` e `listing.py` em `QT_FREE` e importam sem PyQt6; nenhum arquivo de `ui/` com `kind ==`; `test_no_file_of_the_ui_knows_the_dummy_module` passa.
- [x] `uv run pytest -m "not realdata and not perf"`, `uv run ruff check . && uv run ruff format --check .` (menos o `report-04-10-26.md`, ver o Status) e `uv run pyright` limpos.
- [ ] **Aceite manual (pendente: precisa do mouse real e do LibreOffice)** (o offscreen não prova a roda real nem a leitura pelo LibreOffice): (1) abrir um plot de bandas e rolar o painel de ajustes
  com o mouse sobre campos numéricos e listas: só o painel rola, nenhum valor muda; (2) na PDOS, "Átomos…", marcar alguns átomos, "Salvar": a figura
  é refeita e some o erro; (3) exportar bandas e abrir o `.csv` no LibreOffice: colunas separadas, vírgula decimal, `π`, `↑` e acentos certos, nomes na
  primeira linha.
