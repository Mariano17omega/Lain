# Grids

O botão **Grids** (barra de atividades; menu *Gráficos ▸ Grids…*) junta **gráficos já plotados** numa só figura
N × M. Nunca é detectado: nasce de sessões de gráficos abertos.

- Cada célula tem posição e título; `cell_width`/`cell_height` definem o tamanho de cada uma.
- Grids são salvos por nome em `.lain/` (`grid_store.py`) e reabertos depois.
- Os gráficos individuais podem ser escondidos com o botão **Gráficos**.
- Exporta como qualquer gráfico (PNG/SVG/PDF).

Código: `core/calculations/grid/`, `core/plotting/grid.py`, `grid_session.py`, `core/project/grid_store.py`,
`ui/plot/grids_controller.py`, `ui/dialogs/grid_dialog.py`.
