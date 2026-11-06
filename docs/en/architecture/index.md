# Architecture — overview

Lain separates **logic** from **interface**:

- `src/qe_studio/core/` — logic without widgets, testable without Qt (parsers, detection, physics, files, sync,
  generation).
- `src/qe_studio/ui/` — the PyQt6 app: widgets, layout, dialogs and signal wiring.
- Package `qe_studio` (historical internal name) with the `lain` command.

## Context (level 1)

```mermaid
flowchart LR
    U([Researcher]) --> L[Lain: QE Studio]
    L <-->|rsync + ssh| C[(Cluster<br/>SGE + QE)]
    L -->|reads/writes| D[(Simulation folders<br/>local_root)]
    L -.->|optional| X[XCrySDen]
    L -->|reads| CFG[config.yaml]
```

## Containers (level 2)

```mermaid
flowchart TB
    subgraph APP[Lain process]
        subgraph UI[ui/ — PyQt6]
            MW[MainWindow<br/>composition root]
            CTRL[controllers<br/>shell · files · plot · cluster · tools]
            WID[widgets and dialogs]
        end
        subgraph CORE[core/ — no widgets]
            DET[sniff + detection]
            CALC[calculations<br/>plot modules]
            QE[qe<br/>input/output parsers]
            PLOT[plotting<br/>style, export, session]
            CC[calc_create<br/>types + templates]
            REM[remote + sync]
            S3D[structure3d]
            PRJ[project, files, search, viewer]
        end
        TASKS[[core/tasks.py<br/>QThreadPool]]
    end
    UI --> CORE
    CTRL --> TASKS --> CORE
    REM -->|subprocess| SSH[ssh / rsync]
    SSH --> CL[(Cluster)]
    CORE --> FS[(Disk)]
```

## Principles

1. **The GUI thread never reads or parses files**; everything goes through `core/tasks.py` (`run_task`, `TaskGroup`).
2. **Identification by content**, never by file name.
3. **Modular**: a new plot or calculation type is a new module plus a registration (`REGISTRY`), not an `if` in a
   central class. The UI does not know `kind == "bands"`.
4. **Cluster safety**: strict ssh, commands only from programs in the config, a preview before transfers, nothing
   deleted.
5. **Data integrity**: never overwrite a user file without asking; atomic writes.

## Pages

| Page | Content |
|---|---|
| [Layers and rules](layers.md) | areas of `core/` and `ui/`, rules checked by a test |
| [Detection](detection.md) | `sniff` → `FileRole` → modules |
| [Calculation modules](calc-modules.md) | UML of the plot modules |
| [Create calculation](create-calc.md) | UML of the types and the generation pipeline |
| [Threading](threading.md) | tasks, cancellation, matplotlib |
| [Sync and cluster](sync-cluster.md) | components of the remote backend |
| [State and persistence](state.md) | where each piece of data lives |
| [UI composition](ui-composition.md) | `MainWindow`, controllers, actions, shutdown |
