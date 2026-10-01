# Spec 9: Gráfico da convergência do SCF

| | |
|---|---|
| **Prioridade** | 9 (primeira feature nova; a mais pedida para depurar cálculos) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 8 (contrato do módulo), spec 5 (menu de contexto), spec 6 (padrão de painéis/escala log do relax) |
| **Usada por** | spec 12 (ordem das ações no menu de contexto) |
| **Esforço** | M |

## Itens de origem

> **F1. Convergência SCF** (`report.md` §1.1): "estimated scf accuracy" e energia por iteração; marca `convergence NOT achieved`. SCF já é detectado mas só vira badge. Debugar SCF que não converge é a tarefa mais comum em QE.

Pedido do usuário (30/09/2026):
> Plot do grafico da convergencia do SCF. Quero que quando o usuario clicar no output do scf com o botão direito no mouse, entre as opções do menu, tenha a opção 'Plotar', que irá gerar um plot. Outra forma de fazer esse plot, é quando o usuario estiver com output aberto na aba de visualização, deve aparecer um novo botão ao lado do botão 'Gerar Gráficos' um botão 'Plotar SCF'. Esse botão "Plotar SCF" só deve ficar visivel quando o output do scf estiver aberto.

## Situação atual

- `ScfModule` (`core/calculations/info.py:11-25`) é um módulo de detecção pura:
  - `fallback = True`, badge "SCF", "Cálculo SCF";
  - papel único `scf_out` (`output_of(FileKind.PW_OUT, "scf")`);
  - não é plotável.
- `pw_output.parse_pw_output` (`core/qe/pw_output.py:97-146`) só lê `converged` (achieved / NOT
  achieved). Não lê as iterações.
- Gerar gráfico numa pasta só com SCF abre o mapeamento manual com "Esta pasta foi identificada como
  SCF, que não tem gráfico próprio…" (`ui/main_window.py:676-698`).
- Menu de contexto (`ui/widgets/context_menu.py:51-62`, `ItemActions.menu`): exatamente "Abrir local de
  origem", "Abrir com", "Copiar", "Renomear". Os testes fixam a lista em
  `tests/test_file_grid_menu.py:18`.
- "Gerar Gráfico" fica na TopBar (`ui/widgets/bars.py:182-186`), sempre visível. Abrir uma saída no
  workspace cria um `TextViewer` (`ui/widgets/workspace.py:222-228`), e o caminho dele fica em
  `TextViewer.path`.
- O tipo de um arquivo já sniffado vem de `DetectionService.file_sniff` (`ui/services.py:99-100`), um
  `peek` no cache que nunca lê o disco.
- Já existe a forma de plotar arquivos escolhidos: `_Manual(module, folder, mapping, sniff)`
  (`main_window.py:82-96`), que monta o `DetectionResult` no worker.
- Formato das iterações no QE 7.x (`tests/fixtures/al_bands/al.scf.out`):
  ```
  scf convergence threshold =      1.0E-08          (l.49)
  mixing beta               =       0.7000          (l.50)
  iteration #  1     ecut=   100.00 Ry     beta= 0.70
  total energy              =      -5.03857033 Ry
  estimated scf accuracy    <       0.00554324 Ry
  ...
  iteration #  4     ecut=   100.00 Ry     beta= 0.70
  !    total energy              =      -5.03855495 Ry   (l.390: a energia da última iteração vem só aqui)
  estimated scf accuracy    <          3.7E-09 Ry
  convergence has been achieved in   4 iterations
  ```
  Com spin (`ni_pdos_spin/ni.scf.out`) cada iteração tem também `total magnetization` e
  `absolute magnetization`.
- Fixtures com SCF: `al_bands/al.scf.out` (4 iterações), `al_pdos_flat/al.scf.out` (4),
  `si_bands/si.scf.out` (7), todas do QE 7.3.1, e `ni_pdos_spin/ni.scf.out` (11, com spin, QE 6.0).

## Requisitos

### R1: Parser `core/qe/scf.py`
1. Mesmo estilo de `core/qe/relax.py`: regex linha a linha (streaming), sem ASE e sem carregar o arquivo
   inteiro. Roda no worker (`load`).
2. Por iteração, `ScfIteration`:
   - `index` (o `n` de `iteration #  n`), `ecut_ry`, `beta`;
   - `energy_ry`: o `total energy` da iteração, ou o `!    total energy` para a última;
   - `accuracy_ry` (`estimated scf accuracy <`, aceita notação `3.7E-09`);
   - `harris_ry` (opcional);
   - `total_mag`, `abs_mag` (opcionais). Na saída não colinear, `total magnetization` tem 3 componentes,
     e guarda-se o módulo;
   - `cpu_s` (`total cpu time spent up to now is`, opcional).
3. Por execução, `ScfData`:
   - `iterations`;
   - `threshold_ry` (`scf convergence threshold`), `mixing_beta`, `mixing_mode` (`plain`/`TF`/
     `local-TF` de `number of iterations used`);
   - `status`: `converged` (`convergence has been achieved in N iterations`), `not_converged`
     (`convergence NOT achieved after N iterations`) ou `running` (nenhum dos dois);
   - `n_reported` (o N da frase final), `final_energy_ry`, `job_done`, `spin`.
