# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Lain: QE Studio: a PyQt6 desktop app to browse, pull-sync (rsync + ssh) and plot Quantum ESPRESSO
simulations (band structures, PDOS, relax/vc-relax progress). Requirements live in `specs/spec_0-PRD.md`; code comments
cite it as "PRD §x.y". Change specs derived from `specs/Ideias.md` are `specs/spec_N-*.md`
(prioritized index in `specs/README.md`). The UI follows `Documentation/design system (UX)/`.

Supported Quantum ESPRESSO versions: **7.1 or newer**. No code or fixture handles older formats.

User-facing strings (labels, dialogs, error messages, even `Method` enum values like `"conteúdo"`)
are **Portuguese**. Code, comments, docstrings and commit messages are English.

Naming: the product and CLI are `lain`, but internal identifiers keep the old name on purpose, so
existing configs keep working: package `qe_studio`, `QE_STUDIO_*` env vars, `~/.config/qe-studio`,
`~/.cache/qe-studio`, QSettings keys, `qe-studio-askpass`. Do not rename them.

## Commands

Managed with uv (Python ≥ 3.11).

```bash
uv sync                                          # install deps + dev group
uv run lain [--config path/to/config.yaml] [--verbose]
uv run pytest                                    # full suite (~40 s), headless
uv run pytest -m "not realdata and not perf"     # what CI runs (.github/workflows/ci.yml)
uv run pytest tests/test_detection.py::test_name # single test
uv run pytest -m perf -s                         # latency budgets: plot (NFR §7) and detection (spec 14)
QE_STUDIO_REAL_DATA=/runs:/other uv run pytest -m realdata   # user's own QE runs (off by default)
uv run ruff check . && uv run ruff format --check .
uv run pyright                                   # basic mode over src/ (CI), no ignore list
uv run python scripts/screenshot.py --plot       # off-screen PNGs of both themes → screenshots/
uv run python scripts/fetch_assets.py            # refresh vendored fonts/icons
uv run python scripts/build_icons.py             # re-render the app icon PNGs from ui/resources/app/lain.svg
uv run python scripts/install_desktop.py         # optional: .desktop + icons for the user (--prefix DIR)
```

Config lookup order: `--config`, `$QE_STUDIO_CONFIG`, `./config.yaml`,
`~/.config/qe-studio/config.yaml`. `config.yaml` is git-ignored (may hold credentials); every key
is documented in `config.example.yaml`. There is no settings window by design (PRD §6), so new
settings go into the pydantic models in `core/config.py` and `config.example.yaml`.

## Testing notes

- `tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen` and `MPLBACKEND=Agg` before any Qt
  import, and an autouse fixture redirects `XDG_*` dirs to temp paths. Keep both properties:
  tests must not touch the real home directory.
