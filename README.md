# Lain: QE Studio

[![CI](https://github.com/Mariano17omega/Lain/actions/workflows/ci.yml/badge.svg)](https://github.com/Mariano17omega/Lain/actions/workflows/ci.yml)

Desktop app (PyQt6) to browse, sync and plot [Quantum ESPRESSO](https://www.quantum-espresso.org/)
simulations (QE 7.1 or newer). See [`specs/spec_0-PRD.md`](specs/spec_0-PRD.md) for the product
requirements, [`specs/README.md`](specs/README.md) for the index of change specs and
`Documentation/design system (UX)/` for the design system the UI follows.

- **Automatic detection** of band-structure, PDOS and relax runs. File names are only hints:
  every file is identified by its content (`bands.in` can be a pw.x or a bands.x input), so
  tutorial-style names (`al.scf.out`, `si.band.in`) and flat or `orbitals/` PDOS layouts are
  recognised. A missing SCF output is looked up in sibling `*scf*` folders, and anything still
  missing can be mapped by hand (remembered per folder).
- **Publication plots** (matplotlib) with Γ-labelled high-symmetry paths, E − E_F zeroing (or
  VBM / mid-gap / absolute), gap readout, PDOS grouped by species and/or orbital (spin-down
  mirrored), relax / vc-relax progress (|ΔE| and total force per BFGS step against the
  convergence thresholds, log or linear), and a tuning panel. Figures go to each simulation's `plots/` folder as PNG
  (300/600 DPI), SVG and PDF; existing files are never replaced without asking.
- **Pull-only cluster sync** over rsync + ssh with configurable excludes (`tmp/`, `*.save/`,
  wavefunctions, …), a per-file conflict prompt and a cancellable progress dialog.
- **Dark and light themes**, Inter + JetBrains Mono, Portuguese UI.

## Setup

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/). Cluster sync also needs `rsync`
(≥ 3.1) and `ssh` on `PATH`.

```bash
uv sync
cp config.example.yaml config.yaml   # then edit paths and cluster settings
uv run lain                           # or: uv run lain --config /path/to/config.yaml
```

To start it from any terminal by typing just `lain`, install it as a uv tool (editable, so code
changes apply without reinstalling; rerun with `--force` after changing dependencies or entry
points):

```bash
uv tool install --editable .
lain
```

Outside the repository `./config.yaml` is not found, so keep your config in
`~/.config/qe-studio/config.yaml` (or point `$QE_STUDIO_CONFIG` at it).

### Desktop integration (optional)

So the window manager shows Lain's icon in the taskbar and the application menu lists it, install
the launcher and icons for your user (nothing is installed unless you run this; it needs the
`lain` command on `PATH`, see above):

```bash
uv run python scripts/install_desktop.py              # into $XDG_DATA_HOME (~/.local/share)
uv run python scripts/install_desktop.py --prefix DIR # or into another data directory
```

All settings live in `config.yaml` (there is no settings window); see
[`config.example.yaml`](config.example.yaml) for every key. Lain looks for it in `--config`,
`$QE_STUDIO_CONFIG`, `./config.yaml`, then `~/.config/qe-studio/config.yaml`. `config.yaml` is
git-ignored because it may hold credentials.

### Cluster authentication

- **Key (recommended):** `auth: key` and `key_path`. ssh runs non-interactively, so a key with a
  passphrase must be loaded in `ssh-agent`.
- **Password:** `auth: password`; export the password in the variable named by `password_env`
  (default `QE_STUDIO_SSH_PASSWORD`) or type it when prompted (kept in memory for the session
  only). The password reaches ssh through `SSH_ASKPASS` and never appears on a command line or in
  logs; `sshpass` is not needed.
- The cluster's host key must already be in `~/.ssh/known_hosts`: connect once with
  `ssh user@host` in a terminal. Unknown keys are never accepted automatically.

### How sync decides

"Sincronizar" pulls the selected folder (or the whole project) from `remote_root`. rsync lists the
files that differ; each one is then compared with the local copy:

| Situation | Action |
|---|---|
| file only on the cluster | downloaded |
| cluster copy newer | you choose: overwrite this / overwrite all in this folder / keep local / cancel |
| local copy newer | kept, reported |

A folder whose differing files are all newer locally is reported as "local is newer" and nothing
is transferred (PRD §5.2). Files that exist only locally, such as generated `plots/`, never block
a pull.

## Usage

1. Pick a simulation folder in the explorer; badges show what was detected
   (BANDS, PDOS, RELAX, SCF, CALC), and outputs show `OK` / `INCOMPLETO`. Queue logs
   (`job.o12345`, `job.e12345`) show `SEM ERROS` when empty and `ERRO` otherwise; they and the
   submission scripts (`.qsub`, `.slurm`, `.pbs`) open read-only in a tab. The grid cards show
   only that state (list mode also shows sizes); `..`, Backspace or Alt+↑ go up a folder.
   Right-click a file or folder for **Abrir local de origem**, **Abrir com** (installed programs
   for its type, or any other), **Copiar** (paste it in the file manager or a terminal) and
   **Renomear** (never overwrites; tabs showing the item are closed). On an SCF output
   there is also **Plotar**, which previews its convergence (estimated accuracy against
   `conv_thr`, |ΔE| or total energy, and the magnetization of spin runs) without saving; the
   **Plotar SCF** button next to **Gerar Gráfico** does the same for the SCF output open in a tab.
   Every QE output (pw.x, bands.x, projwfc.x…) also has **Resumo**: a tab with its state
   (`Concluído` / `Incompleto` / `Erro`), WALL and CPU time, parallelization, memory, system,
   results (energies, Fermi / HOMO-LUMO and gap, magnetization, pressure and stress, forces, SCF and
   BFGS progress) and the warnings and errors, read from the file and never saved. **Copiar** puts
   it on the clipboard as text, **Atualizar** reads the file again (the job may still be running)
   and a double click on a row opens the output at the line it came from.
   Text files open in a viewer with line numbers, **Ctrl+F** search (F3 / Shift+F3 for the next and
   previous hit), coloured QE outputs (energies, errors, warnings, convergence) and **Ir à linha…**
   (Ctrl+L). A file above 4 MB shows its first 1 MB and last 2 MB (line numbers stay real); the
   banner offers **Abrir no editor externo** and **Carregar tudo** (up to 64 MB). Right-click a tab
   (or middle-click it to close it) for **Fechar** (Ctrl+W), **Fechar outras / à direita / todas**,
   **Copiar caminho** and **Revelar no explorador**.
   QE inputs get syntax colours and a check of how they are *written* (not of what the
   parameters mean): an unclosed quote, a namelist without its `/`, a line without `=`, an
   unbalanced parenthesis, a malformed logical or number, a misspelled namelist or card
   name, a bad card option. Problems are underlined in red, marked in the margin (hover for the
   message) and counted in a banner (**Ir ao primeiro**, **F8** / **Shift+F8**). Above the text, a
   strip of chips shows `calculation`, cutoffs, the `K_POINTS` grid and other key parameters (click
   one to go to its line). **Comparar com…** opens a tab that lists the parameters that differ
   (`1d-8` and `1.0e-8` are the same number) or shows the two files side by side.
2. **Gerar Gráfico** (Ctrl+G) plots it, saves the figure into `plots/` and switches the left
   panel to the plot parameters (toggle back with **Árvore**). The tab area starts hidden and
   opens when a plot is generated or a file is opened. **Plot** in the activity bar plots the
   folder without saving anything (a plot already open is just brought to front); clicking it
   again hides the plot and its parameters.
3. Tune the plot. Zooming or panning with the toolbar updates the energy window, and
   **Exportar** (Ctrl+E) saves again. Hovering the plot shows the values under the cursor in the
   toolbar (k and energy with the nearest high-symmetry point, PDOS, relax step, SCF iteration). Your settings are kept in `<kind>.plot` (e.g. `bands.plot`)
   inside the simulation folder and come back the next time you plot it; **Restaurar padrões**
   deletes it.
4. **Rsync** pulls the folder from the cluster.

## Development

```bash
uv run pytest            # unit, integration (real rsync and ssh) and headless UI tests
uv run pytest -m "not realdata and not perf"   # what CI runs
uv run pytest -m perf    # NFR §7 latency budget (CI reports it without blocking)
uv run ruff check . && uv run ruff format --check .
QE_STUDIO_REAL_DATA=/path/to/runs:/other/runs uv run pytest -m realdata   # your own runs
uv run python scripts/screenshot.py --plot   # off-screen PNGs of both themes in screenshots/ (--text: text viewer, --input: an input with errors, --diff [text]: input comparison, --summary: output summary)
uv run python scripts/build_icons.py         # re-render the app icon PNGs after editing the SVG
```

CI (`.github/workflows/ci.yml`) runs lint, formatting and the tests on Python 3.11 and 3.12, and
a non-blocking `perf` job. `HYPOTHESIS_PROFILE=ci` makes the property tests lighter.

The sync tests drive the real `rsync` and `ssh` against a local SSH server built with paramiko
(`tests/ssh_server.py`) that serves a temp folder as the cluster; `ssh` runs with a temporary
`ssh_config`, so the tests never read your `~/.ssh`. They are skipped if `rsync` or `ssh` is
missing.

Code map: `src/qe_studio/core` holds the Qt-free logic: config loading (`core/config.py`), QE
parsers (`core/qe`), detection, calculation modules (`core/calculations`; add new plot types
there) and plotting/export. `core/sync` holds the rsync engine and the ssh askpass helper.
`src/qe_studio/ui` holds the app bootstrap (`ui/app.py`) and the widgets, and
`ui/resources/styles/**.qss` the modular stylesheets, which use `${token}` colours from
`ui/resources/themes/*.yaml`.

Fonts (Inter, JetBrains Mono: OFL) and Material Symbols icons (Apache-2.0) are vendored under
`src/qe_studio/ui/resources/`; `scripts/fetch_assets.py` refreshes them.

### Known MVP limitations

- Pull only (no push).
- Relaxation plots show energy and force only (no structure view; vc-relax |ΔE| uses the total
  energy, not the enthalpy).
- Spin-polarized band structures show a single `.gnu` channel. k-resolved PDOS files are
  reported as unsupported.
- On Windows, rsync/ssh must come from cwRsync or MSYS2 (`sync.rsync_binary`,
  `sync.ssh_binary`). Linux is the primary target.
