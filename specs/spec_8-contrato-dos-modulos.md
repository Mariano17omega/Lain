# Spec 8: Contrato dos módulos de cálculo, tipagem e painel de ajustes

| | |
|---|---|
| **Prioridade** | 8 (base mínima: deixa barato o módulo novo das specs 9 e 13) |
| **Status** | Implementada, falta o primeiro run do CI com o `pyright` |
| **Depende de** | spec 7 (o pyright entra no CI) |
| **Usada por** | spec 9 (SCF), spec 10 (`format_coordinates`), spec 13 (spin), spec 15 (`PlotWorkflow`) |
| **Esforço** | M |

## Itens de origem (`report.md`)

> **A3. Contrato do módulo vaza para a UI** (quebra "módulo novo sem código de UI"): `plot_session.py` `reset_view`/`apply_limits` com `if kind == …`; `plot_params.py:420` lista fixa de nomes que forçam `refresh_values`; `plot_file.py:139-147` validação por heurística de nome; `main_window.py:738-740` rótulos legados só para `kind == "bands"`. → Hooks no `CalculationModule` (`apply_limits`, `reset_fields`, `legacy_params`) e flags no `ParamField` (`refreshes=True`; validar por `kind == "color"`). Módulo novo passa a ser 1 arquivo + registro.
>
> **A4. Tipagem frouxa**: `PlotSession.params/dataset: Any`, `render(...)` sem tipos. → `CalculationModule(Generic[D, P])` + pyright no dev group.
>
> **O6.** `ParamsPanel.bind` **reconstrói todos os widgets** a cada troca de aba e perde estado das seções. → Um painel por sessão em `QStackedWidget`, ou reuso + `refresh_values`.

O CLAUDE.md promete (NFR §7): "Adding a calculation type: subclass `CalculationModule`, register it
[…] no UI code is needed for new fields". A spec 6 (relax) teve de mexer em `plot_session.py` e no
`main_window.py`. As specs 9 e 13 vão criar ou estender módulos, então este contrato vem antes delas.

## Situação atual

**Vazamentos do contrato (o `kind` ou nomes de campos aparecem fora do módulo):**
- `ui/plot_session.py:59-63`: `reset_view` restaura uma lista fixa
  `("emin", "emax", "xmin", "xmax", "dos_max")` via `hasattr`.
- `ui/plot_session.py:65-77`: `apply_limits` ramifica em `kind == "bands" / "pdos" / "relax"`. Trabalha
  junto com `ui/widgets/plot_view.py:212-216`, que sempre lê `figure.axes[0]`.
- `ui/widgets/plot_params.py:420`: `if name in ("reference", "shift_to_fermi", "fermi_source",
  "grouping", "background"): self.refresh_values()`. Os nomes são de bandas, de PDOS e comuns.
- `ui/widgets/plot_params.py`, campo `"series"`:
  - assume `module.series_colors(...)`, que só existe em `PdosModule` (`core/calculations/pdos.py:277`)
    e não na base;
  - assume `params.hidden_series` / `params.series_colors` e emite o nome fixo `"series_colors"`
    (l.346-351, 403-408).
- `ui/widgets/plot_params.py`, outros acoplamentos:
  - o campo `"labels"` lê `getattr(session.dataset, "labels", [])` (l.356);
  - `session.dataset.warnings` é assumido (l.273);
  - `if title == "Exportar"` acrescenta o botão "Salvar em plots/" (l.209).
- `core/plotting/plot_file.py:139-147`: `_valid_value` valida cor por nome
  (`name == "background" or name.endswith("color")`, `name.endswith("_colors")`). Só o `"choice"` usa o
  schema.
- `ui/main_window.py:737-740`: rótulos k legados do `FolderMemory` só para `result.kind == "bands"`.
- `ui/main_window.py:681-684`: texto fixo "Para plotar bandas, PDOS ou relaxamento, indique os
  arquivos.".
- `core/calculations/params.py:10-19`: `SECTIONS` é uma tupla global com seções de módulos específicos
  ("Relaxamento", "Projeções").
- `ui/painting.py:10`: `BADGE_KINDS = {"BANDS": "bands", …}`, mais tokens `badge_<kind>_*` em
  `ui/resources/themes/{dark,light}.yaml`. Um badge novo sem token não tem cor.