- `tests/fixtures/` holds real, trimmed QE 7.3.1 outputs (see its README for each folder's
  quirks, e.g. `al.scf.out` crashes ASE's reader on purpose as a regression). PRD-style layouts
  (`scf.out`, `nscf.out`, `orbitals/`) are built at test time by the `al_pdos_orbitals` and
  `demo_project` fixtures; don't add renamed copies of fixtures. Never write into
  `tests/fixtures/` (copy with `copy_fixture` first): `test_fixtures_untouched.py`, sorted last
  by `conftest.py`, fails on any untracked or modified file there.
- `test_qe_versions.py` keeps one table with a row per fixture folder and checks each version's
  Fermi/HOMO line, `.gnu` separators, bands.x output and PDOS headers. Adding a QE version =
  a real trimmed run in `tests/fixtures/qe<ver>_<system>/` + a row there (see the fixtures README).
- `test_properties.py` holds the Hypothesis tests of the parsers (`read_gnu`/`gnu_shape`, `parse_relax`,
  the input lexer/linter; specs 9, 12 add theirs). `conftest.py` registers profiles `dev` and `ci`
  (`HYPOTHESIS_PROFILE=ci`: fewer examples, no deadline, no example database).
- `viewer_helpers.py` (`open_text`, `key`) is shared by the text viewer tests, like `sync_helpers.py`
  is by the sync ones, and `grid_helpers.py` (`show_folder`, `names`, `click`, `select_names`,
  `reset_modifiers`) by the grid, filter, selection, navigation and favorites ones. Qt keeps the
  modifiers of the last simulated event (`setCurrentIndex` reads them): after a Ctrl/Shift click or
  key, call `reset_modifiers`.
- `tests/fixtures/qe731_ni_spin_{bands,pdos,fixed}/` are real Ni nspin=2 runs (QE 7.3.1): two bands.x
  runs, spin PDOS, and an SCF with `tot_magnetization` (two Fermi energies). `spin_helpers.py` has the
  paths and small helpers of the spin tests (`test_bands_spin_*`, `test_pdos_spin.py`,
  `test_spin_window.py`); `test_figure_regression.py` compares the artists of no-spin figures and the
  mirrored PDOS (`figure_structure.py`) with data captured before the spin work.
- `main_window` fixture builds a full `MainWindow` with isolated QSettings, `FolderMemory` and
  `NavigationStore` (`tmp_path` files); it is `window_factory()`, which a test calls again (after
  `window.close()`) to restart the app on the same files. The
  controllers are tested without it too: `test_plot_workflow_unit.py` (a `Rig` with real workspace,
  params panel, status bar and detection service) and `test_sync_coordinator.py`. Dialogs are patched
  where they are imported: `qe_studio.ui.plot_workflow.{ask_mapping,choose_result}`,
  `qe_studio.ui.plot_export.ask_overwrite`, `qe_studio.ui.main_window.ask_rename`.
- Exports and `.plot` writes run in workers: wait for `window.export_finished` (the written paths)
  before looking into `plots/`, and call `window.plot_settings.flush_now()` (drains the settings
  queue, then writes what is pending) before reading a `.plot`.
- `test_architecture.py` checks the architecture rules by AST: no `.py` over 500 lines (exceptions
  list, empty), `core/` never imports `qe_studio.ui`, PyQt6 only in the three `core` modules listed
  below, no `open(` / `read_text` / `read_bytes` / `loadtxt` in `ui/` (but `ui/theme/manager.py`),
  and the modules moved to `core` by spec 15 import without PyQt6. `test_tasks.py` covers the
  background-task helper; `test_busy_indicator.py` and `test_export_worker.py` the spinner and the
  non-blocking export.
- Detection performance (spec 14): `tests/synthetic.py` builds a 520-folder project from the fixtures,
  a 200 MB relax output, an 80 MB `.gnu` and a 20 MB output with a long header, always in tmp dirs.
  `test_perf_detection.py` times them (`-m perf -s` prints the numbers; the baseline and budgets are
  in the spec's notes); its import test (no `ase` after importing `main_window`) is not `perf`.
  `test_pw_output_regression.py` compares `PwOutput` of every fixture output with
  `pw_output_golden.json`, captured from the parser before it read head and tail separately.
- Sync integration tests run the **real `rsync` and `ssh` binaries** (skipped if either is absent).
  Cluster sync is tested against `tests/ssh_server.py`, a **local SSH server built with paramiko**
  (dev dependency): the `ssh_server` fixture yields `(server, remote_root)`, a server on a free
  `127.0.0.1` port serving the temp folder `remote_root` as the "cluster". Key and password
  authentication run through it, `exec` requests run as local subprocesses (no shell) from an
  allowlist (`rsync --server …`, `true`, `echo`; anything else gets status 127, is logged and is
  not run), and `server.log` / `server.attempts` record who ran what with which auth method.
  Failure modes a test switches on before connecting: `reject_auth`, `stall_banner`,
  `drop_after_bytes`. `server.config_data(auth=, strict=, known_hosts=, **cluster)` gives the
  config dict (`known_hosts`: `server` / `empty` / `other`; `strict`: `yes` / `ask`).
  OpenSSH reads the passwd home, not `$HOME`, so `server.ssh_binary()` pins `ssh` to a temp
  `ssh_config` (`-F`): no `~/.ssh`, no agent, no default identities. Do not bypass it. The server
  tests itself in `test_ssh_server.py`; real pulls over it are in `test_sync_ssh.py`,
  `test_sync_integration.py` and `test_sync_ui.py` (shared helpers: `tests/sync_helpers.py`).
  Tests whose remote is a plain local path (`Endpoint(path)` without host) need no server.
- Tests have a 60 s timeout (pytest-timeout).

## Architecture

`src/qe_studio/core` is logic without widgets (only `core/sync/controller.py`,
`core/sync/monitor.py` and `core/tasks.py` use Qt, for `QProcess`, signals and the thread pool);
`src/qe_studio/ui` is the PyQt6 app.

### Architecture rules

- **No files over ~500 lines that centralize everything.** Split by responsibility before a module
  grows past that. `tests/test_architecture.py` keeps every file of `src/qe_studio` under 500.
- **`ui/` holds interface logic only.** Widgets, layout, dialogs, and wiring signals to `core/`.
  Parsing, detection, physics, file operations, sync decisions and any other backend logic belong in
  `core/`, where they are testable without Qt. If a UI method computes something that doesn't depend
  on a widget, move it to `core/`. Every new piece of logic that does not need a widget starts in
  `core/` (spec 15 R5.3).
- **Keep the program modular to ease maintenance.** Each module has one job, and depends on small
  explicit interfaces (hooks, signals, injected services) instead of reaching into other modules'
  internals. New behaviour is a new module plus a registration, not another branch in a central class.

### Main window and controllers (spec 15)

`ui/main_window.py:MainWindow` is the composition root: it builds the widgets, three controllers and
the `.plot` store, registers the actions and wires signals. It keeps only what spans controllers:
`rename_path`, `reload_config`, `closeEvent`, plus a thin facade the tests and
`scripts/screenshot.py` use (`plot_ready`, `plot_failed`, `export_finished`, `sync_finished`,
`generate_plot_for`, `export_plot`, `monitor`…).

- `ui/layout_controller.py:LayoutController`: panels, splitter widths (`fit_widths`), left panel
  mode and the QSettings `window/geometry`, `layout/*`, `files/*`. Knows no plot or sync.
- `ui/plot_workflow.py:PlotWorkflow`: detect → `core/detection.plot_choice` (`Chosen` / `Ambiguous`
  → `choose_result` / `NeedsMapping` → `ask_mapping`, `ManualTarget`) → `load_plot` (load pool) →
  `.plot` read (settings queue) → `build_session` → tab; readout, "Plotar SCF" source, busy
  indicator (`ui/busy.py:BusyTracker`, counted by name: the footer spinner and "Detectando cálculo…"
  / "Carregando …" / "Exportando…", plus a spinner in the tab of a plot being regenerated; no
  `setOverrideCursor`). It asks the window for panels and messages through signals
  (`panel_requested`, `message`). Exports: `ui/plot_export.py:PlotExporter` (overwrite question on
  the GUI thread from `core/plotting/export.plan_export`, then `export_figure` in a worker on a
  snapshot of the params; close waits up to 10 s for exports).
- `ui/sync_coordinator.py:SyncCoordinator`: `core/sync/request.prepare_sync` → session password →
  `SyncController` + dialogs → report; owns the `ConnectionMonitor` (replaced on config reload) and
  emits `cluster_changed`, `synced(local_dir)` (the window refreshes) and `finished`.
- `ui/plot_settings.py:PlotSettingsStore`: every `.plot` read, write and removal in one private
  single-thread pool, so they happen in order (a regenerate reads what closing the tab wrote);
  edits are debounced 1 s; `flush_now` writes on the spot (window close, before a rename).
- `ui/navigation_controller.py:NavigationController` (spec 16): the history, the breadcrumb and the
  favorite / recent folders. `MainWindow.on_folder_selected` is where every folder change arrives
  and calls `visited`; going back, forward, to a breadcrumb level or to a favorite is
  `ExplorerPanel.select_path` like a tree click (the history already holds the target, so `visited`
  pushes nothing). Also owns the side mouse buttons (an application event filter limited to this
  window) and answers the explorer's two `NavSection`s. `rename_path` tells it before reselecting.
- `ui/actions.py:ACTIONS`: the window's actions by stable id (`plot.generate`, `plot.export`,
  `view.theme`, `files.refresh`…) with menu, text, shortcut and slot path; `MainWindow._actions`
  holds the `QAction`s (spec 18 reads it).

What files are for the panels is `core` too: `core/file_kinds.py` (`viewer_kind`, `status_label` →
(label, level), `human_size`, job logs) and `core/paths.py` (`ui.hidden_dirs` matching, entry
counts); `ui/file_types.py` keeps only the icon of a file and the level → color token map.

### Detection pipeline (PRD §3)

File names are only hints; everything is identified by content.

1. `core/sniff.py`: `sniff(path)` classifies one file into a `FileKind` (pw.x in/out, bands.x
   in/out, projwfc, dos, `.gnu`, PDOS atm/tot…) by reading head/tail bytes with the parsers in
   `core/qe/`. `SniffCache` memoizes per (mtime, size) and is thread-safe. pw.x outputs up to
   16 MB are read whole; bigger ones as a 256 KB head (facts printed once: k points, electrons…)
   and a 1 MB tail (last ones: Fermi, convergence, `JOB DONE`), `parse_pw_output(head, tail)`.
   A `.gnu` is streamed (`bands_x.gnu_shape`, no size limit), never loaded by the sniff.
2. `core/calculations/base.py`: each `CalculationModule` declares `FileRole`s (id, content
   predicate `accepts`, optional PRD naming `globs`, `required`/`multiple`/`anchor`).
   `match(listing, sniffs, sniff, forced)` fills roles in passes: user mapping (`forced`) → PRD glob
   verified by content → content only; `finalize()` hooks cross-role logic, and
   `infer_from_neighbours()` finds the SCF output in the parent or sibling `*scf*` folders. A module
   with no anchor role present returns `None`.
3. `core/detection.py`: `detect_folder()` sniffs each file once (`sniff_once`: a per-call memo that
   also covers neighbour folders and the hooks) and runs every module in `REGISTRY` on those sniffs;
   `fallback` modules (SCF/CALC info badges) apply only when no primary kind matched.
   `core/folder_memory.py:FolderMemory` stores manual mappings and typed k-point labels in the app
   data dir (`folders.json`, format version 2), never inside simulation folders (they get synced).
   Keys are folder paths relative to `paths.local_root` (`"."` = the root, `abs:<path>` outside it;
   `MainWindow` calls `set_root` on start and config reload) and mapped files are relative to their
   folder, so a moved or copied project keeps them. Version 1 files (absolute keys) migrate on the
   first read; an unreadable file is renamed `folders.json.corrompido-<date>`, never overwritten.

**Adding a calculation type** (NFR §7): subclass `CalculationModule[Dataset, Params]` in
`core/calculations/` (detection-only modules use `CalculationModule[None, CommonParams]`), register
it in `core/calculations/__init__.py:REGISTRY`, and for plottable modules implement
`load(result, sniff)` (`sniff` is the caller's cache, the service's in the app: read
`sniff(path).pw` instead of parsing outputs again; never import the module-level `sniff`),
`default_params`, `param_schema`, `render` (returns `RenderInfo`) and optionally `param_changed`.
Params are dataclasses extending `CommonParams`; the tuning panel (`ui/widgets/params_body.py`) is
generated from the `ParamField` list in `param_schema`. **No file in `ui/` may know a module**
(`kind == "bands"` and the like): everything the UI needs from a module is a declaration or a hook
on the base class:

- ClassVars: `view_fields` (params the toolbar Reset restores), `sections` (own panel sections as
  `(name, insert before)`, ordered by `ordered_sections`), `badge_token` (theme colors
  `badge_<token>_{bg,fg,border}`; none → the generic `badge_other_*`), `single_file_role` (a role
  whose one file can be plotted alone: the right-click "Plotar" and the "Plotar SCF" button ask
  `module_for_file(sniff)`, never a module name).
- Hooks: `apply_limits(params, axes_limits)` (pan/zoom of *every* figure axes into the params),
  `legacy_params` (old `FolderMemory` data when there is no `<kind>.plot`), `default_labels`,
  `series_colors` (for a `"series"` field), `format_coordinates(x, y, axes_index, dataset, params)`
  (cursor readout of each axes; `PlotView` installs it as `ax.format_coord` after every render, through
  `PlotSession.format_coordinates`, which swallows module errors), `plot_target(folder,
  files)` (what one plot shows: the folder, or the output file of a single-file module such as SCF;
  it keys and names the tab, `<kind>.plot` stays per folder).
- `ParamField`: `refreshes=True` makes the panel re-read all values after an edit (dependent
  fields); `colors=` names the color-override dict of a `"series"` field. `plot_file` validates stored
  values by field kind (`color`, `choice`, series colors), never by name: a parameter without a
  schema field declares `field(metadata={"kind": "color" | "colors"})` on its dataclass.

`load_cached()` memoizes `load()` on file stamps and is called from worker threads.
`tests/test_module_contract.py` has a `DummyModule` that exercises the whole contract; extend it
when the contract grows.

### Plotting

`core/plotting/session.py:PlotSession[D, P]` = detection result + dataset + params (+ copy of
defaults); `build_session` makes one from a load (defaults → stored `.plot` or legacy `FolderMemory`
→ the edits of the open tab). `render()` wraps the module's `render` in `PlotStyle.rc(...)` under
`core/plotting/mpl_lock.py:MPL_LOCK`. The style is `PlotSession.style` =
`figure_style(params.background)` (`core/plotting/style.py`), never the app theme, so preview and
export match; `ThemeManager` only styles the widgets around the canvas. Toolbar pan/zoom is written back into params (`apply_limits`) so exports keep
it. `core/plotting/export.py` writes into `<simulation>/plots/`; existing files are never
overwritten without asking (PRD §7 data integrity).

`ParamsPanel` (`ui/widgets/plot_params.py`) keeps one `ParamsBody` per open plot in a `QStackedWidget`
(keyed by `session.key`): `bind` shows it (rebuilding only if the session or its schema changed),
`discard` drops it when the tab closes. Section open/closed state is QSettings
`params/sections/<kind>/<title>`.

Plot settings persist in `<simulation>/<kind>.plot` (YAML, `core/plotting/plot_file.py`): read by
`PlotSettingsStore` after the load worker, applied field by field over `default_params`
(`PlotSession.defaults` stays the module default), written only after a user edit (params panel or
pan/zoom), debounced 1 s and flushed on tab close, regenerate and exit. Window layout, grid mode/sort and the last folder are
QSettings (`layout/*`, `files/*`, `explorer/last_folder`).

### Spin (spec 13)

`core/calculations/bands/` and `pdos/` are packages split by responsibility: `module` (roles and thin
hooks) ties `detection`, `data`, `params` and `render`. A collinear spin run (the SCF or pw.x bands
output has `spin_polarized`) has two bands.x runs (`spin_component` 1 and 2 of `&BANDS`): the ↑ files
stay in the `gnu` / `filband` roles and the ↓ ones are the roles `gnu_down` / `filband_down`, so the
mapping dialog, `FolderMemory` and the panel need no spin code. Pairing runs in `finalize`
(`detection.assign_channels`), not in `select`, because the SCF may only be inferred from a neighbour
folder there: bands.x input (`spin_component`, `filband`) → file named by a bands.x output → a whole
`up`/`dw`/`dn`/`down` word in the name; if nothing identifies the files, ↑ only plus a warning (never
guessed by order), and a role the user mapped is never touched. A file the inputs of *both* channels
name (repeated `filband`) holds only the last run: it goes to no channel, with its own warning.
`BandsDataset.spin` is `bands_down is not None`; edges are per channel (`data.spin_channel_edges`):
counted from `PwOutput.n_electrons_up_down` with fixed occupations (pw.x prints one HOMO for both
channels, and a band path may top it), else split at the channel's E_F (`channel_edges`, smearing).
The dataset's `vbm` / `cbm` / `gap` are the global ones, set only when both channels have a gap; a spin
run with ↑ only gets `edges["up"]` (summary "gap ↑" / "↑ metálico", never a bare "metálico"). A run
without spin keeps the old path (`render._render_plain`, `n_electrons / 2` edges). Two Fermi energies
(`PwOutput.fermi_up_down`, fixed magnetization): the reference is their mean, one line per channel
(↑ solid, ↓ dashed). The side-by-side layout shares both axes (`draw.side_axes`), so a zoom in either
panel lands in `axes_limits[0]`. PDOS `spin_mode`: mirror (default) | overlay | up | down | sum.

### Navigation, filters and selection (spec 16)

Backend in `core/` (Qt-free, in `test_architecture`'s `QT_FREE`): `navigation.py` (`NavigationHistory`:
back stack, current, forward stack, 50 each, no repeat in a row, vanished folders skipped and
forgotten; `breadcrumb_segments`, `collapse_count`), `nav_store.py` (`NavigationStore`: favorites and
the last 10 recents per project in `navigation.json`, keyed by the resolved `local_root`, paths
relative to it, favorites saved at once and recents on `flush`, a corrupt file set aside by
`appdirs.set_aside_corrupt` like `folders.json`) and `filtering.py` (`name_matcher`: case-insensitive
substring with `*`/`?`; `CategoryFilter`: badges pick folders, states and visual types pick files, a
kind with nothing ticked is hidden while the other has something).

`ui/widgets/breadcrumb.py:Breadcrumb` sits in the `TopBar` with the ◀ ▶ buttons; the middle levels
nearest the project collapse into a "…" menu (`relayout`, in `resizeEvent`). `filter_bar.py:FilterBar`
(name field, "Filtrar ▾" menu, removable chips; Esc clears and hides; typing debounced) is in both
the explorer and the grid, opened by a Ctrl+F `QShortcut` on the panel with `WidgetWithChildren`
context, so the text viewer's Ctrl+F never crosses it. `FileFilterProxy` applies the filters from
caches only (`DetectionService.peek_results`, `file_sniff`): `scope` limits them to the grid's folder
(its ancestors must stay), `keep_ancestors` is the tree's recursive filtering (only while filtering);
an undetected folder under a badge filter stays as "detectando…" and `refilter_later` runs when
`detected` arrives; turning a badge filter on in the grid requests detection of the folders it lists
(it paints no badges, so nothing else would). The grid's filter is cleared when it changes folder;
the tree's when navigation (`select_path`) would be hidden by it. `nav_sections.py:NavSection`
(FAVORITOS, RECENTES) sit above the tree, hidden while empty; a missing folder is dimmed.
`grid_view.py:GridView` is the grid's `ExtendedSelection` view: Enter with several selected emits
`enter_many`, `FilePanel` drops `..` from every selection (`selection_changed(list[Path])`) and opens
at most `MANY_FILES` files without asking (`ask_open_many`).

### Help, command palette and first run (spec 18)

`ui/actions.py:ACTIONS` ends with the "Ajuda" menu (F1 shortcuts, Ctrl+K palette, log, data folder,
about). Three controllers are built by `for_window(window)` factories (keeps `main_window.py` thin):
`ui/help_controller.py:HelpController`, `ui/palette_controller.py:PaletteController` and
`ui/first_run.py:FirstRunController`; slot paths in `ACTIONS` reach them as `help.*` and
`command_palette.open` (never `palette`: that is a `QWidget` method).

- **Shortcuts dialog** (`ui/dialogs/shortcuts.py`, non-modal, one at a time): rows are the registry's
  actions that have a key, plus `shortcut_help() -> list[(action, keys, where)]` of the widgets that
  handle keys themselves (`FilePanel`, `ExplorerPanel`, `Workspace`, `NavigationController`; `TextViewer`
  is a `staticmethod` over its module `SHORTCUTS` table, which also builds its `QShortcut`s). A new
  widget shortcut = an entry there; keys already in `ACTIONS` are not repeated.
- **About** (`ui/dialogs/about.py`, `core/about.py`): versions come from `importlib.metadata`, so ASE is
  never imported (spec 14). `core/appdirs.log_path()` is the one place for the log path.
- **Palette**: `core/fuzzy.py` (`rank`, accent/case-blind subsequence, scopes `>` `/` `@`, recency only
  breaks ties) is Qt-free; `core/folder_index.py:list_folders` is the worker's walk (same hidden-dir
  rule as the panels, breadth first, 20 000 cap, symlinks skipped). `PaletteController` builds rows
  (enabled actions, favorites, recents, tabs, index folders) and the index lazily on the first open;
  `refresh()` (F5) and root swaps call `invalidate()`. `widgets/command_palette.py` is only the window.
