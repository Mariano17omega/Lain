# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Lain: QE Studio: a PyQt6 desktop app to browse, pull-sync (rsync + ssh) and plot Quantum ESPRESSO
simulations (band structures, PDOS, relax/vc-relax progress). Requirements live in `specs/spec_0-PRD.md`; code comments
cite it as "PRD §x.y". Change specs derived from `specs/Ideias.md` are `specs/spec_N-*.md`
(prioritized index in `specs/README.md`); the implemented ones are moved to `specs/Archived/`. The UI follows `Documentation/design system (UX)/`.

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
  queue, then writes what is pending) before reading a `.plot`. Spec 32: an export is named from the
  project root (`<folder from local_root>-<stem>`: `demo_project` is the root, so `03_bands` exports
  `03_bands-bands.png`; a folder outside it, like the contract test's `dummy_sim`, keeps its own name) and
  writes `.csv` last for bands, PDOS and bands + DOS. `test_export_names.py` (names, `plan_export(session,
  root)`), `test_plot_table.py` (the CSV format and every module's columns, each compared with the
  artists of the rendered figure: a table that drifts from the drawing fails there) and
  `test_export_csv_ui.py` (a window on the `raiz` fixture) cover it; `test_no_wheel.py` the fields of the
  panel. A modal run with a real `exec()` needs `test_atoms_dialog.py:drive_modal(act)`, which acts on the
  window once `exec` has it up (a plain call before `exec` runs would block).
- `test_architecture.py` checks the architecture rules by AST: no `.py` over 500 lines (exceptions
  list, empty; `PER_FILE_LIMIT` gives `ui/main_window.py` 450), `core/` never imports `qe_studio.ui`, PyQt6 only in the four `core` modules listed
  below, no `open(` / `read_text` / `read_bytes` / `loadtxt` in `ui/` (but `ui/theme/manager.py`),
  and the modules moved to `core` by spec 15 import without PyQt6. Spec 27-8: `FS_ALLOWED` lists, per `ui/` file,
  how many disk-touching calls (`FS_CALLS`: `resolve`, `exists`, `is_dir`, `is_file`, `stat`, `iterdir`, `glob`, `rglob`,
  `samefile`) it makes today; a new one fails the test (put it in `core/` or a worker) and so does a count *lower*
  than listed (lower the list: it only shrinks). `test_tasks.py` covers the
  background-task helper; `test_busy_indicator.py` and `test_export_worker.py` the spinner and the
  non-blocking export.
- Detection performance (spec 14): `tests/synthetic.py` builds a 520-folder project from the fixtures,
  a 200 MB relax output, an 80 MB `.gnu` and a 20 MB output with a long header, always in tmp dirs.
  `test_perf_detection.py` times them (`-m perf -s` prints the numbers; the baseline and budgets are
  in the spec's notes); its import test (no `ase` after importing `main_window`) is not `perf`.
  `test_perf_grid.py` (spec 27-8) times a 100-atom PDOS and bands + DOS (`draw` = render + Agg draw) and, for a 6×6 grid
  drawn by a worker, the longest stall of the GUI thread and the time until the picture shows.
  `test_plot_view_worker.py` and `test_offscreen.py` cover the worker path; a test that reads `view.figure` of a grid first
  waits with `plot_grid_helpers.settled(qtbot, view)`.
  `test_pw_output_regression.py` compares `PwOutput` of every fixture output with
  `pw_output_golden.json`, captured from the parser before it read head and tail separately.
- Sync integration tests run the **real `rsync` and `ssh` binaries** (skipped if either is absent).
  `sync_helpers.run_sync(..., before_confirm=plan -> None)` is where a test edits local files while the
  preview is open (spec 27-3); `test_instance_lock.py` and `test_appdirs.py` cover the lock and the write;
  `test_rename_blocked.py` fakes a running sync with `window.sync.controller` + `window.sync.scope`
  (reset it afterwards: closing the window shuts the controller down).
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
  `test_sync_integration.py` and `test_sync_ui.py` (shared helpers: `tests/sync_helpers.py`, whose
  `run_sync` answers `plan_ready` with `confirm` (default True; None leaves it to the test) and
  collects the plans in `plans=`). `test_sync_dialog.py` drives `SyncCoordinator.run` with a
  host-less `Endpoint` (the stacked window, Esc on the preview, a failure over the window);
  `test_toast.py` injects short `duration_ms` / `fade_ms`.
  Tests whose remote is a plain local path (`Endpoint(path)` without host) need no server.
- The one compound command the server accepts is a push's `--rsync-path` (spec 27):
  `mkdir -p <dir> && rsync --server …` makes `<dir>` in Python, only inside `remote_root` (anything
  else, outside it or another `&&`, is 127 and logged), then runs rsync. Pushes are tested in
  `test_sync_push.py` (host-less: preview first, integrity, the race, excludes; over the server: the
  nested `mkdir -p`, key and password), `test_sync_push_plan.py` (Qt-free) and `test_sync_push_ui.py`;
  `sync_helpers.run_push(..., confirm=, plans=, before_confirm=)` runs one. A host-less push makes
  only the last missing level (local rsync ignores `--rsync-path`).
- Spec 27-4: `test_load_cache.py` builds a `LoadCache` with small budgets (the real constants have their own test),
  `test_cancel_loaders.py` runs every loader under `cancel.bind(token)` and in a started-then-cancelled `run_task`
  (`cancelled_midway`), `test_parser_memory.py` measures peaks with `tracemalloc` on `synthetic.make_gnu` /
  `make_filband` and compares with the old readers, which live only there, and `test_tab_close_loads.py` closes tabs
  mid-load. `conftest.py` empties the process-wide dataset cache around every test (`drop_cached()`).
- Tests have a 60 s timeout (pytest-timeout).

## Architecture

`src/qe_studio/core` is logic without widgets (only `core/sync/_process.py`,
`core/sync/controller.py`, `core/sync/monitor.py` and `core/tasks.py` use Qt, for `QProcess`, signals
and the thread pool);
`src/qe_studio/ui` is the PyQt6 app.

### Architecture rules

- **No files over ~500 lines that centralize everything.** Split by responsibility before a module
  grows past that. `tests/test_architecture.py` keeps every file of `src/qe_studio` under 500, and
  `ui/main_window.py` under 450 (`PER_FILE_LIMIT`: the room spec 27-5 made is not spent again by accident).
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
`rename_path`, `reload_config`, `refresh_folder`, `closeEvent` (a few lines over `ui/shutdown.py`), plus a thin facade the tests and
`scripts/screenshot.py` use (`plot_ready`, `plot_failed`, `export_finished`, `sync_finished`,
`generate_plot_for`, `export_plot`, `monitor`…).

- `ui/layout_controller.py:LayoutController`: panels, splitter widths (`fit_widths`), left panel
  mode and the QSettings `window/geometry`, `layout/*`, `files/*`. Knows no plot or sync.
- `ui/plot_workflow.py:PlotWorkflow`: detect → `core/detection.plot_choice` (`Chosen` / `Ambiguous`
  → `choose_result` / `NeedsMapping` → `ask_mapping`, `ManualTarget`) → `load_plot` (load pool) →
  `.plot` read (settings queue; a second request for a plot that is loading replaces the first, spec 27-9: `_load`
  cancels both stages, `PlotSettingsStore.cancel_read`, and keeps the first one's `auto_export`) →
  `build_session` → tab; readout, "Plotar SCF" source, busy
  indicator (`ui/busy.py:BusyTracker`, counted by name: the footer spinner and "Detectando cálculo…"
  / "Carregando …" / "Exportando…", plus a spinner in the tab of a plot being regenerated; no
  `setOverrideCursor`). It asks the window for panels and messages through signals
  (`panel_requested`, `message`). Exports: `ui/plot_export.py:PlotExporter` (overwrite question on
  the GUI thread from `core/plotting/export.plan_export(session, root)`, `root` = `lambda: config.paths.local_root`
  read at each export, then `export_files` in a worker on a snapshot of the params; close waits up to 10 s for
  exports).
- `ui/sync_coordinator.py:SyncCoordinator`: `core/sync/request.prepare_sync` → session password →
  `SyncController` + dialogs → report; owns the `ConnectionMonitor` (replaced on config reload) and
  emits `cluster_changed`, `synced(local_dir)` (its own `on_synced` calls the injected `refresh`, the window's
  `refresh_folder`) and `finished`. Its entry points are `start_selected()` (the Rsync button, `sync.start`:
  the injected `current_folder`) and `start_project()` (`sync.project`: the selected project, else the root; spec 31
  `set_project`), the slots in `ACTIONS`. It also says
  the scope (spec 17 R1): `show_scope(folder)` (called by `on_folder_selected`) renames the
  `sync.start` action ("Sincronizar a/b"), sets the text and tooltip of `sync.project` ("Sincronizar projeto ilita" /
  "Sincronizar tudo"), the tooltip of `sync.start` (bound by
  `bind_actions`) and emits `scope_changed(tooltip)` for the Rsync button. A pull that ends DONE /
  UP_TO_DATE emits `notice(text, level, details)` → `MainWindow.toast`; FAILED and LOCAL_NEWER
  open their `QMessageBox` over the `SyncDialog`, which the coordinator closes after it (`finish`).
- `ui/widgets/toast.py:Toast` (spec 17 R3.4): a child of the window (never top level), queue of
  notices, one at a time; the countdown `QPropertyAnimation` *is* the timer (pause on hover), then
  a `QGraphicsOpacityEffect` fade; an event filter on the window places it (`toast_position`, a
  pure function) on resize/show and `shutdown`s it on close. "Detalhes" opens the non-modal
  `dialogs/details.py`. Reusable: `show_message(text, level, details)`.
- `ui/plot_settings.py:PlotSettingsStore`: every `.plot` read, write and removal in one private
  single-thread pool, so they happen in order (a regenerate reads what closing the tab wrote);
  edits are debounced 1 s; `flush_now` writes on the spot (window close, before a rename). Every write
  takes a ticket from `core/plotting/plot_file.py:WriteOrder` when it is asked for and `WriteOrder.run`
  (one lock) drops one older than what that `.plot` already got (spec 27-3): after `DRAIN_MS` the GUI
  thread writes anyway, and the older write still queued in the worker cannot land over it.
- `ui/rename_controller.py:RenameController` (spec 27-3): the body of `MainWindow.rename_path` (now a
  one-line facade over `window.renamer`). `blocked(path)` asks the *blockers* `for_window` builds and
  refuses (`QMessageBox.information`, before the name dialog) while a pull / push (`SyncCoordinator.folder`
  overlaps the path: `file_ops.overlaps`; the project root blocks all), an export (`PlotExporter.running`),
  a derived SCF (`DeriveController.active_under`) or a new calculation (`CalcCreateController.creating_under`)
  works there; `wait_for_exports()` returning False after the dialog refuses too. A new blocker is a
  function path → reason in that list. `ask_rename` and `rename_item` are imported there: patch
  `qe_studio.ui.rename_controller.*`.
- `ui/navigation_controller.py:NavigationController` (spec 16): the history, the breadcrumb and the
  favorite / recent folders. `MainWindow.on_folder_selected` is where every folder change arrives
  and calls `visited`; going back, forward, to a breadcrumb level or to a favorite is
  `ExplorerPanel.select_path` like a tree click (the history already holds the target, so `visited`
  pushes nothing). Also owns the side mouse buttons (an application event filter limited to this
  window) and answers the explorer's two `NavSection`s. `rename_path` tells it before reselecting. `restore()`
  (start-up) selects the last folder of QSettings `explorer/last_folder` if it is still inside the project, else the root.
- `ui/shutdown.py` (spec 27-5): what `MainWindow.closeEvent` does. `close_dialogs(window)` first: each non-modal
  dialog's controller has `close_dialog() -> bool` (`CalcCreateController` closes its window, whose `closeEvent` asks
  `ask_discard` only when `TabsPage.dirty` and refuses while `_busy`: False keeps the main window, with the dialog in
  front; `Grids` and `Help` always close; the one that can refuse is asked first). Then `run_shutdown`: layout saved,
  `window.hide()`, and the `Step`s of `steps_for(window)` in a `ShutdownSequence` with one budget (`TOTAL_MS` = 8 s):
  `cancelar` (loads, tab reads through `Workspace.cancel_loads` → `cancel_load()`, grids, derive, palette), `sync`
  (≤ 2 s, then killed), `exportações` (`own_budget`: waits `EXPORT_WAIT_MS` whatever is left, never cut short, and not
  charged to the budget), `.plot` (`PlotSettingsStore.close`: one drain), `estado` (navigation flush, last folder, theme,
  `QSettings.sync()`), `detecção`, `grade`, `árvore`. A step gets the ms it may take (0 when the budget is gone: it does
  its non-blocking part; no step is skipped, so the state is always saved) and returns False if it overran: the logged
  warning and `ShutdownReport.late` (`MainWindow.shutdown_report`). A new `shutdown` must take the time it may use and say
  whether it finished. `ui/app.py:finish` then gives the global pool `POOL_WAIT_MS`; with a task still running it logs
  the late steps and `os._exit`s (the state is written already) instead of finalizing Python under live Qt threads.
- `ui/excepthook.py:ExceptionReporter` (spec 27-5 R3) is `sys.excepthook` (`install_excepthook`; `app.main` calls
  `set_excepthook_window(window)`): every error to the log; to the user, once, as a `Toast` of level `error` (traceback
  in "Detalhes") — before the window exists, as one `QMessageBox`. The same (type, text, file:line) within 10 s only counts
  (" (xN)" in the log), an error raised while one is reported goes to the log alone, a hidden window gets the log only.
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
   with no anchor role present returns `None`. `FolderListing` (the files a detection reads) and `IGNORED_SUBDIRS`
   live in `core/calculations/listing.py`, which `base` re-exports: `base.py` stays under the 500 lines.
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
  fields); `colors=` names the color-override dict of a `"series"` field; `requires=` names a bool parameter the field does
  nothing without (the panel disables it while that one is off and says which to turn on: `ParamsBody._apply_gates`).
  `plot_file` validates stored
  values by field kind (`color`, `choice`, series colors), never by name: a parameter without a
  schema field declares `field(metadata={"kind": "color" | "colors"})` on its dataclass.

`load_cached()` memoizes `load()` on file stamps and is called from worker threads (spec 27-4):
`core/calculations/load_cache.py:LoadCache` keeps the datasets within 8 entries *and* `LOAD_CACHE_BYTES` (256 MB, counted
by `core/sizing.py:nbytes_of`: every ndarray reached through dataclasses / containers, a view through its root array; a
dataset over the whole budget is returned, never kept), loads a key once however many threads ask (a waiter whose loader
failed or was cancelled loads it itself) and does not keep the result of a cancelled task. `drop_cached(under, *,
min_bytes)` empties it by folder: `DetectionService.invalidate` (F5, sync, rename, remap) and `PlotWorkflow._on_tab_closing`
(`CLOSE_DROP_MIN_BYTES` = 4 MB; not when the tab is only being replaced by its regenerated plot, `_replacing`).
The bands.x readers keep their peak near the file: `read_gnu(path)` hands the file to numpy's C reader (`read_gnu_text`
is the same for text in memory) and `read_filband` fills the array the header announces; neither result may be a view
of the parsed table.
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

