# PDOS

**Detecção (`PDOS`)**: arquivos `*pdos_atm#*` do `projwfc.x` (na pasta ou em `orbitals/`), mais saída do SCF/NSCF
(Fermi, HOMO/LUMO).

## Recursos

- **Fonte do Fermi** (SCF ou NSCF), deslocar para E_F, janela `E mín`/`E máx`, `dos_max`, **orientação** (energia no
  eixo x ou y).
- **Agrupamento**: *Espécie + orbital*, *Espécie* ou *Orbital*; DOS total (cor própria); preencher estados ocupados.
- **Átomos…**: escolhe quais átomos entram; a seleção é lembrada por composto (fórmula + ordem das espécies) em
  `.lain/compounds.json`.
- **Séries** ocultáveis e com cor própria; mapas de cores por orbital e por espécie.
- **Spin** (se há dois canais): *Espelhado (↓ negativo)*, *Sobreposto*, *Só ↑*, *Só ↓*, *Soma (↑+↓)*.
- **Gap na legenda** (`legend_gap`) pelo HOMO/LUMO ou pela curva de DOS.
- CSV dos dados na exportação.

Código: `core/calculations/pdos/` (`atoms.py`, `data.py`, `gap.py`, `params.py`, `render.py`, `table.py`),
parser em `core/qe/projwfc.py`, seleção em `core/project/compounds.py`.