4. Se a saída tiver mais de um ciclo SCF (relax, vc-relax), o parser lê **só o primeiro** e registra o
   aviso "saída com N ciclos SCF; mostrando o primeiro". O caso relax fica fora de escopo (ver abaixo).
5. Uma iteração cortada (job rodando ou interrompido) é descartada e conta em `truncated`, sem exceção.

### R2: Módulo plotável
1. `ScfModule` sai de `info.py` para `core/calculations/scf.py`. Fica na mesma posição do `REGISTRY` e
   mantém `kind = "scf"`, badge "SCF", `fallback = True` e o papel `scf_out`. Passa a ter
   `plottable = True` e `display_name = "Convergência SCF"`.
2. `load(result) -> ScfDataset(folder, path, data: ScfData, warnings)`. Sem nenhuma iteração completa:
   `LoadError("Nenhuma iteração SCF completa em <arquivo>.")`.
3. Consequência na pasta: como `ScfModule` só aparece quando nenhum tipo principal foi detectado, o
   Ctrl+G / "Gerar Gráfico" numa pasta só com SCF passa a plotar a convergência, sem diálogo. A mensagem
   de `_map_manually` deixa de citar SCF (com a spec 8, ela já é gerada do registro).

### R3: Figura
1. Até três painéis empilhados, com eixo X compartilhado "Iteração SCF" (ticks inteiros, rareados acima
   de 20, como o relax):
   - **Precisão estimada (Ry)**: linha com marcadores, escala log por padrão, linha tracejada horizontal
     no `conv_thr` com legenda `conv_thr = 1.0e-08 Ry`;
   - **Energia**: |ΔE| entre iterações consecutivas (Ry, log) ou energia total (Ry, linear), escolhido em
     parâmetro;
   - **Magnetização (μB/célula)**: total e absoluta. Só existe se a saída tem magnetização.
2. Não convergido: faixa ou texto "convergência NÃO atingida" no painel de precisão, na cor de
   `threshold_color`. Em andamento: texto "em andamento".
3. Escala log com valor ≤ 0: mesmo piso de `relax.positive_for_log`.
4. Estilos e fundo vêm de `PlotStyle`/`CommonParams` (spec 2), como nos outros módulos.

### R4: Parâmetros (`ScfParams(CommonParams)`), seção "Convergência"
| Campo | Rótulo | Tipo | Padrão |
|---|---|---|---|
| `show_accuracy` | Precisão estimada | bool | `True` |
| `show_energy` | Energia | bool | `True` |
| `energy_mode` | Energia como | choice: `delta` "\|ΔE\| entre iterações", `total` "E total" | `delta` |
| `show_magnetization` | Magnetização | bool (só no schema se houver magnetização) | `True` |
| `scale` | Escala Y | choice: `log`, `linear` (vale para precisão e \|ΔE\|) | `log` |
| `show_threshold` | Limiar | bool | `True` |
| `accuracy_color`, `energy_color`, `magnetization_color`, `threshold_color` | cores | color | `#38bdf8`, `#10b981`, `#a78bfa`, `#f43f5e` |
| `xmin`, `xmax` | Iteração mín./máx. | float opcional | `None` |

- `view_fields = ("xmin", "xmax")`; `apply_limits` grava só o X (hooks da spec 8).
- Com todos os painéis desligados, a figura mostra "Nenhum painel selecionado".
- Altura padrão: `plot.figure_size` do config × (1 + 0,5 por painel extra).

### R5: Resumo do gráfico (`RenderInfo.summary`)
- `Convergiu ✓ em 4 iterações · precisão 3.7e-09 Ry (limiar 1.0e-08) · E = −5.03855495 Ry`
- `Não convergiu ✗ após 100 iterações · precisão 1.2e-05 Ry (limiar 1.0e-08)`
- `Em andamento · 12 iterações · precisão 4.1e-06 Ry`

Avisos (vários ciclos, iteração cortada, sem limiar no cabeçalho) aparecem no topo do painel de ajustes.

### R6: Item "Plotar" no menu de contexto
1. Aparece **só** para arquivos cujo sniff em cache (`file_sniff`) é `FileKind.PW_OUT` com
   `calculation == "scf"`. Fica no topo do menu, seguido de um separador e das 4 ações da spec 5.
2. Se o arquivo ainda não está no cache, o item não aparece, e o menu pede ao `DetectionService` a
   detecção da pasta. O próximo clique já mostra o item. O thread da GUI nunca lê o arquivo.
3. Ação: plota **aquele arquivo**. O `MainWindow` recebe um sinal `plot_file_requested(path, kind)` do
   `ItemActions`, monta `_Manual(ScfModule, path.parent, {"scf_out": [path]}, sniff)` e segue o fluxo
   normal de `_load`.
4. **Não** exporta para `plots/`: é uma pré-visualização, como o botão "Plot" da spec 1. Para salvar,
   o usuário usa "Salvar em plots/" / Ctrl+E.

