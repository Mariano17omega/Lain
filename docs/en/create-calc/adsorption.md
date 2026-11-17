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
  table; the parameters of each rule are shown only when it is chosen) and `etot_conv_thr`.
- **Saw-like field and dipole correction** (the `tefield` and `dipfield` boxes are shown in the Padrão mode too), as
  in the [Slab](slab.md): they start as the surface's SCF has them. The ramp is placed again in the middle of the
  vacuum left above the molecule (the surface's may fall on it), unless `emaxpos`/`eopreg` are typed; `geracao.md`
  shows the old `emaxpos` when it changes. Without the correction, the warning under `dipfield` explains why to turn
  it on (the molecule sits on one side only); another shows when the choice differs from the surface's SCF: for the
  adsorption energy, the complex and the clean surface need the same one. Neither blocks "Create".
- The window has tabs (Surface / Molecule / Fixed atoms) and the **3D view** highlights fixed atoms.
- **Maximum steps** (`nstep`, default 100, shown in the Padrão mode too) and the commented line
  `! restart_mode = 'restart'` in `&CONTROL` are the [Relaxation](relax.md)'s: if the relax does not converge,
  uncomment the line and run again.

Code: `core/calc_create/types/adsorption.py`, `adsorption_fields.py`, `adsorption_fixed.py`;
`core/calc_create/surface/` (`candidates.py`, `adsorb.py`, `merge.py`, `molecule.py`, `fixing.py`).
