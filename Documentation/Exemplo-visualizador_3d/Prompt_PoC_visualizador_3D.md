# prova de conceito de um visualizador 3D de estrutura (SCF do Quantum ESPRESSO)

---

## Contexto

Construa, do zero, uma aplicação desktop **PyQt6** independente e pequena, `viewer3d`, que **abre um input SCF do
Quantum ESPRESSO (pw.x)** e mostra a **estrutura atômica em 3D**, num estilo XCrySDen simplificado. É uma prova de
conceito: se funcionar como esperado, o desenho será portado para um aplicativo maior (o Lain). Por isso:

- a **lógica fica separada da interface**: `core/` não importa PyQt6; `ui/` não lê disco nem faz física;
- módulos pequenos (nenhum `.py` com mais de ~400 linhas), uma responsabilidade cada;
- a forma dos dados é a que será portada (§3.1), e tudo que for lógica tem teste.

Decisões **já tomadas** (não rediscuta, não ofereça alternativas):

- O renderer é **`QPainter`** com projeção própria em numpy e algoritmo do pintor. **Sem OpenGL**, sem VTK, PyVista,
  vispy, pyqtgraph, matplotlib 3D, Qt Quick 3D ou WebEngine.
- A aplicação **só visualiza e informa**: não edita a estrutura, não mostra densidade de carga, não roda cálculos.

## 1. Stack e convenções

- Python ≥ 3.11, gerenciado com **uv** (`uv init`, `uv add`, `uv run`). Layout `src/viewer3d/`.
- Dependências de runtime: `PyQt6>=6.7`, `numpy`, `ase` (**somente** `ase.data`: raios covalentes, de van der Waals,
  símbolos e cores Jmol; importado de forma tardia; **nunca** `ase.io`, que recusa `ibrav != 0`).
- Dev: `pytest`, `pytest-qt`, `pytest-timeout` (60 s), `ruff` (`line-length = 100`).
- **Textos da interface em português** (rótulos, mensagens, erros). **Código, comentários, docstrings e commits em
  inglês.**
- Comando `viewer3d [ARQUIVO] [--screenshot SAIDA.png] [--size 1000x800] [--repeat N1 N2 N3] [--style ...]`.
  `--screenshot` renderiza **sem abrir janela** (offscreen) e sai: é como você verá o resultado e confirmará que o
  desenho está certo (leia o PNG gerado).
- Teste e `--screenshot` rodam com `QT_QPA_PLATFORM=offscreen` (defina em `conftest.py` antes de qualquer import do Qt).
- Faça commits pequenos, um por etapa do §8, com os testes passando.

## 2. Estrutura de pastas

```
src/viewer3d/
  core/                      # sem PyQt6
    structure.py             # Structure (dados) e Atom identity
    qe_input.py              # lexer/parsers tolerantes do input do pw.x
    lattice.py               # ibrav -> vetores da célula (port do latgen do QE)
    elements.py              # rótulo -> elemento, Z, raio covalente, vdW, cor
    bonds.py                 # ligações e vizinhos (com imagens periódicas)
    replicate.py             # repetição n1 x n2 x n3
    measure.py               # distância, ângulo, diedro
    camera.py                # arcball, matrizes, projeção
    pick.py                  # seleção por clique
  ui/
    main_window.py           # janela, menus, painel esquerdo, barra de status
    canvas.py                # QWidget do desenho: eventos de mouse, câmera, seleção
    renderer_paint.py        # desenho com QPainter (sem lógica de dados)
    panels.py                # abas do painel esquerdo
  __main__.py                # CLI
tests/
samples/                     # inputs reais do usuário (pode estar vazia); ver §7
```

## 3. Núcleo (sem Qt)

### 3.1 Dados

```python
@dataclass(frozen=True)
class Structure:
    cell: np.ndarray            # (3, 3) Å; linhas a1, a2, a3
    labels: tuple[str, ...]     # rótulo de espécie de cada átomo, na ordem do input
    frac: np.ndarray            # (n, 3) coordenadas fracionárias
    flags: tuple[tuple[int, int, int] | None, ...]   # if_pos de cada átomo (None: não escrito)
    species: tuple[SpeciesInfo, ...]  # ATOMIC_SPECIES: label, massa, pseudopotencial, nº (1-based)
    source: SourceInfo          # caminho, ibrav, nat, prefix, calculation, avisos, valores &SYSTEM úteis
    # propriedades: len, cart (= frac @ cell), formula
```

