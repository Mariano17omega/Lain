# Spec 3: Persistência de estado entre execuções

| | |
|---|---|
| **Prioridade** | 3 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 1 (larguras de trabalho dos painéis), spec 2 (`background` entra nos parâmetros salvos) |
| **Usada por** | spec 6 (`relax.plot`) |
| **Esforço** | M |

## Itens de origem (`Ideias.md`)

> - Atualmente, quando fecha o programa, todas as informações do programa são perdidas. O usuário pode abrir a mesma pasta novamente e o programa não guarda nenhuma informação sobre o estado anterior. Quero que as mudanças em runtime que o usuario fizer sejam persistidas após fechar o app.
> - As informações que quero que pesistam são:
>   - Possição dos divisores verticais das abas.
>   - As mudanças de parametros feitas na aba de configuraçõe de plot (AJUSTE DO GRÁFICO). Deve ser salvos as configurações de plot em um arquivo .plot na pasta da simulação, de forma que quando abrir a past novamente, o programa vai carregar as ultimas configurações de plot usadas na simulação.

Decisão confirmada: **um arquivo por tipo de cálculo** na pasta da simulação: `bands.plot`,
`pdos.plot` e `relax.plot` (spec 6), em YAML.

## Situação atual

- Já persistidos via `QSettings` (`src/qe_studio/ui/main_window.py:238-253`): geometria da janela
  (`window/geometry`), tamanhos do splitter (`window/splitter`), visibilidade da grade
  (`window/grid_visible`) e tema (`ui/theme`).
- Problema dos divisores: `window/splitter` grava `QSplitter.sizes()`, que devolve **0** para painéis
  ocultos. Fechar o app com um painel oculto grava um zero, e na próxima execução esse painel reaparece
  espremido ou com tamanho arbitrário. Somado ao comportamento da spec 1, a posição dos divisores
  parece "perdida".
- Parâmetros do gráfico não são persistidos: `MainWindow._on_loaded` (`main_window.py:467`) sempre
  cria `module.default_params(config, dataset)`. A única exceção são os rótulos de pontos k das
  bandas, guardados em `FolderMemory` (`src/qe_studio/core/detection.py:58`, fora da pasta da simulação)
  e reaplicados em `main_window.py:468-470`.
- Parâmetros são dataclasses (`BandsParams`, `PdosParams`, que estendem `CommonParams` de
  `core/calculations/params.py`) com campos `float`, `int`, `bool`, `str`, `float | None`,
  `list[str]` (`hidden_series`) e `dict[str, str]` (`series_colors`, `orbital_colors`).

## Requisitos

### R1: Posição dos divisores
1. Persistir as **larguras de trabalho** de cada painel mantidas pela spec 1 (`_panel_widths`:
   `tree`, `grid`, `workspace`) na chave `layout/panel_widths`, e não `sizes()` cru.
2. Persistir a visibilidade de árvore e grade (`layout/tree_visible`, `layout/grid_visible`). O
   workspace sempre inicia oculto (spec 1 R1).
3. Na inicialização, aplicar as larguras restauradas respeitando os mínimos dos painéis e a largura
   atual da janela (proporção da spec 1 R3).
4. Migração: se só existir a chave antiga `window/splitter`, usá-la apenas quando não tiver zeros.
   Depois, removê-la.
5. Gravar ao fechar a janela (como hoje em `_save_state`).

### R2: Arquivo `<tipo>.plot` na pasta da simulação
1. **Nome e local:** `<pasta da simulação>/<kind>.plot`, onde `kind` é o `CalculationModule.kind`
   (`bands.plot`, `pdos.plot`, depois `relax.plot`). A pasta é `PlotSession.folder`, a mesma usada
   para `plots/`.