**Legend and axis text sizes.** `CommonParams` (so every module, in the "Legenda" section of `COMMON_FIELDS`) has
`legend_size` ("Tamanho"), `legend_transparency` ("Transparência": 0 opaque … 1 invisible, the frame's alpha upside
down, default 0.2 = matplotlib's 0.8; only visible with `legend_frame`), `tick_size` ("Marcações") and `label_size`
("Rotulagem dos eixos"); the three sizes are `float | None` (`None` = "auto": 0.85 × `font_size` for the legend, the
figure font for the others, so figures made before them do not change). `plotting/draw.py` is the one place that
applies them: `add_legend` and `apply_text_sizes`, which `finish`, `finish_side` and `finish_joined` call before
`tight` (a module draws its labels first, then calls one of them). A stored value that cannot be a size or an alpha
falls back to the default instead of raising. Tests: `test_legend_style.py`.

**Names and CSV of an export (spec 32).** The stem is `names.join_stem(names.export_prefix(folder, root),
module.export_stem(params))`: the folders from `local_root` down to the simulation joined by `-`, then the module's
own stem (`<local_root>/ilita/Analise_1/Bandas` → `ilita-Analise_1-Bandas-bands.png`). Pure, no disk: the root itself
has no prefix (the grid keeps `grid_<name>`), a folder outside it only its own name, no leading dot, at most
`MAX_STEM_BYTES` (whole parts go from the left), and `_remove_orphans` matches the stem with `glob.escape`.
A module with `has_table = True` (bands, PDOS, bands + DOS) also gives `table(dataset, params) -> PlotTable | None`
(`core/plotting/table.py`: `Column`, `PlotTable`, `to_csv`): the values *as drawn*, whole (energy minus the plot's
reference; the view's limits do not cut them), laid out by `bands/table.py`, `pdos/table.py` (the series of
`draw_pdos`, in its order; a spin ↓ in `mirror` is negative) and `bands_dos/table.py` (the two blocks side by side,
each with its own x, both from the bands' reference). `k` is `k (2π/alat)`: bands.x's own unit. `to_csv` separates
columns by `;`, writes decimals with a comma and 10 significant digits (QE prints ≤ 8; the rounding noise of
`E − E_F` stays out of the file), leaves NaN / infinity / the end of a short column empty and the first
line holds the names; `write_table` adds a UTF-8 byte-order mark (Excel in pt-BR) and moves a temporary file in
place like the figures. `export_files` = `export_figure` (unchanged: figures only) + the CSV, last; `ExportPlan.table`
puts the `.csv` in `existing` and in the `_2` search, so the set is asked about and versioned together. The CSV is
not an `export_formats` entry and has no checkbox.

**Element colors of the PDOS.** `plot.atomos_colors` (`config.DEFAULT_ATOMOS_COLORS`: Al, C, H, Hg, K, O, Si) is
`orbital_colors` keyed by species label: the user's entries are *added to* the defaults (`PlotConfig._fill_atoms`), copied
into `PdosParams` / `BandsDosParams.atomos_colors` (`kind: colors`, kept in the `.plot` like `orbital_colors`).
`pdos/render.py:series_colors` gives a species with an entry its color (grouping "Espécie"), shaded per orbital with
`_shade(color, "spdf".find(orbital))` in "Espécie + orbital" (s pure); a species without one keeps the orbital color /
palette; `series_colors` (the panel's swatches) still wins; grouping "Orbital" ignores it.

`ParamsPanel` (`ui/widgets/plot_params.py`) keeps one `ParamsBody` per open plot in a `QStackedWidget`
(keyed by `session.key`): `bind` shows it (rebuilding only if the session or its schema changed),
`discard` drops it when the tab closes. Section open/closed state is QSettings
`params/sections/<kind>/<title>`.

Plot settings persist in `<simulation>/<kind>.plot` (YAML, `core/plotting/plot_file.py`): read by
`PlotSettingsStore` after the load worker, applied field by field over `default_params`
(`PlotSession.defaults` stays the module default), written only after a user edit (params panel or
pan/zoom), debounced 1 s and flushed on tab close, regenerate and exit. Window layout, grid mode/sort and the last folder are
QSettings (`layout/*`, `files/*`, `explorer/last_folder`).

### Figures drawn by a worker (spec 27-8 R2)

A module with `render_in_worker = True` (the grid: 36 cells take ~2.4 s of layout and Agg) is never drawn on the GUI
thread. `core/plotting/offscreen.py:draw_offscreen(session, params, target)` (Qt-free) builds the figure in a `Figure` +
`FigureCanvasAgg` of its own under `MPL_LOCK`, from `snapshot(session)` (the parameters when it was asked), and draws it at
`Target(inches, dpi)`; `render_grid` calls `cancel.check()` between cells, so a newer render supersedes it. `PlotView.render()`
runs it with `run_task` (`drawing`, `drawing_changed(key, on)` → footer "Desenhando…" and the tab spinner in
`PlotWorkflow._on_drawing`) and `_adopt`s the result when its `Target` still matches the canvas (else it draws again):
`ScaledFigureCanvas.adopt` makes the worker's figure the canvas's, with its `renderer` and the event registry matplotlib keeps
on the figure (`_canvas_callbacks`, so the toolbar's pan/zoom and the readout stay connected), and nothing is drawn on the
GUI. A canvas that `worker_draws` never draws on a resize: it keeps the picture on show (`_stale`), stretched, and the view
draws again `RESIZE_MS` after the last resize. The picture and figure on show stay until the new one arrives; closing the
tab or the window cancels the worker (`PlotView.cancel_load`). A new slow module sets the ClassVar; no UI file knows which.

### Relax and vc-relax (spec 6, spec 27-7)

`core/qe/relax.py:parse_relax` is one pass over the output (also the `summarize` stream) and keeps per
`RelaxStep` the energy, force and BFGS step, and for a vc-relax `enthalpy_ry`, `pressure_kbar`,
`volume_ang3` and `cell` (3 rows, Å; `alat` / `bohr` / `angstrom` `CELL_PARAMETERS` all converted).
pw.x prints a block as `!` energy, `Total force`, `P=`, `number of bfgs steps = k`, `enthalpy new` (the
geometry just computed), then `new unit-cell volume` and `CELL_PARAMETERS` (the geometry of step k + 1),
so the pressure and enthalpy go to step k and the volume and cell to the step that ran on them: held as
`carry` and applied only when its `bfgs_step` follows (a trimmed output leaves `None`); the last step of a
converged run takes `Begin final coordinates`, and `Final enthalpy` is its enthalpy. The header
`unit-cell volume` is the *input* cell (wrong after `restart_mode = 'restart'`), so step 0 has no volume.
These checks run only in the tail of a block (`block`: from the step closing to `ATOMIC_POSITIONS`), not on
every line: `parse_relax` of 200 MB is `test_parse_relax_huge_output`. `RelaxData` also has
`pressure_threshold` (header → `criteria: … cell <` → input `press_conv_thr` → 0.5 kbar, never part of
`defaulted_thresholds`), `target_pressure_kbar` (input `press`) and `convergence_deltas()`: |ΔH| in a
vc-relax (the BFGS compares the enthalpy to `etot_conv_thr`), |ΔE| otherwise, a pair without H falling back
to |ΔE| (`RenderInfo.notes`: "entalpia indisponível neste passo").

`RelaxParams.panels` is `both` | `energy` | `force` | `all`; `all` adds the pressure (the `press ±
press_conv_thr` band) and the volume panels from `core/calculations/relax_panels.py` (always linear, steps
without a value skipped) and is `both` for a run with neither. `test_relax_figures.py` compares the artists
(bars included) of every relax fixture with `relax_golden.json`: the non-vc entries were captured before
spec 27-7, so a change of `both` / `energy` / `force` fails there.

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

### Energy gap in the legend (spec 20)

`legend_gap` (default off) is a `bool` of `BandsParams` and `PdosParams` only: the shared
`calculations/params.py:LEGEND_GAP_FIELD` goes after `COMMON_FIELDS` in both schemas (SCF and relax never see it;
bands and bands + DOS use `bands/params.py:BANDS_LEGEND_GAP_FIELD`, whose tooltip adds that the gap is along the k path).
The entry is text only (`core/plotting/gap_label.py`, Qt-free: `gap_label`, `gap_handle`: an invisible `Line2D`),
last in the legend, and does nothing with the legend hidden (the panel disables the field then: `requires="show_legend"`)
or without a gap (a metal writes no "metálico" in the legend; with the legend visible `bands/gap.py:legend_gap_notes` puts
"Sem gap para a legenda: …" in `RenderInfo.notes`, for bands and bands + DOS, unless `gap_note` already says why).
Bands: `bands/gap.py:gap_entries(dataset)` is the one source of the footer (`summary`, `_spin_gaps`) and the legend:
no spin → one entry (`channel=None`); spin → `up` / `down` (those with a gap) and `global`; the gap is `CBM − VBM`,
independent of `reference` and the window. Every band gap is the one *along the path* (spec 27-6): the footer says
`E_gap (no caminho) = …` / `gap ↑ (no caminho) …`, the legend keeps `$E_{gap}$ = …`. Without spin,
`bands/data.py:band_edges` trusts the electron count only when E_F backs it: with smearing (`fermi_kind == "fermi"`)
E_F outside `[VBM − EDGE_TOL, CBM + EDGE_TOL]` leaves no gap and `BandsDataset.gap_note` (`GAP_OFF_PATH_NOTE`; the
footer then says no "metálico"), and no E_F at all keeps the counted gap with `GAP_NO_FERMI_NOTE`; fixed occupations
and spin are not checked. An electron count that fills no whole bands (odd: one half-filled band, or a fractional charge) has no
counted gap: with smearing and E_F known `data.fermi_edges` takes the edges around E_F as `channel_edges` does for a
spin channel (VBM = top of the bands below E_F, CBM = bottom of the ones above; a band crossing E_F leaves no gap)
and sets `gap_note = GAP_FROM_FERMI_NOTE` ("gap pela posição de E_F: 495 elétrons não enchem bandas inteiras"): it
is a gap between the bands below and above E_F, not an insulating one. `bands/render.notes` puts the note in `RenderInfo.notes` (never on the figure), and
bands + DOS adds it to its own. PDOS: `PdosDataset.gap` (`pdos/gap.py:GapInfo`, set in `load_dataset`, so
the GUI only draws) is the HOMO / LUMO pw.x printed (`homo_lumo`, first of NSCF, SCF; a closed pair = metal) else
`projwfc.dos_gap` on `PdosData.total` (`dos`, drawn `≈`, 2 decimals): always the system's total, never the drawn
series, and smeared edges make it read narrower than the true gap. `dos_gap` takes the *widest* empty region within
`GAP_SEARCH_EV` = 1.0 eV of E_F (nearest on a tie; a region touching the grid edge is no candidate): with smearing E_F
often sits a few tenths of eV *inside* the top of the valence band, so a tighter window (it was 0.25 eV) found no gap
in real insulators; semicore gaps are further away, and a metal still has no empty region near E_F.

### Atom selection in the PDOS (spec 21)

`PdosParams.atoms` (`list[int] | None`, 1-based, `None` = all) is picked in `ui/dialogs/atoms.py:AtomsDialog` (button
"Átomos…" of the "Projeções" section, a `ParamField(..., "atoms")` that `ParamsBody` turns into the button + "3 de 12"; it
asks the module for `atoms_of(dataset) -> AtomChoices(sites, compound)`, disabled when `sites` is empty). The selection is
**per compound**, not per folder: `core/compounds.py` has `compound_key` (the species sequence in input order: positions
never matter, a different order is another compound), `compound_of(sites)`, `normalize_selection` (all or nothing valid
= `None`) and `CompoundStore` (`compounds.json` in the data dir, like `NavigationStore`: lazy read, atomic write, a corrupt
file set aside, `save(key, formula, None)` removes the entry). `core/qe/structure.py:read_sites` streams the pw.x header
(positions in alat units → Å, no ASE) in the load worker; `PdosDataset.sites` / `.compound`.

Another geometry of the same sequence reuses the selection, so it warns (spec 27-6 R2): `save(key, formula, atoms,
sites)` *merges* into the entry (unknown keys kept) and stores `"sites"` (Å, 0.01) without a new `FORMAT_VERSION`;
`stored_sites(key)` reads them (None for an older entry or bad shapes). `pdos/atoms.py:stored_params` sets
`PdosDataset.selection_drift = geometry_drift(saved, current)` (`GeometryDrift`: the atom that moved most over
`DRIFT_TOLERANCE` = 0.5 Å, or `counts`) when a saved selection is applied; `save_stored` passes the sites and clears it.
`pdos/atoms.notes` → `RenderInfo.notes` of the PDOS and of bands + DOS. The selection itself never changes. An atom
that re-enters through the cell boundary is a known false positive.

A parameter kept in a user store instead of `<kind>.plot` declares `field(metadata={"store": ...})`
(`plot_file.stored_elsewhere`; `stored_params` and `apply_stored` skip it, an old `.plot` with the key is ignored). The base
class has three hooks for it: `stored_params(dataset, stores)` (read: `build_session(..., stores=)` applies it over the
defaults, before the `.plot`, so `defaults` hold it), `save_stored(dataset, params, name, stores)` (write) and `atoms_of`.
`Stores` (`calculations/base.py`) is the bag of stores a module may use; `PlotWorkflow` owns it (`compounds=` kwarg, the
window's `self.compounds`). `PlotWorkflow._on_param_changed` calls `PlotSession.persist(name, stores)`: for a store-backed
field it saves through the hook and copies the value into `session.defaults` (not a plot edit: no `.plot` write, and
"Restaurar padrões" keeps it); otherwise the `.plot` write is scheduled as before. Regenerating reads the store again.

The filter is `projwfc.aggregate(data, grouping, atoms)`, applied before grouping and `hidden_series`; colors follow the
order of all atoms (`series_colors` lists only the groups left). With `atoms` set, "DOS total" is the sum of the chosen
atoms (`projwfc.selected_total`, label "Soma dos átomos selecionados") instead of `pdos_tot`; the summary says "N de M
átomos"; the gap (`PdosDataset.gap`) stays the system's. `tests/atoms_helpers.py:pdos_folder(root, species)` builds a
many-atom PDOS folder from `al_pdos_flat` (atom *n* = the fixture times *n*).

### Bands + DOS (spec 22)

"Bandas com DOS" is in the grid's `multi_menu` when the selection is two folders that
`core/calculations/bands_dos/pair.py:bands_dos_pair(results_a, results_b)` pairs: a plottable `bands` result in one
and a `pdos` one in the other, in either order. It reads the cached results (`service.results`, which schedules a
miss). Two folders that both have both kinds are ambiguous → no item. `ItemActions.bands_dos_requested(bands, dos)`
→ `PlotWorkflow.plot_pair` → `_load(core/detection.py:PairTarget(bands, dos, sniff, memory))`. Like `ManualTarget`,
its `build()` runs in the load worker: it detects both folders, calls `ordered_pair` and then `pair_result`. A folder
that is gone or no longer pairs raises a `LoadError` ("Pasta da DOS não encontrada: …"), shown by the usual failure
path. `PairTarget.from_plot_file(bands)` (worker) reopens the pair named in `bands/bands_dos.plot`.

- **Generic hooks it added.** A module can say `selectable = False`: never in the mapping combo, `plottable_modules`
  or `describe_plottable`. `DetectionResult.parts` holds the results of other folders plotted together. In that
  case `plot_id` (what keys the tab, `plot:<kind>:<plot_id>`) is their targets joined by `|`, and
  `PlotSession.paths` / `PlotView.paths` list them, so renaming either folder closes the tab.
  `PlotSession.composite` keeps `PlotWorkflow.plot_of(folder)` from taking the figure for the bands plot.
  `CalculationModule.plot_title(target, dataset)` names the tab. `match` returns at once for a module without
  an anchor role and without a mapping. A field with `metadata={"derived": True}` is written to the `.plot` but
  never applied back (`plot_file.derived_fields`): that is `dos_folder`, relative to the bands folder.
  `ParamsBody` shows `RenderInfo.notes` as "⚠" lines under the readout and drops "Remapear" for a module that
  is not selectable.
- **The module** (`bands_dos/`: `pair`, `data`, `params`, `render`, `module`). The combined result is the bands
  folder's, with both results as `parts`. Their files go under prefixed roles (`bands.gnu`, `dos.pdos_atm`:
  the panel's "Arquivos" and the load cache key).
- **Load.** `load` calls each part's `load_cached`, one after the other in the same worker, and reads the
  bands compound (`read_sites`).
- **Params.** `BandsDosParams(CommonParams)` maps onto each panel through `bands_view` (spin always overlaid)
  and `dos_view` (vertical). The schema is the band and PDOS `ParamField`s picked by name and re-sectioned:
  "Energia" is shared, the panel sections are "Bandas ▸ …" / "DOS ▸ …".
- **Render.** `draw.bands_dos_axes` (`sharey`, `width_ratios`, no space) and `finish_joined` (`tight_layout`,
  then `wspace=0`). One reference, the bands' one, goes into `bands/render.draw_bands` and
  `pdos/render.draw_pdos` (the two cuts of the standalone renderers; the goldens did not change). The
  Fermi line and filled states follow the bands' E_F.
- **Legend.** One legend, on the DOS axes (on the bands axes if the DOS draws nothing), outside by default.
  It has the DOS series, then the bands' entries, then the gap once (`gap_handles` of the bands).
- **Notes.** E_F of the two runs differing by more than 0.05 eV; compounds that differ (the atom selection
  is the DOS compound's).
- **Ticks.** `ClearOfJoin` keeps DOS tick labels off the last k label.

### Grids of plots (spec 23)

"Grids" (top bar button, action `grids.open`) puts open plots in one figure, N×M up to 6×6, a `SubFigure` per cell,
each drawn by its own module (vector export, pan/zoom per cell).

- **Definition** (`core/plotting/grid.py`, Qt-free, imports no module): `PlotRef(path, kind, partner)` (`path` is what
  the plot shows: a folder, or the output file of a single-file module such as SCF; `partner` the DOS folder of bands +
  DOS), `GridCell(row, col, ref, title)` (0-based), `GridSpec.validate()` (Portuguese sentences).
  `PlotSession.ref` makes the ref of a plot.
- **Store** (`core/grid_store.py:GridStore`, `grids.json` in the data dir, like `CompoundStore`): grids by name, paths
  relative to the root in force (`abs:` outside it; another project resolves them there, nothing is deleted), the
  grid figure's settings under `params`, `rename(old, new)` (called by `MainWindow.rename_path`).
  `PlotWorkflow` owns it as `Stores.grids`.
- **Module** (`core/calculations/grid/`, kind `grid`, in `REGISTRY`, no roles, never detected or loaded from files):
  `GridDataset(spec, cells)` where each `GridCellData` holds a *copy* of a plot session or the reason it has none
  ("Plot indisponível: …"). `render` adds one `SubFigure` per position in row-major order, draws each cell with
  `PlotSession.render(cell, style, params=)` (a cell title replaces the plot's: drawn from a copy with `title=""`) and
  fits it with `core/plotting/cell_layout.fit_cell`. `GridParams`: cell size (figure size = cols × rows of it,
  `derived` like name/rows/cols), titles, font of the titles, background, export. Exports go to
  `<local_root>/plots/grid_<name>.*`; the tab is `plot:grid:<name>`.
- **No layout engine.** A `SubFigure` has no `tight_layout` (`draw.tight` skips it), and constrained layout pads every
  axes on both sides, which split the joined bands + DOS panels. `fit_cell` is `tight_layout` for one cell: it moves
  the outer edges of the cell's axes grid until ticks, labels, legends and the cell's suptitle fit, keeping the
  module's inner spacing (`wspace=0` for bands + DOS).
- **Generic hooks it added.** `DetectionResult.plot_name` (a figure that belongs to no folder keys its tab by name) and
  `targets` (every folder shown, recursive: renaming any closes the tab). ClassVars `plot_file` (False: no
  `<kind>.plot`; `PlotSettingsStore` skips it, `ParamsBody` has no "Restaurar padrões", `PlotSession.persist` sends
  every edit to `save_stored`, which writes `GridStore.save_params`) and `grid_cell` (False: never a cell). Hook
  `axes_routes(figure, dataset)`: the session and local index of every axes; `PlotSession.routes` defaults to the
  plot itself. `PlotView` reads it for the cursor readout, pan/zoom (only the cells whose view changed get
  `apply_limits`, in memory: a cell's `.plot` is never written from a grid) and Reset, so it knows no grid.
  `PlotSession.copy()` (a cell takes an open plot as it is now) and `render(..., params=)`.
  `PlotWorkflow.show_session(session)` opens any session's tab (`show_loaded` builds one and calls it).
- **Reloading a cell** (`core/detection.py`): `ref_target(ref, sniff, memory)` → `PairTarget` (partner),
  `ManualTarget` (single-file module; a missing file is a `LoadError`) or `FolderTarget` (detect again, take the
  plottable result of the kind; a missing folder or kind is a `LoadError`).
- **UI.** `ui/grids_controller.py:GridsController.for_window` (store root set before each use, so the window needs
  no `set_root` call), `ui/grid_loader.py:GridLoader` (open tab → `session.copy()`; else `ref_target` + `load_plot`
  in the global pool, the `.plot` through the settings queue, `build_session`; then
  `core/plotting/grid_session.build_grid_session` → `ready` → `show_session`; footer spinner "Carregando grid…"),
  `ui/dialogs/grid_dialog.py` (non-modal, one at a time; "Gerar" saves too, then closes; replacing another saved grid
  asks), `grid_cells.py` (the table: combo of open plots plus the saved refs, "(pasta não encontrada)"), and
  `ui/widgets/grid_preview.py` (the thumbnail). Tests: `tests/plot_grid_helpers.py` (not `grid_helpers.py`, the file
  grid's) builds sessions and grids from the fixtures.

### Input editor and "Gerar SCF convergido" (spec 24)

- **`core/qe/input_edit.py:InputEditor`** (Qt-free, never raises) edits an input's *text* and keeps the rest byte for
  byte: lines split on `\n` with a CR flag each (`text()` of an unedited editor is the original), re-indexed with
  `scan_line` after every operation. `get` (last occurrence, no outer quotes) / `raw`, `set` (in place; a new key is a
  line above the `/`, or goes before a `/` that shares its line; a new namelist goes after the last one before it in
  `NAMELIST_ORDER`, in the case of the first namelist), `remove` (the line, or only `key = value,` on a shared line),
  `remove_namelist` (the first; returns whether it removed), `keys`, `card` (`input_lint.Card`), `replace_card`
  (header option swapped inside its brackets; blank lines after the body stay; a missing card goes at the end).
  Spec 30 added `card_rows` (the rows as written, end-of-line comments and flags kept; `Card.lines` drops them),
  `replace_card_rows` (the body only, the header line untouched; comments between the old rows are lost), `remove_card`
  and `rename_key` (the key's text in place, the case and spacing it was written with: `Starting_Magnetization (3)` →
  `Starting_Magnetization (1)`). Repeated namelists: the first one, as pw.x. A failing operation restores the text and adds to `issues`. The lexer's
  `Entry` has `value_start` / `value_end` (`compare=False`) for it. Spec 25 builds on it.
- **`core/unique_names.py`**: `next_free(path, first=1)` (`_1`, `_2`…; folders get the number at the end) and
  `write_new(path, text)` (`O_EXCL` in a loop, newline as in `text`, a failed write removes its file). The figure export
  keeps `next_free_stem` (`_2` first).
- **Geometry convergence**: `PwOutput.geometry_converged` from the tail: True only with `bfgs converged`; False with
  `bfgs failed`, `The maximum number of steps has been reached` or a bare `End of BFGS Geometry Optimization` (pw.x
  prints it when `nstep` runs out too); None without a marker (a huge output's 1 MB tail missed it).
- **`core/qe/final_structure.py`**: `read_final_structure(path)` streams to the first `Begin final coordinates` …
  `End final coordinates` block: positions lines as printed (`if_pos` kept) and, for a vc-relax, `FinalCell(unit, alat
  text, rows)`.
- **`core/qe/scf_from_relax.py`**: `can_generate_scf(sniff)` (pw.x relax / vc-relax, `geometry_converged is True`,
  `JOB DONE`); `pair_input(output, results)` (`X.in` that `looks_like_input`, else the `relax_in` of the result whose
  `relax_out` is this output); `scf_availability(...)` → None (no item) / "" (enabled) / the disabled tooltip, from
  caches only; `scf_from_relax(final, in_text)` (`calculation='scf'`, no `restart_mode`/`nstep`/`&IONS`/`&CELL`, every
  occurrence; `nat` must match; vc-relax: final `CELL_PARAMETERS`, `ibrav = 0`, no `celldm`/`A…cosBC`, except an
  `alat` cell, which keeps `celldm(1)` = the printed alat); `generate_scf_file` (worker) writes
  `scf_convergido_<prefix>.in` (`pwscf` without a prefix) through `write_new`. Errors are `ScfError` (Portuguese).
  `ScfResult.warnings` (→ the toast's "Detalhes") always open with the shared `prefix`/`outdir` (running the SCF
  overwrites `<outdir>/<prefix>.save`; `./` without outdir) and a vc-relax adds `VC_RELAX_CELL` (spec 27-6 R3).
- **UI**: `ItemActions.scf_state` → `menu(scf=)` puts the item under "Resumo" (disabled with the reason as tooltip,
  `setToolTipsVisible`); `scf_from_relax_requested(Path)` → `ui/derive_controller.py:DeriveController.for_window`
  (`TaskGroup` by output, spinner "Gerando SCF convergido…" in `plot_workflow.busy`, toast `success` + refresh of the
  folder, or `QMessageBox.warning`; signals `generated(Path)` / `failed(str)` for tests). Tests:
  `test_input_edit.py`, the editor properties in `test_properties.py`, `test_unique_names.py`,
  `test_scf_from_relax.py`, `test_scf_from_relax_ui.py`.

### "Criar cálculo" backend (spec 25, spec 28)

`core/calc_create/` (Qt-free; the window is spec 26) turns the user's SCF input into a new folder with the inputs and the
SGE `.qsub` of a calculation. `jinja2` is a runtime dependency imported inside functions only
(`test_perf_detection.py` checks neither it nor `ase` loads with `main_window` nor with the package's modules).

- **Structure without ASE.** ASE's `read_espresso_in` refuses `ibrav != 0`, so `core/qe/lattice.py` ports QE 7.1's
  `latgen` (every ibrav, QE's own vectors and its 13-digit `sqrt(2)`/`sqrt(3)`) and `abc2celldm`; `crystal_from_editor`
  gives `Crystal(cell Å, labels, frac)` or raises `StructureError` (`crystal_sg` is not supported).
- **`scf_info.py`**: `scf_info(text, path)` (pure) / `read_scf(path)` (worker; adds `scf_bands`, the Kohn-Sham states
  of `X.out` next to `X.in`) → `ScfInfo` (prefix [`pwscf`], outdir, pseudo_dir, nspin, occupations, nbnd, `kmesh`,
  `crystal` or `structure_problem`; `value(namelist, key)` reads the text as written). `calculation` other than scf →
  `ScfInputError`.
- **Types** (`types/`, `REGISTRY`, `by_id`): `CalcType` ClassVars `id` (never renamed: QSettings and tests use them),
  `label`, `folder_prefix` (`SCF`, `Relax`, `VC-Relax`, `Bands`, `PDOS`, `Charge`), `script_stem` (`scf`, `relax`,
  `vc-relax`, `bands`, `pdos`, `charge` → `script_name` `<stem>.qsub`), `script_template`, `input_templates`, `uses_name`
  (spec 29: a standard file name takes the folder's name). `input_files(scf, name="")` lists the
  inputs as `types/files.py:InputFile(key, name, label)`: a stable key (`scf`, `relax`/`vc-relax`, `bands`, `bands_pp`
  or `bands_pp_up`/`_dw`, `nscf`, `projwfc`, `pp_charge`) and the standard name (spec 28 R1.3: `scf_<prefix>.in`,
  `relax_<prefix>.in`, `vc-relax_<prefix>.in`, `nscf_<prefix>.in`, `<prefix>` = `unit_stem(scf.prefix)`; plain
  `bands.in`, `bands_pp.in`, `projwfc.in`; `pp_<name>_charge.in`, or `pp_charge.in` without a name, for Carga).
  `fields(scf, jobs, name="")` = the script's three (`types/script.py`, key `script`:
  `job_name` sanitized to 15 chars, `np` = `jobs.cores`, `nk` = `jobs.nk`) + a "Nome do arquivo" field per input
  (`name:<key>`, first in its tab) + `input_fields(scf)`. `FormField.group` and `PlannedFile.key` are that key (names
  can be edited), and the script gets the names through `script_values(work)` (`pw_runs`, `bands_x`, `projwfc`: `(in,
  out)` pairs from `work.run(key)`; no `.j2` under `qsub/` names an input, `test_no_script_template_names_an_input`).
  `plan(scf, values, jobs, mode="padrao", name="")` (`name`: the folder's name typed in step 1, read only by a
  `uses_name` type) never raises nor reads a file: values of fields `visible_fields` hides in
  the mode are dropped (their default counts; the window keeps them), `resolve` (empty → default, invalid /
  required-without-value → errors), `files.check_names` (`.in`, `[A-Za-z0-9._-]`, unique; a bad name is still
  previewed), then the script and `inputs(work)` (`work.name(key)`, `work.planned`, `work.pw_file`,
  `work.problem(field_id, text)`: an error the window marks on that field).
  `CalcPlan(files, notes, errors, problems)`: files in tab order (script first), `notes` warn, `errors` block "Criar",
  `problems` (field id → text) are what the window marks. A new type = a module + its templates + a registry entry.
- **Modes** (spec 28 R3): `Mode` = `padrao` | `avancado` (`MODES`, `DEFAULT_MODE`). `FormField.standard` shows a field
  in `padrao`; `is_visible` = `standard or avancado or (required and default is None)` (`nbnd` without an SCF value
  or output shows in both). `padrao` shows: nothing for SCF / Relax / VC-Relax, the path for Bandas, `e_min` / `e_max`
  for PDOS (its NSCF mesh only when the SCF has no automatic one). Defaults: projwfc `degauss` 0.000735 Ry, `filband`
  `./band` (`channel_filband` → `./band_up` / `./band_dw`, the names spec 13 pairs by the bands.x input).
- **Carga** (`types/charge.py`, spec 29): `charge.qsub`, the SCF copy and `qe/charge/pp_charge.in.j2` (the idea's
  input, no indent; `filepp(1)` = `filplot`). `padrao` shows no field; `avancado` adds `plot_num`, `iflag`, `output_format`
  (`choice` fields whose text is `"5 — XSF …"`, `choice` / `code_of`) and `fileout` (`cdd_xsf/<prefix>_charge.xsf`):
  `fileout` must be relative and inside the folder (`unit.absolute` / `climbs`), and `output_format` must fit `iflag`
  where pp.x checks it (`FORMATS_OF_IFLAG`: 2 → 2, 3, 7; 3 → 3, 5, 6; the 1D and polar plots ignore it). The script
  makes `fileout`'s folder (`mkdir -p cdd_xsf`: pp.x does not; `fileout_dir`, none for a bare name) before the pw.x of
  the folder's own SCF and runs pp.x without MPI. The inputs of pp.x lint clean: `pw_input.PROGRAM_NAMELISTS["pp"]`,
  decided by `&INPUTPP` only (`DECIDING_NAMELISTS`: a bare `&PLOT` is a bands.x `filband` header), and
  `input_lint._ALL_NAMELISTS` leaves it out (else ph.x's `&INPUTPH` would be "corrected" to `&INPUTPP`). Nothing detects
  pp.x: the folder shows the SCF badge.
- **Diferença de carga** (`types/charge_diff.py`, spec 30): `charge_diff.qsub` and eight inputs (keys `scf`, `scf_clean`,
  `scf_isolated`, `pp_base`, `pp_clean`, `pp_isolated`, `pp_diff`; names from `unit_stem(prefix)`, the pp.x ones by the SCF's
  prefix, never the folder's: `uses_name` stays False). The user's SCF becomes three: the base copy (the unit's), `clean`
  (without the atoms picked) and `isolated` (only those), `prefix = '<p>_clean'` / `'<p>_isolated'`, the same cell, cutoffs
  and mesh (nothing of that is a field: pp.x subtracts densities on one FFT grid). `pp_charge_diff.in`
  (`qe/charge_diff/pp_charge_diff.in.j2`) is Δρ = ρ(base) − ρ(clean) − ρ(isolated) (weights 1, −1, −1). The script runs the
  three SCFs alike, with `${MPICOMMAND} ${PWCOMMAND}` and the same `-nk` (they share the `K_POINTS automatic`; the
  cluster's `cargas.qsub` runs the isolated one serial, which Lain does not), then the four pp.x without MPI;
  `mkdir -p <xsf_dir>` first. `padrao` asks for the atoms alone; `avancado`
  adds `iflag`, `output_format` (`charge.iflag_field` / `output_format_field` / `format_problem`, shared with Carga) and
  `xsf_dir` ("Pasta dos .xsf", `cdd_xsf`), the same for the four pp.x (`<dir>/<x>_charge.xsf`, `<dir>/<p>_charge_diff.xsf`).
  **The plan always has all eight files**: an invalid selection puts the error on the `atoms` field (`work.problem`) and
  both fragments are the base text, so the tabs never come and go.
  - `fragments.py` (Qt-free): `atom_rows(text)` (`AtomRows(unit, rows, error)`: the atoms of `ATOMIC_POSITIONS` as written,
    first `nat`; no `ScfInfo.crystal` needed; cached) and `split_input(text, selected) -> Fragments(clean, isolated,
    notes, errors)`. Each fragment keeps the *text* of its position rows (`if_pos`, comments), updates `nat`, drops the
    species no atom uses (`ATOMIC_SPECIES`, `ntyp`), filters `ATOMIC_FORCES` / `ATOMIC_VELOCITIES` by atom and removes
    `nbnd` (note). Errors: none selected, all selected, `CONSTRAINTS`, an unreadable structure (`crystal_sg` included).
    Notes (`(fragment, text)`, the type prefixes the file's name): `nbnd`, `nspin = 2` with no `starting_magnetization`
    left, `tot_charge` / `tot_magnetization`, dropped `V` lines.
  - `species_keys.py`: `remap_species_keys` follows the species through the old → new map (`SPECIES_KEYS`, the species
    being the *last* index): the keys of a dropped species are removed first, then `rename_key` lowers the others
    (the map only lowers an index, so no rename lands on a key not yet moved); `Hubbard_V(i,j,k)` is only noted.
    `remap_hubbard` (QE ≥ 7.1 card): lines of a dropped species label (`Fe-3d` → `Fe`) go, a `V` line citing a removed
    atom goes (note), the others renumber their atoms; an index past `nat` is an image of the 3×3×3 supercell and becomes
    `new atom + nat_new · k` for `index = atom + nat · k` (**unverified assumption**: `INPUT_PW` only says "index of the atom
    I / J"; the supercell numbering is `Hubbard_input.pdf`'s, not read, and no run was made; the plan notes it); an empty
    card is removed.
  - Tests: `tests/fragment_helpers.py` (`SMALL`: Fe / O / H with spin, `HUBBARD`, `if_pos`, comments; `slab_scf()`),
    `test_fragments.py`, `test_calc_charge_diff.py`, `test_input_edit.py` / `test_properties.py` (the new editor operations
    and `split_input` on random selections and texts), a row in `test_calc_roundtrip.py`.
- **Self-contained folder** (`unit.py`, spec 28 R2): `Work.editor()` is the SCF's text after `apply_unit`
  (`outdir = './tmp/'` always, `jobs.pseudo_dir` when set; `edits.put_text` compares with case), so every pw.x input,
  the SCF copy included, gets it (the copy differs from the SCF only there); bands.x and projwfc.x templates get
  `UNIT_OUTDIR`. `unit_notes(scf, jobs)`: without `jobs.pseudo_dir`, `PSEUDO_DIR_NOTE` plus the missing / relative
  pseudo_dir notes; a `..` pseudo_dir or an absolute / `..` `wfcdir` is "O SCF usa um caminho fora da pasta: …".
  The pw.x inputs are edits of the SCF's text (`edits.py`: `put_*` change a value only when it differs, so an
  unchanged field keeps its line; `ensure_smearing`). NP not a multiple of nk is a note (pw.x stops on it in
  `mp_start_pools`).
- **Templates** (`resources/templates/`, `render.py`: `FunctionLoader` over `importlib.resources`, `StrictUndefined`,
  `trim_blocks`/`lstrip_blocks`, filters `fstr`/`fnum`): `qsub/_base.qsub.j2` is the reference header once
  (`Documentation/Referencia_de_scripts_QSUB`), each `qsub/<type>.qsub.j2` (`bands.qsub.j2` for Bandas) extends it
  with its commands; `qe/bandas/bands_pp.in.j2`, `qe/pdos/projwfc.in.j2`. The cluster side comes from `config.yaml`
  `jobs:` (`JobsConfig`: `qe_bin`, `mpi_command`, `parallel_env`, `omp_threads`, `env_lines`, `cores`, `nk`,
  `pseudo_dir`), never from the form.
- **K-points** (`kpath.py`): `KMesh` (`K_POINTS automatic`), `KPoint(label, frac, npts)`, `KPath(points, breaks,
  warnings)`, `to_card` (`crystal_b`; weight `npts`, 1 at a break and at the end, `! Gamma` labels). The band path is
  typed by the user (spec 27-2: nothing suggests it). Two checks use `Crystal.cell` (Å) and never raise:
  `segment_progress(path, cell)` expands the card as pw.x does (`_expand`), runs `bands_x.path_coordinates` and gives
  each segment's real length and x advance (Å⁻¹, with 2π; a break or a weight-1 point is not a segment);
  `collapsed_segments` keeps those under 50 % (`CollapsedSegment(a, b, lost)`, `a` the vertex the segment starts at,
  `collapse_note` its Portuguese text); `distribute(path, cell, density, min_pts=2)` sets each `npts` to
  `round(length · density)` (≤ `MAX_NPTS` = 1000); the last point and the ones before a break keep theirs.
- **`writer.py`**: `folder_name` (`<folder_prefix>_<name>`, or the prefix alone: the name is optional),
  `validate_target`, `preview_name` (`unique_names.next_free_dir`), `files_to_write` (+
  `descricao.md` when the notes have text), `create_folder` (worker): `unique_names.make_new_dir` (`mkdir` loop,
  `_N` always at the end), every file `open(…, "x")`, a failure removes only the files it wrote and `rmdir`s its
  folder (`CreateError`). Tests: `tests/calc_helpers.py` and `test_lattice.py`, `test_kpath.py`, `test_calc_*.py`
  (`test_calc_types.py` plans in `avancado`; `test_calc_standard.py` holds spec 28's names, modes and unit; `test_calc_charge.py` spec 29's Carga type;
  `test_calc_roundtrip.py` fills generated folders with fixture outputs under the new names and detects them).

### "Criar cálculo" window (spec 26, spec 28 R5)

`ui/calc_create_controller.py:CalcCreateController.for_window` connects `ActivityBar.create_requested` (button
`new_calc`, "Criar") and the `calc.create` action (Ferramentas); both are disabled while `local_root` is not a
folder (`FirstRunController.refreshed` → `update_available`). One non-modal window at a time; "Criar" runs
`writer.create_folder` in `run_task` (footer spinner "Criando …", window `set_busy`), then closes it, refreshes
the parent, `select_path`s the folder and shows `preview.created_notice` as a `success` toast (signals `created` /
`failed`); `CreateError` → `QMessageBox.critical`, window stays open. The window never writes.

- `ui/dialogs/calc_create/`: `dialog.CalcCreateDialog` (steps in a `QStackedWidget`; `continue_` rebuilds step 2
  only when the type or the `ScfInfo` object changed (or, for a `uses_name` type, the folder's name: `_wanted` / `_stale`); Esc / X / "Cancelar" ask `ask_discard` only when
  `TabsPage.dirty`; emits `create_requested(CreateRequest)`; `settings=` is where the mode lives, QSettings
  `calc_create/mode`, `padrao` the first time: the controller passes `window.settings`), `mode_switch.ModeSwitch`
  (two exclusive `toggle` `QToolButton`s right of the step title, step 2 only; `set_mode` never emits),
  `setup_page.SetupPage` (type combo, SCF via `looks_like_input` then `read_scf` in a `TaskGroup` → `scf_ready`,
  `choose_scf` / `choose_folder` module functions, "Nome da pasta" optional, `problems()` gate "Continuar"),
  `tabs_page.TabsPage` (a tab per `CalcPlan.files` entry, keyed by `PlannedFile.key` (`previews[key]`, labels
  refreshed by every plan: a renamed file renames its tab): `FieldForm` | `FilePreview` in a `QSplitter`, then
  "Arquivos" and "Descrição"; a `FormField` whose `group` is no file's key (spec 30: "Átomos") has a form-only tab named
  by the group *before* the file tabs, in declaration order (empty group: the first file's tab); edits replan after
  `debounce_ms` (tests: 0 or `flush()`); `set_mode` shows the rows of
  `visible_fields` and hides the form side of a tab with none (`form_shown(key)`; a group tab is hidden whole), never rebuilding;
  `blocking()` = first plan error, the "Criar" tooltip), `form.FieldForm` (widget per `FormField.kind`, `rows` per
  field for `set_visible(ids)` / `shown(id)`, `mark(plan.problems)` sets the `invalid` property; kind `atoms`: an
  `AtomTable` fed by `FormField.data` (`AtomRows`) under the label and `FormField.hint`, value = the marked atom numbers),
  `kmesh.KMeshEditor`, `preview.FilePreview` (read-only `CodeView`, `InputHighlighter` / `ShellHighlighter`, changed
  lines in `diff_change_bg`) and `FilesView`.
- `ui/widgets/atom_table.py:AtomTable(rows, selected, unit, count_format)` (spec 30, extracted from the PDOS atom window):
  checkbox, #, element and three coordinates as text (`AtomRow`), "Marcar todos" / "Desmarcar todos" / "Inverter" /
  "Só espécie ▸" and the count; `changed` fires once per click or button, `value()` / `checked()` the marked numbers.
  `ui/dialogs/atoms.py:AtomsDialog` builds one and keeps its old attributes (`checks`, `table`, `mark_all`, …) pointing at it.
- `ui/widgets/kpath_editor.py:KPathEditor(theme, cell)`: the `crystal_b` table, empty on open (`FieldForm` passes
  `scf.crystal.cell`, None without a readable structure); `set_path` shows a path without `changed(True)`. Cells take
  finite numbers only (no `nan`/`inf`/`1_0`), points 1 to `MAX_NPTS`. A point added after a break inherits it, removing
  a break point hands it to the previous one, the last point holds none. `refresh_marks` paints the row each collapsed
  segment starts at (`warning` color, the note as tooltip) after every edit and theme change; "Distribuir pelo
  comprimento" (density field, 25 points/Å⁻¹) rewrites only the points column and is disabled without a `cell`. The
  bands plan carries the same notes (`types/bandas.py`), never as errors.
- Tests: `test_calc_create_preview.py` (core), `test_kpath_editor.py`, `test_calc_create_dialog.py` (window alone,
  `make_dialog(mode="avancado", settings=None)`; `calc_dialog_helpers.py`: `pick_scf`, `fill_setup`, `to_files`),
  `test_calc_create_ui.py` (main window),
  `test_shell_highlighter.py`. Patch `dialog.ask_discard` in every test that leaves a dirty window: a real
  question blocks, even at teardown; and do not `qtbot.addWidget` the dialog (delete-on-close).

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

### Projetos (spec 31)

A **project** is a first-level folder of `paths.local_root` (the root folder: the texts say "pasta raiz"); the simulation
units are plain folders inside it at any depth, with no list or mark of their own. The dropdown "Projeto" above the
explorer tree narrows the window to one project or to "Todos os projetos" (= the root, how it was before). The **data
stays keyed by `local_root`** (`FolderMemory`, `NavigationStore`, `GridStore`, `CompoundStore`).

- **`core/projects.py`** (Qt-free): `list_projects(root, hidden_dirs, cancelled)` (first level only, the rules of
  `core/folder_index`: no dotted names, `ui.hidden_dirs`, symlinks, plus `plots`, the grids' exports; sorted without case or
  accents), `project_of(path, root)` (first component below the root; `None` for the root itself and for a path outside it:
  pure, nothing resolved), `validate_project_name(name, existing, hidden_dirs)` (charset `[A-Za-z0-9._-]+`, no leading
  `.`, not `plots` nor a hidden pattern, no duplicate in any case) and `create_project(root, name)` (`mkdir(exist_ok=False)`,
  never `_N`: an existing folder is `ProjectError`; it validates again, so `../x` cannot leave the root).
- **`ui/project_controller.py:ProjectController`** (`for_window`, `window.project`): the selected name (`None` = Todos),
  QSettings `explorer/project`, the list (`TaskGroup`, `reload()`: start, F5 through `MainWindow.refresh`, a config reload,
  a rename, a new project; the dropdown keeps the last list meanwhile) and "Criar projeto…" (`ask_new_project`, then
  `create_project` in `run_task`, busy `project:create`, toast / `QMessageBox.warning`; signals `created` / `failed` /
  `listed` for tests). **`switch(name)`** is the one place that fans the scope out, through small calls that know no
  "projeto": `ExplorerPanel.set_scope` (= `set_root`: `current_folder()` falls back to the project, which is the default
  place of "Criar cálculo"), `FilePanel.set_view_root` (the `..` row and `go_up` stop there; the grid's folder is still
  driven by `on_folder_selected`), `NavigationController.set_view_root` (breadcrumb root; favorites / recents filtered to
  the view, labels relative to it; the history is kept, so never `set_root`, which clears it),
  `SyncCoordinator.set_project`, the window title (`[Projeto: ilita]` / `[Raiz: <caminho>]`), then it selects the project's
  folder like a click (`on_folder_selected`, history). `PaletteController(view_root=)` filters the folder, favorite and
  recent rows (the index stays one, of the root). At start the stored name is applied at once, with no disk read; the first
  list checks it: a project that is gone → "Todos" and the footer says "Projeto <nome> não encontrado".
- **Auto-switch** (R3.6): every navigation ends in `ExplorerPanel.select_path`, which emits `outside_scope(path)` for a path
  above the tree's root (a pure `is_relative_to`, no `FS_ALLOWED` cost) and returns. `ProjectController.on_outside_scope`
  switches to `project_of(path)` (or to "Todos" for the root) and selects the path again; a path outside `local_root` is
  ignored. History back / forward, "Revelar no explorador", a created folder, a renamed project and `explorer/last_folder`
  in another project all follow it with no change in their callers. `config_applied(old_root)` (in `_apply_loaded`, after
  `explorer` / `files.apply_config` reset the views to the root) keeps the project of the same root, another root → "Todos".
- **Widgets:** `ui/widgets/project_combo.py:ProjectCombo` (`explorer.projects`: label "Projeto" + `QComboBox#projectCombo`,
  `accessibleName` "Projeto"; entries "Todos os projetos", the projects, "Criar projeto…" with a NUL-prefixed key that no
  folder name can equal; `set_projects` / `set_current` never emit, `project_chosen` / `create_requested` come from the user,
  `restore()` after a cancelled dialog; disabled in `missing_root` through `first_run.refreshed` → `update_available`) and
  `ui/dialogs/new_project.py` (modal like `rename.py`, live message under the field, "Criar" only for a clean name).
  The action `project.create` ("Arquivo ▸ Criar projeto…") is in `ACTIONS`, so the palette lists it.
- **Sync and push** (`core/sync/request.py`): the root says "tudo" / "Sincronizar tudo"; the selected project's scope has the
  explicit hint `sync_scope(..., project=name)` ("projeto ilita" / "Sincronizar projeto ilita"; a plain pull of a first-level
  folder keeps "ilita (e subpastas)", so the words are never derived from depth). `SyncScope.at_project` (a first-level
  folder) and `prepare_push` (`resolved.parent == root`, after the "Pasta não encontrada" check) refuse a push of a project
  (`PUSH_PROJECT`; the root keeps `PUSH_ROOT`): a push is of one calculation folder, so a pre-spec-31 layout with
  calculations directly in the root cannot be pushed from there. `remote_dir_for` is unchanged (`remote_root/<project>/…`).
  `SyncCoordinator.set_project` rebuilds the `sync.project` scope once (never in `show_scope`: a test counts its `resolve`s).
- **Criar cálculo:** `core/calc_create/preview.py:location_warnings(parent, root)` = `OUTSIDE_PROJECT` (outside the root) or
  `AT_ROOT` ("A pasta será criada fora de um projeto…": the place is the root itself, so the folder becomes a new project).
- **Tests:** `conftest.py` has the `raiz` fixture (projects `ilita` / `outro`, `plots`, a hidden folder, a loose file),
  `tests/project_helpers.py` the dropdown as the user drives it (`pick`, `current_text`, `config_of`), `test_projects.py`
  (core), `test_project_combo.py`, `test_new_project_dialog.py`, `test_project_ui.py` (a window on `raiz`: the model reads
  a folder in its own thread, so wait with `qtbot.waitUntil(lambda: tree_names(window) == …)` after a switch) and
  `test_project_integration.py` (sync, push and "Criar cálculo" with a project selected).

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

### Theme modes, font scale and keyboard focus (spec 19)

- **Modes.** `ThemeManager.mode` is the user's pick (`dark` | `light` | `system`, `MODES`) and `name` the
  concrete theme applied (`THEMES`); `theme_changed` always carries the concrete name, `mode_changed` the
  mode. `system` reads `QStyleHints.colorScheme` (`Unknown` → dark) and follows `colorSchemeChanged`.
  `toggle()` cycles dark → light → system. QSettings `ui/theme` stores the **mode**, never `name`. Tests
  fake the scheme by patching `QStyleHints.colorScheme` and emitting `colorSchemeChanged` (offscreen
  always says `Unknown`).
- **Font scale** (`ui.font_scale`, 0.8–1.6). `core/fontscale.py` (Qt-free) scales every `font-size: Npx` of
  the QSS (`scale_qss`) and gives the size tokens (`${row_h}`, `${bar_h}`, `${status_h}`,
  `${activity_w}`) of the heights that hold text; `ui/theme/scale.py` keeps the scale in force for code
  without a `ThemeManager` (`scaled`, `scaled_font`). `mono_font` / `ui_font` take the size **at scale 1**.
  Row and card heights come from there or from `QFontMetrics` (`ui/widgets/file_card.py:card_size`), never
  from a bare constant; paddings, icons and dialog widths do not scale. A widget that caches a size
  connects `theme.scale_changed`. `MainWindow._apply_loaded` re-reads the scale ("Recarregar config.yaml").
- **Contrast.** `core/colors.py` has `contrast_ratio` and `composite` (rgba over its background);
  `tests/test_theme_contrast.py` holds the WCAG AA table of the tokens in both themes. `text_dim` is only
  for disabled states, placeholder and LEDs (the test lists the files that may read it); informative
  text (grid and tree metadata, counts, separators) uses `text_meta`. A new color token must pass there.
- **Focus.** `focus_ring` is the color of the keyboard focus. Controls recolor the border they already
  reserve (`controls/focus.qss`: a new focusable control reserves a transparent 1 px border and is added
  there); the painted delegates draw a 2 px ring when `State_HasFocus`. `ui/focus_controller.py:
  FocusController` rebuilds the tab order (activity bar → top bar → tree → grid → workspace →
  adjustments → footer) from Qt's chain, grouped by region, in `MainWindow.focusNextPrevChild` before each
  Tab (widgets created later land at the end of Qt's chain), and answers Ctrl+1..4 (`focus.*` actions).
  An icon-only `IconButton` takes its tooltip as `accessibleName`; a parameter widget the label of its field.
  The mouse wheel only scrolls the settings panel (spec 32 R2): its spin boxes and combos are
  `ui/widgets/no_wheel.py:NoWheelSpinBox / NoWheelDoubleSpinBox / NoWheelComboBox` (`wheelEvent` ignores the event,
  so the scroll area gets it; `StrongFocus`: a wheel turn gives no focus). Any field of a scrolled form takes them.

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
- Cancellation is cooperative (spec 27-4): `core/cancel.py` (Qt-free) has a thread-local the task runner sets
  (`_Runnable.run` binds the `TaskHandle` and clears it in `finally`), `check()` (raises `Cancelled` when the task of
  this thread was cancelled; does nothing outside a task, so parsers stay plain functions), `is_cancelled()` and
  `checked(lines)` (a check per batch of `CHECK_EVERY_LINES`, never per line). A `Cancelled` ending a task is neither a
  result nor an error: no callback, no log. Called by `summarize_lines`, `parse_relax`, `load_pdos` (between files),
  `read_gnu` / `read_filband` (between phases), `textfile.read_slice` (between chunks) / `read_preview` and `LoadCache`;
  `TaskGroup.shutdown` therefore ends a running loader at its next check. Closing a plot tab cancels its pending load
  (`_on_tab_closing`); `SummaryView` and `TextViewer` cancel theirs when they die. A new long loop in `core/` calls `check()`.
- Private pools (a thread limit or an order) have **no Qt parent**: a child pool is destroyed
  inside its parent's C++ destructor, maybe with the GIL held, and waits for tasks that need the GIL.
- `ui/services.py:DetectionService` caches detection per folder and runs misses in its 2-thread pool
  (`TaskGroup` by folder; `fresh` requests jump the queue and supersede). `detect_now()` is
  synchronous: scripts and tests only. F5 (`invalidate()` without a folder) keeps the sniffs of files
  that still exist (`SniffCache.prune`: each entry is checked against its file's (mtime, size) when
  used anyway); `ui.paranoid_refresh: true` drops them all.
  `invalidate(folder)` clears what the detection of other folders may read of it (`core/calculations/base.py:reads_from`,
  the one rule `infer_from_neighbours` shares through `neighbour_scf_folders`): the folders inside it, its sibling folders when it is
  an SCF folder (`*scf*`), and its parent when it holds PDOS files (`feeds_parent`, one `scandir`: `FolderListing.scan` reads
  them). A detection that raises is not an empty folder (spec 27-8 R5): `_on_error` logs, caches `[]` marked in `_failed`, emits
  `detected` (the busy ends) and then `message` ("Falha ao detectar …", once per folder until F5 clears the mark); `SniffCache.sniff`
  turns any parser exception into an `UNKNOWN` it caches (logged once), so one odd file does not zero its folder.
- `PlotWorkflow` loads datasets in the global pool, then renders on the GUI thread. Exports run in a
  worker with their own `Figure` + `FigureCanvasAgg`. matplotlib's global state is serialized by
  `MPL_LOCK` (`threading.RLock`): `PlotSession.render`, `render_figure` and `export_figure` (so `export_files`) hold it;
  on screen `PlotView.render` and `ScaledFigureCanvas.draw` only *try* it and retry after 50 ms, so
  the GUI never waits for an export.
- Connect long-lived signals (e.g. `ThemeManager.theme_changed`) to bound methods, not lambdas,
  so they disconnect when the widget is deleted. Dialogs use delete-on-close, **except a modal run with `exec()`**
  whose answer is read afterwards (`ask_atoms`, `ask_rename`…): `exec` deletes a `WA_DeleteOnClose` dialog before it
  returns, and reading the answer then raises "wrapped C/C++ object … has been deleted" (spec 32 R1). Read the answer,
  then `deleteLater()`.
- `app.main()` waits on the global pool before exit (`finish`: `POOL_WAIT_MS`, then `os._exit`; see `ui/shutdown.py`).
- Data files are written whole by `core/appdirs.py:atomic_write_text` (unique temp `.<name>.<pid>.<token>.tmp`
  made with `O_EXCL` and mode `0o666` so the umask applies, `fsync`, `os.replace`, folder `fsync`; any error
  removes the temp). Two instances would still lose each other's stores (last writer wins, no merge), so
  `ui/app.py:claim_instance` takes a `QLockFile` (`appdirs.lock_path()`, `lain.lock` in the data dir,
  `setStaleLockTime(0)`: only a dead owner makes it stale, not its age) and a second instance asks "Abrir mesmo
  assim?" (yes goes on without a lock, no exits 0); an unwritable data dir never asks.

### Sync (PRD §5, pull; push of new files only, spec 27)

`core/sync/rsync.py` builds commands/env and parses output (children run with `LC_ALL=C.UTF-8`,
`TZ=UTC`, `--no-h` because rsync output is locale-dependent). `planner.py` is pure: dry-run
records + local stats → per-file NEW / UPDATE / LOCAL_NEWER; files only present locally (like
`plots/`) never block a pull; `LARGE_FILE_BYTES` (100 MB) gives `PlanItem.is_large` /
`SyncPlan.large`. `request.py:prepare_sync` (and `prepare_push`, `push_availability`, `sync_scope`: `resolved_root=` is the root the
caller already resolved; `SyncCoordinator` keeps it and the whole-project scope per config, so `show_scope` resolves one path) decides whether a pull can start (configured? folder
inside the project? password needed?) and `sync_scope` says what it covers (`SyncScope`: tooltip,
menu text, dialog header, window title, confirm button; `direction`: `Direction.PULL` / `PUSH`).
`preview.py` is what the plan preview shows: `describe_plan(plan)` → `Preview` (summary, large-file
warning, date column, `PreviewSection`s of folders and rows) for either plan, which `PreviewPage`
only lays out (`plan_groups`, `plan_summary`, `large_summary` stay public); `report.py` the
`SyncReport` (re-exported by the controller; `details` is the full report; `changes_local` says
whether the window refreshes). `_process.py:RsyncRun` is the `QProcess` state machine both
directions share (`rsync --version` → dry run → plan, whose local stats run in a `run_task` worker
→ `plan_ready(plan)` / `confirm_plan(bool)` → transfer → `finished(report)`), with hooks a direction
fills (`_reset`, `_dry_run_command`, `_build_plan`, `_use_plan`, `_accepted`, `_discard_partial`,
`_report`). `controller.py:SyncController` is the pull: `confirm_plan` skipped when
`sync.confirm_plan: false`, then `conflict_needed` / `resolve()`, rsync temps removed after a
failed transfer. It never opens dialogs, so UI and tests supply the answers; `transfer_started(n)`
comes before the transfer's stage and progress. `ui/dialogs/sync_dialog.py:SyncDialog` is one
window for the whole run: a `QStackedWidget` of `sync_pages.py`'s search, preview (tree by action →
folder, large files flagged) and transfer pages, switched by those signals; Esc / X on the preview
declines it; the coordinator connects a pull's `conflict_needed` to `await_decision`. Every stage
runs through `_step()`, so an exception ends the sync as FAILED instead of hanging it. `monitor.py`
probes in daemon threads, not a `QThreadPool` (DNS ignores the connect timeout and a pool's
destructor waits without limit). Passwords reach ssh only via `SSH_ASKPASS` (`askpass.py`,
installed as `qe-studio-askpass`) through the child env, never argv or logs; unknown host keys are
always refused, and Lain enforces it itself: `ssh_command` passes `-o StrictHostKeyChecking=yes`, which
wins over any `StrictHostKeyChecking no` / `accept-new` in the user's `~/.ssh/config` (spec 27-3 R1;
the test `ssh_config` may be permissive, `test_sync_ssh.py` checks it makes no difference).
**The recheck (spec 27-3 R3):** after the preview and the conflict prompts the pull calls
`planner.recheck_local` (worker; `PlanItem` keeps `local_mtime` and `local_size`) on what it is about to
write: a file edited, created or removed locally meanwhile is left out of `--files-from` and listed in
`SyncReport.changed_locally` ("Detalhes"; `headline` is what the toast and the footer say). The window
between that check and rsync's write stays (no `-u`: the planner is not reopened).

**Push (spec 27)** only adds files the cluster does not have, for one calculation folder:
`request.prepare_push` refuses the project root (`PUSH_ROOT`) and a missing folder,
`push_availability` is the disabled menu item's reason. `push_dry_run_command` goes local → remote
with `-i` and no `--ignore-existing` (identical files are not listed; differing ones are) and excludes
`sync.exclude + sync.push_exclude` (`plots/`, `*.plot`). `push_plan.build_push_plan` (Qt-free):
`<f+++++++++` → `PushAction.NEW`, any other file code → `EXISTS` (listed, never sent; no conflicts).
`push.py:PushController` always emits `plan_ready` (ignores `confirm_plan`) and sends only the NEW
files with `push_transfer_command` (`--ignore-existing` against a race, `--omit-dir-times`, never
`--delete` / `-u` / `--inplace`; with a host, `--rsync-path="mkdir -p <shlex.quote(dir)> && rsync"`
makes a new folder and its parents: `--mkpath` needs rsync 3.2.3 on the cluster; the dry run has no
`--rsync-path`, so nothing is made before "Enviar"). Nothing local is touched; `PushReport`
(`existing`). UI: `SyncCoordinator.push` / `run_push` / `start_push` (action `sync.push`, renamed by
`show_scope`, disabled at the root), `bind_actions(actions)`, `bind_menu(item_actions)` (sets
`ItemActions.push_state`, connects `push_requested`): "Enviar ao cluster" under "Abrir com" of a
folder. A push ends with a toast (DONE `success`, UP_TO_DATE `info`), a FAILED box over the window,
and never emits `synced`. "Criar cálculo"'s toast reminds of it when sync is on
(`created_notice(..., sync=)`).

### Context menu (spec 5)

`ui/widgets/context_menu.py:ItemActions` builds the right-click menu for the tree and the grid
(both panels emit `item_menu_requested(paths: list[Path], pos)`, the tree a one-item list →
`MainWindow._show_item_menu` → `ItemActions.show`, which reads the cached sniff once, in
`file_actions_of`: "Plotar" for a
single-file module, "Resumo" for any QE output, both above the four spec-5 actions). "Abrir com" lists programs from `core/desktop_apps.py` (Qt-free `.desktop`/`mimeapps.list` reader, one
cached `catalog()` per session; `Terminal=true` programs stay in `apps` but are never listed nor the default) and starts them with `QProcess.startDetached(argv)`, never a
shell. A folder also gets "Adicionar/Remover dos favoritos" (`favorite_toggled`, answered by the
`NavigationController`). With several items selected in the grid (`multi_menu`) the menu is the
count title, "Abrir local de origem" (`ShowItems` with every URI), "Copiar" (one URI / path per line),
"Comparar" for exactly two `looks_like_input` files (path order; `compare_requested` →
`MainWindow.compare_inputs`) and the favorites item when all are folders; per-item actions are hidden.
Renaming goes through `MainWindow.rename_path` (a facade over `ui/rename_controller.py:RenameController`)
because it touches global state: refuse while something works in the folder (`blocked`), write the
pending `.plot` settings of what it moves (`flush_now(inside=)`), wait for running exports,
`core/file_ops.rename_item` (never replaces: `renameat2(RENAME_NOREPLACE)` on Linux, `link` + `unlink` for a
file or a checked `rename` where that is missing; a directory without it keeps a documented window),
`Workspace.close_tabs_under`, `FolderMemory.rename`, invalidate detection. Tests must patch `QMenu.exec` (the
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
