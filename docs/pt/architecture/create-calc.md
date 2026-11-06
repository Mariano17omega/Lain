# Criar cálculo (UML e pipeline)

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
    participant W as Janela (2 etapas)
    participant T as CalcType
    participant E as InputEditor
    participant J as render (Jinja2)
    participant WR as writer
    W->>T: plan(scf, valores, modo)
    T->>E: edita o SCF (preserva formatação)
    T->>J: render(qsub/qe templates, valores)
    T-->>W: CalcPlan (PlannedFile por aba)
    W->>W: edição manual + verificação de escrita
    W->>WR: create_folder(plan, notas, fingerprint)
    WR->>WR: next_number, nome único, atomic write
    WR-->>W: pasta criada
```

- `plan()` **nunca levanta exceção nem lê arquivo**; os problemas voltam em `CalcPlan`/`field_problems`.
- A janela não conhece nenhum tipo: lista `REGISTRY`, desenha os `FormField` que `shown_fields` mantém para o modo e
  mostra os `PlannedFile` em abas.
- **Modos**: `padrao` mostra campos `standard`; os demais assumem o padrão. `avancado` mostra todos e os nomes dos
  arquivos. `shown_when` esconde campos que dependem de outros.
- Templates em `src/qe_studio/resources/templates/{qsub,qe}/`; `qsub/_base.qsub.j2` é a base comum (cabeçalho SGE, Intel
  MPI, e-mails) e cada tipo estende com `programs`, `body` e `post`.

Código: `core/calc_create/` — `types/` (um módulo por tipo + `base.py` + `__init__.py:REGISTRY`), `scf_info.py`,
`render.py`, `writer.py`, `numbering.py`, `fingerprint.py`, `surface/`.
