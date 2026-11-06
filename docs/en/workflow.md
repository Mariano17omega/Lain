# Recommended workflow

```mermaid
flowchart TD
    A[Converged SCF<br/>cutoff, k-points] --> B[Relax / VC-Relax]
    B --> C[SCF of the<br/>final structure]
    C --> D[Bands]
    C --> E[PDOS]
    C --> F[Charge / Charge difference]
    C --> G[Slab]
    G --> H[Supercell]
    H --> I[Molecule on surface]
    I --> J[Adsorption energy]
```

## Suggested order

1. **SCF** with tested cutoffs and k-mesh. It is the base: almost every "Criar cálculo" type starts from an SCF.
2. **Relax** (positions) or **VC-Relax** (positions + cell). Follow `|ΔE|` and force in the [relax plot](plots/relax.md).
3. **Converged SCF**: from the context menu of a converged relax/vc-relax output, "Gerar SCF convergido" creates the
   `.in` with the final structure.
4. From the final SCF:
    - **Bands** (pw.x `bands` + `bands.x`) — [plot](plots/bands.md);
    - **PDOS** (NSCF + `projwfc.x`) — [plot](plots/pdos.md); join both in **Bands with DOS**;
    - **Charge** / **Charge difference** (`pp.x`) to view in XCrySDen.
5. **Surfaces**: Slab (opens vacuum) → Supercell (repeats the cell) → Molecule on surface → run the SCFs and compute
   the [adsorption energy](features/adsorption-energy.md).

## Daily loop

```mermaid
sequenceDiagram
    actor U as You
    participant L as Lain
    participant C as Cluster
    U->>L: Create calculation (folder + .in + .qsub)
    U->>L: Send to cluster (preview, new files only)
    L->>C: rsync (ssh)
    U->>L: Cluster mode ▸ Submit… (confirm)
    L->>C: cd folder && chmod a+x && qsub
    U->>L: Queue (top bar) follows the job
    U->>L: Sync (preview) ▸ download results
    U->>L: Plot / Summary / 3D
```

!!! tip "Never skip the SCF"
    Bands, PDOS and charge read the Fermi energy and the structure from the SCF. Keep it close: Lain looks for it in
    sibling `*scf*` folders.
