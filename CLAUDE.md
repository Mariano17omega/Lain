# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Lain: QE Studio: a PyQt6 desktop app to browse, pull-sync (rsync + ssh) and plot Quantum ESPRESSO
simulations (band structures, PDOS). Requirements live in `specs/spec_0-PRD.md`; code comments
cite it as "PRD §x.y". Change specs derived from `specs/Ideias.md` are `specs/spec_N-*.md`
(prioritized index in `specs/README.md`). The UI follows `Documentation/design system (UX)/`.

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
uv run pytest                                    # full suite (~12 s), headless
uv run pytest tests/test_detection.py::test_name # single test
uv run pytest -m perf                            # NFR §7 latency budget (<500 ms, 100 bands)
QE_STUDIO_REAL_DATA=/runs:/other uv run pytest -m realdata   # user's own QE runs (off by default)
uv run ruff check . && uv run ruff format --check .
uv run python scripts/screenshot.py --plot       # off-screen PNGs of both themes → screenshots/
uv run python scripts/fetch_assets.py            # refresh vendored fonts/icons
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
  `tests/fixtures/` (copy with `copy_fixture` first).
- `main_window` fixture builds a full `MainWindow` with isolated QSettings and `FolderMemory`.
- Sync integration tests run the **real `rsync` binary** (skipped if absent) against a temp
  "remote"; `tests/fake_ssh.py` stands in for ssh by running the remote command locally.
- Tests have a 60 s timeout (pytest-timeout).

## Architecture

`src/qe_studio/core` is logic without widgets (only `core/sync/controller.py` and
`core/sync/monitor.py` use Qt, for `QProcess`/signals); `src/qe_studio/ui` is the PyQt6 app.

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

**Adding a calculation type** (NFR §7): subclass `CalculationModule` in `core/calculations/`,
register it in `core/calculations/__init__.py:REGISTRY`, and for plottable modules implement
`load`, `default_params`, `param_schema`, `render` (and optionally `param_changed`). Params are
dataclasses extending `CommonParams`; the tuning panel (`ui/widgets/plot_params.py`) is generated
from the `ParamField` list in `param_schema`, so no UI code is needed for new fields.
`load_cached()` memoizes `load()` on file stamps and is called from worker threads.

### Plotting

`ui/plot_session.py:PlotSession` = detection result + dataset + params (+ copy of defaults).
`render()` wraps the module's `render` in `PlotStyle.rc(...)`. The style is `PlotSession.style` =
`figure_style(params.background)` (`core/plotting/style.py`), never the app theme, so preview and
export match; `ThemeManager` only styles the widgets around the canvas. Toolbar pan/zoom is written back into params (`apply_limits`) so exports keep
it. `core/plotting/export.py` writes into `<simulation>/plots/`; existing files are never
overwritten without asking (PRD §7 data integrity).

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
`plots/`) never block a pull. `controller.py` is a `QProcess` state machine (dry run → plan →
conflicts → transfer) that never opens dialogs: it emits `conflict_needed` and waits for
`resolve()`, so UI and tests supply the answer. Passwords reach ssh only via `SSH_ASKPASS`
(`askpass.py`, installed as `qe-studio-askpass`) through the child env, never argv or logs; unknown
host keys are always refused.

### Theming

`ui/theme/manager.py` assembles modular QSS from `ui/resources/styles/<domain>/*.qss` (domains
listed in `STYLE_DOMAINS`), substituting `${token}` colours from `ui/resources/themes/{dark,light}.yaml`.
Any new colour must be added as a token to **both** theme files. Custom-painted widgets read
`ThemeManager.color(token)` and refresh on `theme_changed`. Icons are Material Symbols SVGs tinted
at runtime; fonts (Inter for UI, JetBrains Mono for numbers/paths) are vendored.
