# Spec 2: Fundo das figuras

| | |
|---|---|
| **Prioridade** | 2 (afeta todas as figuras exportadas; pré-requisito das specs 3 e 6) |
| **Status** | Rascunho para revisão |
| **Depende de** | nenhuma |
| **Usada por** | spec 3 (o parâmetro novo é persistido), spec 6 (gráficos de relax usam o mesmo estilo) |
| **Esforço** | P |

## Itens de origem (`Ideias.md`)

> - O fundo das figuras de grafico geradas no plot possuem fundo transparente. Quero que o fundo seja branco. Atualmente quando o tema é escuro, o fundo da imagem é transparente, aparecendo aparecendo um fundo escuro no tema escuro e um fundo brando no tema claro. Deixe o fundo sempre branco, tanto no tema escuro quanto no tema claro.
> - Adicione um novo parametro na aba "Ajustes" que permite ao usuario escolher a cor de fundo do gráfico, o padrão é fundo branco.

## Situação atual

O fundo não é transparente: **a figura inteira segue o tema do app**.
- `src/qe_studio/core/plotting/style.py:81` define o `PlotStyle` DARK com `figure_bg`/`axes_bg`
  `#0f1216` e texto claro; o `LIGHT` (`style.py:94`) tem fundo `#ffffff` e texto escuro.
- O preview usa o estilo do tema atual: `PlotView.render` → `self.theme.plot_style`
  (`src/qe_studio/ui/widgets/plot_view.py:193`, que chama `style_for(theme.name)`).
- A exportação usa `plot.export.theme` do `config.yaml` (padrão `current`, que segue o tema do app):
  `MainWindow.export_plot` (`src/qe_studio/ui/main_window.py:553`). Com o tema escuro, os PNG/SVG/PDF
  saem com fundo `#0f1216` e texto claro.
- Cores automáticas também dependem do tema: paleta das projeções PDOS (`style.palette`,
  `core/calculations/pdos.py:290`), cor da DOS total (`style.total_dos`, `pdos.py:328`) e linhas-guia
  (`style.guide`, `bands.py:419`, `pdos.py:341`).
- `ParamsPanel._rebuild_series` (`src/qe_studio/ui/widgets/plot_params.py:390`) monta as amostras de cor
  das séries PDOS com `self.theme.plot_style`.

## Requisitos

### R1: A figura não depende mais do tema do app
1. Preview e exportação usam o **mesmo** estilo, derivado só dos parâmetros do gráfico (R2), e nunca
   do tema claro/escuro da interface.
2. Padrão: fundo `#ffffff` com o estilo LIGHT (texto, eixos, grade e guias escuros), nos dois temas.
3. Alternar o tema (Ctrl+T) não altera a figura. A moldura ao redor do canvas (`#plotCard` /
   `#plotFrame`, estilizados por QSS) continua seguindo o tema.
4. Arquivos exportados nunca têm fundo transparente: `savefig` recebe a cor de fundo explicitamente,
   como já faz em `core/plotting/export.py:68`.

### R2: Parâmetro "Cor de fundo"
1. Novo campo em `CommonParams` (`src/qe_studio/core/calculations/params.py:31`):
   `background: str = "#ffffff"`. Assim ele vale para bandas, PDOS e, depois, relax (spec 6).
2. Novo `ParamField("background", "Cor de fundo", "Figura", "color")` em `COMMON_FIELDS`. Ele aparece
   na seção **Figura** do painel "Ajuste do gráfico" com amostra de cor e campo hex, que são os widgets
   já existentes para `kind == "color"`.
3. A cor se aplica ao fundo da figura (`figure.facecolor`) e ao fundo dos eixos (`axes.facecolor`),
   além do fundo da legenda.
4. Alterar a cor re-renderiza o preview (fluxo atual de `ParamsPanel.changed` → `_render_timer`).

### R3: Contraste automático
1. Se a cor de fundo for escura (luminância relativa < 0,5), texto, eixos, grade, guias, paleta
   automática e cor da DOS total vêm do estilo DARK. Caso contrário, vêm do estilo LIGHT.
2. Cores escolhidas pelo usuário ou vindas do config (bandas de valência/condução, E_F, orbitais,
   cores sobrescritas de séries PDOS) não mudam.
