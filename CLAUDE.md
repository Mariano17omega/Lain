# CLAUDE.md

Guidance for Claude Code in this repository.

## Project

- **Lain: QE Studio**: a PyQt6 desktop app to browse, sync (rsync + ssh) and plot Quantum ESPRESSO runs (bands,
  PDOS, relax/vc-relax, SCF convergence), generate new calculations ("Criar cálculo") and view structures in 3D.
- Supported QE versions: **7.1 or newer**. No code or fixture handles older formats.
- Requirements: `specs/Archived/spec_0-PRD.md` (code cites "PRD §x.y"). New work is `specs/spec_N-*.md`, indexed in
  `specs/README.md` (written with the `spec-sdd` skill). Implemented specs move to `specs/Archived/`: they are the
  detailed record of each feature, and code comments cite them as "spec N".
- The UI follows `Documentation/design system (UX)/`. The rest of `Documentation/` holds the user's reference
  scripts and reports, not project code (ruff excludes it).

## Stack

- Python ≥ 3.11, managed with **uv**. Runtime: PyQt6, matplotlib, numpy, pydantic (config), PyYAML, Jinja2
  (calculation templates), ASE, spglib, scipy.
- Dev: pytest + pytest-qt + pytest-timeout, Hypothesis, paramiko (local SSH server for the sync tests), ruff
  (line length 100), pyright (basic mode over `src/`, no ignore list).
- External binaries: `rsync` and `ssh` (sync, and the sync tests).

## Commands

```bash
uv sync                                          # install deps + dev group
uv run lain [--config path/to/config.yaml] [--verbose]
uv run pytest                                    # full suite, headless
uv run pytest -m "not realdata and not perf"     # what CI runs (.github/workflows/ci.yml)
uv run pytest tests/test_detection.py::test_name # single test
uv run pytest -m perf -s                         # latency budgets (prints the numbers)
QE_STUDIO_REAL_DATA=/runs:/other uv run pytest -m realdata   # the user's own QE runs (off by default)
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run python scripts/screenshot.py --plot       # off-screen PNGs of both themes → screenshots/ (--language en)
uv run python scripts/i18n.py update|compile|check [--area N]   # the English catalog (locale/README.md)
uv run python scripts/fetch_assets.py            # refresh vendored fonts/icons
uv run python scripts/build_icons.py             # re-render app icon PNGs from ui/resources/app/lain.svg
uv run python scripts/install_desktop.py         # optional: .desktop + icons for the user (--prefix DIR)
```

CI = `ruff check`, `ruff format --check`, `pyright`, then the `not realdata and not perf` suite.

## Conventions

- **Language:** user-facing strings are written in **Portuguese inside `_()`** (or `N_()` for a Portuguese
  token that is also data, like `"conteúdo"`); English lives in `locale/en/LC_MESSAGES/lain.po` (workflow in
  `src/qe_studio/locale/README.md`). Code, comments, docstrings and commit messages are **English**.
- **Old internal names, on purpose** (existing configs keep working): package `qe_studio`, `QE_STUDIO_*` env vars,
  `~/.config/qe-studio`, `~/.cache/qe-studio`, QSettings keys, `qe-studio-askpass`. Product and CLI are `lain`.
  Never rename them.
- **Config:** lookup order `--config`, `$QE_STUDIO_CONFIG`, `./config.yaml`, `<checkout>/config.yaml` (the repository
  an editable install runs from; tests turn it off with `QE_STUDIO_NO_CHECKOUT_CONFIG`), `~/.config/qe-studio/config.yaml`.
  `config.yaml` is git-ignored (may hold credentials). There is no settings window (PRD §6): a new setting is a
  pydantic field in `core/config.py` plus both copies of `config.example.yaml` (root and
  `src/qe_studio/resources/`, kept identical by `tests/test_config.py`).
