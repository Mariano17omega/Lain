# viewer3d

Prova de conceito de um visualizador 3D de estrutura atômica a partir de um **input SCF do
Quantum ESPRESSO (`pw.x`)**, num estilo XCrySDen simplificado. Interface PyQt6 com renderer
próprio em `QPainter` (projeção em numpy + algoritmo do pintor; sem OpenGL).

Só visualiza e informa: não edita a estrutura, não mostra densidade de carga, não roda cálculos.
O objetivo real da prova de conceito está em [`PORTING.md`](PORTING.md).

## Instalar e rodar

```bash
uv sync                                   # cria .venv com as dependências
uv run viewer3d samples/scf.in            # abre a janela
uv run viewer3d                           # sem arquivo: Si diamante embutido
```

Linha de comando:

```
viewer3d [ARQUIVO] [--screenshot SAIDA.png] [--size LxA] [--repeat N1 N2 N3]
         [--style bola-vareta|vareta|fio|espaco-cheio]
```

`--screenshot` renderiza **sem abrir janela** (plataforma `offscreen`) e sai:

```bash
uv run viewer3d samples/scf.in --screenshot /tmp/x.png --size 1000x800 --repeat 2 1 1
```

## Atalhos e gestos

| Ação | Gesto |
|---|---|
| Rotacionar | arrastar com o botão esquerdo (arcball) |
| Mover | botão do meio, ou Shift + esquerdo |
| Zoom | roda do mouse (em direção ao ponteiro); `+` / `-` |
| Selecionar | clique adiciona o átomo (até 4, na ordem do clique); Ctrl + clique alterna; clique no vazio limpa |
| Resetar vista | duplo clique, ou `R` |
| Vista ao longo de a / b / c | `A` / `B` / `C` (e `X` / `Y` / `Z` para os eixos cartesianos) |
| Perspectiva ⇄ ortográfica | `P` |
| Abrir arquivo | `Ctrl+O`, ou arrastar e soltar na janela |

O mouse sobre um átomo mostra `#n Símbolo` na barra de status; o tempo do último quadro (ms) fica
à direita. Avisos do leitor aparecem como ⚠ na barra de status (texto completo no tooltip e na aba
"Célula").

## Abas do painel esquerdo

- **Átomo**: nº (como o QE numera), espécie, elemento, Z, massa, pseudopotencial, posição
  cartesiana/fracionária, imagem, `if_pos`, `starting_magnetization`, `Hubbard_U`, coordenação e
  tabela de vizinhos (clicável).
- **Medidas**: átomos selecionados, distância (com Δx Δy Δz), ângulo e diedro; tabela acumulada,
  copiar (TSV), limpar, "usar imagem mais próxima".
- **Exibição**: estilo, escala do raio, fator de ligação, ligações, repetição N1×N2×N3 (1…5),
  rótulos, caixa, eixos, projeção, fundo e tabela de espécies (cor, visível).
- **Célula**: a, b, c, α, β, γ, volume, vetores, `ibrav`, `nat`, fórmula, `prefix`, `calculation`
  e avisos.

## Testes

```bash
uv run pytest                  # núcleo + interface (offscreen); o teste perf fica de fora
uv run pytest -m perf -s       # medidas de tempo por quadro (N = 100 … 10 000 átomos)
uv run ruff check .
```

Inputs reais colocados em `samples/` são abertos automaticamente por `tests/test_samples.py`
(leitura sem erro e `--screenshot` não uniforme).

## Estrutura

```
src/viewer3d/core/   # sem PyQt6: dados, leitor do input, rede, ligações, câmera, medidas, seleção
src/viewer3d/ui/     # PyQt6: janela, painéis, canvas e renderer QPainter
tests/               # pytest / pytest-qt
samples/             # inputs reais
```
