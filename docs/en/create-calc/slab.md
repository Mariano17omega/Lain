# Slab

Opens **vacuum** along an axis of the bulk's SCF, as a `relax` (or a `vc-relax`, if chosen). No Miller plane is cut: the bulk cell keeps its layer
and one axis grows until the requested vacuum (the minimum, plus the height of a molecule and the adsorption distance
if the molecule's SCF is given).

- **Calculation** (`calculation`, shown in the Padrão mode too):
    - `relax` (default): the cell stays fixed and the plane at the bulk's lattice parameter. This is right for the
      **surface of a crystal**: the slab stands for a semi-infinite solid, and letting the plane relax would let the
      surface stress of a thin slab shrink it (and adsorption energies would carry that artefact).
    - `vc-relax`: the plane relaxes too (`cell_dofree`, default `2Dxy`), for an **isolated 2D material**.
- **Saw-like field and dipole correction** (two boxes, shown in the Padrão mode too): **`tefield`** and
  **`dipfield`**, each writing its own key and both starting as the source SCF has them (off for a bulk's SCF, which
  never has them). Both on give Bengtsson's correction; `dipfield` without `tefield` is ignored by pw.x, and the
  window says so.
    - With `tefield` on, the Avançado mode shows **`edir`** (default 3: the vacuum is along c), **`emaxpos`**,
      **`eopreg`** and **`eamp`** (default 0: the correction alone, no external field). `emaxpos` and `eopreg` come
      filled with the value computed so that the ramp of the potential sits in the middle of the generated slab's
      vacuum; a typed value is written as it is, and an emptied field goes back to the computed one. Outside
      `(0, 1)`, or an `edir` other than 1 to 3, the field shows the error.
    - **Warnings under the field, which never block "Create"**: on an asymmetric slab (bottom layer fixed, or no
      symmetry turns c over) without the correction, the warning under `dipfield` explains that the dipole interacts
      with the periodic images and the energy comes to depend on the vacuum, and asks for both boxes. There are
      warnings too for a ramp less than 3 Å from an atom (or with atoms inside it), `eamp ≠ 0`, `edir ≠ 3` and a
      `tefield` with no effect. The same texts are in the "Files" tab.
    - With `tefield` pw.x uses no symmetry; in a `vc-relax`, `tstress` is removed (with it pw.x would turn the
      stress off) and the stress has no term for the field. `geracao.md` says the keys, where the ramp went and how
      far from the nearest atom. The complex and the clean surface of an adsorption need the same choice.
- **Files**: `relax_<prefix>.in` or `vc-relax_<prefix>.in` (`prefix = '<prefix>-slab-<hkl>'`), the `.qsub` and
  `geracao.md` (a report of what was done, with the chosen calculation). If the structure cannot be built, the input is
  the SCF with the relaxation's edits and the report says why.
- **Fields**: **Surface (stacked axis)**, **Flip the surface** (the atoms stay inside the box), **Minimum vacuum (Å)**,
  **Adsorption distance (Å)** (shown and added only with a molecule), **Molecule SCF (optional)**, **Complete edge
  polyhedra (O + H)** with **Edge metals** (shown only when that option is on) and **Reconnect cut H**, **k-point
  grid** (empty = the SCF's, rescaled), **Cell degrees of freedom** (`cell_dofree`, vc-relax only; `2Dxy` relaxes only the plane) and
  **Fixed atoms** (`if_pos 0 0 0`; the parameters of each rule are shown only when it is chosen).
- **Maximum steps** (`nstep`, default 100, shown in the Padrão mode too) and the commented line
  `! restart_mode = 'restart'` in `&CONTROL` are the [Relaxation](relax.md)'s: if the relax does not converge,
  uncomment the line and run again.

Code: `core/calc_create/types/slab.py`, `slab_fields.py`, geometry in `core/calc_create/surface/`
(`slab.py`, `fixing.py`, `kmesh.py`, `report.py`, `dipole.py`); the fields of the field and its correction in `types/dipole_fields.py`.
