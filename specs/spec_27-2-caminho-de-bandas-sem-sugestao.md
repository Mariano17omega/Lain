# Spec 27-2: Caminho de bandas — sem "Sugerir", com proteção contra o eixo x colapsado

| | |
|---|---|
| **Prioridade** | 27-2 (antes da spec 28, cujo modo Padrão das bandas só pede o caminho) |
| **Status** | Proposta |
| **Depende de** | spec 25 (`kpath.py`), spec 26 (`KPathEditor`) |
| **Usada por** | spec 28 (Bandas no modo Padrão: o usuário digita o caminho `crystal_b`) |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): a maior parte é remoção guiada por uma lista exata de símbolos e testes; as duas funções novas (`collapsed_segments`, `distribute`) reaproveitam `path_coordinates` e `KPath.weights()` e têm critério numérico no teste. |

## Itens de origem (`specs/report-04-10-26.md` e decisão do usuário)

- **Decisão do usuário (05/10/2026):** "Remova a função de *Sugerir caminho* das bandas. Não preciso de sugestões para os pontos das bandas."
  Isso tira a necessidade do `pymatgen` (Q3) e torna obsoletas as partes do F2 e o F9 que dependem dele.
- **F2 (Alto, confirmado):** `npts` uniforme faz o eixo x de um segmento colapsar quando ele é mais de 5× mais longo que o anterior (regra do
  `bands.x`). Continua valendo para caminhos digitados à mão; o que muda é a correção (aviso e redistribuição, não sugestão).
- **B3 (Baixo):** o editor aceita `nan`/`inf`/`1e999`; a quebra de segmento se desloca ao inserir ou remover pontos.
- **Q1(b) (Médio):** `tests/test_kpath.py:60` exige `npts == 20` em todos os pontos.
- **Q3 (Baixo):** `pymatgen` como dependência de runtime só serviria a "Sugerir".
- **F9 (Baixo):** mapeamento pymatgen → célula do input e `_elements` ("CO" lido como cobalto): **obsoleto** com a remoção.

## Situação atual

- `src/qe_studio/core/calc_create/kpath.py` (203 linhas): `DEFAULT_NPTS = 20` (`:32`), `KPoint.npts` (`:79`), `KPath.weights()` (`:92`: peso 1 no último
  ponto ou num ponto de `breaks`, senão `max(int(npts), 1)`), `to_card` (`:109`), `suggest_path(crystal, npts=DEFAULT_NPTS)` (`:170`, dá o mesmo `npts` a
  todos os pontos), `_to_input_cell` (`:148-167`), `_elements` (`:125-145`) e `KPathUnavailable` (levantada em `:176-179` quando o `import` do pymatgen falha).
- `src/qe_studio/core/qe/bands_x.py:152-170` `path_coordinates(kcart)`: `typical = steps[0]`; se `step > 5 * typical`, o x não avança e `typical` não é
  atualizado; senão avança e `typical` acompanha. Com `npts` uniforme, a razão entre passos é a razão entre comprimentos de segmento: um segmento > 5×
  mais longo que o anterior colapsa inteiro (curto → longo colapsa; longo → curto não). Usada por `bands_x.py:127` e `calculations/bands/data.py:308`.
  Reproduzido no relatório com uma célula hexagonal (a = 3,16 Å, c = 20 Å, c/a = 6,33): A→L tem comprimento 0,1827 e avança 0,0000.
- `src/qe_studio/ui/widgets/kpath_editor.py`: botão "Sugerir (pymatgen)" e worker (`_suggest`, ~`:329`; mensagem de `KPathUnavailable` em `:356`);
  `float(text)` em `:236-239` (`float(text) if column != NPTS else int(text)`; `nan`, `inf`, `1e999` e `1_0` passam; `npts` só confere `< 1`);
  `_Row(label, frac, npts, jump)` onde `jump` = "o caminho quebra depois deste ponto"; `add_point` (`:262-268`) insere `_Row("", (0,0,0), DEFAULT_NPTS)` em
  `current + 1` com `jump=False`; `remove_point` (`:270`) apaga a linha **e** o seu `jump`; `move_point` leva o `jump` com o ponto.
