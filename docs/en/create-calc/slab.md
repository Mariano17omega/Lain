# Slab

Opens **vacuum** along an axis of the bulk's SCF, as a `vc-relax`. No Miller plane is cut: the bulk cell keeps its layer
and one axis grows until the requested vacuum (the minimum, plus the height of a molecule and the adsorption distance
if the molecule's SCF is given).

- **Files**: `vc-relax_<prefix>.in` (`prefix = '<prefix>-slab-<hkl>'`), the `.qsub` and `geracao.md` (a report of what
  was done). If the structure cannot be built, the input is the SCF with the vc-relax edits and the report says why.
- **Fields**: **Surface (stacked axis)**, **Flip the surface**, **Minimum vacuum (Å)**, **Adsorption distance (Å)**
  (added only with a molecule), **Molecule SCF (optional)**, **Complete edge polyhedra (O + H)** with **Edge metals**
  and **Reconnect cut H**, **k-point grid** (empty = the SCF's, rescaled), **Cell degrees of freedom** (`cell_dofree`,
  `2Dxy` relaxes only the plane) and **Fixed atoms** (`if_pos 0 0 0`).

Code: `core/calc_create/types/slab.py`, `slab_fields.py`, geometry in `core/calc_create/surface/`
(`slab.py`, `fixing.py`, `kmesh.py`, `report.py`).
