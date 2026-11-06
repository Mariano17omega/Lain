# Create calculation (UML and pipeline)

```mermaid
classDiagram
    class CalcType {
        <<abstract>>
        +id: str
        +label: str
        +folder_prefix: str
        +script_stem: str
        +script_template: str
        +multi_scf: bool
        +input_files(scf, name, scfs) list~InputFile~
        +input_fields(scf) list~FormField~
        +inputs(work) list~PlannedFile~
        +script_values(work) dict
        +check_scf(scf) str
        +plan(scf, values, mode) CalcPlan
    }
    class FormField {
        +id
        +label
        +kind
        +default
        +standard: bool
        +shown_when
    }
    class PlannedFile {
        +key
        +name
        +kind: FileKind
        +text
    }
    class CalcPlan {
        +files: list~PlannedFile~
        +ok
        +file(name)
    }
    class Work {
        +editor() InputEditor
        +run(key)
        +planned(key, kind, text)
    }
    class ScfInfo
    CalcType <|-- ScfType
    CalcType <|-- RelaxType
    RelaxType <|-- VcRelaxType
    CalcType <|-- BandasType
    CalcType <|-- PdosType
    CalcType <|-- ChargeType
    CalcType <|-- ChargeDiffType
    CalcType <|-- SlabType
    CalcType <|-- SupercellType
    CalcType <|-- AdsorptionType
    CalcType <|-- AdsEnergyType
    CalcType o-- FormField
    CalcType ..> CalcPlan
    CalcPlan o-- PlannedFile
    CalcType ..> Work
    Work ..> ScfInfo
```

## Pipeline

```mermaid
sequenceDiagram
    participant W as Window (2 steps)
    participant T as CalcType
    participant E as InputEditor
    participant J as render (Jinja2)
    participant WR as writer
    W->>T: plan(scf, values, mode)
    T->>E: edits the SCF (preserves formatting)
    T->>J: render(qsub/qe templates, values)
    T-->>W: CalcPlan (PlannedFile per tab)
    W->>W: hand edits + writing check
    W->>WR: create_folder(plan, notes, fingerprint)
    WR->>WR: next_number, unique name, atomic write
    WR-->>W: folder created
```

- `plan()` **never raises nor reads a file**; problems come back in `CalcPlan`/`field_problems`.
- The window knows no type: it lists `REGISTRY`, draws the `FormField`s that `shown_fields` keeps for the mode and
  shows the `PlannedFile`s in tabs.
- **Modes**: `padrao` shows `standard` fields; the others take their default. `avancado` shows all and the file names.
  `shown_when` hides fields that depend on others.
- Templates in `src/qe_studio/resources/templates/{qsub,qe}/`; `qsub/_base.qsub.j2` is the common base (SGE header,
  Intel MPI, e-mails) and each type extends it with `programs`, `body` and `post`.

Code: `core/calc_create/` — `types/` (one module per type + `base.py` + `__init__.py:REGISTRY`), `scf_info.py`,
`render.py`, `writer.py`, `numbering.py`, `fingerprint.py`, `surface/`.
