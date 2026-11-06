# Automatic detection

Each file is classified by what it **contains** (`core/sniff.py`), never by name: `bands.in` may be a `pw.x` or a
`bands.x` input. Each calculation module then declares the **roles** (`FileRole`) it needs and `core/detection.py`
runs every module of `REGISTRY` over the folder.

| Badge | Module | Needs |
|---|---|---|
| `BANDS` | bands | pw.x `bands`, bands.x output, Fermi energy (SCF) |
| `PDOS` | PDOS | `pdos_atm#*` files (in the folder or `orbitals/`), SCF/NSCF |
| `RELAX` | relax / vc-relax | pw.x output with `calculation` relax/vc-relax |
| `SCF` | SCF convergence | pw.x output |
| `CALC` | generic | any QE output/input (enables Summary and 3D) |

- Missing SCF: looked up in sibling `*scf*` folders. Any missing role can be mapped by hand (mapping dialog,
  remembered per folder in `.lain/`).
- Spin-polarized: bands from two `bands.x` runs (`spin_component` 1 and 2) and two-channel PDOS are recognized.
- Cached by `(path, mtime, size)`; `sniff` reads only the head and tail of large files.

See the diagram in [Architecture ▸ Detection](../architecture/detection.md).