- O `fortran_float` de `core/qe/pw_input.py:90` já rejeita `nan`/`inf` (guarda por regex).
- Testes: `test_kpath.py` (`:60` `{p.npts ...} == {20}`; `:111-118` força `sys.modules["pymatgen.symmetry.bandstructure"] = None`; `:122-145`
  `test_card_weights_and_labels`; `:147-157` `vertex_indices() == [0, 20, 50, 60, 90]` com `AL_PATH` de `calc_helpers`; helpers `reciprocal(cell)` e
  `segment_lengths(path, cell)` em `:34-47`), `test_kpath_editor.py` (`:75` levanta `KPathUnavailable` à mão; `:87`, `:105`, `:122`),
  `test_calc_create_dialog.py:234`.
- `pyproject.toml`: `pymatgen>=2026.9.24` (resolvido em 2026.9.24, com `spglib` e dezenas de transitivas); `tests/test_perf_detection.py:155-170` confere que
  `ase`, `pymatgen` e `jinja2` não são importados por `main_window`. `CLAUDE.md` chama o pymatgen de dependência de runtime (seções de "Criar cálculo" backend).
- `ScfInfo.crystal` (`Crystal(cell Å, labels, frac)` de `core/qe/lattice.py`) é `None` quando `structure_problem` (ex.: `crystal_sg`).

## Requisitos

### R1: Remover "Sugerir caminho" e o pymatgen
1. `kpath.py`: sai `suggest_path`, `_to_input_cell`, `_elements`, `KPathUnavailable`. `DEFAULT_NPTS` continua (valor das linhas novas do editor). Ficam `KMesh`, `KPoint`,
   `KPath`, `weights`, `to_card` e tudo o que o card precisa.
2. `ui/widgets/kpath_editor.py`: sai o botão "Sugerir (pymatgen)", o worker, o spinner e a mensagem de indisponibilidade; o construtor deixa de receber
   `suggest`; `ui/dialogs/calc_create/tabs_page.py` deixa de passar `partial(suggest_path, crystal)`. A tabela abre **vazia** (o usuário digita; "Criar" segue
   bloqueado com menos de 2 pontos, como hoje).
3. Dependências: `pymatgen` sai de `pyproject.toml` e `uv.lock` é regenerado (somem `spglib` e as transitivas que só ele trazia). `tests/test_perf_detection.py`
   deixa de checar `pymatgen` (continua checando `ase` e `jinja2`).
4. Testes removidos ou reescritos: `test_kpath.py:60` e `:111-118` (sugestão), `test_kpath_editor.py:75`, `test_calc_create_dialog.py:234`, os mocks de
   `suggest_path`; o que testa `to_card`, `weights` e a leitura dos rótulos pelo Lain (`:122-157`) fica.
5. Textos: nenhuma string de UI menciona "pymatgen" ou "Sugerir". `CLAUDE.md` (seções "Criar cálculo backend" e "janela") deixa de falar de `HighSymmKpath`,
   `suggest_path` e `KPathUnavailable` e diz que o caminho é digitado.
6. **Ficam** `core/qe/lattice.py`, `Crystal` e `ScfInfo.crystal`: R3 usa a célula.

### R2: Aviso do eixo x colapsado (F2)
1. `core/calc_create/kpath.py:collapsed_segments(path: KPath, cell) -> list[CollapsedSegment]` (Qt-free, `cell` = `Crystal.cell` em Å):
   - monta os pontos k do card como o pw.x os gera (de cada vértice ao seguinte em `weights()` passos, o último vértice uma vez; sem passos entre
     vértices separados por quebra), converte para cartesianas com `2π·inv(cell).T` (Å⁻¹) e roda `bands_x.path_coordinates`;
   - para cada segmento compara o avanço em x com o comprimento real (soma de |Δk|); devolve `CollapsedSegment(a, b, lost)` quando o avanço é menor
     que 50 % do real (`lost` = fração perdida);
   - não levanta: caminho com menos de 2 pontos, passos nulos ou `cell` singular devolvem lista vazia.