**Tipagem:**
- `ui/plot_session.py:21-23`: `dataset: Any`, `params: Any`, `defaults: Any`.
- `core/calculations/base.py:264-283`:
  - `render(self, figure: Figure, dataset: Any, params: Any, style: Any) -> Any`, embora toda
    implementação devolva `RenderInfo`;
  - `default_params`, `param_schema -> list`, `param_changed`, `export_stem`, `load` e `load_cached`
    também usam `Any`.
- Não há pyright nem mypy no projeto. O ruff não seleciona `ANN`.

**Painel de ajustes (`ParamsPanel.bind`, `plot_params.py:187-222`):**
- monta um corpo novo a cada chamada e `_set_body` apaga o anterior;
- as `Section`s começam abertas (l.68), e "Arquivos" é forçada a fechar (l.301). Nem o estado de
  abertura nem a rolagem são guardados;
- `bind` roda até 3 vezes ao gerar um gráfico: `workspace.add` (`main_window.py:752`) dispara
  `currentChanged` → `_on_tab_changed` faz `bind`; `_on_loaded` faz `bind` de novo (l.754); e, ao
  regerar uma aba aberta, `close_key` (l.747) provoca o terceiro;
- `SeriesList.rebuild` recria todas as linhas a cada `refresh_values` (l.232).

## Requisitos

### R1: Hooks de visualização no `CalculationModule`
1. `view_fields: ClassVar[tuple[str, ...]]`: campos que o Reset da barra do gráfico restaura. Padrão
   `()`. `PlotSession.reset_view` copia só esses campos de `defaults`. Bandas:
   `("emin", "emax", "xmin", "xmax")`; PDOS: `("emin", "emax", "dos_max")`; relax: `("xmin", "xmax")`.
2. `apply_limits(params, axes_limits: list[tuple[xlim, ylim]]) -> None`: grava pan/zoom nos parâmetros.
   Recebe os limites de **todos** os eixos da figura, e não só de `axes[0]`, por causa das figuras com
   painéis lado a lado da spec 13. Padrão: não faz nada. O código de `plot_session.py:65-77` passa para
   os módulos bands, pdos e relax.
3. `legacy_params(params, folder, memory) -> None`: aplica dados antigos do `FolderMemory` quando não há
   `<kind>.plot`. Padrão: nada. As bandas usam para os rótulos k (`main_window.py:737-740` sai do
   `MainWindow`).
4. `format_coordinates(x, y, axes_index, dataset, params) -> str`: texto das coordenadas do cursor
   (usado pela spec 10). Padrão: `"x = {x:.4g} · y = {y:.4g}"`.
5. `series_colors(dataset, params, style) -> dict[str, str]` declarado na base (padrão `{}`). O campo
   `"series"` funciona com qualquer módulo que o implemente.

### R2: Metadados do schema no `ParamField`
1. `refreshes: bool = False`: depois de editar o campo, o painel chama `refresh_values()`. Marcar
   `reference` (bandas), `shift_to_fermi`, `fermi_source` e `grouping` (PDOS) e `background` (comum).
   Some a lista de `plot_params.py:420`.
2. `plot_file._valid_value` valida pelo `kind` do campo: `"color"` aceita cor válida (ou `""` quando o
   padrão é `""`); `"series"` valida as cores do dicionário; `"choice"` continua como está. Some a
   heurística por nome.
3. Seções:
   - `SECTIONS` passa a conter só as seções comuns, na ordem atual ("Energia", "Eixo X", "Estilo",
     "Legenda", "Figura", "Exportar");
   - o módulo declara as suas em `sections: ClassVar[tuple[tuple[str, str | None], ...]]` como pares
     (nome, inserir antes de). Exemplos: relax `("Relaxamento", "Estilo")`, PDOS `("Projeções", "Legenda")`;
   - a ordem final é calculada por `ordered_sections(module)` em `core/calculations/params.py`.
4. O botão "Salvar em plots/" passa a ser acrescentado pela seção marcada como `export=True` na
   definição de seções, e não pelo título "Exportar".

### R3: Dataset e mensagens sem acoplamento
1. Protocolo `Dataset` (`folder: Path`, `warnings: list[str]`) em `core/calculations/base.py`. O painel lê
   os avisos por ele.
