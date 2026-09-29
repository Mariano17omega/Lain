# QE Studio (Lain)

Desktop app (PyQt6) to browse, sync and plot [Quantum ESPRESSO](https://www.quantum-espresso.org/)
simulations: automatic detection of band-structure / PDOS / relax runs, publication-ready matplotlib
figures saved to each simulation's `plots/` folder, and pull-only synchronization from an HPC
cluster over rsync + ssh. See [`PRD.md`](PRD.md) for the product requirements.

## Setup

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/). Cluster sync also needs `rsync` and
`ssh` on `PATH` (on Windows: cwRsync or MSYS2).

```bash
uv sync
cp config.example.yaml config.yaml   # then edit paths and cluster settings
uv run qe-studio                      # or: uv run qe-studio --config /path/to/config.yaml
```

All settings live in `config.yaml` (there is no settings window). Prefer SSH keys; for password
login set `auth: password` and export the password in the variable named by `password_env`.

## Development

```bash
uv run pytest            # unit + UI tests (headless)
uv run ruff check . && uv run ruff format --check .
QE_STUDIO_REAL_DATA=/path/to/runs:/other/runs uv run pytest -m realdata   # optional real-data smoke
```

Fonts (Inter, JetBrains Mono — OFL) and Material Symbols icons (Apache-2.0) are vendored under
`src/qe_studio/resources/`; `scripts/fetch_assets.py` refreshes them.