2. O plano (`types/bandas.py`) acrescenta uma nota por segmento: "Segmento Γ→A colapsa no eixo x do bands.x (passo maior que 5× o anterior):
   aumente os pontos do segmento anterior, reduza os deste ou use ‘Distribuir pelo comprimento’". **Nunca bloqueia** "Criar". Sem `Crystal`
   (`structure_problem`), uma nota diz que a checagem não foi feita.
3. O editor marca (cor de aviso `warn`, tooltip com o texto) a linha do ponto de origem do segmento problemático, a cada edição (mesmo debounce das demais).

### R3: Botão "Distribuir pelo comprimento"
1. `kpath.distribute(path: KPath, cell, density: float, min_pts: int = 2) -> KPath`: cada segmento recebe `npts = max(min_pts, round(comprimento_Å⁻¹ ×
   density))`; pontos antes de uma quebra e o último ponto não contam (têm peso 1 no card); rótulos, coordenadas, `breaks` e `warnings` preservados.
2. No editor, ao lado do botão: campo "Pontos por Å⁻¹" (padrão 25) e o botão "Distribuir pelo comprimento"; só muda a coluna "Pontos" (desfazível por
   Ctrl+Z da tabela, se existir; senão o usuário reedita). Desabilitado, com tooltip "Estrutura do SCF não legível", quando não há `Crystal`.
3. Nunca roda sozinho: nem ao abrir a aba, nem ao adicionar linhas.

### R4: Editor (B3)
1. As células numéricas passam por `math.isfinite`: `nan`, `inf`, `-inf`, `1e999` são rejeitados como texto inválido (volta ao valor anterior, como
   `"meio"` hoje). `npts` é inteiro entre 1 e 1000.
2. **Quebra de segmento** (`_Row.jump` = "quebra depois deste ponto"):
   - `add_point` depois de um ponto com quebra: a linha nova continua o segmento daquele ponto e **herda a quebra**; o ponto anterior fica com `jump = False`
     (a quebra continua entre a linha nova e a seguinte, que é o par que o usuário tinha quebrado);
   - `remove_point` de um ponto com quebra passa a quebra ao ponto anterior (se existir), em vez de perdê-la;
   - `move_point` continua levando o `jump` com o ponto.

### R5: Testes (Q1b)
1. `test_kpath.py:60` sai (não há mais `npts` uniforme sugerido).
2. Célula hexagonal sintética (a = 3,16, c/a = 6,33) e o caminho Γ-M-K-Γ-A-L-H-A com `npts` uniforme: `collapsed_segments` aponta A→L. Depois de
   `distribute(..., density=25)` o resultado é vazio **e** em `path_coordinates` nenhum segmento perde mais de 5 % do comprimento real.
3. Al (fcc, `AL_PATH`): sem avisos antes nem depois; `distribute` mantém rótulos, quebras e a soma dos pesos coerente com `to_card` (N correto).
4. Editor: `nan`/`inf`/`1e999` rejeitados; inserir depois de ponto com quebra e remover ponto com quebra seguem R4.2; o botão "Distribuir" fica
   desabilitado sem `Crystal`.
5. `uv sync` sem `pymatgen`: o teste de importação confirma que nada importa `pymatgen` (o módulo nem é mencionado em `src/`).

