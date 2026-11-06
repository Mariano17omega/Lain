# Mapa do código

Onde revisar ou modificar cada parte. Caminhos relativos a `src/qe_studio/`.

## "Quero mudar…" → "olhe em…"

| Quero mudar… | Código |
|---|---|
| **O input/script que um tipo de cálculo gera** | `core/calc_create/types/<tipo>.py` (campos, edições) + templates em `resources/templates/qsub/*.qsub.j2` e `resources/templates/qe/*/*.j2` |
| O cabeçalho comum dos `.qsub` (SGE, MPI, e-mail) | `resources/templates/qsub/_base.qsub.j2` |
| A lista de tipos do "Criar cálculo" | `core/calc_create/types/__init__.py` (`REGISTRY`) |
| Geometria de slab, supercélula, adsorção | `core/calc_create/surface/*` |
| Edição de inputs preservando formatação | `core/qe/input_edit.py` |
| Nome/numeração/escrita da pasta nova | `core/calc_create/writer.py`, `numbering.py`, `naming.py`, `fingerprint.md` em `fingerprint.py` |
| **Extração de dados de inputs** | `core/qe/pw_input.py`, `input_extract.py`, `cell_card.py`, `lattice.py`, `structure.py`; resumo do SCF em `core/calc_create/scf_info.py` |
| **Extração de dados de saídas** | `core/qe/pw_output.py`, `bands_x.py`, `projwfc.py`, `relax.py`, `core/qe/summary/` |
| Identificação de arquivo por conteúdo | `core/sniff.py` |
| Detecção de pasta (selos) | `core/detection.py`, `core/calculations/<tipo>/detection.py` |
| **Desenho de um gráfico** | `core/calculations/<tipo>/render.py` |
| Parâmetros/painel de um gráfico | `core/calculations/<tipo>/params.py` (`ParamField`) |
| Gap, CSV de um gráfico | `…/gap.py`, `…/table.py` |
| Estilo, exportação, nomes de arquivo | `core/plotting/style.py`, `styles.py`, `export.py`, `names.py`, `table.py`; estilos YAML em `resources/templates/plot_styles/` |
| Salvar/ler `.plot` | `core/plotting/plot_file.py`, `saved.py` |
| **Comandos executados no cluster** | `core/remote/actions.py` (execução e validação), `submit.py`, `job_cancel.py`, `trash.py`, `cluster_jobs.py`, `listing.py` |
| Opções do ssh, rsync, conexão compartilhada | `core/sync/rsync.py` (`ssh_command`), `command.py`, `mux.py`, `askpass.py` |
| Plano/prévia de sync, push | `core/sync/planner.py`, `preview.py`, `push.py`, `push_plan.py` |
| Chaves do `config.yaml` | `core/config.py` + `config.example.yaml` (raiz) **e** `resources/config.example.yaml` (idênticos) |
| Visualização 3D | `core/structure3d/*` (lógica), `ui/widgets/structure3d/*`, `ui/tools/structure3d_controller.py` |
| Visualizador de texto/inputs | `core/viewer/*`, `core/qe/input_lexer.py`, `input_lint.py`, `ui/widgets/viewer/*` |
| Menus, atalhos | `ui/actions.py` |
| Tema/cores/QSS | `ui/resources/themes/*.yaml`, `ui/resources/styles/*` |
| Textos e tradução | `_()` no código; `locale/en/LC_MESSAGES/lain.po` |
| Log | `core/app/logs.py` |
| Explorador, filtros, favoritos | `core/files/*`, `core/project/*`, `ui/files/*`, `ui/widgets/files/*` |

## Receitas

### Adicionar um gráfico { #adicionar-um-grafico }

1. Crie `core/calculations/<tipo>/` com `data.py`, `params.py` (`Params` + `ParamField`), `render.py` e `module.py`
   (subclasse de `CalculationModule[Dataset, Params]` com `roles`, `load`, `default_params`, `param_schema`, `render`).
2. Registre em `core/calculations/__init__.py:REGISTRY`.
3. Nada na UI deve conhecer o tipo: use ClassVars/ganchos da base; estenda `DummyModule` em
   `tests/test_module_contract.py` se o contrato crescer.
4. Cores: `metadata={"kind": "color"}`; estilo via `figure_style`, nunca o tema do app.
5. Fixture real em `tests/fixtures/` (cópia com `copy_fixture`; nunca escreva ali) e testes.

### Adicionar um tipo de "Criar cálculo"

1. `core/calc_create/types/<tipo>.py` com uma subclasse de `CalcType` (`input_files`, `input_fields`, `inputs`,
   `script_values`) e templates Jinja2 em `resources/templates/`.
2. Registre em `core/calc_create/types/__init__.py:REGISTRY`.
3. `plan()` nunca levanta exceção nem lê arquivo.

### Adicionar uma chave de configuração

Campo pydantic em `core/config.py` **e** nas duas cópias de `config.example.yaml` (o teste `tests/test_config.py`
exige que sejam idênticas).

### Adicionar um texto na interface

Escreva em português dentro de `_()`; depois `uv run python scripts/i18n.py update`, traduza em
`locale/en/LC_MESSAGES/lain.po`, `compile` e `check`.

### Adicionar uma ação de menu

Uma entrada em `ui/actions.py:ACTIONS` (id estável, menu, texto, atalho, slot).

## Regras que o teste de arquitetura impõe

Arquivos ≤ 500 linhas; `core/` não importa `ui/`; `ui/` não lê disco; módulos novos no topo só se listados em
`TOP_LEVEL`. Veja [Camadas e regras](architecture/layers.md).
