# Glossary

| Term | Meaning |
|---|---|
| **QE** | Quantum ESPRESSO (7.1 or newer) |
| **pw.x** | QE's plane-wave program: SCF, NSCF, bands, relax, vc-relax |
| **bands.x** | post-processes `pw.x` bands (`.gnu`/`.dat`) |
| **projwfc.x** | projects states on atomic orbitals → `pdos_atm#*` files |
| **pp.x** | post-processing (charge density, XSF) |
| **SCF / NSCF** | self-consistent cycle / non-self-consistent calculation on a mesh |
| **relax / vc-relax** | optimization of positions / of positions and cell |
| **BFGS** | optimization algorithm used by relax |
| **PDOS** | projected density of states |
| **E_F, VBM, CBM, HOMO/LUMO** | Fermi energy, valence band maximum, conduction band minimum, frontier orbitals |
| **`prefix`, `outdir`, `pseudo_dir`** | `&CONTROL` keys of `pw.x` |
| **`.qsub`** | job script (SGE) |
| **SGE / `qsub` / `qstatus` / `qdel`** | queue manager, submit, query, remove |
| **`#$ -N`** | job name |
| **`<prefix>.EXIT`** | file that makes `pw.x` stop cleanly |
| **NP / NK (pools)** | job cores / `-nk` of `pw.x` |
| **Badge** | label of the detected type: BANDS, PDOS, RELAX, SCF, CALC |
| **Project** | first-level folder of `local_root` |
| **Simulation unit** | folder with the inputs and outputs of one calculation |
| **`.lain/`, `.plot`, `tmp_remote/`, `trash/`** | see [Folder organization](folders.md) |
| **Cluster mode** | browsing the remote files — [Remote mode](remote-mode.md) |
| **Slab / supercell** | cell with vacuum / repeated cell |
| **Monodentate / bidentate** | adsorbate bound to one / two atoms |

## Interface: Portuguese ↔ English

| Português | English |
|---|---|
| Criar cálculo | Create calculation |
| Sincronizar / Baixar / Enviar ao cluster | Sync / Download / Send to cluster |
| Modo cluster (Ver arquivos do cluster) | Cluster mode |
| Submeter… / Cancelar simulação… / Apagar… | Submit… / Cancel simulation… / Delete… |
| Gerar gráfico / Exportar gráfico | Generate plot / Export plot |
| Bandas com DOS | Bands with DOS |
| Visualização 3D | 3D view |
| Resumo / Comparar com… | Summary / Compare with… |
| Recarregar config.yaml | Reload config.yaml |
| Padrão / Avançado | Standard / Advanced |
