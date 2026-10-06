# Product Requirements Document (PRD) — Lain: QE Studio

## 1. Overview and Objectives

**Lain: QE Studio** is a native desktop application (Linux/Windows) built with Python and PyQt6 to manage, synchronize, and visualize scientific simulations performed with the *ab initio* **Quantum ESPRESSO (QE)** suite.

The system acts as a specialized file manager for solid-state physics and materials science data. It eliminates the need for repetitive manual plotting scripts by automating calculation type detection, data post-processing, and publication-ready scientific plot generation.

### 1.1. MVP Scope
- **Target Calculations:** Electronic Band Structure and Projected Density of States (PDOS / DOS).
- **Synchronization:** Download (*pull*) from the HPC cluster via SSH/Rsync. Upload (*push*) is limited to adding new files of one calculation folder (spec 27): it never overwrites or deletes anything on the cluster and always shows its plan first.
- **Configuration:** 100% driven by `config.yaml`. There will be no graphical settings/preferences window in the MVP.

---

## 2. Interface Architecture and UX (Design System)

The interface employs a modern *Full-Height* layout without floating blocks or disconnected frames, strictly following the Design System defined in `Documentation/design system (UX)`.

### 2.1. Layout Components

1. **Left Activity Bar (Far Left):**
   - Quick access to core modules: Folder Explorer, File Grid, Cluster Sync, Generate Plot, and Theme Toggle.
   - Remote cluster connection status indicator.

2. **Switchable Left Panel (Contextual):**
   - **Default Mode (Navigation):** Displays the hierarchical local project directory tree.
   - **Plot Mode (Active Tuning):** Upon triggering plot generation, the folder tree is hidden and replaced by the **Plot Parameters Panel** (X and Y axis limits, colors, line widths, Fermi-relative energy shift, and legend settings). The user can toggle back to the directory tree at any time via a top/side toggle button.

3. **Central / Right Workspace (Work & Visualization Area):**
   - **File View Tab:** Grid or list view of files and subdirectories for the active simulation (with distinct icons by extension: `.in`, `.out`, `.dat`, `.gnu`, images).
   - **Text Viewer Tab:** Quick preview of QE input cards and log outputs.
   - **Scientific Plot Tab (Matplotlib Canvas):** Renders the scientific figure centered with preserved aspect ratio (preventing image stretching or distortion). Includes an interactive navigation toolbar (pan, zoom, reset, export).

### 2.2. Visual Guidelines & Theming
- **Themes:** Native support for Dark Mode (high-contrast, low eye strain for lab work) and Light Mode (for publication/report figure preparation).
- **Typography:** *Inter* font family for UI controls and *JetBrains Mono* for numerical values, file names, and paths.
- **Style Sheet Modularization:** Styling must be split across multiple modular `.qss` files organized by component/domain inside logical subdirectories (avoiding a monolithic QSS file).

---

## 3. Heuristics and Automatic Calculation Detection

The system dynamically scans the selected directory to determine the calculation type without requiring mandatory user intervention.

### 3.1. Standard Naming Heuristics
- **Electronic Band Structure:** Simultaneous presence of SCF output (`scf*.out`), bands input/output (`bands*.in`, `bands*.out`), and numeric data files (`*.gnu` or `*.dat.gnu`).
- **PDOS / DOS:** Simultaneous presence of SCF output (`scf*.out`), NSCF output (`nscf*.out`), Projwfc output (`projwfc*.out`), and a mandatory `orbitals/` subfolder containing files matching `pdos_atm#*_wfc#*`.
- **Structural Optimization (Relax / Vc-relax):** Presence of `relax*.in` / `relax*.out` or `vc-relax*.in` / `vc-relax*.out`.

### 3.2. Fallback Mechanism & Content Inspection
- If filenames deviate from standard naming conventions, the engine must inspect file headers and QE namelists/cards (e.g., `calculation = 'bands'`, `calculation = 'scf'`, `&projwfc`, etc.).
- If automatic detection fails completely, the system displays an alert modal containing manual file selector fields, allowing the user to map each required file explicitly.

---

## 4. Scientific Engine and Plot Generation

### 4.1. Processing Libraries
- Extraction of crystal structures, eigenvalues, and k-points must prioritize established Python materials science libraries (e.g., **ASE**, **Pymatgen**, **qe-tools**) rather than custom regexes prone to Fortran formatting discrepancies.