## Fora de escopo
- Qualquer sugestão automática de pontos ou caminhos 2D (decisão do usuário).
- F9 (obsoleto) e as demais conversões de célula.
- **F8 (pendente, depende de dados reais):** só o ibrav 2 é comparado com os eixos impressos pelo pw.x (`test_lattice.py:39`, fixtures `al_*`, `si_*`, `qe731_ni_*`);
  não há fixture de ibrav 4 ou 5. Como `lattice.py` agora serve ao aviso e à redistribuição, vale ter saídas reais de ibrav 4 e 5 (com `a(i)` impressos) quando
  o usuário rodar um QE de teste; quando existirem, entram em `tests/fixtures/qe<ver>_<sistema>/` e na tabela de `test_qe_versions.py`. Sem elas, nada muda.
  (O relatório também aponta que `CELL_PARAMETERS` sem unidade é lido como `alat` em `lattice.py:185`; o código levanta `StructureError` sem `celldm(1)`/`A`, então a falha é
  explícita, e a documentação do QE não declara o padrão.)
- Extra opcional `lain[kpath]`: descartado, o pymatgen sai de vez.

## Decisões assumidas (confirmar na revisão)
1. Manter `lattice.py`/`Crystal` (a spec não apaga código que ainda tem uso e testes), embora o pymatgen tenha saído.
2. `distribute` usa comprimento recíproco **com** 2π (Å⁻¹); densidade inicial 25 pontos/Å⁻¹ (Al: Γ–X ≈ 1,55 Å⁻¹ → 39 pontos). Valor de partida, a ajustar com o uso.
3. O aviso de R2 usa o limiar de 50 % de avanço (qualquer colapso real zera o avanço, então o limiar só evita ruído por arredondamento).
4. `npts` máximo de 1000 por ponto (evita um card gigante por um zero a mais).
5. O relatório só diz que a quebra "se desloca para o novo par" ao inserir, sem definir o desejado. Escolhi: a linha nova entra no segmento do ponto
   selecionado e a quebra continua imediatamente antes do ponto que vinha depois (R4.2). Se o esperado for o contrário (a linha nova abrir o segmento
   seguinte), é só trocar quem herda o `jump`.

## Notas de implementação
- Alterados: `core/calc_create/kpath.py`, `core/calc_create/types/bandas.py` (notas), `ui/widgets/kpath_editor.py`, `ui/dialogs/calc_create/tabs_page.py`,
  `pyproject.toml`, `uv.lock`, `tests/test_kpath.py`, `tests/test_kpath_editor.py`, `tests/test_calc_create_dialog.py`, `tests/test_perf_detection.py`,
  `tests/calc_helpers.py` (se algo de sugestão sobrar), `CLAUDE.md`.
- `kpath.py` fica ≈ 150 linhas; `collapsed_segments` e `distribute` ficam em `kpath.py` ou em `kpath_density.py` se passar de ~250 (regra de 500 linhas é folgada).
- Nenhuma leitura de arquivo em `ui/`; o cálculo é puro e instantâneo (não precisa de worker).
- O tooltip do botão e a nota do plano são textos em português.

## Critérios de aceite e testes
- [ ] `grep -rni pymatgen src pyproject.toml` não encontra nada; `uv.lock` sem `pymatgen` e `spglib`; `uv sync` e a suíte passam.
- [ ] Editor sem botão "Sugerir"; tabela vazia na primeira visita; "Criar" bloqueado com < 2 pontos.
- [ ] Hexagonal c/a 6,33 com `npts` uniforme: nota de segmento colapsado e linha marcada; depois de "Distribuir": sem nota e perda ≤ 5 % por segmento.
- [ ] Al: nenhuma nota; `to_card` com N e pesos corretos; Lain lê os rótulos do card (teste existente).
- [ ] `nan`/`inf`/`1e999` rejeitados; `npts` fora de 1..1000 rejeitado; quebra preservada ao inserir e ao remover.
- [ ] Sem `Crystal`: "Distribuir" desabilitado e nota "checagem não feita".
- [ ] `test_architecture.py`, `ruff`, `pyright` sem regressão; `CLAUDE.md` sem `pymatgen` nem `suggest_path`.