- **Where state lives:** UI state in QSettings (`<paths.data>/settings.ini` when the config sets `paths.data`, which
  also holds `core/appdirs.py:data_dir()`; fixed at startup by `set_data_dir`); per-root data (folder mappings, grids, PDOS atom selections,
  favorites/recents) in `<local_root>/.lain/` (only `core/project_data.py` names that folder); plot settings
  (`<kind>.plot`, `view3d.plot`) and exports in `<simulation>/plots/`; the cluster's copy of a remote plot in
  `<mirror>/tmp_remote/`, with its exports and `.plot` in `tmp_remote/plots_remote/` (`core/scratch.py`, spec 66);
  the jobs Lain submitted in `<data_dir>/submitted_jobs.log` (`core/remote/submit_log.py`, spec 71).
  Nothing else is written into simulation folders.
- **Numbers:** a decimal **point** everywhere text is shown or written (`decimal()` in `surface/report.py`, `QLocale.c()` in spin boxes), as QE reads it, in both languages; a comma typed by the user is read as a point. The one exception is the CSV export (`core/plotting/table.py`: `;` and a decimal comma, for Excel/Origin in pt-BR); `tests/test_decimal_point.py` guards both.
- **Data integrity:** never overwrite a user file without asking (`core/unique_names.py`, `_2` suffixes; the export
  asks first), **except** inside `tmp_remote/`, the scratch copy of a remote plot (spec 66), which a new copy
  overwrites. Data files are written whole with `core/appdirs.py:atomic_write_text`.

## Architecture

`src/qe_studio/core/` is logic without widgets, testable without Qt. `src/qe_studio/ui/` is the PyQt6 app.

### Rules (checked by `tests/test_architecture.py`)

- **No file over 500 lines**; `ui/main_window.py` is capped at 450. Split by responsibility before a module grows
  past it; `SIZE_EXCEPTIONS` stays empty.
- **`core/` never imports `qe_studio.ui`.** PyQt6 appears in `core/` only in `sync/_process.py`,
  `sync/controller.py`, `sync/monitor.py` and `tasks.py`.
- **`ui/` holds interface logic only:** widgets, layout, dialogs, signal wiring. Parsing, detection, physics, file
  operations and sync decisions belong in `core/`. New logic that needs no widget starts in `core/` (Qt-free
  modules are listed in `QT_FREE`).
- **`ui/` does not touch the disk:** no `open(` / `read_text` / `read_bytes` / `loadtxt` (except
  `ui/theme/manager.py`). Disk calls (`resolve`, `exists`, `stat`, `iterdir`, `glob`…) are counted per file in
  `FS_ALLOWED` and the counts only go down: a new one goes to `core/` or a worker.
- **Modular:** one job per module, small explicit interfaces (hooks, signals, injected services). New behaviour is
  a new module plus a registration, not another branch in a central class.

### Composition

- `ui/main_window.py:MainWindow` is the composition root: it builds widgets, controllers and stores, keeps only what
  spans controllers, and a thin facade used by tests and `scripts/screenshot.py`. A new feature gets its own
  controller built by a `for_window(window)` factory.
- Window actions live in `ui/actions.py:ACTIONS` (stable id, menu, text, shortcut, slot path). Keys a widget
  handles itself go in its `shortcut_help()`.
- Closing: `ui/shutdown.py`. A non-modal dialog's controller provides `close_dialog() -> bool`; a new background
  job joins the shutdown steps, takes the time it is given and reports whether it finished.

### Calculation modules

- **Identification is by content, never by file name** (PRD §3): `core/sniff.py` classifies files, each
  `CalculationModule` declares `FileRole`s, `core/detection.py` runs every module in `REGISTRY`.
- A new plot type subclasses `CalculationModule[Dataset, Params]` (`core/calculations/base.py`), is registered in
  `core/calculations/__init__.py:REGISTRY` and implements `load`, `default_params`, `param_schema` and `render`.
  The tuning panel is generated from the `ParamField` list. `load` uses the `sniff` it receives (the caller's
  cache); never import the module-level `sniff`.
