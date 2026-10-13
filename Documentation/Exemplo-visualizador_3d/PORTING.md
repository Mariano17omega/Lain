# PORTING.md — de `viewer3d` para o Lain

Prova de conceito concluída: núcleo sem Qt, renderer `QPainter` com projeção em numpy, 228 testes
(núcleo, interface offscreen, arquitetura) e medidas de desempenho abaixo. Tudo que está em `core/`
foi escrito para ser copiado como está.

## 1. Mapa de módulos

### `core/` — portável como está (não importa PyQt6; só `numpy`, e `ase.data`/`scipy` com import tardio)

| Módulo | Responsabilidade |
|---|---|
| `structure.py` | `Structure` (a forma de dados do Lain: `cell` Å em linhas, `labels`, `frac`, `flags`, `species`, `source`), `AtomRef(index, shift)`, `SpeciesInfo`, `SourceInfo`, `StructureError` |
| `qe_lexer.py` | camada léxica tolerante: namelists e cards (`split_input`) |
| `qe_input.py` | leitor do input do `pw.x`: `Structure` ou `StructureError`, nunca exceção |
| `lattice.py` | `ibrav` → vetores da célula (port do `latgen` do QE 7.1) e `A,B,C,cos…` → `celldm` |
| `elements.py` | rótulo de espécie → elemento, Z, nome (PT), raio covalente, vdW, cor Jmol |
| `bonds.py` | ligações com imagens periódicas e `BondGraph` (vizinhos/coordenação) |
| `replicate.py` | repetição n1×n2×n3 por translação e átomos fantasmas → `Scene` |
| `measure.py` | distância, ângulo, diedro (IUPAC), imagem mais próxima |
| `camera.py` | arcball, matrizes, projeção perspectiva/ortográfica, vistas, enquadramento |
| `pick.py` | seleção por clique sobre a projeção |
| `example.py` | Si diamante embutido (texto de input) |

### `ui/` — PyQt6, específico deste protótipo

| Módulo | Responsabilidade |
|---|---|
| `main_window.py` | janela, menus, splitter, barra de status, abrir/soltar arquivo |
| `canvas.py` | `QWidget`: eventos de mouse/teclado, câmera, seleção, modo rascunho |
| `renderer_paint.py` | projeção + ordenação + laço de desenho `QPainter` (sem lógica de dados) |
| `renderer_overlay.py` | rótulos, anéis de seleção, triedro x/y/z, setas |
| `render_types.py` | `FrameStats`, `Projection`, `Prims` |
| `panels.py`, `panel_measures.py`, `panel_display.py` | abas Átomo/Célula, Medidas, Exibição |
| `options.py` | `DisplayOptions` (dados puros; poderia morar em `core/`) |

Regra verificada por `tests/test_architecture.py`: `core/` não importa PyQt6; `ui/` não abre arquivos nem
importa `ase`; nenhum `.py` passa de 400 linhas; carregar uma estrutura nunca importa `ase.io`,
`matplotlib` nem Qt.

## 2. API pública do `core/`

