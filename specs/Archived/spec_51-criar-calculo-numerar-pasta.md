# Spec 51: "Criar cálculo" — caixa "Numerar" no nome da pasta

| | |
|---|---|
| **Prioridade** | 51 (independente das demais; mexe só no passo 1 da janela e no nome da pasta) |
| **Status** | Implementada. Ajuste ao R1.2 e ao R2.3: `writer.preview_names` devolve o nome pedido e o final numa só listagem do local (`target_text` e a aba "Arquivos" o usam), para o "já existe X" e o nome mostrado virem da mesma conta; `preview_name` continua (o "Criando …" do controlador). O teste da janela principal usa o `demo_project`, que já tem `01_relax` … `04_pdos`: a pasta criada é `5_PDOS_Al` (zeros à esquerda contam). O `CLAUDE.md` não mudou: ele guarda só as regras do projeto inteiro, não a descrição das funcionalidades. |
| **Depende de** | spec 25/28 (`writer.folder_name`, `preview_name`, `create_folder`), spec 26 (a janela) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho do nome da pasta que as specs 25–28 abriram; poucos arquivos e nenhum perto do limite. |

## Itens de origem (`Ideias.md`)

> Além disso, quero que na criação de um calculo, tenha um botão Checkbox, 'Numerar', quando ele for marcado, ele vai adicionar uma numeração no prefixo do nome da pasta criada. Essa numeração é opcional, e vai seguir a ordem de numeração se já tiver outras pastas com o mesmo prefixo. A numeração considera todas as pastas presentes dentro da pasta onde vai ser criado o calculo, ou seja, não é restrito ao tipo de calculo, por exemplo: "0_Relax", "1_Bands", "PDOS".

Interpretação: o "prefixo" de que ela fala é o número antes do `_`; a pasta nova recebe `<N>_` na frente do nome de hoje (`Bands_Al` → `2_Bands_Al`), com
`N` = o maior número já usado entre as pastas irmãs + 1. Os três nomes do exemplo são de **tipos diferentes** de propósito: a numeração atravessa os tipos, e
**todo cálculo que o programa gera é numerável**, o PDOS como os outros (`0_Relax`, `1_Bands`, e o PDOS que vem a seguir é `2_PDOS`). Nenhum tipo é excluído da caixa
nem da conta: uma pasta numerada de qualquer tipo, `2_PDOS` inclusive, conta para o número da próxima.

## Situação atual

- `core/calc_create/writer.py:49-51`: `folder_name(type_, suffix)` = `<folder_prefix>_<nome>` ou só o `folder_prefix`. Os dez tipos do `REGISTRY` passam por ele, sem exceção, e
  são os dez que a caixa cobre: `SCF`, `Relax`, `VC-Relax`, `Bands`, `PDOS`, `Charge`, `Diff_Charge`, `Slab`, `Supercell`, `Adsorption`.
  `preview_name(parent, type_, suffix)` (`:76-78`) é o nome livre agora (`next_free_dir`: `_N` **no fim** se o nome existe) e `create_folder(parent, type_, suffix, plan, notes)`
  (`:109-…`) cria a pasta com `make_new_dir(parent / folder_name(...))` (`core/unique_names.py:91-101`, `mkdir` em laço) no worker. **Nada numera.**
- Quem chama: `core/calc_create/preview.py:97-103` (`target_text`: "Será criada: <nome>" e "— já existe <pedido>"), `ui/dialogs/calc_create/tabs_page.py:353-356`
  (`_show_files`, a aba "Arquivos", via `set_target(parent, suffix, warnings)`), `ui/calc_create_controller.py:160` (`create`: o texto "Criando <nome>…") e `:164-171` (o
  `run_task(create_folder, …)`), `ui/dialogs/calc_create/dialog.py:51-56,273-277` (`CreateRequest(parent, calc_type, suffix, plan, notes)` e `request_create`).
- O passo 1 é `ui/dialogs/calc_create/setup_page.py`: o campo `suffix_edit` ("Nome da pasta", opcional; `suffix` `:158-160`), `_update` (`:262-288`) que valida o
  nome, mostra `name_preview` e emite `changed`. O modo Padrão/Avançado é lembrado em QSettings `calc_create/mode` (`dialog.py:MODE_KEY`, `settings=` do diálogo).
