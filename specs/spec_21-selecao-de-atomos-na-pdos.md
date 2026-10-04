# Spec 21: Seleção de átomos na PDOS, lembrada por composto

| | |
|---|---|
| **Prioridade** | 21 |
| **Status** | Implementada. Desvios: as seleções chegam ao módulo por um `Stores` (saco de stores do usuário, hoje só `compounds`) e um terceiro hook, `save_stored(dataset, params, name, stores)`, grava a edição; `PlotSession.persist(name, stores)` o chama e copia o valor para `defaults`, então escolher átomos não é uma edição do gráfico (nenhum `.plot` é agendado) e "Restaurar padrões" mantém a escolha do composto; `plot_file.stored_elsewhere(params)` lista os campos com `metadata={"store": …}` e `stored_params` / `apply_stored` os ignoram; as cores das séries seguem a ordem de **todos** os átomos (filtrar não recolore) e a lista de séries do painel só mostra os grupos com átomo marcado; `ask_atoms` devolve um `AtomsAnswer` (`atoms=None` = todos) ou `None` ao cancelar; `AtomChoices.available` é falso sem sítios, e o botão é criado desabilitado; os sítios vêm de `read_sites` no worker do `load_dataset` (não do `PwOutput`, cujo golden não muda) |
| **Depende de** | spec 20 (mesma seção de parâmetros e mesmos goldens); spec 13 (PDOS em pacote) |
| **Usada por** | spec 22 (a DOS da figura combinada respeita a seleção) |
| **Esforço** | M |

## Itens de origem (`Ideias.md`)

> - Na aba de configurações dos graficos, para o caso de plot de PDOS, na sessão Projeções, inclua um botão "Atomos", que abre uma janela com a lista de todos atomos do composto. É exibido o rotulo do elemento, as coordenadas x, y, z, (com tabela), com uma coluna de checkbox. Nessa janela o usuario pode selecionar os atomos que deseja plotar (obtiais da PDOS) e salvar essa seleção. Essa seleção é salva por composto, então o usuario não precisa selecionar os atomos toda vez que for plotar PDOS do mesmo composto. Para cada composto existe uma lista de atomos selecionados. Por padrão todos os atomos estão selecionados. Ao iniciar o Lain, o usuario deve selecionar os atomos para cada composto. Quando o usuario seleciona uma pasta que contém um composto que já foi selecionado, o Lain deve carregar os atomos selecionados para esse composto. È util quando o usuario quer plotar apenas os orbitais de dois atomos, no caso de analize de ligações quimicas.

## Situação atual

- `PdosParams` (`core/calculations/pdos/params.py:30`) tem `grouping`, `hidden_series` (lista de rótulos
  `"<espécie> <orbital>"`), `series_colors`, `orbital_colors`, `show_total`, `fill_occupied`, `spin_mode`.
  A seção "Projeções" (`PdosModule.sections`, `pdos/module.py:49`) tem `grouping`, `show_total`,
  `fill_occupied`, `spin_mode` e o campo `hidden_series` do tipo `"series"` (`params.py:136`).
- `PdosData.series` (`core/qe/projwfc.py:109,119`) guarda um `PdosSeries(atom, species, wfc, l, j, channel)` por
  arquivo `pdos_atm#N(El)_wfc#M(l)`. `aggregate(data, grouping)` (l.148) soma **todos** os átomos; não há filtro
  por átomo. `hidden_series` filtra por rótulo (`render.py:129`), que não distingue átomos da mesma espécie.
- Coordenadas e rótulos dos átomos: o nome do arquivo dá só o índice e a espécie. O cabeçalho da saída do pw.x
  tem `site n.  atom  positions (alat units)` com `N  Si  tau(  N) = ( x y z )`; `SITE` (`core/qe/structure.py:10`)
  captura só índice e espécie, e `summary/scan.py:239` e `core/qe/relax.py` só contam espécies. **Nenhum código
  lê as coordenadas.** `pw_output.read_structure` (l.191) usa ASE (import tardio; proibido no caminho de
  detecção pela spec 14, e quebra de propósito em `al.scf.out`).
