# Code map

Where to review or change each part. Paths relative to `src/qe_studio/`.

## "I want to change…" → "look at…"

| I want to change… | Code |
|---|---|
| **The input/script a calculation type generates** | `core/calc_create/types/<type>.py` (fields, edits) + templates in `resources/templates/qsub/*.qsub.j2` and `resources/templates/qe/*/*.j2` |
| The common `.qsub` header (SGE, MPI, e-mail) | `resources/templates/qsub/_base.qsub.j2` |
| The list of "Criar cálculo" types | `core/calc_create/types/__init__.py` (`REGISTRY`) |
| Slab, supercell, adsorption geometry | `core/calc_create/surface/*` |
| Format-preserving input editing | `core/qe/input_edit.py` |
| New folder name/numbering/writing | `core/calc_create/writer.py`, `numbering.py`, `naming.py`, `fingerprint.md` in `fingerprint.py` |
| **Data extraction from inputs** | `core/qe/pw_input.py`, `input_extract.py`, `cell_card.py`, `lattice.py`, `structure.py`; SCF summary in `core/calc_create/scf_info.py` |
| **Data extraction from outputs** | `core/qe/pw_output.py`, `bands_x.py`, `projwfc.py`, `relax.py`, `core/qe/summary/` |
| File identification by content | `core/sniff.py` |
| Folder detection (badges) | `core/detection.py`, `core/calculations/<type>/detection.py` |
| **Drawing a plot** | `core/calculations/<type>/render.py` |
| A plot's parameters/panel | `core/calculations/<type>/params.py` (`ParamField`) |
| A plot's gap, CSV | `…/gap.py`, `…/table.py` |
| Style, export, file names | `core/plotting/style.py`, `styles.py`, `export.py`, `names.py`, `table.py`; YAML styles in `resources/templates/plot_styles/` |
| Saving/reading `.plot` | `core/plotting/plot_file.py`, `saved.py` |
| **Commands run on the cluster** | `core/remote/actions.py` (execution and validation), `submit.py`, `job_cancel.py`, `trash.py`, `cluster_jobs.py`, `listing.py` |
| ssh, rsync options, shared connection | `core/sync/rsync.py` (`ssh_command`), `command.py`, `mux.py`, `askpass.py` |
| Sync plan/preview, push | `core/sync/planner.py`, `preview.py`, `push.py`, `push_plan.py` |
| `config.yaml` keys | `core/config.py` + `config.example.yaml` (root) **and** `resources/config.example.yaml` (identical) |
| 3D view | `core/structure3d/*` (logic), `ui/widgets/structure3d/*`, `ui/tools/structure3d_controller.py` |
| Text/input viewer | `core/viewer/*`, `core/qe/input_lexer.py`, `input_lint.py`, `ui/widgets/viewer/*` |
| Menus, shortcuts | `ui/actions.py` |
| Theme/colors/QSS | `ui/resources/themes/*.yaml`, `ui/resources/styles/*` |
| Texts and translation | `_()` in code; `locale/en/LC_MESSAGES/lain.po` |
| Log | `core/app/logs.py` |
| Explorer, filters, favorites | `core/files/*`, `core/project/*`, `ui/files/*`, `ui/widgets/files/*` |

## Recipes

### Adding a plot { #adding-a-plot }

1. Create `core/calculations/<type>/` with `data.py`, `params.py` (`Params` + `ParamField`), `render.py` and `module.py`
   (a `CalculationModule[Dataset, Params]` subclass with `roles`, `load`, `default_params`, `param_schema`, `render`).
2. Register it in `core/calculations/__init__.py:REGISTRY`.
3. Nothing in the UI may know the type: use ClassVars/hooks on the base; extend `DummyModule` in
   `tests/test_module_contract.py` if the contract grows.
4. Colors: `metadata={"kind": "color"}`; style via `figure_style`, never the app theme.
5. A real fixture in `tests/fixtures/` (copy with `copy_fixture`; never write there) and tests.

### Adding a "Criar cálculo" type

1. `core/calc_create/types/<type>.py` with a `CalcType` subclass (`input_files`, `input_fields`, `inputs`,
   `script_values`) and Jinja2 templates in `resources/templates/`.
2. Register it in `core/calc_create/types/__init__.py:REGISTRY`.
3. `plan()` never raises nor reads a file.

### Adding a configuration key

A pydantic field in `core/config.py` **and** in both copies of `config.example.yaml` (`tests/test_config.py` requires
them to be identical).

### Adding an interface text

Write it in Portuguese inside `_()`; then `uv run python scripts/i18n.py update`, translate in
`locale/en/LC_MESSAGES/lain.po`, `compile` and `check`.

### Adding a menu action

An entry in `ui/actions.py:ACTIONS` (stable id, menu, text, shortcut, slot).

## Rules the architecture test enforces

Files ≤ 500 lines; `core/` does not import `ui/`; `ui/` does not read disk; new top-level modules only if listed in
`TOP_LEVEL`. See [Layers and rules](architecture/layers.md).