- Nomes que o resto do programa lê: `core/plotting/names.export_prefix` junta as pastas da raiz ao projeto (`0_Relax` entra tal como é no nome das figuras); a detecção
  chama "vizinha SCF" qualquer irmã com `scf` no nome (`core/calculations/base.py:42-47`, sem diferenciar maiúsculas): `0_SCF` casa como `SCF`. O número não muda
  nenhuma regra de detecção (**não verificado em execução**: sem pasta numerada nas fixtures de `calc_helpers`).
- Tamanhos: `ui/dialogs/calc_create/setup_page.py` 296, `tabs_page.py` 377, `dialog.py` 319, `core/calc_create/writer.py` 142, `ui/calc_create_controller.py` 199.

## Requisitos

### R1: o número da próxima pasta (`core/`)

1. `core/calc_create/numbering.py` (novo, Qt-free): `next_number(parent: Path) -> int`. Uma `os.scandir(parent)`; cada **pasta** (`entry.is_dir()`) cujo nome casa
   `^([0-9]+)_` conta o seu número, **seja qual for o tipo de cálculo que a pasta guarda** (a regra olha só o nome: `2_PDOS`, `1_Bands` e `0_Relax` contam do mesmo
   jeito); devolve o maior + 1, ou `0` se nenhuma casa ou a pasta não pode ser lida (`OSError`). Arquivos, nomes sem número (`plots`, `Notas`),
   nomes com ponto no início (`.lain`) e um número sem `_` (`3`, `3.old`) são ignorados. Os números são decimais, sem preenchimento de zeros e sem teto de
   dígitos (`03_bands` conta como 3 → a próxima é `4_…`; `12_a` e `2_b` → `13`). Os buracos não são reusados (`0_a` e `5_b` → `6`).
2. `writer.folder_name(type_, suffix, number: int | None = None)`: com `number`, `f"{number}_{nome de hoje}"` (`2_Bands_Al`, `2_Bands`, `2_PDOS`); sem, igual a hoje.
   Vale para todo `CalcType` do `REGISTRY`: o número entra em `folder_name`, que é de onde os dez tipos tiram o nome, e nenhum tipo tem caminho próprio para a pasta
   nem uma lista de "tipos que não numeram".
   `preview_name(parent, type_, suffix, numbered=False)` e `create_folder(parent, type_, suffix, plan, notes="", numbered=False)` chamam `next_number(parent)` quando
   `numbered` (no `create_folder`, **dentro do worker, logo antes do `make_new_dir`**, para o número ser o do momento da criação). O `_N` de colisão continua no fim
   (`2_Bands_Al_1`); `validate_suffix` não muda (o número não vem do campo). `Created.folder` traz o nome final, e o toast/“Arquivos” dizem o nome real.
3. **Testes** (`tests/test_calc_numbering.py`, `tmp_path`): pai vazio → `0`; `0_Relax`, `1_Bands`, `2_PDOS` → `3`; `0_Relax`, `1_Bands` e `Notas` (sem número) → `2`;
   `0_a` e `5_b` → `6`; `12_a` e `2_b` → `13`; `03_bands` → `4`; `7_x.txt` (arquivo) e `.3_x` (oculta) e `3` e `3.old` ignorados; pai inexistente → `0`;
   `folder_name(type, "Al", 2) == "2_Bands_Al"` e sem nome `"2_Bands"`; `create_folder(..., numbered=True)` num pai com `0_Relax`, `1_Bands` cria `2_Bands_Al`, e uma
   segunda criação `3_Bands_Al`; com `numbered=False` o nome é `Bands_Al` (o padrão não muda); a colisão de nome numerado dá `_1` no fim.
   **Todos os tipos** (parametrizado sobre `REGISTRY`, nenhum de fora): `folder_name(t, "Al", 4) == f"4_{t.folder_prefix}_Al"` e `folder_name(t, "", 4) ==
   f"4_{t.folder_prefix}"`; `preview_name(pai, t, "Al", numbered=True)` num pai com `0_Relax`, `1_Bands` dá `2_<prefixo>_Al`; e `create_folder(..., numbered=True)` do PDOS
   (e de um tipo de cada família: `scf`, `charge_diff`, `slab`) cria `2_PDOS_Al` etc., com o plano que `tests/calc_helpers.py` / `test_calc_create_matrix.py` já montam
   para o tipo. Uma sequência `0_Relax` → `1_Bands` → `2_PDOS` criada pelo `create_folder` numerado, tipo após tipo, dá esses três nomes.