- **No file in `ui/` may know a module** (`kind == "bands"` and the like): what the UI needs is a ClassVar or a
  hook on the base class. Extend `DummyModule` in `tests/test_module_contract.py` when the contract grows.
- Figure style comes from the params (`core/plotting/style.py:figure_style(params.background)`), never the app
  theme, so preview and export match.
- "Criar cálculo" types live in `core/calc_create/types/` (a `CalcType`, its Jinja templates under
  `resources/templates/`, a registry entry). `plan()` never raises nor reads a file.

### Threading

- **The GUI thread never reads or parses files.** Every background task goes through `core/tasks.py`
  (`run_task`, `TaskGroup`): callbacks run on the GUI thread, and a cancelled or superseded task never calls back.
- Cancellation is cooperative: a long loop in `core/` calls `core/cancel.py:check()`.
- Private thread pools have no Qt parent.
- matplotlib's global state is serialized by `core/plotting/mpl_lock.py:MPL_LOCK`; the GUI only *tries* it.
- Connect long-lived signals to bound methods, not lambdas. Never connect a lambda or `partial` to an object's own
  `destroyed` (PyQt may call it after freeing the object).
- Dialogs use `WA_DeleteOnClose`, **except** a modal `exec()` whose answer is read afterwards: read it, then
  `deleteLater()`.

### Sync safety (PRD §5)

- Pull and push always go through a dry run and a preview of the plan. The copy of a remote plot into `tmp_remote/`
  (spec 66) has the dry run but shows the preview only for a file over 100 MB; `tmp_remote/` itself is never synced
  (a fixed exclusion, like `.lain/`).
- Push only adds files the cluster does not have: it never overwrites or deletes anything remote.
- Unknown host keys are always refused (`-o StrictHostKeyChecking=yes` is forced). Passwords reach ssh only via
  `SSH_ASKPASS` in the child env, never argv or logs.