- **Tooltips** (R3): `CalculationModule.description` + `badge_tooltip()` and
  `core/file_kinds.status_tooltip` hold the wording; `widgets/item_tooltips.py` and the delegates'
  `helpEvent` read caches only (`peek_results`, `file_sniff`). `ui/painting.badge_layout` is shared by
  paint and hit-test.
- **Footer** (R4): `widgets/elided_label.py:ElidedLabel` + `StatusBar._fit_labels` (budgets set from the
  bar's width, message keeps 200 px). Tests read `.full_text()`, not `.text()`.
- **First run** (R5): `LoadedConfig.first_run` is True only when the lookup found no file (a
  `LoadedConfig(cfg, None)` built in code is not a first run). `FirstRunController.state` is `first_run`,
  `missing_root` (`local_root` is not a dir) or None; the overlay (`widgets/empty_state.py`) sits on the
  splitter's parent. Lain only *creates* a config (`core/config_template.create_config`, mode `"x"`);
  with an existing config "Escolher pasta…" is session-only (`MainWindow.use_session_root`). The
  template ships as `src/qe_studio/resources/config.example.yaml`; `tests/test_config.py` keeps it
  identical to the root `config.example.yaml`.

### Text viewer and tabs (spec 10)

`ui/widgets/text_viewer.py:TextViewer` = banner bar ("Abrir no editor externo", "Carregar tudo"),
a small navigation bar, `SearchBar` and `CodeView` (`code_view.py`: `QPlainTextEdit` + line number
margin + search highlights as `ExtraSelection`s). `core/textfile.py:read_slice` returns the whole text
or, above 4 MB, head + tail with a marker; a `LineMap` keeps real line numbers after the marker (it
counts the omitted newlines in streaming, in the worker). The worker also decides the highlighter:
`highlighters.py:OutputHighlighter` for QE outputs and job logs (rules are theme tokens `hl_*`; only
the `%%%%` error block keeps state between lines). The viewer's shortcuts (Ctrl+F, F3, Ctrl+L,
Ctrl+Home/End, Esc) are `QShortcut`s with `WidgetWithChildrenShortcut`, so Ctrl+F in the explorer or
the grid never reaches it. Tabs: `workspace_tabs.py` (`TabBar` emits `middle_clicked` and
`menu_requested`); every close path of `Workspace` goes through `close_tab`, so `tab_closing` still
flushes `<kind>.plot`. "Revelar no explorador" and "Abrir no editor externo" are signals of
`Workspace`; `MainWindow` answers them (`reveal_in_explorer`, `ItemActions.open_default`).
`Workspace.close_tabs_under(path)` closes the tabs whose `paths` / `path` (a `PlotView`'s is what it
shows) lie inside a renamed path; `set_busy(key, on)` swaps a tab's icon for a spinner.
`core/text_preview.py:read_preview` (worker) is what the viewer shows: text or ends, banner (job logs,
big files), `LineMap`, and for inputs the lint and the extract.