### R7: Botão "Plotar SCF" na TopBar
1. `QPushButton("Plotar SCF")` (ícone `monitoring`, variante secundária), logo à direita de "Gerar
   Gráfico" (`bars.py:182`). Tooltip: "Plotar a convergência do SCF do arquivo aberto".
2. Visível **só** quando a aba atual do workspace é um `TextViewer` de saída SCF (mesmo critério do
   R6.1). O `MainWindow` atualiza a visibilidade em `Workspace.current_changed`, no fechamento de abas e
   quando chega uma detecção (`DetectionService.detected`) da pasta do arquivo aberto.
3. Clique: mesma ação do R6.3 com o caminho do `TextViewer`.

### R8: Aba, chave e persistência
1. Chave da aba: `plot:scf:<caminho do arquivo>` (por arquivo, não por pasta), e título
   "Convergência SCF · <nome do arquivo>". Plotar de novo o mesmo arquivo reaproveita a aba, como hoje.
2. Ajustes em `<pasta>/scf.plot` (spec 3), compartilhados pelas saídas SCF da mesma pasta.
3. `export_stem` → `scf`, com o controle de versões atual (`next_free_stem`).

## Fora de escopo
- Convergência dos ciclos SCF dentro de relax/vc-relax (escolher um passo iônico). Fica para depois. O
  relax já tem o seu gráfico (spec 6).
- Saídas do `ph.x`, do `cp.x` e de outros programas.
- Atualizar o gráfico sozinho enquanto o job roda (F10, adiado).
- Item "Plotar" para outros tipos (bandas, PDOS, relax) no menu de contexto.

## Decisões assumidas (confirmar na revisão)
1. "Plotar" e "Plotar SCF" não salvam em `plots/` (R6.4). O Ctrl+G numa pasta só com SCF continua salvando,
   como qualquer "Gerar Gráfico".
2. A energia é mostrada como |ΔE| entre iterações consecutivas por padrão (mesma convenção do relax), e
   não como |E_i − E_final|, que não existe para um job em andamento.
3. Com vários ciclos SCF no arquivo, só o primeiro é lido (R1.4).
4. Um `scf.plot` por pasta, e não por arquivo (R8.2).
5. As cores padrão seguem a paleta do relax (spec 6).

## Pendência
- **Fixture SCF não convergida (QE ≥ 7.1):** é preciso uma saída real com
  `convergence NOT achieved after N iterations: stopping`, reduzida (remover o meio das iterações e as
  listas de autovalores). Sem ela, o R1.3 `not_converged` fica testado só com texto sintético.
- **Magnetização em QE ≥ 7.1:** a única fixture com spin é a `ni.scf.out` (QE 6.0). A fixture com spin da
  spec 13 deve substituí-la nos testes deste módulo.

## Notas de implementação
- Novos: `core/qe/scf.py`, `core/calculations/scf.py`, `tests/test_scf.py`.
- Alterados:
  - `core/calculations/info.py` (sai o `ScfModule`), `core/calculations/__init__.py`;
  - `ui/widgets/context_menu.py` (item e sinal), `ui/widgets/bars.py` (botão);
  - `ui/main_window.py` (plotar arquivo, visibilidade do botão);
  - `tests/test_file_grid_menu.py` (o menu de SCF tem "Plotar"; os demais continuam com 4 ações).
- O caso de propriedade do `parse_scf` (corte aleatório nunca levanta exceção) entra em
  `tests/test_properties.py` (spec 7).
- Performance (NFR §7): parser em streaming de uma saída com 200 iterações abaixo de 500 ms, num caso
  `@pytest.mark.perf`.

## Critérios de aceite e testes
- [ ] Parser em `al_bands/al.scf.out`: 4 iterações, a última com energia −5.03855495 Ry (linha `!`),
      precisão final 3.7e-09, limiar 1.0e-08, `converged`, `job_done`.
- [ ] `si_bands/si.scf.out`: 7 iterações, `converged`.
- [ ] `ni.scf.out`: magnetização total/absoluta por iteração e painel de magnetização presente.
- [ ] Cópia truncada (`copy_fixture` + corte no meio de uma iteração): status `running`, `truncated = 1`,
      sem exceção.
- [ ] Texto sintético com `convergence NOT achieved after 3 iterations`: status `not_converged`, e o
      resumo começa com "Não convergiu".
- [ ] Menu de contexto: numa saída SCF, as ações são `["Plotar", "Abrir local de origem", "Abrir com",
      "Copiar", "Renomear"]`. Numa saída bands/relax/nscf ou num input, "Plotar" não aparece.
- [ ] "Plotar" abre a aba "Convergência SCF · al.scf.out" sem criar `plots/`.
- [ ] Botão "Plotar SCF": invisível sem abas, visível com `al.scf.out` aberto, invisível ao trocar para a
      aba de um input ou de um gráfico.
- [ ] Ctrl+G numa pasta só com `scf.in`/`scf.out` plota a convergência sem o diálogo de mapeamento.
- [ ] Render: 3 painéis com spin, 2 sem spin. `scale=log` com |ΔE| = 0 não gera erro.
      `show_threshold=False` remove a linha.
