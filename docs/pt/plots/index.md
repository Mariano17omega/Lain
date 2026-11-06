# Gráficos — visão geral

Os gráficos são feitos com matplotlib e pensados para publicação. Há cinco tipos detectáveis e dois compostos:

| Tipo | Origem | Página |
|---|---|---|
| Estrutura de bandas | pasta `BANDS` | [Bandas](bands.md) |
| PDOS | pasta `PDOS` | [PDOS](pdos.md) |
| Bandas + DOS | 1 pasta de bandas + 1 de PDOS | [Bandas com DOS](bands-dos.md) |
| Relax / vc-relax | saída do `pw.x` | [Relax](relax.md) |
| Convergência do SCF | saída do `pw.x` | [SCF](scf.md) |
| Grid de gráficos | gráficos já abertos | [Grids](grids.md) |

## Como plotar

1. Selecione a pasta (ou, para Bandas + DOS, as duas pastas com `Ctrl`-clique).
2. **Plot** na barra de atividades, **Gerar gráfico** (`Ctrl+G`) ou **Plotar** no menu de contexto.
3. O painel esquerdo troca para os **ajustes** (botão **Árvore** volta). O painel é gerado a partir da lista de
   `ParamField` do módulo, em seções (Energia, Eixo x, Estilo, Spin, Projeções…).
4. **Exportar** (`Ctrl+E`) salva em `plots/` da simulação.

Pastas já plotadas reabrem como estavam (a partir do `.plot`) sem salvar de novo. Com
`ui.auto_generate_plot: false`, uma pasta nunca plotada só abre o painel e **Gerar Plot** plota.

Passar o mouse mostra os valores sob o cursor na barra do gráfico (k e energia com o ponto de alta simetria mais
próximo, PDOS, passo do relax, iteração do SCF). Zoom/pan da barra atualizam a janela de energia.

## Ajustes persistentes (`.plot`)

Os ajustes ficam em `<tipo>.plot` (por exemplo `bands.plot`) em `<simulação>/plots/` e voltam na próxima vez.
**Restaurar padrões** apaga o arquivo. Um `.plot` antigo na pasta da simulação não é mais lido.

## Estilos { #estilos }

O visual de um gráfico novo (tamanho, largura de linha, cores, fundo, legenda) vem do **estilo** escolhido em
**Estilo do gráfico** (primeiro campo da seção Estilo). Cada estilo é um YAML em
`src/qe_studio/resources/templates/plot_styles/`; `padrao.yaml` é o padrão. Para criar um, copie-o com outro nome,
defina `name:` e mantenha só os campos que mudam:

```yaml
lain_style: 1
name: Escuro
params:
  background: "#111827"
  valence_color: "#facc15"
  orbital_colors: {s: "#f97316"}   # somado ao mapa do padrão, não substitui
```

Um estilo novo aparece após **Recarregar config.yaml** (ou na próxima partida). O Lain só **lê** estilos.

!!! info "Figuras independem do tema do app"
    O estilo vem dos parâmetros (`core/plotting/style.py:figure_style`), nunca do tema escuro/claro, para que prévia e
    exportação sejam idênticas. O fundo padrão é branco.

## Exportação

- Formatos: `plot.export.formats` (`png`, `svg`, `pdf`) e DPI `plot.export.dpi` (300/600).
- Nome: `<projeto>-<pastas>-<gráfico>.png` (caminho desde a raiz); em Bandas, PDOS e Bandas + DOS há também um `.csv`
  dos dados plotados (separador `;` e vírgula decimal, para Excel/Origin em pt-BR).
- Um arquivo existente nunca é substituído sem perguntar.
- Gráfico de pasta remota: cópia em `tmp_remote/`, exportações em `tmp_remote/plots_remote/`.

Código: `core/calculations/*` (módulos), `core/plotting/*` (estilo, exportação, sessão), `ui/plot/*`.
Para criar um tipo novo: [Mapa do código](../code-map.md#adicionar-um-grafico).
