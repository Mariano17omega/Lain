# Composição da UI

`ui/main_window.py:MainWindow` é a **raiz de composição**: constrói widgets, controllers e stores, mantém só o que
atravessa controllers e uma fachada fina usada por testes e por `scripts/screenshot.py`.

```mermaid
flowchart TB
    APP[ui/app.py<br/>QApplication, config, idioma, tema] --> MW[MainWindow]
    MW --> ACT[actions.ACTIONS<br/>menu · texto · atalho · slot]
    MW --> C1[shell: layout · foco · ajuda · paleta]
    MW --> C2[files: navegação · projeto · detecção · renomear]
    MW --> C3[plot: workflow · settings · export · grids]
    MW --> C4[cluster: sync · remoto · jobs · lixeira]
    MW --> C5[tools: criar cálculo · 3D · derivar · energia de adsorção]
    C1 & C2 & C3 & C4 & C5 --> CORE[(core/)]
    MW --> SD[shutdown.py]
```

- **Um recurso novo** ganha o próprio controller, criado por uma fábrica `for_window(window)`.
- **Ações de janela**: `ui/actions.py:ACTIONS` (id estável, menu, texto, atalho, caminho do slot). Teclas que um widget
  trata sozinho vão em `shortcut_help()`.
- **Fechamento**: `ui/shutdown.py`. O controller de um diálogo não modal implementa `close_dialog() -> bool`.
- **Diálogos** usam `WA_DeleteOnClose`, exceto um `exec()` modal cuja resposta é lida depois.
- **Sinais de longa vida** ligam a métodos, não a *lambdas*.
- **Tema**: QSS modular em `ui/resources/styles/<domínio>/*.qss` com `${token}` de `ui/resources/themes/{dark,light}.yaml`.
- **Tamanhos** que contêm texto vêm da escala de fonte (`core/app/fontscale.py`, `ui/theme/scale.py`).
- **Idioma**: textos em português dentro de `_()`; o inglês vem de `locale/en/LC_MESSAGES/lain.po`.