### R2: a caixa "Numerar" no passo 1

1. `SetupPage.number_check` = `QCheckBox("Numerar")` na linha do "Nome da pasta" (abaixo do campo e acima de `name_preview`), `objectName` `numberCheck`, desmarcada na
   primeira vez; `accessibleName` "Numerar"; tooltip "Põe um número antes do nome da pasta, seguindo as pastas que já existem aqui (0_Relax, 1_Bands…)". Propriedade
   `numbered`. Ligar/desligar chama `_update` (como o campo de nome) e muda o `name_preview` na hora: "Será criada: 2_Bands_Al".
2. A escolha é lembrada: QSettings `calc_create/numbered` (bool), lida e gravada pelo `CalcCreateDialog` com o `settings=` que ele já recebe (como `MODE_KEY`); sem
   `settings` vale só na janela. O padrão é desmarcada.
3. O número vem do **local** escolhido (`location`): trocar a pasta, ou o conteúdo dela mudar, atualiza a prévia na próxima `_update`
   (`core.preview.target_text(parent, type_, suffix, numbered)` chama `preview_name`; a `ui/` não toca o disco, `FS_ALLOWED` não muda).
4. `CreateRequest` ganha `numbered: bool = False` (no fim); `request_create` o preenche com `self.setup.numbered`; `CalcCreateController.create` passa
   `request.numbered` a `preview_name` e a `create_folder`. A aba "Arquivos" (`TabsPage.set_target`) recebe o mesmo flag para mostrar `parent / nome numerado`
   (`_target` passa a `(parent, suffix, numbered)`; a chamada do diálogo a atualiza quando a caixa muda, sem recriar a etapa 2).
5. **O número é provisório até criar:** a prévia o calcula de novo a cada atualização e o worker o calcula uma última vez; se outra pasta numerada surgiu entre os
   dois, o nome final difere do mostrado (o toast diz o nome real). Aceito; não há reserva.
6. **Testes** (`tests/test_calc_numbering_ui.py`, `calc_dialog_helpers.make_dialog`, `fill_setup`; e uma linha em `test_calc_create_ui.py` com a janela principal):
   a caixa existe, desmarcada; marcá-la com `0_Relax`, `1_Bands` no local muda `name_preview` para `Será criada: 2_Bands_Al`; desmarcar volta a `Bands_Al`; **para cada
   tipo do combo (os dez do `REGISTRY`, PDOS incluído) a caixa fica habilitada e a prévia marcada é `Será criada: 2_<prefixo>_Al`** (a prévia do passo 1 não precisa de
   SCF); o `CreateRequest` emitido tem `numbered` certo; a aba "Arquivos" mostra o nome numerado; a escolha é lembrada com um `QSettings` de `tmp_path` e o padrão é
   desmarcado sem ele; criar pelo controlador faz `2_Bands_Al` com o `created_notice` do nome certo; com a caixa desmarcada nada muda (`Bands_Al`).

## Fora de escopo

- Preencher com zeros (`02_Bands`) para ordenar bem a partir de 10: o exemplo do usuário não preenche (`0_Relax`); a grade ordena por nome, então `10_x` fica antes
  de `2_x` até uma spec de "ordem natural" (ver decisão 3).
- Renumerar pastas existentes ou preencher buracos.
- Numerar pastas de projeto (`Criar projeto…`, spec 31) ou os arquivos dentro da pasta.
- Reservar o número entre a prévia e a criação.
- Efeito do número nas regras de detecção: ver "Situação atual" (não verificado).

## Decisões assumidas (confirmar na revisão)