- ssh options are built only in `core/sync/rsync.py:ssh_command`. With `cluster.multiplex` they end with a shared
  master (`ControlMaster=auto`, `ControlPersist=120`, `ControlPath` in `core/sync/mux.py:control_dir()`: short,
  `0700`, the user's own). The shutdown stops the masters with `ssh -O stop` (spec 72).
- rsync children run with `LC_ALL=C.UTF-8`, `TZ=UTC` and `--no-h` (its output is parsed).
- A remote command other than rsync is built only from programs named in `config.yaml` (`cluster.jobs_command`,
  `cluster.submit_command`, `cluster.delete_command`) plus the fixed `cd`, `chmod a+x` and `touch`, in
  `core/remote/actions.py` and `core/sync/command.py`, with the same ssh options; a value read from the cluster (a
  file or folder name, a `prefix`, a job-ID) enters only as an argument, after `checked_name` and `shlex.quote`. A
  command that changes the cluster runs only after the user confirms it.
- The cluster mode lists (`rsync --list-only`, `core/remote/listing.py`), downloads through the usual pull (or into
  `tmp_remote/` to plot), submits a `.qsub` after a confirmation (`chmod a+x`, then `qsub`, in its folder), never
  while a job of the user runs in that folder or one Lain submitted from it (its log) is still in the queue, and asks
  first when a job of the user has the script's `#$ -N` (`core/remote/submit.py`), and cancels a job
  (`core/remote/job_cancel.py`).
- Cancelling a job (spec 70) never guesses: a fresh `qstatus` right before acting decides. A running job is stopped
  only by creating `<prefix>.EXIT` in its folder (matched by its `<name>.o<id>`), one per prefix of the folder's
  SCF, relax and vc-relax inputs, the cluster administrator's rule (spec 71); `qdel` runs only on a job still
  waiting, by its ID, never on one that is running.

### Theming and UI

- QSS is modular (`ui/resources/styles/<domain>/*.qss`) with `${token}` colours from
  `ui/resources/themes/{dark,light}.yaml`. A new colour is a token in **both** files and must pass WCAG AA in
  `tests/test_theme_contrast.py`. `text_dim` is only for disabled states and placeholders.
- Sizes that hold text come from the font scale (`core/fontscale.py`, `ui/theme/scale.py`), never a bare constant.
- A focusable control reserves a transparent 1 px border (`ui/resources/styles/controls/focus.qss`). Spin boxes
  and combos in a scrolled form are `ui/widgets/no_wheel.py:NoWheel*`.

## Testing

- `tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen` and `MPLBACKEND=Agg` before any Qt import and redirects
  `XDG_*` to temp dirs: tests never touch the real home. Every test has a 60 s timeout.
- `tests/fixtures/` holds real, trimmed QE outputs (see its README). **Never write there**: copy with
  `copy_fixture` first (`test_fixtures_untouched.py` fails otherwise). Don't add renamed copies: PRD-style layouts
  are built by fixtures (`demo_project`, `al_pdos_orbitals`, `raiz`). A new QE version is a real trimmed run in
  `tests/fixtures/qe<ver>_<system>/` plus a row in `test_qe_versions.py`.
- Reuse the shared helpers in `tests/*_helpers.py` (grid, viewer, sync, plot grid, calc, surface, 3D…).
- The `main_window` fixture builds a full `MainWindow` with isolated stores; `window_factory()` again (after
  `window.close()`) restarts the app on the same files.
- Patch dialogs where they are imported (e.g. `qe_studio.ui.plot_workflow.ask_mapping`,
  `qe_studio.ui.rename_controller.ask_rename`). `QMenu.exec` must be patched (the fixture fails otherwise); never
  reach the real session D-Bus.
- Exports and `.plot` writes run in workers: wait for `window.export_finished`, call
  `window.plot_settings.flush_now()` before reading a `.plot`. A real modal `exec()` needs
  `test_atoms_dialog.py:drive_modal`.
- Qt quirks: Qt keeps the modifiers of the last simulated event (call `grid_helpers.reset_modifiers` after a
  Ctrl/Shift click); `qtbot.keyClicks` with `"\n"` aborts the process; never `qtbot.addWidget` a delete-on-close
  window.
- Sync tests run the real `rsync` / `ssh` against `tests/ssh_server.py` (paramiko on `127.0.0.1`, allowlisted
  commands). `server.ssh_binary()` pins ssh to a temp `ssh_config`: never bypass it.
- The cluster is production: no test or verification ever reaches it. Tests talk only to `tests/ssh_server.py`
  (`127.0.0.1`) or fakes; the autouse guard in `tests/conftest.py` fails a test that reads the real `config.yaml` or
  contacts any other host (spec 69 R7, `tests/cluster_guard.py`).
- Hypothesis profiles `dev` / `ci` (`HYPOTHESIS_PROFILE=ci` in CI). Timing checks are marked `perf`.
- Goldens (`test_figure_regression.py`, `tests/*_golden.json`) guard default behaviour: a change must pass them, not
  regenerate them.
- `test_i18n.py` fails when a text is outside `_()`, the English catalog has an untranslated or fuzzy message, the `.po` lags
  the code (`scripts/i18n.py update`) or the `.mo` lags the `.po` (`compile`), or a translated text still shows in Portuguese
  (the probe runs the window in its own process); `test_i18n_closing.py` proves that nothing persisted (`.lain/`, `.plot`,
  exports, QSettings) depends on the language. A new text means `update`, translate, `compile`: CI runs `scripts/i18n.py check`.

## Keeping this file lean

When a spec is implemented, move it to `specs/Archived/` and update `specs/README.md` (and `README.md` /
`config.example.yaml` when users see the change). Add here only rules that hold for the whole project, never the
description of a feature: that lives in the archived spec and the code.