2. **Formato** (YAML, legível e editável à mão):
   ```yaml
   # Lain: ajustes do gráfico. Gerado automaticamente; apague para voltar aos padrões.
   lain_plot: 1          # versão do formato
   kind: bands
   params:
     reference: fermi
     emin: -6.0
     emax: 4.0
     xmin: null
     labels: "W, G, X, K, G"
     valence_color: "#2563eb"
     background: "#ffffff"
     # ... todos os campos do dataclass de parâmetros
   ```
3. **Quando grava:**
   - só depois da **primeira alteração feita pelo usuário** naquele gráfico: edição no painel de
     ajustes (`ParamsPanel.changed`) ou pan/zoom (`PlotView.limits_changed`). Só gerar um gráfico não
     cria o arquivo;
   - com debounce de ~1 s após a última alteração;
   - imediatamente (flush) ao fechar a aba do gráfico, ao regerar o mesmo gráfico e ao fechar o app;
   - de forma atômica, reutilizando `core/appdirs.atomic_write_text` (arquivo temporário + `os.replace`).
4. **Quando lê:** ao gerar o gráfico daquela pasta e tipo. A leitura ocorre **no worker** (`_LoadTask`,
   junto com `load_cached`), nunca na thread da GUI. Os valores válidos são aplicados sobre
   `default_params(config, dataset)`.
5. **Validação na leitura:**
   - `lain_plot` desconhecido ou `kind` diferente do arquivo: ignora o arquivo inteiro e mostra aviso
     no rodapé;
   - YAML inválido ou ilegível: usa os padrões e mostra o aviso "bands.plot inválido; usando ajustes
     padrão.";
   - campo desconhecido: ignorado (log em nível debug);
   - campo com tipo incompatível com o padrão do dataclass: ignorado (log warning). `int` é aceito
     onde se espera `float`. `null` só é aceito em campos opcionais.
6. **Falha de escrita** (pasta somente leitura, disco cheio): aviso no rodapé uma vez por sessão e
   gráfico, sem diálogo modal e sem interromper o uso.
7. **Reset e padrões:**
   - `PlotSession.defaults` continua sendo o padrão do módulo, calculado **antes** de aplicar o
     `.plot`. O botão "Reset" da barra do gráfico volta os limites ao automático, como hoje.
   - Novo botão **"Restaurar padrões"** no painel de ajustes (seção Exportar ou rodapé do painel):
     pede confirmação, volta todos os parâmetros ao padrão e apaga o `.plot`.
8. **Rótulos k (bandas):** o campo `labels` passa a ser persistido no `bands.plot`. `FolderMemory.labels`
   vira fallback somente leitura, usado quando não existe `bands.plot` (migração). Novas edições não
   gravam mais em `FolderMemory`.

### R3: Integração com o restante do app
1. **Detecção:** adicionar `.plot` a `SKIP_SUFFIXES` (`src/qe_studio/core/sniff.py:27`) para o sniff
   não ler esses arquivos.
2. **Visualização:** `.plot` entra em `TEXT_SUFFIXES` (`src/qe_studio/ui/file_types.py:9`), abre no
   visualizador de texto (somente leitura) e ganha ícone próprio (`tune`, token `icon_other`) em
   `_VISUALS`.
3. **Sincronização:** o sync é só pull e não usa `--delete`. Arquivos que existem só localmente não
   participam do plano (`src/qe_studio/core/sync/planner.py`, docstring). Um `.plot` local nunca
   bloqueia um pull nem é apagado. Se o cluster tiver um `.plot` com o mesmo nome, o fluxo normal de
   conflito (PRD §5.4) pergunta antes de sobrescrever.
4. **Exportação:** nada muda. `plots/` continua recebendo só as figuras.

## Fora de escopo
- Restaurar abas abertas, gráfico ativo ou posição de rolagem.
- Guardar os `.plot` fora da pasta da simulação.
- Histórico/versões de ajustes.