### Input viewer (spec 11)

A QE input opens in the same `TextViewer`. `core/qe/input_lexer.py:scan_line(text, LexState, lineno)`
is the one lexer (tolerant, never raises; `LexState.code` fits a Qt block state): `core/qe/input_lint.py:lint`
walks a file with it and adds the whole-file rules (unclosed namelist, repeated/unknown namelist or card,
card options), and `highlighters.py:InputHighlighter` colors blocks with it (theme tokens `syn_*`), so
both agree on what a token is. It checks how things are *written* only: an unknown parameter name is
advanced validation, not done. `LintIssue.line` is 1-based and columns 0-based half-open. `lint` is not
`parse_input` (ASE), which detection and plots keep using. `core/sniff.py:looks_like_input(path)` (head
only, no ASE, GUI-thread safe) decides what is an input, even when sniff says UNKNOWN because ASE
choked; `core/file_kinds.py:viewer_kind` uses it for unknown suffixes. `read_preview` (worker) lints
inputs up to `INPUT_READ_LIMIT` (above it: colors only, banner says so) and extracts key parameters
(`core/qe/input_extract.py`); `ui/widgets/input_view.py:InputView` shows the issues row (F8 /
Shift+F8), the chip strip (`ui/widgets/flow_layout.py`) and "Comparar com…". `CodeView` has generic
diagnostics (`set_diagnostics`: margin marker + tooltips; the wavy underline is the highlighter's),
`set_numbers` and `set_row_backgrounds` for padded side-by-side panes. `Workspace.open_diff(a, b)`
(tab key `diff:<a>|<b>`; `compare_with` asks for the file) opens `ui/widgets/diff_view.py:DiffView`,
which only lays out `core/qe/input_diff.py:compare_files` (worker): by parameter (`normalize_value`:
numbers as floats, logicals as bools, strings casefolded) or line by line (`text_rows`, `difflib`).

### Output summary (spec 12)

"Resumo" (context menu of every file whose cached sniff `is_output`) opens a `summary:<path>` tab with
`ui/widgets/summary_view.py:SummaryView`: a bar ("Copiar", "Abrir saída", "Atualizar") and sections of
label/value rows (`summary_widgets.py`; rows with `children` expand, a double click on a row with a
`line` opens the output there through `Workspace.open_output` and `TextViewer.go_to_line`). The
summary is never saved; closing the tab drops it. The package `core/qe/summary/` is Qt-free:
`scan.py:Scanner` is a one-pass line scanner (substring test before each regex; "last wins" facts,
"first" ones for the initial energy and volume) that keeps the line of every fact; `build.py` turns
the facts into `SummarySection`s (`SummaryRow.level` colors the value, `.line` is the source line);
`text.py` has the value formatting and `to_text` ("Copiar"). `summarize(path)` streams the file once:
the scanner sees each line through `_observe`, and for relax / vc-relax the same stream feeds
`parse_relax`. Fermi / HOMO-LUMO and the calculation type come from the `PwOutput` the sniff cache
already holds, so `summarize_lines(lines, pw=None)` (the property tests) has neither. `parse_scf` is
not used: it describes the first SCF cycle only. The formula counts the `tau(` site lines of the
header (no ASE). Only pw.x outputs get "Sistema" and "Resultados"; every program gets "Geral" and
"Avisos e erros". Outputs of hundreds of MB take seconds (about 30 MB/s), in a worker, behind
"Lendo <arquivo>…".

### Threading rules (GUI thread must never parse files)

- One helper runs every background task (spec 15 R1): `core/tasks.py`. `run_task(fn, *args,
  on_done=, on_error=, pool=None)` returns a `TaskHandle` (`cancel()`, `cancelled`, `done`); a
  `TaskGroup` keys tasks so a new one for a key cancels the previous (`submit(key, fn, …)` calls
  back `on_done(key, result)` / `on_error(key, exc)`; `active(key)`, `cancel_all()`, `wait()`,
  `shutdown(timeout_ms)`). Callbacks run on the GUI thread through one dispatcher object; a
  cancelled or superseded task never calls back. There is no signal object per task, so nothing has
  to be kept alive until its slot returns (no `QTimer.singleShot(0)` for workers). A callback that
  is a bound method of a `QObject` holds it weakly, and its destruction cancels the task (a closed
  tab neither stays alive nor gets its read). Without `on_error`, exceptions are logged.
- Private pools (a thread limit or an order) have **no Qt parent**: a child pool is destroyed
  inside its parent's C++ destructor, maybe with the GIL held, and waits for tasks that need the GIL.
- `ui/services.py:DetectionService` caches detection per folder and runs misses in its 2-thread pool
  (`TaskGroup` by folder; `fresh` requests jump the queue and supersede). `detect_now()` is
  synchronous: scripts and tests only. F5 (`invalidate()` without a folder) keeps the sniffs of files
  that still exist (`SniffCache.prune`: each entry is checked against its file's (mtime, size) when
  used anyway); `ui.paranoid_refresh: true` drops them all.
- `PlotWorkflow` loads datasets in the global pool, then renders on the GUI thread. Exports run in a
  worker with their own `Figure` + `FigureCanvasAgg`. matplotlib's global state is serialized by
  `MPL_LOCK` (`threading.RLock`): `PlotSession.render`, `render_figure` and `export_figure` hold it;
  on screen `PlotView.render` and `ScaledFigureCanvas.draw` only *try* it and retry after 50 ms, so
  the GUI never waits for an export.
- Connect long-lived signals (e.g. `ThemeManager.theme_changed`) to bound methods, not lambdas,
  so they disconnect when the widget is deleted. Dialogs use delete-on-close.
- `app.main()` waits on the global pool before exit so no worker outlives the interpreter.

### Sync (PRD §5, pull only)

`core/sync/rsync.py` builds commands/env and parses output (children run with `LC_ALL=C.UTF-8`,
`TZ=UTC`, `--no-h` because rsync output is locale-dependent). `planner.py` is pure: dry-run
records + local stats → per-file NEW / UPDATE / LOCAL_NEWER; files only present locally (like
`plots/`) never block a pull. `request.py:prepare_sync` decides whether a pull can start (configured?
folder inside the project? password needed?). `controller.py` is a `QProcess` state machine (`rsync
--version` → dry run → plan, whose local stats run in a `run_task` worker → conflicts → transfer)
that never opens
dialogs: it emits `conflict_needed` and waits for `resolve()`, so UI and tests supply the answer.
Every stage runs through `_step()`, so an exception ends the sync as FAILED instead of hanging
it. `monitor.py` probes in daemon threads, not a `QThreadPool` (DNS ignores the connect timeout
and a pool's destructor waits without limit). Passwords reach ssh only via `SSH_ASKPASS`
(`askpass.py`, installed as `qe-studio-askpass`) through the child env, never argv or logs; unknown
host keys are always refused.

### Context menu (spec 5)

`ui/widgets/context_menu.py:ItemActions` builds the right-click menu for the tree and the grid
(both panels emit `item_menu_requested(paths: list[Path], pos)`, the tree a one-item list →
`MainWindow._show_item_menu` → `ItemActions.show`, which reads the cached sniff once, in
`file_actions_of`: "Plotar" for a
single-file module, "Resumo" for any QE output, both above the four spec-5 actions). "Abrir com" lists programs from `core/desktop_apps.py` (Qt-free `.desktop`/`mimeapps.list` reader, one
cached `catalog()` per session) and starts them with `QProcess.startDetached(argv)`, never a
shell. A folder also gets "Adicionar/Remover dos favoritos" (`favorite_toggled`, answered by the
`NavigationController`). With several items selected in the grid (`multi_menu`) the menu is the
count title, "Abrir local de origem" (`ShowItems` with every URI), "Copiar" (one URI / path per line),
"Comparar" for exactly two `looks_like_input` files (path order; `compare_requested` →
`MainWindow.compare_inputs`) and the favorites item when all are folders; per-item actions are hidden.
Renaming goes through `MainWindow.rename_path` because it touches global state: write the
pending `.plot` settings of what it moves (`flush_now(inside=)`), wait for running exports,
`core/file_ops.rename_item` (refuses existing targets), `Workspace.close_tabs_under`,
`FolderMemory.rename`, invalidate detection. Tests must patch `QMenu.exec` (the
`main_window` fixture makes an unpatched one fail) and never reach the real session D-Bus
(`ItemActions._show_items_dbus`).

### Theming

`ui/theme/manager.py` assembles modular QSS from `ui/resources/styles/<domain>/*.qss` (domains
listed in `STYLE_DOMAINS`), substituting `${token}` colours from `ui/resources/themes/{dark,light}.yaml`.
Any new colour must be added as a token to **both** theme files (badge colors of a new module are
optional: it falls back to `badge_other_*`). Custom-painted widgets read
`ThemeManager.color(token)` and refresh on `theme_changed`. Icons are Material Symbols SVGs tinted
at runtime; fonts (Inter for UI, JetBrains Mono for numbers/paths) are vendored.

### App identity and desktop

`ui/app_identity.py:configure_application` (called by `ui/app.py:main`) sets the application and
organization names (old product name, see Naming), `setDesktopFileName("lain")` and the window
icon from `ui/resources/app/` (`lain.svg` + `lain-<N>.png`, rendered by `scripts/build_icons.py`
and committed). `packaging/lain.desktop` and `scripts/install_desktop.py` are the optional,
user-run desktop integration; nothing installs them automatically.
