# Folder organization

Lain does not require particular file names, but it follows conventions about **structure**. If you keep to them,
detection, sync and "Criar cálculo" work with no extra configuration.

## Projects and simulation units

- `paths.local_root` is the root. **Each first-level folder is a project** (a system/compound under study).
- Inside a project, the **simulation units** (a folder with the inputs and outputs of one calculation) live at any
  depth; they need no mark.
- `trash` is a reserved name at the root (it cannot be a project name).

```text
~/qe_simulations/                  ← paths.local_root
└── Pt111/                         ← project
    ├── 0_SCF/                     ← unit: scf_Pt.in, scf.out, scf.qsub
    ├── 1_Relax/                   ← relax_Pt.in, relax.out, relax.qsub
    ├── 2_Bands/                   ← pw.x bands + bands.x (band_up/band_dw with spin)
    ├── 3_PDOS/                    ← scf, nscf and projwfc.x
    │   └── orbitals/              ← *pdos_atm#* files (or directly in the folder)
    └── plots/                     ← created by Lain
```

## Rules detection uses

- **Bands**: a `pw.x` with `calculation='bands'`, the `bands.x` output (`.gnu`/`.dat`) and the Fermi energy from the
  SCF. If the SCF is not in the folder, Lain looks in sibling folders with `scf` in the name (`*scf*`); whatever is
  still missing can be mapped by hand (remembered per folder).
- **PDOS**: `*pdos_atm#*` files directly in the folder or in `orbitals/`.
- **Relax / vc-relax**: the `pw.x` output with the matching `calculation`.
- Everything is recognized by **content** (`bands.in` may be a `pw.x` or a `bands.x` input).

## Folder numbering in "Criar cálculo"

"Criar cálculo" prefixes the new folder with a growing number: `0_Relax`, `1_Bands`, `2_PDOS`… (next = largest
number present + 1; gaps are not reused). You may add suffixes (site, tag). An existing folder is never overwritten
(`_2`, `_3`…).

## On the cluster

Mirror the local tree under `paths.remote_root`:

```text
/home/user/qe_simulations/         ← paths.remote_root
├── Pt111/…                        ← same subfolders as local
└── trash/                         ← created by "Apagar…" (never emptied by Lain)
```

- Sync mirrors `local_root/<sub>` ⇄ `remote_root/<sub>`. Use folder and file names with letters, digits, `.`, `_`, `+`
  and `-` if you want to submit, cancel or delete from cluster mode (names with spaces are refused).
- Each job folder should hold the `.qsub`; the job name (`#$ -N`) should match the one in the queue (`qstatus`).

## What Lain writes (and where)

| What | Where |
|---|---|
| Folder mappings, grids, PDOS atom selections, favorites/recents | `<local_root>/.lain/` |
| Plot settings `<kind>.plot`, exported figures, `view3d.plot` | `<simulation>/plots/` |
| Local copy of a remote plot + its exports | `<folder>/tmp_remote/` and `tmp_remote/plots_remote/` |
| Interface state (QSettings) | `<paths.data>/settings.ini` or `~/.config/qe-studio/` |
| Log, instance lock, `submitted_jobs.log` | `<paths.data>` or `~/.local/share/qe-studio/` |
| Cluster trash | `<remote_root>/trash/` |

`.lain/`, `tmp_remote/` and `trash/` (at the root) are **never** synced; `plots/` and `*.plot` never go up to the
cluster. Nothing else is written inside simulation folders.
