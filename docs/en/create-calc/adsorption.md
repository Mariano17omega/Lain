# Molecule on surface

Places a molecule **on one surface atom or between two**, as a `relax`.

- **Inputs**: the SCF of a **relaxed** surface (a bulk is refused) and a second SCF for the **molecule** (read, never
  changed).
- **Files**: `relax_<prefix>.in` (`prefix = '<surface>-<formula>-<site>'`), `.qsub`, `geracao.md`. If no structure is
  possible, the input is the surface's SCF with the relax edits and the report explains.
- **Fields**: **Molecule anchor atom** (automatic: the heaviest), **Coordination** (*monodentate* or *bidentate*, at the
  midpoint), **Choose the site by** *candidate list* (a table with letters for equivalent sites via `spglib`,
  **symmetry tolerance**) or *coordinates* (fractions x y z, tolerance in Å), **relative adsorption distance**,
  **Δx/Δy/Δz**, **minimum clearance**, **minimum vacuum**, **surface window**, **fixed atoms** (surface only, or a
  table) and `etot_conv_thr`.
- The window has tabs (Surface / Molecule / Fixed atoms) and the **3D view** highlights fixed atoms.

Code: `core/calc_create/types/adsorption.py`, `adsorption_fields.py`, `adsorption_fixed.py`;
`core/calc_create/surface/` (`candidates.py`, `adsorb.py`, `merge.py`, `molecule.py`, `fixing.py`).
