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
uv run pytest -m perf                            # NFR §7 latency budget (<500 ms, 100 bands)
QE_STUDIO_REAL_DATA=/runs:/other uv run pytest -m realdata   # user's own QE runs (off by default)
uv run ruff check . && uv run ruff format --check .
uv run pyright                                   # basic mode over src/ (CI); see [tool.pyright] ignore list
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
- `test_properties.py` holds the Hypothesis tests of the parsers (`read_gnu`, `parse_relax`, the input
  lexer/linter; specs 9, 12 add theirs). `conftest.py` registers profiles `dev` and `ci`
  (`HYPOTHESIS_PROFILE=ci`: fewer examples, no deadline, no example database).
- `viewer_helpers.py` (`open_text`, `key`) is shared by the text viewer tests, like `sync_helpers.py`
  is by the sync ones.
- `main_window` fixture builds a full `MainWindow` with isolated QSettings and `FolderMemory`.
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

`src/qe_studio/core` is logic without widgets (only `core/sync/controller.py` and
`core/sync/monitor.py` use Qt, for `QProcess`/signals); `src/qe_studio/ui` is the PyQt6 app.

### Architecture rules

- **No files over ~500 lines that centralize everything.** Split by responsibility before a module
  grows past that. Current offenders: `ui/main_window.py` (~1050 lines, split by spec 15) and
  `core/calculations/bands.py` (~550, split by spec 13).
- **`ui/` holds interface logic only.** Widgets, layout, dialogs, and wiring signals to `core/`.
  Parsing, detection, physics, file operations, sync decisions and any other backend logic belong in
  `core/`, where they are testable without Qt. If a UI method computes something that doesn't depend
  on a widget, move it to `core/`.
- **Keep the program modular to ease maintenance.** Each module has one job, and depends on small
  explicit interfaces (hooks, signals, injected services) instead of reaching into other modules'
  internals. New behaviour is a new module plus a registration, not another branch in a central class.

### Detection pipeline (PRD §3)

File names are only hints; everything is identified by content.

1. `core/sniff.py`: `sniff(path)` classifies one file into a `FileKind` (pw.x in/out, bands.x
   in/out, projwfc, dos, `.gnu`, PDOS atm/tot…) by reading head/tail bytes with the parsers in
   `core/qe/`. `SniffCache` memoizes per (mtime, size) and is thread-safe.
2. `core/calculations/base.py`: each `CalculationModule` declares `FileRole`s (id, content
   predicate `accepts`, optional PRD naming `globs`, `required`/`multiple`/`anchor`). `match()`
   fills roles in passes: user mapping (`forced`) → PRD glob verified by content → content only;
   `finalize()` hooks cross-role logic, and `infer_from_neighbours()` finds the SCF output in the
   parent or sibling `*scf*` folders. A module with no anchor role present returns `None`.
3. `core/detection.py`: `detect_folder()` runs every module in `REGISTRY`; `fallback` modules
   (SCF/CALC info badges) apply only when no primary kind matched. `FolderMemory` stores manual
   mappings and typed k-point labels in the app data dir, never inside simulation folders (they
   get synced).

**Adding a calculation type** (NFR §7): subclass `CalculationModule[Dataset, Params]` in
`core/calculations/` (detection-only modules use `CalculationModule[None, CommonParams]`), register
it in `core/calculations/__init__.py:REGISTRY`, and for plottable modules implement `load`,
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

`ui/plot_session.py:PlotSession[D, P]` = detection result + dataset + params (+ copy of defaults).
`render()` wraps the module's `render` in `PlotStyle.rc(...)`. The style is `PlotSession.style` =
`figure_style(params.background)` (`core/plotting/style.py`), never the app theme, so preview and
export match; `ThemeManager` only styles the widgets around the canvas. Toolbar pan/zoom is written back into params (`apply_limits`) so exports keep
it. `core/plotting/export.py` writes into `<simulation>/plots/`; existing files are never
overwritten without asking (PRD §7 data integrity).

`ParamsPanel` (`ui/widgets/plot_params.py`) keeps one `ParamsBody` per open plot in a `QStackedWidget`
(keyed by `session.key`): `bind` shows it (rebuilding only if the session or its schema changed),
`discard` drops it when the tab closes. Section open/closed state is QSettings
`params/sections/<kind>/<title>`.

Plot settings persist in `<simulation>/<kind>.plot` (YAML, `core/plotting/plot_file.py`): read in
`_LoadTask` next to `load_cached`, applied field by field over `default_params` (`PlotSession.defaults`
stays the module default), written only after a user edit (params panel or pan/zoom), debounced 1 s
and flushed on tab close, regenerate and exit. Window layout, grid mode/sort and the last folder are
QSettings (`layout/*`, `files/*`, `explorer/last_folder`).

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