## Extras propostos (confirmar na revisão: incluir ou não)
Usam o mesmo `QSettings` e custam pouco. Atendem ao "mudanças em runtime persistidas":
- [ ] modo da grade (grade/lista) e ordenação (nome/tamanho/data) do `FilePanel`;
- [ ] última pasta selecionada na árvore, reaberta ao iniciar se ainda existir dentro de `local_root`;
- [ ] modo do painel esquerdo (árvore/ajustes).

## Decisões assumidas (confirmar na revisão)
1. O `.plot` guarda **todos** os campos do dataclass, não só os alterados. Consequência: mudar o
   `config.yaml` depois não afeta pastas que já têm `.plot`, e "Restaurar padrões" resolve isso.
2. Limites de energia em modo "Absoluta" ficam gravados como números absolutos. Se a simulação for
   refeita com outro E_F, os limites podem ficar deslocados, e o "Reset" corrige.
3. Cores de séries PDOS que não existem mais no dataset são mantidas no arquivo e ignoradas no desenho.
4. Gravação na thread da GUI é aceitável (arquivo de poucos KB). A leitura é no worker.

## Notas de implementação
- Novo módulo sem Qt: `src/qe_studio/core/plotting/plot_file.py` (ou `core/calculations/plot_file.py`)
  - `plot_file_path(folder, kind) -> Path`
  - `read_plot_file(folder, kind) -> dict | None` e `apply_stored(params, data) -> list[str]`
    (validação campo a campo usando `dataclasses.fields` e o tipo do valor padrão; devolve avisos)
  - `write_plot_file(folder, kind, params) -> None` (`dataclasses.asdict` + `yaml.safe_dump`,
    `sort_keys=False`, `allow_unicode=True`)
- `MainWindow`: `_LoadTask.run` também lê o `.plot` e emite `loaded(result, dataset, stored)`.
  `_on_loaded` monta `params = default_params(...)`, cria o `PlotSession` (defaults) e só depois
  aplica `stored`. Um `QTimer` single-shot de debounce por sessão (ou um único, com o conjunto de
  sessões "sujas") grava via `write_plot_file`. `closeEvent` e `Workspace.close_tab` fazem flush.
- `PlotSession` ganha `dirty: bool`, marcado em `_on_param_changed` e em `limits_changed`.
- Divisores: `_save_state` / `_restore_state` (`main_window.py:238-253`) passam a usar `_panel_widths`
  (spec 1).

## Critérios de aceite e testes
- [ ] `tests/test_plot_file.py` (core, headless): round trip `write` → `read` → `apply_stored` para
      `BandsParams` e `PdosParams`, incluindo `None`, listas e dicts; campo desconhecido ignorado;
      tipo errado ignorado com aviso; `kind` trocado → arquivo ignorado; YAML corrompido → `None` + aviso.
- [ ] `tests/test_plot_workflow.py`: gerar bandas sem mexer em nada não cria `bands.plot`. Alterar
      `emin` cria o arquivo após o debounce (`qtbot.waitUntil`). Fechar a aba, gerar de novo e o
      `emin` alterado volta. "Restaurar padrões" apaga o arquivo.
- [ ] Pan/zoom marca a sessão como alterada e grava `xmin/xmax/emin/emax`.
- [ ] Pasta somente leitura (`chmod`): alterar parâmetro gera aviso no rodapé e nenhuma exceção.
- [ ] O detector ignora `bands.plot` (o sniff devolve `UNKNOWN` sem ler) e o badge da pasta não muda.
- [ ] Divisores: criar `MainWindow`, ajustar larguras, fechar, criar outro `MainWindow` com o mesmo
      `QSettings` → larguras restauradas (±2 px) e workspace oculto. Com `window/splitter` antigo
      contendo zero, ele é ignorado.
- [ ] Atualizar `test_typed_labels_are_remembered` (rótulos agora vêm do `bands.plot`) e
      `test_close_saves_state`.
- [ ] Nenhum teste escreve em `tests/fixtures/` (usar `copy_fixture` / `demo_project`).