Use exatamente essa forma de dados (`cell` em Å em linhas, `labels`, `frac`, `flags`): é a que o app de destino já usa.

**Identidade de um átomo na cena**: `AtomRef(index, shift)` com `shift = (n1, n2, n3)` inteiros. A posição
cartesiana é `(frac[index] + shift) @ cell`. Toda seleção e toda medida usa `AtomRef`, nunca só o índice.

### 3.2 Leitura do input (`qe_input.py`)

Escreva um leitor **próprio e tolerante**, que nunca levanta exceção para a GUI: devolve `Structure` ou um
`StructureError` com frase em português ("ibrav ausente ou inválido (…)", "sem ATOMIC_POSITIONS", "nat = 5, mas
ATOMIC_POSITIONS tem 3 linhas", …). Casos reais que têm de funcionar (vieram de inputs de usuário):

- espaço antes de `&control`, `&system` sem espaço, `/` em linha própria;
- chaves em linhas separadas **sem vírgula**, vírgula no fim da linha, várias chaves na mesma linha;
- linhas em branco dentro da namelist; comentários `!` (e `#` nos cards);
- chaves **sem diferenciar maiúsculas** (`ECUTWFC`, `Celldm(1)`), valores com aspas, `1.0D-6`, `1.d-8`, `.5`;
- `celldm(1)`, `celldm(2)`… e também `A`, `B`, `C`, `cosAB`, `cosAC`, `cosBC` (em Å);
- cards (`ATOMIC_SPECIES`, `ATOMIC_POSITIONS`, `CELL_PARAMETERS`, `K_POINTS`, …) em qualquer caixa; a opção pode vir
  como `(angstrom)`, `{angstrom}` ou `angstrom`; um card termina no próximo card ou no fim do arquivo;
- `ATOMIC_POSITIONS`: unidades `alat` (padrão, com aviso se a opção faltar), `bohr`, `angstrom`, `crystal`.
  `crystal_sg` e `ibrav` desconhecido: erro claro. Exatamente `nat` linhas são átomos; os 3 inteiros opcionais depois
  das coordenadas são `if_pos`;
- `CELL_PARAMETERS` (para `ibrav = 0`): `alat`, `bohr`, `angstrom`; a forma `(alat= 10.2)` dá o `alat` em bohr;
- `K_POINTS` e o resto do input são **ignorados**, sem erro.

Regras do QE para a escala:

- 1 bohr = 0.529177210903 Å. Os cálculos internos seguem em bohr; `Structure.cell` sai em Å.
- `alat` (bohr) = `celldm(1)` se dado; senão `A / 0.529177210903`; senão, em `ibrav = 0` com `CELL_PARAMETERS bohr` ou
  `angstrom`, é a **norma do primeiro vetor** da célula. `ATOMIC_POSITIONS alat` e `CELL_PARAMETERS alat` precisam dele.
- Posições `alat`/`bohr`/`angstrom` viram fracionárias por `frac = cart @ inv(cell)`.

Outros dados que o painel mostra (a leitura é por rótulo, índice 1-based da espécie na ordem de `ATOMIC_SPECIES`):
`starting_magnetization(i)`, `Hubbard_U(i)`, `nspin`, `prefix`, `calculation`. Se houver um card `HUBBARD` (QE ≥ 7.1),
registre um aviso "card HUBBARD presente: não interpretado". Rótulos de espécie viram elementos pela regra:
tente as duas primeiras letras (primeira maiúscula, segunda minúscula) como símbolo; senão a primeira letra
(`Fe1`, `Fe_up` → Fe; `C2` → C; `H_ads` → H). Sem elemento (`X`…): cinza, raio 1.0 Å e um aviso, nunca uma exceção.

### 3.3 Célula a partir do `ibrav` (`lattice.py`)

`ibrav = 0` usa `CELL_PARAMETERS`. Para os demais, port do `latgen` do QE 7.1. Linhas = a1, a2, a3, em bohr,
`a = celldm(1)`, `c[i] = celldm(i)`; constantes do QE: `SR2 = 1.414213562373`, `SR3 = 1.732050807569`.

```python
if ibrav == 1:   v = a * eye(3)
if ibrav == 2:   v = a/2 * [[-1, 0, 1], [0, 1, 1], [-1, 1, 0]]
if ibrav == 3:   v = a/2 * [[1, 1, 1], [-1, 1, 1], [-1, -1, 1]]
if ibrav == -3:  v = a/2 * [[-1, 1, 1], [1, -1, 1], [1, 1, -1]]
if ibrav == 4:   v = a * [[1, 0, 0], [-0.5, SR3/2, 0], [0, 0, c3]]
if abs(ibrav) == 5:                 # c4 = cos(gamma), -0.5 < c4 < 1
    t1, t2 = sqrt(1 + 2*c4), sqrt(1 - c4)
    if ibrav == 5:
        x, y, z = a*t2/SR2, -a*t2/SR2/SR3, a*t1/SR3
        v = [[x, y, z], [0, SR2*a*t2/SR3, z], [-x, y, z]]
    else:
        u, w = a*(t1 - 2*t2)/3, a*(t1 + t2)/3
        v = [[u, w, w], [w, u, w], [w, w, u]]
if ibrav == 6:   v = a * diag(1, 1, c3)
if ibrav == 7:   v = a/2 * [[1, -1, c3], [1, 1, c3], [-1, -1, c3]]
# b = a*c2, cc = a*c3
if ibrav == 8:   v = [[a, 0, 0], [0, b, 0], [0, 0, cc]]
if ibrav == 9:   v = [[a/2, b/2, 0], [-a/2, b/2, 0], [0, 0, cc]]
if ibrav == -9:  v = [[a/2, -b/2, 0], [a/2, b/2, 0], [0, 0, cc]]
if ibrav == 91:  v = [[a, 0, 0], [0, b/2, -cc/2], [0, b/2, cc/2]]
if ibrav == 10:  v = [[a/2, 0, cc/2], [a/2, b/2, 0], [0, b/2, cc/2]]
if ibrav == 11:  v = [[a/2, b/2, cc/2], [-a/2, b/2, cc/2], [-a/2, -b/2, cc/2]]
# cos = c4 se ibrav > 0, c5 se < 0;  sin = sqrt(1 - cos²)
if ibrav == 12:  v = [[a, 0, 0], [b*cos, b*sin, 0], [0, 0, cc]]
if ibrav == -12: v = [[a, 0, 0], [0, b, 0], [cc*cos, 0, cc*sin]]
if ibrav == 13:  v = [[a/2, 0, -cc/2], [b*cos, b*sin, 0], [a/2, 0, cc/2]]
if ibrav == -13: v = [[a/2, b/2, 0], [-a/2, b/2, 0], [cc*cos, 0, cc*sin]]
if ibrav == 14:                     # c4 = cos(bc), c5 = cos(ac), c6 = cos(ab)
    sg = sqrt(1 - c6**2)
    t = sqrt((1 + 2*c4*c5*c6 - c4**2 - c5**2 - c6**2) / (1 - c6**2))
    v = [[a, 0, 0], [b*c6, b*sg, 0], [cc*c5, cc*(c4 - c5*c6)/sg, cc*t]]
```

`A, B, C, cosAB, cosAC, cosBC` → celldm (`abc2celldm`): `celldm1 = A/0.529177210903`, `celldm2 = B/A`, `celldm3 = C/A`;
`celldm4..6` = `(cosBC, cosAC, cosAB)` para `ibrav` 14 e 0; `(0, cosAC, 0)` para -12 e -13; `(cosAB, 0, 0)` para
5, -5, 12, 13; zero nos demais. Validações (célula de volume nulo, `celldm(1) <= 0`, `|cos| >= 1`) viram
`StructureError`, não exceção solta.

### 3.4 Ligações (`bonds.py`)

- Ligado se `d < fator × (r_cov(i) + r_cov(j))` e `d > 0.1 Å`; `fator = 1.15` por padrão, ajustável.
- Busca com **imagens periódicas** (−1…1 em cada eixo; ao menos isso) a partir de `frac` e `cell`. Cada ligação
  guarda `(i, j, shift_j)`: o parceiro é a cópia `j + shift_j`.
- Calcule as ligações **uma vez**, da célula original, e **replique por translação** na repetição (§3.5): nunca
  recalcule por átomo repetido (custo O(N²) e 27× pior).
- Para cenas ≥ 1 000 átomos use uma grade de células (ou `scipy.spatial.cKDTree`, se `scipy` já estiver instalado
  via ASE; neste caso, importe de forma tardia). Para menos, numpy basta.
- `neighbors(ref)`: lista `(AtomRef, distância)` ordenada, usada pelo painel (número de coordenação = tamanho).

### 3.5 Repetição (`replicate.py`)

`shifts(n1, n2, n3)` = produto de `range(n_i)` (cópias 0…n−1), com a cópia (0,0,0) marcada como "original".
Só visual: a `Structure` nunca muda. As ligações cujo parceiro cai fora do bloco repetido são desenhadas até um
átomo **fantasma** (opacidade reduzida, não selecionável): evita moléculas "cortadas" na borda do bloco.

### 3.6 Medidas (`measure.py`)

Sobre `AtomRef`s, na posição **exata** da cópia clicada (sem imagem mínima implícita):
`distance(a, b)` (Å, mais `Δx, Δy, Δz`), `angle(a, b, c)` (graus, vértice em `b`), `dihedral(a, b, c, d)` (graus,
com sinal, convenção IUPAC). Extras: `nearest_image(a, b)`, que dá o `shift` de `b` que minimiza a distância a `a`
(busca −2…2; célula muito oblíqua não pode errar).

### 3.7 Câmera e seleção (`camera.py`, `pick.py`)

- Rotação por **arcball** (quaternion ou matriz 3×3), centro na caixa da célula (ou do bloco repetido).
- `project(points) -> (xy, depth, scale)` vetorizado em numpy; perspectiva com `scale = f / (f + z)`; modo ortográfico.
- Vistas ao longo de a, b, c e de x, y, z; "resetar" volta a uma vista isométrica que enquadra tudo.
- `pick(xy_click, projected, radii_px, order)` devolve o `AtomRef` mais próximo da câmera cujo círculo contém o
  clique (raio + 3 px de tolerância), ou `None`.

## 4. Interface

### 4.1 Janela

`QSplitter`: **painel esquerdo** (largura ~320 px) | **canvas 3D** (restante). Menu Arquivo ▸ Abrir (Ctrl+O), Sair;
Exibir ▸ estilos e projeção; arrastar e soltar um arquivo na janela abre. Barra de status: arquivo, fórmula, `nat`,
`ibrav`, e o **tempo do último quadro** (ms) à direita. Erros de leitura: mensagem em português na barra e um
`QMessageBox` (nunca traceback). Avisos do parser: ícone ⚠ na barra de status, texto completo em tooltip.

### 4.2 Canvas (interação)

| Ação                        | Gesto                                                |
| --------------------------- | ---------------------------------------------------- |
| Rotacionar                  | arrastar com o botão esquerdo (arcball)              |
| Mover                       | botão do meio, ou Shift + esquerdo                   |
| Zoom                        | roda do mouse (em direção ao ponteiro); `+` / `-`    |
| Selecionar                  | clique; Ctrl + clique alterna; clique no vazio limpa |
| Resetar vista               | duplo clique, ou tecla `R`                           |
| Vista ao longo de a / b / c | teclas `A` / `B` / `C`                               |
| Perspectiva ⇄ ortográfica   | tecla `P`                                            |

Hover mostra `#n Símbolo` na barra de status. A roda e o arraste **não** chamam nada pesado: só câmera e repintura.

### 4.3 Estilos e elementos desenhados

- Estilos: **bola-e-vareta** (padrão; esfera = 0.45 × raio covalente), **vareta** (ligações grossas, sem esferas),
  **fio** (linhas finas coloridas), **espaço-cheio** (raio de van der Waals). Controle deslizante da escala do raio.
- Esferas: círculo com gradiente radial (luz no canto superior esquerdo); borda fina escura.
- Ligações: quebradas **no meio**, cada metade com a cor do seu átomo, ordenadas junto com os átomos.
- Caixa da célula (12 arestas, cor discreta), **setas a, b, c rotuladas** e **triedro x, y, z** no canto.
- Selecionado: anel de destaque; os dois ou três átomos de uma medida, numerados na ordem do clique.
- Rótulos opcionais: nenhum | símbolo | índice | ambos.
- Cores: Jmol (`ase.data.colors.jmol_colors`); cor por espécie pode ser trocada no painel (QColorDialog).

## 5. Painel esquerdo (`QTabWidget`)

**Aba "Átomo"** (para o último átomo clicado; "Clique em um átomo" quando não há):
nº (1-based, como o QE numera), rótulo da espécie, elemento (nome e símbolo), Z, massa (de `ATOMIC_SPECIES`),
pseudopotencial, posição cartesiana (Å) e fracionária, **imagem** `(n1, n2, n3)` quando não é a original,
`if_pos`, `starting_magnetization`, `Hubbard_U` (quando existirem), número de coordenação e **tabela de vizinhos**
(até 12: átomo, imagem, distância em Å), clicável: clicar numa linha seleciona aquele vizinho.

**Aba "Medidas"**: lista dos átomos selecionados na ordem do clique (nº, símbolo, imagem). Com 2: distância
(Å, Δx Δy Δz); com 3: ângulo em graus (vértice = 2º clicado); com 4: diedro. Tabela das medidas feitas
(acumula), botão "Copiar" (TSV), botão "Limpar", botão "Usar imagem mais próxima" (`nearest_image`).

**Aba "Exibição"**: estilo, escala do raio, fator de ligação, ligações ligadas/desligadas, **repetição
N1 × N2 × N3** (1…5, rótulos "a", "b", "c"), rótulos, caixa da célula, eixos, projeção, fundo (claro / escuro),
tabela de espécies (cor, visível).

**Aba "Célula"**: `a, b, c` (Å), `α, β, γ` (°), volume (Å³), os três vetores, `ibrav`, `nat`, fórmula,
`prefix`, `calculation`, e os avisos do parser.

Mudar qualquer controle repinta na hora e não dispara cálculo pesado.

## 6. Renderer e desempenho (`renderer_paint.py`)

- A projeção, a ordenação (`np.argsort`) e os raios em pixels são **vetorizados em numpy**; só o laço de desenho é
  Python (um `drawEllipse`/`drawLine` por primitivo).
- Algoritmo do pintor: átomos, metades de ligação e fantasmas num único vetor ordenado por profundidade.
- Cache de pincéis de gradiente por `(cor, raio quantizado)`.
- **Modo rascunho** durante rotação/zoom/movimento quando houver mais de ~1 500 primitivos: cores lisas, sem
  gradiente, sem ligações finas; um `QTimer` single-shot de ~150 ms após o último evento redesenha em qualidade plena.
- `devicePixelRatioF()` respeitado (nitidez e tolerância do clique).
- Uma única origem de repintura (`update()` coalescido), sem timers extras.
- Orçamento de referência (medido por mim com este mesmo algoritmo, 1000×800, 1,5 ligação por átomo, antialiasing):
  500 átomos ≈ 14–18 ms, 2 000 ≈ 44–65 ms, 5 000 ≈ 110–170 ms, 10 000 ≈ 215–330 ms por quadro. A sua implementação
  não precisa bater isso; **meça e reporte** (§9).

## 7. Testes

Núcleo (sem Qt, rápidos):

- **Si diamante**, `ibrav = 2`, `celldm(1) = 10.2`, `ATOMIC_POSITIONS alat` com (0,0,0) e (0.25, 0.25, 0.25): célula
  = `5.39760755/2 × [[-1,0,1],[0,1,1],[-1,1,0]]` Å (linhas); distância Si–Si ≈ 2.3372 Å (±1e-3); **4 vizinhos** por
  átomo com `fator = 1.15`.
- **Molécula H3CHg**, `ibrav = 14`, `celldm(1) = 40.0`, `celldm(2) = celldm(3) = 1.0`, `celldm(4..6) = 0.0`,
  `nat = 5`, `ATOMIC_POSITIONS (angstrom)`: Hg (0, −0.000323, −0.140002), C (0, 0.000173, 2.176393) e três H.
  Célula cúbica de 21.16709 Å; Hg–C ≈ 2.316 Å e C–H ≈ 1.09 Å ligados; Hg–H não ligado.
- Cada família de `ibrav` da tabela: volume > 0 e, onde há fórmula conhecida, comprimentos e ângulos esperados.
  `ibrav = 0` nas três unidades (`alat`, `bohr`, `angstrom`) dá a mesma estrutura quando escritas de forma equivalente.
- Parser: todos os casos tolerantes do §3.2 (um teste por caso), erros em português, `crystal_sg`, `nat` maior que
  o número de linhas, `if_pos` presente/ausente, rótulos `Fe1`/`Fe_up`/`X`.
- Medidas: distância invariante a translação inteira de rede; ângulo em [0°, 180°]; diedro conhecido (±90°, 0°, 180°);
  `nearest_image` correto em célula oblíqua.
- Ligações: replicar por translação dá o mesmo conjunto que recalcular em um bloco pequeno.
- Câmera: projeção ortográfica preserva razões; `pick` escolhe o átomo da frente numa sobreposição.

Interface (`pytest-qt`, offscreen):

- abrir um sample (ou o Si embutido) preenche painel e barra; `grab()` não é uma imagem uniforme;
- `qtbot.mouseClick` na posição projetada de um átomo seleciona esse átomo e a aba "Átomo" mostra seu nº e vizinhos;
- dois cliques → aba "Medidas" mostra a mesma distância que `measure.distance`;
- repetição 2×1×1 duplica os átomos desenhados (contador exposto pelo renderer para teste);
- arrastar muda a imagem (`grab()` difere); `R` volta à imagem inicial;
- erro de leitura mostra a mensagem em português, sem exceção.

Teste de desempenho (marcador `perf`, fora do padrão): cena sintética com N = 100, 500, 2 000, 5 000, 10 000
átomos; imprima (`-s`) os ms por quadro em qualidade plena e em rascunho.

Pasta `samples/`: se o usuário colocar inputs reais lá, o teste `test_samples.py` abre **todos** e exige que cada um
leia sem erro (ou com um erro conhecido e em português) e produza um `--screenshot` não uniforme.

## 8. Ordem de trabalho (um commit por etapa)

1. Projeto, `pyproject.toml`, `conftest.py` (offscreen), CLI vazia, `ruff` limpo.
2. `qe_input.py` + `lattice.py` + `elements.py` + `structure.py`, com os testes do §7 (núcleo).
3. `bonds.py`, `replicate.py`, `measure.py`, `camera.py`, `pick.py`, com testes.
4. `renderer_paint.py` + `canvas.py` + `--screenshot`: **abra o PNG e confira** a estrutura do Si, da molécula e de
   cada sample (átomos, ligações, caixa, eixos). Corrija antes de seguir.
5. Painel esquerdo e janela: abas Átomo, Medidas, Exibição, Célula.
6. Repetição, fantasmas, modo rascunho, hover.
7. Testes de interface, teste `perf`, `README.md`, `PORTING.md`.

## 9. Entrega

- Aplicação funcionando (`uv run viewer3d samples/x.in`), `uv run pytest` verde, `uv run ruff check .` limpo.
- `README.md`: como instalar, rodar, atalhos.
- **`PORTING.md`** (importante, é o objetivo da prova de conceito), curto e objetivo:
  1. mapa de módulos: o que é `core/` (portável como está) e o que é `ui/`;
  2. a API pública de cada módulo do `core/` (assinaturas);
  3. **tabela de desempenho medida** (N átomos × ms por quadro, qualidade plena e rascunho, com e sem ligações);
  4. o que não funcionou ou ficou frágil (artefatos do algoritmo do pintor, lentidão, cliques imprecisos, bordas);
  5. desvios deste prompt e por quê;
  6. o que você mudaria se houvesse OpenGL.

## 10. Fora de escopo

Edição da estrutura; densidade de carga e isosuperfícies; ler saídas do pw.x, trajetórias ou forças; zona de
Brillouin; formatos além do input do pw.x (xyz, cif, xsf); exportar SVG/PDF; temas do sistema; internacionalização;
empacotamento e instalador; qualquer chamada a rede ou a processos externos.

## Regras de decisão

Se algo estiver ambíguo, **decida, registre em `PORTING.md` e siga**; só pergunte se estiver bloqueado. Não adicione
dependências além das listadas. Não apresente algo como funcionando sem tê-lo visto: gere o `--screenshot`, leia o PNG,
rode os testes.