2. O campo `"labels"` recebe os rótulos padrão de um hook `default_labels(dataset) -> list[str]`, e não
   de `getattr(dataset, "labels")`.
3. A mensagem de `_map_manually` (`main_window.py:681-684`) é montada com os `display_name` dos módulos
   plotáveis do `REGISTRY`, em minúsculas e unidos por vírgula e "ou".
4. Badges: `CalculationModule.badge_token: ClassVar[str | None] = None`. Sem token próprio, o badge usa os
   tokens genéricos `badge_other_*`, novos nos dois temas. Assim, um módulo novo aparece com cor sem
   editar `painting.py` nem os YAML de tema.

### R4: Tipagem
1. `CalculationModule(Generic[D, P])`, com `D` = dataset e `P` = parâmetros (`P` limitado a
   `CommonParams`). Assinaturas tipadas: `load(...) -> D`, `default_params(config: AppConfig, dataset: D)
   -> P`, `param_schema(dataset: D) -> list[ParamField]`, `render(figure, dataset: D, params: P, style:
   PlotStyle) -> RenderInfo`, `export_stem(params: P) -> str`.
2. `PlotSession` genérico em `D`/`P`. `dataset`, `params` e `defaults` deixam de ser `Any`.
3. Módulos de detecção pura (SCF/CALC enquanto não forem plotáveis) herdam
   `CalculationModule[None, CommonParams]`.
4. `pyright` no grupo dev, em modo `basic`, com `[tool.pyright]` no `pyproject.toml` cobrindo `src/`.
   Passo `uv run pyright` no CI (spec 7). PyQt6 traz stubs, e o matplotlib também.
5. Erros pré-existentes que não forem triviais entram numa lista de exclusão documentada no
   `pyproject.toml` e com prazo de saída. A meta é zero erros em `core/calculations/` e
   `ui/plot_session.py`.

### R5: Painel de ajustes por sessão (O6)
1. `ParamsPanel` mantém um `QStackedWidget` com um corpo por sessão aberta (chave = `session.key`).
   Trocar de aba só mostra o corpo existente e chama `refresh_values()`.
2. O corpo é destruído quando a aba do gráfico fecha (`Workspace.tab_closing`) e reconstruído quando o
   schema muda (por exemplo, `param_schema` depende do dataset e o gráfico foi regerado).
3. O estado aberto/fechado de cada `Section` é guardado por `(kind, título)` em QSettings
   (`params/sections/<kind>/<título>`) e reaplicado ao construir um corpo.
4. `bind` roda **uma vez** por geração de gráfico: o `MainWindow` deixa de chamar `bind` em `_on_loaded`
   quando `workspace.add` já disparou `_on_tab_changed`. Alternativa: `bind` é idempotente para a mesma
   sessão.
5. `SeriesList` atualiza as linhas existentes (cor, visível) em vez de recriá-las, quando o conjunto de
   séries não mudou.

## Fora de escopo
- Mudar o formato do `<kind>.plot`. Os nomes dos campos não mudam, então os arquivos existentes
  continuam válidos.
- Plugins externos (módulos fora do pacote).
- `mypy` ou modo `strict` do pyright.

## Decisões assumidas (confirmar na revisão)
1. Pyright em modo `basic` (R4.4), e não `standard`/`strict`, para não travar a spec em ajustes de tipo
   do PyQt.
