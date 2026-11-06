# Módulos de cálculo (gráficos)

Cada tipo de gráfico é uma subclasse de `CalculationModule[Dataset, Params]` registrada em
`core/calculations/__init__.py:REGISTRY`. O painel de ajustes é **gerado** da lista de `ParamField`.

```mermaid
classDiagram
    class CalculationModule~T~ {
        <<abstract>>
        +kind: str
        +badge: str
        +display_name: str
        +roles: tuple~FileRole~
        +plottable: bool
        +match(listing, sniff) DetectionResult
        +load(result, sniff) D
        +default_params(config, dataset) P
        +param_schema(dataset) list~ParamField~
        +render(figure, dataset, params, style) RenderInfo
        +table(dataset, params) PlotTable
        +apply_limits(params, limits)
        +format_coordinates(x, y) str
    }
    class FileRole {
        +id: str
        +accepts(FileSniff) bool
        +globs
        +required: bool
    }
    class ParamField {
        +name
        +label
        +section
        +kind
        +choices
        +requires
    }
    class DetectionResult {
        +module
        +folder
        +files: dict
        +methods: dict
        +missing: list
        +parts
    }
    class PlotSession~T~ {
        +result
        +dataset
        +params
        +defaults
    }
    CalculationModule o-- FileRole
    CalculationModule ..> ParamField : param_schema
    CalculationModule ..> DetectionResult : produz
    PlotSession --> CalculationModule
    PlotSession --> DetectionResult
    CalculationModule <|-- BandsModule
    CalculationModule <|-- PdosModule
    CalculationModule <|-- RelaxModule
    CalculationModule <|-- ScfModule
    CalculationModule <|-- CalcModule
    CalculationModule <|-- BandsDosModule
    CalculationModule <|-- GridModule
```

## Sequência: do clique ao desenho

```mermaid
sequenceDiagram
    actor U as Usuário
    participant UI as plot_workflow (ui/plot)
    participant T as tasks.run_task
    participant M as CalculationModule
    participant S as PlotSession
    participant R as render (matplotlib)
    U->>UI: Plot / Ctrl+G
    UI->>T: carregar (worker)
    T->>M: load(result, sniff)
    M-->>T: Dataset
    T-->>UI: callback na thread da GUI
    UI->>M: default_params + .plot salvo
    UI->>S: PlotSession(result, dataset, params)
    S->>R: render(figure, dataset, params, style) [MPL_LOCK]
    R-->>UI: figura + RenderInfo
    U->>UI: muda um ajuste
    UI->>S: atualiza params → re-render
```

## Pacote de um módulo

Um módulo típico (`core/calculations/bands/`): `detection.py` (papéis), `data.py` (dataset), `params.py`
(`Params` + `ParamField`), `render.py`, `table.py` (CSV) e `module.py` (liga tudo). O **estilo** vem de
`core/plotting/style.py:figure_style(params.background)`, nunca do tema do app. Uma cor declara
`metadata={"kind": "color"}` para que um estilo possa defini-la.

Contrato de teste: `tests/test_module_contract.py` (`DummyModule`) — estenda-o quando o contrato crescer.