```python
# structure.py
class AtomRef(NamedTuple): index: int; shift: tuple[int, int, int] = (0, 0, 0)
@dataclass(frozen=True) class StructureError: message: str; line: int | None = None
@dataclass(frozen=True) class SpeciesInfo: label: str; mass: float | None; pseudo: str | None; number: int  # 1-based
@dataclass(frozen=True) class SourceInfo:
    path; ibrav; nat; ntyp; prefix; calculation; nspin; alat_bohr; celldm
    starting_magnetization: dict[int, float]; hubbard_u: dict[int, float]   # chave = nº da espécie (1-based)
    warnings: tuple[str, ...]
@dataclass(frozen=True, eq=False) class Structure:
    cell: ndarray(3,3) Å; labels: tuple[str, ...]; frac: ndarray(n,3)
    flags: tuple[tuple[int,int,int] | None, ...]; species: tuple[SpeciesInfo, ...]; source: SourceInfo
    species_index: ndarray(n,)            # derivado: índice 0-based em `species`
    def __len__(self) -> int
    cart -> ndarray(n,3); symbols -> tuple[str, ...]; formula -> str (Hill); volume -> float
    lattice_parameters -> (a, b, c, alpha, beta, gamma)
    def position(self, ref: AtomRef) -> ndarray(3,)        # (frac[index] + shift) @ cell

# qe_input.py
def read_structure(path: str | PathLike) -> Structure | StructureError
def parse_input(text: str, path: str | None = None) -> Structure | StructureError

# lattice.py
BOHR = 0.529177210903
def latgen(ibrav: int, celldm: Sequence[float]) -> ndarray(3,3)          # bohr; LatticeError
def celldm_from_abc(ibrav, a, b, c, cos_ab, cos_ac, cos_bc) -> tuple[float, ...]   # 6 valores

# elements.py
@dataclass(frozen=True) class ElementInfo: symbol; z; name; r_cov; r_vdw; color; known
def element_for_label(label: str) -> ElementInfo          # nunca levanta; desconhecido: cinza, 1.0 Å
def symbol_from_label(label: str) -> str | None
def element_by_z(z: int) -> ElementInfo

# bonds.py
DEFAULT_FACTOR = 1.15
def bonds_for(structure: Structure, factor: float = 1.15) -> Bonds
def compute_bonds(cell, frac, r_cov, factor=1.15) -> Bonds        # Bonds(i, j, shift(m,3), dist)
def covalent_radii(structure: Structure) -> ndarray(n,)
class BondGraph(bonds: Bonds, n_atoms: int):
    def neighbors(self, ref: AtomRef) -> list[tuple[AtomRef, float]]   # ordenado por distância
    def coordination(self, ref: AtomRef) -> int

# replicate.py
def shifts(n1: int, n2: int, n3: int) -> ndarray(m,3)
def original_mask(copies: ndarray) -> ndarray(bool)
def build_scene(structure: Structure, bonds: Bonds, reps=(1, 1, 1)) -> Scene
class Scene:   # positions (reais, depois fantasmas), species, refs, n_real, original, bond_a, bond_b, cell, frac, reps
    def position(self, ref) -> ndarray(3,); box_corners(self, vectors=None) -> (8,3); bounds_points(self) -> (k,3)
    n_ghost -> int; block -> (3,3)

# measure.py
def distance(structure, a: AtomRef, b: AtomRef) -> Distance        # .value Å, .delta (3,)
def angle(structure, a, b, c) -> float                              # graus, vértice em b
def dihedral(structure, a, b, c, d) -> float                        # graus, IUPAC, com sinal
def nearest_image(structure, a: AtomRef, b: AtomRef) -> AtomRef

# camera.py
class Camera:   # rotation, center, zoom (px/Å), pan, focal, perspective
    def project(self, points, viewport) -> (xy (n,2), depth (n,), scale (n,))
    def arcball_begin(x, y, viewport); arcball_drag(x, y, viewport)
    def reset(points, viewport, center, pad=0.0); fit(points, viewport, margin=0.9, pad=0.0)
    def view_axis(name: 'a'|'b'|'c'|'x'|'y'|'z', cell); look_along(direction, up); set_isometric()
    def zoom_at(factor, cursor, viewport); pan_by(dx, dy); axes_screen() -> (3,2)

# pick.py
def pick(click_xy, xy, radii_px, order, refs: Sequence[AtomRef], tol_px=3.0) -> AtomRef | None
def hit_test(click_xy, xy, radii_px, order, tol_px=3.0) -> int | None   # `order` = frente → fundo
```

## 3. Desempenho medido

Cena sintética: folhas de grafeno empilhadas (1,5 ligação por átomo, como no orçamento de referência),
quadro de 1000×800, antialiasing, estilo bola-e-vareta, mediana de 5 quadros após aquecimento.
Máquina: 20 CPUs, Linux, Python 3.11, PyQt6 6.11 / Qt 6.11, plataforma `offscreen` (engine raster; o
caminho de pintura é o mesmo da janela real). Reproduzir: `uv run pytest -m perf -s`.

