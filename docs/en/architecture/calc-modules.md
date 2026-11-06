# Calculation modules (plots)

Each plot type is a subclass of `CalculationModule[Dataset, Params]` registered in
`core/calculations/__init__.py:REGISTRY`. The tuning panel is **generated** from the `ParamField` list.

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
    CalculationModule ..> DetectionResult : produces
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

## Sequence: from click to drawing

```mermaid
sequenceDiagram
    actor U as User
    participant UI as plot_workflow (ui/plot)
    participant T as tasks.run_task
    participant M as CalculationModule
    participant S as PlotSession
    participant R as render (matplotlib)
    U->>UI: Plot / Ctrl+G
    UI->>T: load (worker)
    T->>M: load(result, sniff)
    M-->>T: Dataset
    T-->>UI: callback on the GUI thread
    UI->>M: default_params + saved .plot
    UI->>S: PlotSession(result, dataset, params)
    S->>R: render(figure, dataset, params, style) [MPL_LOCK]
    R-->>UI: figure + RenderInfo
    U->>UI: changes a setting
    UI->>S: updates params → re-render
```

## A module's package

A typical module (`core/calculations/bands/`): `detection.py` (roles), `data.py` (dataset), `params.py` (`Params` +
`ParamField`), `render.py`, `table.py` (CSV) and `module.py` (ties it together). The **style** comes from
`core/plotting/style.py:figure_style(params.background)`, never from the app theme. A color declares
`metadata={"kind": "color"}` so a style can set it.

Test contract: `tests/test_module_contract.py` (`DummyModule`) — extend it when the contract grows.