1. **A primeira pasta é `0_…`** (o exemplo começa em 0: `0_Relax`, `1_Bands`). Se preferir começar em 1, é trocar o `0` de `next_number` por `1`.
2. **Próximo = maior + 1**, não a contagem das pastas: com `0_a` e `5_b` a nova é `6_…`, e uma pasta apagada deixa o buraco.
3. **Sem zeros à esquerda**, como no exemplo; `03_bands` (já existente) entra na conta como 3.
4. **"Mesmo prefixo" = o número do início do nome**, `^[0-9]+_`, de qualquer tipo de cálculo (`2_PDOS` conta como `0_Relax`); arquivos e pastas sem número (`plots`, `Notas`)
   não dão número a seguir. A regra olha o nome, nunca o tipo: nenhum tipo (PDOS incluído) é tratado à parte, nem na caixa nem na conta.
5. **Lembrada entre as aberturas** (QSettings `calc_create/numbered`), como o modo Padrão/Avançado; o padrão da primeira vez é desmarcada.
6. **A caixa vale no passo 1 para todos os tipos** (SCF, Relax, VC-Relax, Bands, PDOS, Carga, Diferença de carga, Slab, Supercélula e Molécula na superfície, e os que
   vierem), sem mudar nada dentro da pasta (nomes dos inputs, `name` dos tipos com `uses_name`). Um tipo novo herda a numeração por passar por `folder_name`.
7. **Uma pasta antiga sem número não entra na conta**, seja de que tipo for (uma `Bands_Al` feita antes da caixa não tem número para continuar): a fila é a das
   pastas numeradas. Se preferir que elas ocupem um lugar (contar como uma posição), é trocar a regra de `next_number` e o teste; dizer na revisão.

## Notas de implementação

- Novos: `src/qe_studio/core/calc_create/numbering.py`, `tests/test_calc_numbering.py`, `tests/test_calc_numbering_ui.py`.
- Alterados: `core/calc_create/writer.py` (`folder_name`, `preview_name`, `create_folder`), `core/calc_create/preview.py` (`target_text`),
  `ui/dialogs/calc_create/setup_page.py` (caixa, `numbered`, `_update`), `dialog.py` (`CreateRequest.numbered`, `request_create`, a chave de QSettings, o repasse a
  `set_target`), `tabs_page.py` (`_target`, `_show_files`), `ui/calc_create_controller.py` (`create`), `core/calc_create/__init__.py` (a lista de módulos no docstring).
- Limites: nenhum arquivo perto de 500; `ui/main_window.py` não é tocado.
- Documentação ao implementar: `CLAUDE.md` ("Criar cálculo" backend: `numbering.py`, `folder_name(…, number)`; a janela: a caixa e `calc_create/numbered`),
  `README.md` se descrever o passo 1. O item 6 da terceira rodada ("pastas `<numero>_Bands_<nome>` continuam válidas") fica realizado por esta spec.

## Critérios de aceite e testes

- [ ] Com a caixa desmarcada o nome é o de hoje (`Bands_Al`); `test_calc_create_*` e `test_calc_types` passam sem alterar.
- [ ] Marcada, num pai com `0_Relax`, `1_Bands`, a prévia e a pasta criada são `2_Bands_Al`; a seguinte `3_…` (`test_calc_numbering*.py`).
- [ ] **Todos os tipos do `REGISTRY` são numeráveis, o PDOS também**: a caixa está habilitada em cada um, a prévia e a pasta criada levam o número (`2_PDOS_Al`), e uma
  pasta `N_PDOS…` conta para a próxima como as demais (`test_calc_numbering.py`, `test_calc_numbering_ui.py`).
- [ ] O número ignora arquivos, nomes sem número e pastas ocultas, e usa o maior (não a contagem) (`test_calc_numbering.py`).
- [ ] A escolha da caixa é lembrada entre aberturas (`test_calc_numbering_ui.py`); o padrão é desmarcada.
- [ ] A aba "Arquivos" e o toast de criação mostram o nome numerado real (`test_calc_numbering_ui.py`, `test_calc_create_ui.py`).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` (sem disco novo na `ui/`) e a suíte `-m "not realdata and not perf"` verdes.
