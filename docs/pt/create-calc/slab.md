# Slab

Abre **vácuo** num eixo do SCF do bulk, como um `vc-relax`. Nenhum plano de Miller é cortado: a célula do bulk fica com
sua camada e um eixo cresce até o vácuo pedido (o mínimo, mais a altura de uma molécula e a distância de adsorção se o
SCF da molécula for informado).

- **Arquivos**: `vc-relax_<prefix>.in` (`prefix = '<prefix>-slab-<hkl>'`), o `.qsub` e `geracao.md` (relatório do que
  foi feito). Se a estrutura não puder ser construída, o input sai como o SCF com as edições de vc-relax e o relatório
  diz por quê.
- **Campos**: **Superfície (eixo empilhado)**, **Inverter a superfície**, **Vácuo mínimo (Å)**, **Distância de
  adsorção (Å)** (somada só com molécula), **SCF da molécula (opcional)**, **Completar poliedros de borda (O + H)**
  com **Metais da borda** e **Reconectar H cortados**, **Rede de k-points** (vazio = a do SCF reescalada),
  **Graus de liberdade da célula** (`cell_dofree`, `2Dxy` relaxa só o plano) e **Átomos fixos** (`if_pos 0 0 0`).

Código: `core/calc_create/types/slab.py`, `slab_fields.py`, geometria em `core/calc_create/surface/`
(`slab.py`, `fixing.py`, `kmesh.py`, `report.py`).