- `PdosModule` tem os papéis `scf_out` e `nscf_out` (saídas do pw.x) e nenhum `pw_in`
  (`pdos/module.py:53-80`). `load_dataset` (`pdos/data.py:38`) já tem o `PwOutput` do SCF pelo `sniff`.
- Fórmula: `core/qe/structure.py:format_formula` e `header_formula(path)` (streaming, sem ASE).
- `ParamField.kind` (`core/calculations/params.py:13`): `float|int|bool|color|choice|text|labels|series`.
  `ParamsBody._add_field` (`ui/widgets/params_body.py:166`) é uma cadeia de `if/elif`; o que não é reconhecido
  vira `QLineEdit`. Há botões na seção por `section.add_full(widget)` (`params_body.py:79,149,201`).
- Persistência no mesmo molde de `NavigationStore` (`core/nav_store.py`) e `FolderMemory`: JSON em
  `appdirs.data_dir()`, escrita atômica, arquivo corrompido posto de lado (`appdirs.set_aside_corrupt`).
  `.plot` fica **dentro** da pasta da simulação (spec 3); a seleção por composto vale entre pastas, então não
  cabe nele.

## Requisitos

### R1: Leitura dos átomos (core, sem ASE)
1. `core/qe/structure.py:read_sites(path) -> list[Site]`, com `Site(index, species, x, y, z)` em Å. Lê em
   streaming só o cabeçalho (primeira lista `site n.`), converte as posições de alat para Å com o `alat` do
   mesmo cabeçalho (`lattice parameter (alat)`, em bohr). Falha de leitura ou lista vazia → lista vazia (nunca
   levanta).
2. Os sítios vêm da saída `scf_out` (ou `nscf_out`) do resultado da PDOS, pelo cache de `sniff` quando já há
   `PwOutput` (a ordem dos átomos é a do input, a mesma dos índices dos arquivos `pdos_atm#N`).
3. `PdosDataset` ganha `sites: tuple[Site, ...]` e `compound: Compound | None` (R2), preenchidos em
   `load_dataset` (worker). Sem sítios legíveis, `sites` é vazio e a seleção por átomo fica indisponível.

### R2: Composto e armazenamento
1. `core/compounds.py` (Qt-free, em `QT_FREE`):
   - `compound_key(species: Sequence[str]) -> str`: a **sequência de espécies na ordem do input** (ex.:
     `Al Al O O O`), normalizada (hash curto, mais um rótulo legível). Dois inputs com a mesma fórmula e ordem
     diferente têm chaves diferentes; coordenadas diferentes (depois de um relax) não mudam a chave.
   - `Compound(key, formula)`, com a fórmula de `format_formula` só para exibir.
2. `CompoundStore` (`compounds.json` em `appdirs.data_dir()`, `{"version": 1, "compounds": {chave:
   {"formula": "Al2O3", "atoms": [1, 2, 4]}}}`): `selection(key) -> list[int] | None` (`None` = nunca salvo =
   todos), `save(key, formula, atoms)`, `forget(key)`. Carga preguiçosa e sob lock; escrita atômica;
   `set_aside_corrupt` num arquivo ilegível (nunca sobrescrito); caminho injetável para os testes.
3. Salvar todos os átomos marcados guarda `null`/remove a entrada (volta ao padrão), para a lista não crescer.
4. A seleção **nunca** é gravada na pasta da simulação: pastas são sincronizadas (CLAUDE.md).

### R3: Parâmetro e filtro
1. `PdosParams.atoms: list[int] | None = None` (índices 1-based dos átomos mostrados; `None` = todos). O campo é
   declarado **fora do `.plot`** (metadado `field(metadata={"store": "compound"})`): `plot_file` não o grava nem
   o lê; o valor vem do `CompoundStore` (R5).
2. O filtro roda antes do agrupamento: `projwfc.aggregate(data, grouping, atoms=...)` ignora séries cujo
   `atom` não está em `atoms`. `hidden_series` e `grouping` continuam como hoje sobre o que restou; os rótulos
   das séries não mudam (`"Si s"`, `"Si p"`…), e a cor automática de uma espécie é a mesma com ou sem filtro.