2. O estado das seções é por tipo de gráfico, e não por pasta (R5.3).
3. `apply_limits` recebe todos os eixos (R1.2). `PlotView._on_release` muda para coletar a lista.
4. O texto de `_map_manually` gerado do registro (R3.3) pode mudar a redação atual (ex.: "estrutura de
   bandas, densidade de estados projetada ou otimização estrutural").

## Resultado da implementação
Feito e verificado localmente: `ruff`, `pyright` (0 erros) e 458 testes passam; o teste de latência
(`-m perf`) também. Falta o primeiro run do GitHub Actions com o passo `uv run pyright`.

Diferenças em relação ao texto da spec:
- **R2.3, relax:** `sections = (("Relaxamento", "Eixo X"),)`, e não "Estilo", para manter a ordem que o
  painel já tinha (hoje "Relaxamento" vem antes de "Eixo X"). Um módulo com `before=None` (ou um nome
  que não existe) fica logo antes da seção de exportação, que continua sendo a última.
- **R2.2, validação do `.plot`:** `total_color` e `orbital_colors` da PDOS não têm campo no schema, então
  a validação só por `kind` deixaria de proteger o `render` contra um `.plot` editado à mão. Eles passam a
  declarar `field(metadata={"kind": "color" | "colors"})` na dataclass, e o `plot_file` usa isso quando o
  schema não diz nada. As cores do campo `"series"` vêm de `ParamField.colors` (nome do parâmetro com os
  overrides, `"series_colors"` na PDOS), que o painel também usa no lugar do nome fixo.
- **R1.2:** o `PlotView` agora observa os limites de **todos** os eixos. No relax, o zoom em Y no painel
  de baixo passa a disparar `limits_changed` (e uma gravação do `relax.plot` sem mudança de valores). A
  spec 13 pode refinar isso.
- **R3.4:** `paint_badge` recebe o `badge_token` do módulo (`DetectionResult.badge_token`) e cai em
  `badge_other_*` também quando o tema não tem o token. `ThemeManager.has_color` é novo.
- **R4.5:** o `pyright` começou com 168 erros, quase todos retornos `Optional` do PyQt. Zero erros em
  `core/calculations/`, `core/plotting/` e `ui/plot_session.py`; 10 arquivos ficam na lista `ignore` de
  `[tool.pyright]`, que deve esvaziar até a spec 15. `set_variant` e `PanelHeader.add_button` agora são
  genéricos (devolvem o tipo recebido), o que eliminou mais de 60 erros.
- **R5.1:** o painel guarda cada corpo num `QScrollArea` próprio dentro do `QStackedWidget`, então a
  rolagem também é mantida. `ParamsPanel.bind` já chama `refresh_values()`, e o `MainWindow` não chama mais
  `bind` em `_on_loaded` (a aba nova já faz isso). O corpo é reconstruído quando a sessão é outra ou
  quando `param_schema` mudou.
- **Testes:** `ParamsPanel.set_param(name, value)` (edição como se fosse pelo widget) substitui o uso do
  `ParamsPanel._set` nos testes. As chamadas de `apply_limits` e de `apply_stored` passam a usar a nova
  assinatura e o schema completo.

## Notas de implementação
- Alterados:
  - `core/calculations/base.py`, `core/calculations/params.py`;
  - `core/calculations/{bands,pdos,relax}.py`;
  - `core/plotting/plot_file.py`;
  - `ui/plot_session.py`, `ui/widgets/plot_params.py`, `ui/widgets/plot_view.py`;
  - `ui/main_window.py`, `ui/painting.py`;
  - `ui/resources/themes/{dark,light}.yaml` (`badge_other_*`);
  - `pyproject.toml`, `.github/workflows/ci.yml`;
  - `CLAUDE.md` (seção "Adding a calculation type": lista dos hooks).
- `RenderInfo` continua como está. Só passa a ser o tipo de retorno declarado.

## Critérios de aceite e testes
- [x] `tests/test_module_contract.py`: um módulo fictício `DummyModule` (1 papel, 1 parâmetro `color`,
      seção própria "Teste", `view_fields`, `apply_limits`) registrado num `REGISTRY` de teste é
      detectado, carregado, plotado, editado no painel, salvo em `dummy.plot` e exportado. Nenhum
      arquivo de `ui/` menciona `dummy`.
- [x] `grep -rnE 'kind == "(bands|pdos|relax)"' src/qe_studio/ui` não encontra nada.
- [x] `plot_file`: uma cor inválida num campo `color` é ignorada com aviso, e um campo `text` cujo nome
      termina em `color` deixa de ser validado como cor.
- [x] Os testes atuais de pan/zoom e Reset (bandas, PDOS e relax) passam sem mudança de comportamento.
- [x] Gerar um gráfico chama `ParamsPanel.bind` exatamente uma vez (contador em teste).
- [x] Trocar entre duas abas de gráfico não recria widgets (mesmo `id` do corpo) e mantém uma seção
      fechada como fechada.
- [ ] `uv run pyright` passa no CI (passa localmente; falta o primeiro run do Actions).