### Input viewer (spec 11)

A QE input opens in the same `TextViewer`. `core/qe/input_lexer.py:scan_line(text, LexState, lineno)`
is the one lexer (tolerant, never raises; `LexState.code` fits a Qt block state): `core/qe/input_lint.py:lint`
walks a file with it and adds the whole-file rules (unclosed namelist, repeated/unknown namelist or card,
card options), and `highlighters.py:InputHighlighter` colors blocks with it (theme tokens `syn_*`), so
both agree on what a token is. It checks how things are *written* only: an unknown parameter name is
advanced validation, not done. `LintIssue.line` is 1-based and columns 0-based half-open. `lint` is not
`parse_input` (ASE), which detection and plots keep using. `core/sniff.py:looks_like_input(path)` (head
only, no ASE, GUI-thread safe) decides what is an input, even when sniff says UNKNOWN because ASE
choked; `ui/file_types.py:viewer_kind` uses it for unknown suffixes. `load_for_viewer` (worker) lints
inputs up to `INPUT_READ_LIMIT` (above it: colors only, banner says so) and extracts key parameters
(`core/qe/input_extract.py`); `ui/widgets/input_view.py:InputView` shows the issues row (F8 /
Shift+F8), the chip strip (`ui/widgets/flow_layout.py`) and "Comparar com…". `CodeView` has generic
diagnostics (`set_diagnostics`: margin marker + tooltips; the wavy underline is the highlighter's),
`set_numbers` and `set_row_backgrounds` for padded side-by-side panes. `Workspace.open_diff(a, b)`
(tab key `diff:<a>|<b>`; `compare_with` asks for the file) opens `ui/widgets/diff_view.py:DiffView`,
which only lays out `core/qe/input_diff.py:compare_files` (worker): by parameter (`normalize_value`:
numbers as floats, logicals as bools, strings casefolded) or line by line (`text_rows`, `difflib`).

### Threading rules (GUI thread must never parse files)

- `ui/services.py:DetectionService` caches detection per folder and runs misses in a 2-thread
  `QThreadPool`. Tasks carry a token; `invalidate()` supersedes running tasks so stale results
  are dropped. `detect_now()` is synchronous: scripts and tests only.
- `MainWindow` loads datasets via `QRunnable` in the global pool, then renders on the GUI thread.
- Keep finished `QRunnable`s / their signal objects alive until the next event-loop turn
  (`QTimer.singleShot(0, ...)`) because the slot runs on that signal object.
- Connect long-lived signals (e.g. `ThemeManager.theme_changed`) to bound methods, not lambdas,
  so they disconnect when the widget is deleted. Dialogs use delete-on-close.
- `app.main()` waits on the global pool before exit so no worker outlives the interpreter.

### Sync (PRD §5, pull only)

`core/sync/rsync.py` builds commands/env and parses output (children run with `LC_ALL=C.UTF-8`,
`TZ=UTC`, `--no-h` because rsync output is locale-dependent). `planner.py` is pure: dry-run
records + local stats → per-file NEW / UPDATE / LOCAL_NEWER; files only present locally (like
`plots/`) never block a pull. `controller.py` is a `QProcess` state machine (`rsync --version` →
dry run → plan, whose local stats run in a worker → conflicts → transfer) that never opens
dialogs: it emits `conflict_needed` and waits for `resolve()`, so UI and tests supply the answer.
Every stage runs through `_step()`, so an exception ends the sync as FAILED instead of hanging
it. `monitor.py` probes in daemon threads, not a `QThreadPool` (DNS ignores the connect timeout
and a pool's destructor waits without limit). Passwords reach ssh only via `SSH_ASKPASS`
(`askpass.py`, installed as `qe-studio-askpass`) through the child env, never argv or logs; unknown
host keys are always refused.

### Context menu (spec 5)

`ui/widgets/context_menu.py:ItemActions` builds the right-click menu for the tree and the grid
(both panels emit `item_menu_requested(path, pos)` → `MainWindow._show_item_menu`). "Abrir com"
lists programs from `core/desktop_apps.py` (Qt-free `.desktop`/`mimeapps.list` reader, one
cached `catalog()` per session) and starts them with `QProcess.startDetached(argv)`, never a
shell. Renaming goes through `MainWindow.rename_path` because it touches global state: flush the
item's `.plot` settings, `core/file_ops.rename_item` (refuses existing targets), close affected
tabs, `FolderMemory.rename`, invalidate detection. Tests must patch `QMenu.exec` (the
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
