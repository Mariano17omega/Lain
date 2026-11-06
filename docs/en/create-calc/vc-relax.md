# VC-Relax

The relax plus `&CELL`: the cell relaxes too.

- **Files**: `vc-relax_<prefix>.in`, `vc-relax.qsub`.
- **Fields** of the relax plus **Cell dynamics** (`cell_dynamics`: `bfgs`, `damp-pr`, `damp-w`) and **Pressure**
  (`press`, kbar, default 0).
- Inherits from `RelaxType`.

Code: `core/calc_create/types/vc_relax.py`; template `qsub/vc-relax.qsub.j2`.