3. As amostras de cor das séries no painel (`_rebuild_series`) usam o mesmo estilo da figura.

### R4: Padrão configurável no `config.yaml`
1. Nova chave `plot.background` (tipo `Color`, validada como as outras cores), padrão `"#ffffff"`, em
   `PlotConfig` (`src/qe_studio/core/config.py:136`).
2. `apply_common_config` (`params.py:62`) copia `plot.background` para `params.background`.
3. Documentar a chave em `config.example.yaml` (seção `plot:`).

### R5: Descontinuar `plot.export.theme`
1. A chave perde o efeito. Continua **aceita** pelo validador, porque `_Section` usa
   `extra="forbid"` e configs existentes quebrariam.
2. Se o arquivo contiver `plot.export.theme` (o pydantic indica isso em
   `ExportConfig.model_fields_set`), `LoadedConfig.warnings` ganha a mensagem: "plot.export.theme foi descontinuado: as figuras usam plot.background (padrão
   branco)."
3. Remover a chave de `config.example.yaml` e a lógica de `export_plot` (`main_window.py:553-554`).

## Fora de escopo
- Fundo transparente como opção de exportação.
- Temas de figura nomeados, além de claro/escuro automático pela cor de fundo.
- Mudar as cores padrão de bandas e orbitais.

## Decisões assumidas (confirmar na revisão)
1. O contraste automático (R3) inclui a paleta das projeções PDOS: num fundo escuro a paleta automática
   passa a ser a do estilo DARK. A alternativa seria manter sempre a paleta LIGHT.
2. ~~O limiar de "escuro" é luminância relativa < 0,5~~. Implementado: escolhe-se o estilo (LIGHT ou
   DARK) cujo texto tem o maior contraste WCAG com o fundo. Dá o mesmo resultado para branco, preto e
   `#123456`; em tons médios (ex.: `#808080`) mantém o texto escuro, que fica mais legível.
3. O "Reset" da barra do gráfico continua restaurando só os limites dos eixos, sem mexer na cor de fundo.
4. `ThemeManager.plot_style` deixa de ser usado para figuras e pode ser removido se ficar sem uso.

## Notas de implementação
- `src/qe_studio/core/plotting/style.py`: nova função `figure_style(background: str) -> PlotStyle`,
  que escolhe `LIGHT` ou `DARK` pela luminância e aplica `dataclasses.replace(base, figure_bg=background,
  axes_bg=background)`. O `rc()` já propaga `figure_bg`/`axes_bg` para `figure.facecolor`,
  `savefig.facecolor`, `axes.facecolor` e `legend.facecolor`.
- Pontos que passam a chamar `figure_style(params.background)`: `PlotView.render` (`plot_view.py:193`),
  `MainWindow.export_plot` (`main_window.py:553`), `ParamsPanel._rebuild_series` (`plot_params.py:395`).
  Com isso `PlotView` não precisa re-renderizar em `theme_changed`. Manter a conexão só se a moldura
  precisar.
- `core/plotting/draw.py:new_axes` já aplica `style.figure_bg`/`style.axes_bg`. Não precisa mudar.
- `scripts/screenshot.py --plot` deve continuar gerando os PNGs dos dois temas. A figura sai branca
  nos dois.

## Critérios de aceite e testes
- [ ] `tests/test_plotting.py`: `figure_style("#ffffff")` tem texto escuro e `figure_style("#000000")`
      tem texto claro. A cor de fundo é aplicada a figura e eixos.
- [ ] Exportação com o app no tema escuro gera PNG cujo pixel do canto é branco (ler com
      `matplotlib.image.imread`).
- [ ] Mudar `params.background` para `#123456` e exportar: o pixel do canto é `#123456`, e o SVG
      contém o `fill` correspondente.
- [ ] `tests/test_plot_workflow.py`: com o gráfico aberto, alternar o tema mantém `figure.get_facecolor()`
      branco. Substituir `test_theme_toggle_rerenders_plot`.
- [ ] O painel mostra "Cor de fundo" na seção Figura para bandas e PDOS, e editar o valor re-renderiza.
- [ ] `tests/test_config.py`: `plot.background` inválido gera erro de validação;
      `plot.export.theme: dark` gera aviso e não gera erro. Sem a chave, não há aviso.
- [ ] Atualizar `test_export_theme_colors` para o novo contrato.