### 4.2. Electronic Band Structure
- **Fermi Energy ($E_F$):** Automatically parsed from the corresponding SCF output file.
- **High-Symmetry Path:** Symmetry points and labels ($\Gamma, M, K, X$, etc.) extracted from the `K_POINTS crystal_b` card in the bands input file (`bands*.in`).
- **Eigenvalues:** Parsed from the `.gnu` file or the `bands.x` output.
- **Adjustments:** Zero-centering to the Fermi level ($E - E_F = 0\text{ eV}$) enabled by default, with an option to display absolute energy values.

### 4.3. Projected Density of States (PDOS / DOS)
- Parsed from files inside the `orbitals/` subfolder.
- Plots Total Density of States (DOS) and projected orbital contributions decomposed by atomic species and orbital angular momentum ($s, p, d, f$).
- Energy axis aligned with $E_F$ from the corresponding SCF calculation.

### 4.4. Storage and Export
- **Automatic Subfolder:** All generated figures must be saved automatically to a `plots/` subfolder inside the active simulation directory.
- **File names (spec 32):** the folders from the project root down to the simulation, joined by `-`, then the plot's name (`<local_root>/projeto_ilita/bulk/bandas` → `projeto_ilita-bulk-bandas-bands.png`).
- **Data export (spec 32):** the band structure, PDOS and bands + DOS figures also write a `.csv` with the plotted data (same name, `;` between columns, decimal comma, column names on the first line).
- **Output Formats:** Support for vector export (`SVG`, `PDF`) and high-resolution raster images (`PNG` at 300 or 600 DPI), according to `config.yaml`.

---

## 5. Remote Synchronization Engine (HPC Cluster)

### 5.1. Protocol & Connection
- Connects to the remote cluster via SSH/Rsync using credentials configured in `config.yaml`.
- Pull synchronization (cluster to local) in the MVP.
- Push (local to cluster, spec 27) only adds files the cluster does not have, for one calculation folder (never the
  whole project): a file that exists remotely is never changed (`--ignore-existing`), nothing is deleted, and the
  plan preview is always shown before sending, whatever `sync.confirm_plan` says.

### 5.2. Timestamp Comparison & Sync Rules
- When "Synchronize" is clicked, the app compares folder timestamps between the cluster and local counterpart:
  - **Cluster is newer:** Downloads updated files.
  - **Local is newer:** Performs no transfer and displays an informational warning to the user.

### 5.3. Exclusion Filters (Rsync Exclude)
- Heavy, temporary, or non-essential files must be excluded from transfer:
  - Temporary directories: `tmp/`, `*.save/`.
  - File patterns: `*.amn`, `*.mmn`, `*.unk*`, `*.wfc*`, and temporary runtime binaries.
  - The complete exclusion list must be customizable in `config.yaml`.

### 5.4. Conflict Resolution
- Whenever synchronization identifies that an existing local file would be overwritten, a prompt must ask the user:
  - Overwrite this file only.
  - Overwrite all conflicting files in this folder.
  - Skip / keep local file.
  - Cancel the synchronization entirely.

### 5.5. UI State During Synchronization
- Displays a circular progress indicator.
- Modally locks the GUI during transfer to prevent concurrent access to files in transit, with an explicit cancel button.

---

## 6. System Configuration (`config.yaml`)

There is no in-app settings screen in the MVP. All operational parameters are loaded exclusively from a central `config.yaml`, covering:

1. **Paths:**
   - Local simulation root directory.
   - Remote HPC cluster root directory.
2. **Remote Connection:**
   - Cluster Host/IP (e.g., `cluster.example.org`).
   - SSH user and authentication credentials (password or SSH key path).
   - SSH port.
3. **Sync Exclusion Rules:**
   - Configurable list of directories and file extensions to exclude via Rsync.
4. **Default Plotting and Visual Parameters:**
   - Default energy boundaries ($E_{\min}, E_{\max}$).
   - Default color palette for orbitals and energy bands.
   - Default export formats (`png`, `svg`, `pdf`) and target DPI resolution.

---

## 7. Non-Functional Requirements & Software Architecture

- **Calculation Modularity:** The architecture must allow easy addition of future post-processing modules (e.g., combined Bands + PDOS, dielectric function from `epsilon.x`, adsorption energy curves, vibrational phonon dispersions).
- **Offline Operation:** The application must function 100% autonomously offline when viewing, analyzing, or plotting locally synchronized simulations.
- **Performance:** Curve loading and visualization update latency must stay below 500 ms for structures with up to 100 bands.
- **Data Integrity:** No file overwrite or synchronization action may execute without explicit confirmation when conflicts arise.