| N átomos | ligações | primitivos (c/ lig.) | **cheio c/ lig.** | **rascunho c/ lig.** | cheio s/ lig. | rascunho s/ lig. | ligações (ms) | cena (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 150 | 475 | 5.2 ms | 2.0 ms | 2.7 ms | 0.9 ms | 5.2 | 0.4 |
| 500 | 750 | 2 315 | 14.5 ms | 7.7 ms | 5.2 ms | 2.3 ms | 14.2 | 1.0 |
| 2 000 | 3 000 | 8 615 | 43.7 ms | 25.5 ms | 12.9 ms | 5.7 ms | 160.5¹ | 3.6 |
| 5 000 | 7 500 | 21 215 | 77.2 ms | 53.5 ms | 23.2 ms | 12.2 ms | 9.7 | 6.5 |
| 10 000 | 15 000 | 41 415 | 150.5 ms | 90.1 ms | 41.7 ms | 22.5 ms | 19.6 | 13.0 |

¹ inclui o import tardio de `scipy.spatial` (~230 ms na primeira vez; as chamadas seguintes ficam em
~10 ms). O caminho numpy denso vale até 999 átomos, a `cKDTree` a partir de 1 000.

Comparação com o orçamento de referência (500 ≈ 14–18 ms, 2 000 ≈ 44–65, 5 000 ≈ 110–170, 10 000 ≈ 215–330):
dentro ou abaixo em todos os tamanhos. Custos fixos: `import ase.data` ≈ 190 ms (tardio, só ao ler a
primeira estrutura); `import PyQt6.QtWidgets` ≈ 15 ms.
O ganho do modo rascunho é modesto (≈ 40 % em 10 000 átomos): o gargalo é o laço Python (um
`drawEllipse`/`drawLine` por primitivo), não o preenchimento.

## 4. O que não funcionou ou ficou frágil

- **Algoritmo do pintor sem z-buffer.** Esferas são ordenadas pelo centro: duas esferas que se
  interpenetram (espaço-cheio) ou uma ligação grossa que atravessa a esfera vizinha aparecem com a
  ordem errada na região de contato. Cada metade de ligação é ordenada pelo seu ponto médio, então uma
  metade longa pode ficar atrás de uma esfera que só a cobre parcialmente.
- **Arestas da caixa** são ordenadas pelo ponto médio: uma aresta longa pode passar "por trás" de um
  átomo que está, de fato, atrás dela perto de uma ponta. Aceitável para uma caixa discreta; ruim se a
  caixa fosse sólida.
- **Fantasmas translúcidos** (opacidade 0.35) somam-se e ficam "enlameados" em cenas densas; por isso só
  aparecem quando alguma ligação desenhada os usa (nunca em espaço-cheio nem sem ligações).
- **Cliques**: o alvo é o disco projetado (raio + 3 px), não a esfera; em vareta/fio o raio mínimo é
  5 px. Átomos coincidentes na tela (por exemplo a vista isométrica do Si primitivo, que olha ao longo de
  (1,1,1)) resolvem para o da frente; o de trás só é alcançável girando a vista. Fantasmas não são
  selecionáveis (por decisão), mas vizinhos clicados na tabela podem estar fora do bloco e ganham anel
  mesmo assim.
- **Tolerância em px lógicos.** Em telas com `devicePixelRatio > 1` o alvo real em px de dispositivo
  fica maior; `render_image(dpr=…)` gera a imagem em px de dispositivo com `setDevicePixelRatio`, mas não
  foi exercitado em tela HiDPI real.
- **Gradiente com `setBrushOrigin`**: reaproveita o pincel entre esferas do mesmo tamanho; funciona no
  engine raster, não há garantia em outros paint devices.
- **Busca de ligações** limita o alcance a 3 células por direção; células minúsculas (< ~0,5 Å) perdem
  ligações longínquas. A busca é feita em posições embrulhadas em [0,1) e convertida de volta, então
  átomos fora da célula (frac `-0.0088`, `1.05` no sample) funcionam.
- **Primeira ligação com `scipy`** paga ~230 ms de import (visível como um engasgo em estruturas ≥ 1 000
  átomos).
- **Ordem de seleção**: o clique simples *acrescenta* (até 4; o 5º reinicia). Para ver um átomo isolado
  depois de uma medida é preciso limpar (clique no vazio).
- **Não testado em tela real**: gestos com touchpad e HiDPI; o ciclo de janela foi exercitado com
  `pytest-qt` (offscreen) e um lançamento rápido em X11.

## 5. Desvios do prompt e por quê

| Desvio / decisão | Motivo |
|---|---|
| `qe_lexer.py` separado de `qe_input.py` | o leitor passava de ~450 linhas; léxico e semântica ficam testáveis em separado |
| `renderer_overlay.py`, `render_types.py`, `panel_measures.py`, `panel_display.py` extras | limite de ~400 linhas por arquivo |
| `DisplayOptions` em `ui/options.py` (sem Qt) | é estado de vista; migraria com a UI |
| `Structure.species_index` (derivado) e `Structure.volume/lattice_parameters/symbols/formula` | evita física na UI e repetição de lógica nos painéis |
| `StructureError` é dataclass com `message` e `line` | `str(err)` devolve a frase em português |
| Clique simples acrescenta à seleção (máx. 4) | o §7 pede que dois cliques deem a medida; Ctrl+clique alterna |
| `ATOMIC_SPECIES` ausente é tolerado (aviso) | "ler tolerante"; a espécie é deduzida das posições |
| `CELL_PARAMETERS` com `ibrav ≠ 0` ignorado (aviso); `celldm(1)` com `CELL_PARAMETERS bohr/angstrom` vira só `alat` (aviso) | o QE recusa; o visualizador prefere mostrar |
| Elemento desconhecido (inclui `X`, Z=0 do ASE) → cinza, 1,0 Å, aviso | pedido; o ASE trata `X` como elemento 0 |
| vdW ausente no ASE (50 elementos) → 1,8 Å | o ASE devolve NaN |
| Nomes de elemento em português embutidos em `elements.py` | o ASE só tem inglês |
| Fórmula no sistema de Hill (`CH18Al8HgO36Si8`) | formato conhecido e estável |
| `--style` aceita `bola-vareta`, `vareta`, `fio`, `espaco-cheio` | ids ASCII para a linha de comando |
| Teclas `X`/`Y`/`Z` além de `A`/`B`/`C`; fundo escuro por padrão | o §3.7 pede as vistas cartesianas |
| Sem arquivo: abre o Si embutido (menu "Abrir exemplo") | o §7 cita "o Si embutido" |
| Rascunho: estilos com vareta omitem ligações com pena < 1,5 px; `fio` mantém todas (as duas metades) | "sem ligações finas" sem apagar a cena do `fio`, cuja única geometria são as ligações |
| Átomos soltos em `vareta`/`fio` ganham um ponto | senão sumiriam da cena |
| Fantasmas só existem se houver ligação desenhada | evitar esferas translúcidas sem sentido |
| `scf.in` copiado para `samples/scf.in` (o da raiz foi mantido) | é o sample real do usuário; apagar o duplicado fica com ele |
| Dependências transitivas do `ase` (`scipy`, `matplotlib`, …) | não adicionei nada; o app nunca importa `matplotlib` nem `ase.io` |
| Commits na branch `master` (a única existente, sem commits) | o repositório estava vazio |

## 6. O que mudaria com OpenGL

- **Esferas como impostores** (quad + fragment shader com normal e profundidade corretas) em uma única
  chamada instanciada; ligações como cilindros instanciados. Interpenetração, ordem de ligações e
  arestas passam a ser resolvidas pelo z-buffer: somem os artefatos da §4.
- **Seleção por ID** (render com cor-índice em FBO) em vez de discos projetados; hover O(1), exato em
  sobreposições.
- **Fantasmas e caixa** com blending correto (depth peeling ou alpha-to-coverage), sem ordenação em CPU.
- **Sem modo rascunho**: milhões de átomos a 60 fps; rotação/zoom viram só uma matriz uniforme.
- Iluminação por pixel, sombreamento por profundidade, suavização por MSAA, rótulos via atlas de texto.
- A câmera (`core/camera.py`) e as ligações/cena (`core/bonds.py`, `core/replicate.py`) continuam: o
  renderer só consome `Scene.positions`, `Scene.species`, `Scene.bond_a/bond_b` e a matriz de `Camera`.