3. `show_total` mostra a DOS total do arquivo `pdos_tot` (todos os átomos). Com um subconjunto de átomos isso
   engana: quando `atoms` não é `None`, "DOS total" passa a ser a soma das séries mostradas e o rótulo vira
   "Soma dos átomos selecionados" (sem alterar o padrão de hoje).
4. `RenderInfo.summary` ganha "N de M átomos" quando há filtro.
5. O **gap de energia** da spec 20 (`PdosDataset.gap`, inclusive o lido da curva de DOS) é do sistema e usa a DOS de
   **todos** os átomos: a seleção de átomos não o altera.

### R4: Botão "Átomos…" e janela
1. Novo `ParamField.kind = "atoms"`, na seção "Projeções" do esquema da PDOS (`ParamField("atoms", "Átomos",
   "Projeções", "atoms")`). `ParamsBody` mostra um `QPushButton` "Átomos…" (com o resumo "3 de 12" ao lado) em
   `section.add_full`. Sem `sites`, o botão fica desabilitado com tooltip "Não foi possível ler os átomos da
   saída do SCF".
2. `ui/dialogs/atoms.py:AtomsDialog` (modal, `delete-on-close`; só interface, helper `ask_atoms(...)` no molde
   de `ask_mapping`): tabela com colunas ✓, `#`, elemento, x, y, z (Å, fonte mono); linhas ordenadas por
   índice; botões "Marcar todos", "Desmarcar todos", "Inverter" e um menu "Só espécie ▸ …"; cabeçalho com a
   fórmula do composto e um aviso de que a seleção vale para **todo** gráfico desse composto. Botões "Salvar" e
   "Cancelar". Salvar com nada marcado é recusado ("Marque ao menos um átomo").
3. "Salvar" grava no `CompoundStore` (R2) e aplica na hora ao gráfico aberto: `ParamsBody` atualiza
   `params.atoms`, emite `changed("atoms")` e o gráfico é regenerado. "Cancelar" não altera nada.
4. Nenhum arquivo de `ui/` lê arquivos ou conhece o módulo: o botão aparece porque o esquema tem um campo
   `"atoms"`, e a lista de átomos vem de um hook novo da base, `CalculationModule.atoms_of(dataset) ->
   AtomChoices | None` (sítios + composto; `None` nos módulos sem átomos), como `series_colors`/`default_labels`.

### R5: Carregar a seleção salva
1. Depois do load (`PlotWorkflow`, antes de `build_session`), um hook da base,
   `CalculationModule.stored_params(dataset, stores) -> dict`, devolve `{"atoms": selection}` quando o composto
   tem seleção salva; `build_session` aplica sobre os padrões, **antes** do `.plot` e das edições da aba
   (o campo não está no `.plot`, então nada o sobrescreve).
2. Composto sem entrada: `atoms = None` (todos). **Não há janela ao iniciar o Lain**: a primeira vez que o
   usuário abre "Átomos…" de um composto, a seleção é "todos"; depois que ele salva, qualquer pasta com esse
   composto abre já filtrada (ver "Decisões assumidas").
3. Se a seleção salva cita um índice que não existe no composto (arquivo editado à mão), esse índice é
   ignorado; se nada sobra, vale "todos".
4. Regenerar o gráfico (F5, sync) relê a seleção salva do disco, não a da última aba.

## Fora de escopo
- Escolher orbitais por átomo (um `s` do átomo 1 e um `p` do átomo 2). A seleção é só por átomo; o que mostrar
  de cada átomo continua sendo o agrupamento e `hidden_series`.
- Seleção por região do espaço, por distância ou por vizinhança.
- Gerenciar a lista de compostos salvos (apagar, exportar). O arquivo é JSON simples; `forget` existe no core.
- Seleção de átomos nas bandas ou em outros gráficos.

