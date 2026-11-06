# State and persistence

```mermaid
flowchart LR
    subgraph CFG[Configuration]
        Y[config.yaml<br/>pydantic AppConfig]
    end
    subgraph DATA["Data folder (paths.data or ~/.local/share/qe-studio)"]
        QS[settings.ini<br/>QSettings: window, theme, last folder]
        LOG[lain.log · lain.crash]
        SJ[submitted_jobs.log]
        LOCK[instance lock]
    end
    subgraph ROOT["local_root/.lain/"]
        FM[folder memory]
        GR[grids]
        CO[compounds]
        NV[favorites / recents]
    end
    subgraph SIM["simulation/plots/"]
        PL[bands.plot · pdos.plot · …]
        EX[PNG/SVG/PDF figures + CSV]
        V3[view3d.plot]
    end
    subgraph TMP["folder/tmp_remote/"]
        CP[copy of a remote plot]
        PR[plots_remote/]
    end
    CACHE[(~/.cache/qe-studio<br/>only what can be remade)]
```

| Data | Where | Written by |
|---|---|---|
| Config | `config.yaml` | the user (read-only for Lain) |
| UI state | QSettings (`<data>/settings.ini`) | `ui/*` |
| Per-root data | `<local_root>/.lain/` (only `core/project/project_data.py` names the folder) | `core/project/*` |
| Settings and exports | `<simulation>/plots/` | `core/plotting/*` |
| Remote plot copy | `<folder>/tmp_remote/` | `core/remote/scratch.py` (overwrites without asking, only here) |
| Submitted jobs | `<data>/submitted_jobs.log` | `core/remote/submit_log.py` |
| Log | `<data>/lain.log` | `core/app/logs.py` |
| Plot styles | `resources/templates/plot_styles/*.yaml` | read-only |

- **Integrity**: never overwrite a user file without asking (`core/files/unique_names.py`: `_2` suffixes); data files
  are written whole with `core/appdirs.py:atomic_write_text`.
- Nothing else is written into simulation folders.
- Language influences nothing that persists (`.lain/`, `.plot`, exports, QSettings) — verified by a test.
