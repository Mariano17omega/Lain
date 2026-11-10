# Estrutura de bandas

**Detecção (`BANDS`)**: saída do `bands.x` (`.gnu`/`.dat`), input/saída do `pw.x` com `calculation='bands'` (para o
caminho k e rótulos) e o SCF (energia de Fermi, elétrons). SCF ausente → procurado em pastas `*scf*` irmãs; papéis
faltantes podem ser mapeados à mão.

## Recursos

- Caminho de alta simetria com rótulos Γ (`labels` sobrescreve; **Linhas de alta simetria** liga/desliga).
- **Referência** da energia: `E_F (SCF)` (`E_F (meio do gap)` em isolantes), `Topo da valência (VBM)`, `Meio do gap` ou `Absoluta`; janela `E mín`/`E máx`;
  janela do eixo x (`x mín`/`x máx`); linha de Fermi. Em isolantes, o E_F é o meio do gap: veja
  [Nível de Fermi em isolantes](index.md#fermi-em-isolantes).
- Cores: valência, condução, Fermi.
- **Gap de energia na legenda** (`legend_gap`): gap = CBM − VBM (não a energia de Fermi), com **Método do gap**:
  *Automático* (contagem de elétrons), *HOMO/LUMO do SCF* ou *Maior intervalo na janela*.
- **Spin polarizado** (dois `bands.x`, `spin_component` 1 e 2): **Canais** (Ambos/Só ↑/Só ↓), **Disposição**
  (sobrepostos/lado a lado), **Cores por** (canal ou valência/condução), cores ↑/↓; um gap por canal.
- CSV dos dados na exportação.

Código: `core/calculations/bands/` (`detection.py`, `data.py`, `gap.py`, `params.py`, `render.py`, `table.py`,
`module.py`), parser em `core/qe/bands_x.py`.