## Decisões assumidas (confirmar na revisão)
1. Chave do composto = **fórmula + ordem das espécies** (decisão do usuário nesta rodada); a fórmula é só rótulo.
2. "Ao iniciar o Lain, o usuário deve selecionar os átomos para cada composto" foi lido como "na primeira vez
   de cada composto, e depois fica lembrado", **sem** diálogo ao iniciar. O padrão é todos selecionados.
3. A seleção fica em `compounds.json` no diretório de dados (valor global entre pastas), não no `.plot`.
4. Coordenadas em Å (convertidas do alat do cabeçalho). A saída do pw.x não imprime posições em outra unidade
   na lista `site n.`.
5. A soma "total" com filtro substitui `pdos_tot` (R3.3), para a curva bater com o que é mostrado.
6. As coordenadas mostradas são as do cabeçalho do SCF/NSCF da PDOS, ou seja, a estrutura **daquele** cálculo.

## Notas de implementação
- Novos: `core/compounds.py`, `ui/dialogs/atoms.py`; `read_sites` em `core/qe/structure.py` (hoje ~30 linhas).
  Adicionar `core/compounds.py` e `core/qe/structure.py` à lista `QT_FREE` de `tests/test_architecture.py`.
- Alterados: `core/calculations/pdos/{params,data,render,module}.py`, `core/qe/projwfc.py` (`aggregate`),
  `core/calculations/base.py` (hooks `atoms_of`, `stored_params`), `core/calculations/params.py` (kind `atoms`),
  `core/plotting/plot_file.py` (ignorar campos com `store`), `ui/widgets/params_body.py` (branch `atoms`),
  `ui/plot_workflow.py` (aplicar `stored_params`), `ui/main_window.py` (injetar o `CompoundStore`, 2 linhas;
  o arquivo tem 475/500 linhas: preferir criar o store dentro do `PlotWorkflow.for_window` se existir, senão
  numa fábrica fora do `MainWindow`).
- O `main_window` fixture de testes ganha um `CompoundStore` isolado em `tmp_path`, como `FolderMemory` e
  `NavigationStore`.
- Tabela da janela: `QTableWidget` com `QCheckBox` por linha (padrão do diálogo de atalhos, que também usa
  `QTableWidget`).

## Critérios de aceite e testes
- [ ] `read_sites` nas fixtures (`qe731_*`, `kao_*`): índice, espécie e posições em Å batem com a lista
      `tau(`; saída sem a lista → vazio; arquivo ilegível → vazio. Sem ASE no processo
      (`test_perf_detection` import test segue passando).
- [ ] `compound_key`: mesma fórmula e ordem diferente → chaves diferentes; mesma sequência com posições
      diferentes → mesma chave.
- [ ] `CompoundStore`: ida e volta, todos marcados remove a entrada, arquivo corrompido posto de lado e nunca
      sobrescrito, caminho injetável, nada gravado em `tests/fixtures/`.
- [ ] Filtro: com `atoms=[1]` a soma da série "Si p" é a do arquivo do átomo 1 (fixture com 2 átomos da mesma
      espécie); `atoms=None` reproduz `test_figure_regression` sem regenerar goldens; `show_total` com filtro
      mostra a soma e o rótulo novo.
- [ ] `plot_file`: um `.plot` nunca contém `atoms`; um `.plot` antigo com a chave é ignorado sem erro.
- [ ] Janela (pytest-qt): lista todos os átomos com coordenadas; marcar/desmarcar/inverter/por espécie;
      "Salvar" sem nenhum marcado é recusado; "Salvar" grava no store e regenera o gráfico; "Cancelar" não mexe.
- [ ] Fluxo: salvar a seleção numa pasta; abrir outra pasta com o mesmo composto → já filtrada; composto com
      ordem diferente → todos.
- [ ] Sem sítios legíveis: botão desabilitado com tooltip.
- [ ] `test_module_contract.py`: `DummyModule` cobre `atoms_of` e `stored_params`; nenhum `kind == "pdos"` em `ui/`.
- [ ] `test_architecture.py`: novos módulos do core sem PyQt6 e abaixo de 500 linhas.
