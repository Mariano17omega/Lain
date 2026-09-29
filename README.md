# QE Studio (Lain)

Desktop app (PyQt6) to browse, sync and plot [Quantum ESPRESSO](https://www.quantum-espresso.org/)
simulations. See [`PRD.md`](PRD.md) for the product requirements and
`Documentation/design system (UX)/` for the design system the UI follows.

- **Automatic detection** of band-structure, PDOS and relax runs. File names are only hints:
  every file is identified by its content (`bands.in` can be a pw.x or a bands.x input), so
  tutorial-style names (`al.scf.out`, `si.band.in`) and flat or `orbitals/` PDOS layouts are
  recognised. A missing SCF output is looked up in sibling `*scf*` folders, and anything still
  missing can be mapped by hand (remembered per folder).
- **Publication plots** (matplotlib) with Γ-labelled high-symmetry paths, E − E_F zeroing (or
  VBM / mid-gap / absolute), gap readout, PDOS grouped by species and/or orbital (spin-down
  mirrored), and a tuning panel. Figures go to each simulation's `plots/` folder as PNG
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
uv run qe-studio                      # or: uv run qe-studio --config /path/to/config.yaml
```

All settings live in `config.yaml` (there is no settings window); see
[`config.example.yaml`](config.example.yaml) for every key. QE Studio looks for it in `--config`,
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
   (BANDS, PDOS, RELAX, SCF, CALC), and outputs show `OK` / `INCOMPLETO`.
2. **Gerar Gráfico** (Ctrl+G) plots it, saves the figure into `plots/` and switches the left
   panel to the plot parameters (toggle back with **Árvore**).
3. Tune the plot. Zooming or panning with the toolbar updates the energy window, and
   **Exportar** (Ctrl+E) saves again.
4. **Rsync** pulls the folder from the cluster.

## Development

```bash
uv run pytest            # unit, integration (real rsync) and headless UI tests
uv run ruff check . && uv run ruff format --check .
QE_STUDIO_REAL_DATA=/path/to/runs:/other/runs uv run pytest -m realdata   # your own runs
uv run python scripts/screenshot.py --plot   # off-screen PNGs of both themes in screenshots/
```

Code map: `src/qe_studio/core` holds the Qt-free logic: QE parsers (`core/qe`), detection,
calculation modules (`core/calculations`; add new plot types there) and plotting/export.
`core/sync` holds the rsync engine. `src/qe_studio/ui` holds the widgets, and
`resources/styles/**.qss` the modular stylesheets, which use `${token}` colours from
`resources/themes/*.yaml`.

Fonts (Inter, JetBrains Mono: OFL) and Material Symbols icons (Apache-2.0) are vendored under
`src/qe_studio/resources/`; `scripts/fetch_assets.py` refreshes them.

### Known MVP limitations

- Pull only (no push). Relaxations are detected but not plotted.
- Spin-polarized band structures show a single `.gnu` channel. k-resolved PDOS files are
  reported as unsupported.
- On Windows, rsync/ssh must come from cwRsync or MSYS2 (`sync.rsync_binary`,
  `sync.ssh_binary`). Linux is the primary target.
