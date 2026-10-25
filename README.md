# Lain: QE Studio

[![CI](https://github.com/Mariano17omega/Lain/actions/workflows/ci.yml/badge.svg)](https://github.com/Mariano17omega/Lain/actions/workflows/ci.yml)

Desktop app (PyQt6) to browse, sync and plot [Quantum ESPRESSO](https://www.quantum-espresso.org/)
simulations (QE 7.1 or newer). See [`specs/Archived/spec_0-PRD.md`](specs/Archived/spec_0-PRD.md) for the product
requirements, [`specs/README.md`](specs/README.md) for the index of change specs and
`Documentation/design system (UX)/` for the design system the UI follows.

- **Automatic detection** of band-structure, PDOS and relax runs. File names are only hints:
  every file is identified by its content (`bands.in` can be a pw.x or a bands.x input), so
  tutorial-style names (`al.scf.out`, `si.band.in`) and flat or `orbitals/` PDOS layouts are
  recognised. A missing SCF output is looked up in sibling `*scf*` folders, and anything still
  missing can be mapped by hand (remembered per folder).
- **Publication plots** (matplotlib) with Γ-labelled high-symmetry paths, E − E_F zeroing (or
  VBM / mid-gap / absolute), gap readout, spin-polarized runs with both channels (bands from the
  two bands.x runs, `spin_component` 1 and 2: overlaid or side by side, a gap per channel; PDOS
  mirrored, overlaid, one channel or summed), PDOS grouped by species and/or orbital, relax / vc-relax progress (|ΔE| and total force per BFGS step against the
  convergence thresholds, log or linear), and a tuning panel. Figures go to each simulation's `plots/` folder as PNG
  (300/600 DPI), SVG and PDF, named from the project root (`<project>-<folders>-<plot>.png`), with a `.csv` of the
  plotted data next to bands, PDOS and bands + DOS figures; existing files are never replaced without asking.
- **Pull-only cluster sync** over rsync + ssh with configurable excludes (`tmp/`, `*.save/`,
  wavefunctions, …), a per-file conflict prompt and a cancellable progress dialog.
- **Dark, light and system themes** (`ui.font_scale` for bigger text, AA contrast, visible keyboard focus, Ctrl+1..4), Inter + JetBrains Mono, Portuguese or English UI (see [Language](#language)).

## Setup

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/). Cluster sync also needs `rsync`
(≥ 3.1) and `ssh` on `PATH`.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv sync
cp config.example.yaml config.yaml   # then edit paths and cluster settings
uv run lain                           # or: uv run lain --config /path/to/config.yaml
```

To start it from any terminal by typing just `lain`, install it as a uv tool (editable, so code
changes apply without reinstalling; rerun with `--force` after changing dependencies or entry
points):

```bash
uv tool install --editable .
lain
```

From any folder, `lain` reads the `config.yaml` at the root of this repository (the checkout the
editable install runs from), unless the folder you are in has a `config.yaml` of its own. A
non-editable install (`uv tool install .` without `--editable`) has no checkout to look in: keep the
config in `~/.config/qe-studio/config.yaml`, point `$QE_STUDIO_CONFIG` at it, or pass `--config`.

### Desktop integration (optional)

So the window manager shows Lain's icon in the taskbar and the application menu lists it, install
the launcher and icons for your user (nothing is installed unless you run this; it needs the
`lain` command on `PATH`, see above):

```bash
uv run python scripts/install_desktop.py              # into $XDG_DATA_HOME (~/.local/share)
uv run python scripts/install_desktop.py --prefix DIR # or into another data directory
```

All settings live in `config.yaml` (there is no settings window); see
[`config.example.yaml`](config.example.yaml) for every key. Lain looks for it in `--config`,
`$QE_STUDIO_CONFIG`, `./config.yaml`, the repository's `config.yaml` (editable install), then
`~/.config/qe-studio/config.yaml`. `config.yaml` is git-ignored because it may hold credentials.

### Portable data (`paths.data`)

Besides `config.yaml`, Lain keeps the state of the interface (window size, panel widths, theme, last
folder…) in `~/.config/qe-studio/QE Studio.conf` and a little data of its own (the instance lock, the
settings of a read-only project root) in `~/.local/share/qe-studio`. Set `paths.data` to keep both in
a folder of your choice instead:

```yaml
paths:
  data: data   # relative to the folder of this config.yaml
```

The interface state then lives in `<data>/settings.ini`. Copy the folder holding `config.yaml` and
`data/` anywhere and Lain starts there as you left it. The first start with a new `paths.data` copies
the current interface state into it once (the old file is kept). A change of `paths.data` applies when
Lain restarts. The log and caches stay in `~/.cache/qe-studio`, and each project's own settings stay in
`<local_root>/.lain/`. A `data/` folder at the root of this repository is git-ignored.

### Cluster authentication

- **Key (recommended):** `auth: key` and `key_path`. ssh runs non-interactively, so a key with a
  passphrase must be loaded in `ssh-agent`.
- **Password:** `auth: password` (see below).
- The cluster's host key must already be in `~/.ssh/known_hosts`: connect once with
  `ssh user@host` in a terminal. Unknown keys are never accepted automatically.

`auth` only chooses the method (`key` or `password`); it never holds the password itself. Which
fields apply to each method:

| field | used with | meaning |
|---|---|---|
| `host`, `port`, `user` | both | where and as whom to log in |
| `auth` | both | `key` or `password` |
| `key_path` | `key` | path to your **private** key (default `~/.ssh/id_ed25519`); ignored with `password` |
| `password_env` | `password` | **name** of the environment variable holding the password (not the password) |
| `password` | `password` | the password itself, in plain text (discouraged) |

#### Connecting with an SSH key

No password to store or type. One-time setup:

```bash
ssh-keygen -t ed25519                  # skip if ~/.ssh/id_ed25519 already exists (never overwrite it)
ssh-copy-id -i ~/.ssh/id_ed25519.pub -p 22 your_user@cluster.example.org
ssh -i ~/.ssh/id_ed25519 your_user@cluster.example.org   # must log in without asking for the cluster password
```

The last command also adds the cluster to `~/.ssh/known_hosts`. Then:

```yaml
paths:
  local_root: ~/qe_simulations
  remote_root: /home/your_user/qe_simulations   # matching folder on the cluster

cluster:
  host: cluster.example.org
  port: 22
  user: your_user
  auth: key
  key_path: ~/.ssh/id_ed25519
  connect_timeout: 10
```

If the key has a passphrase, load it before starting Lain, because ssh runs non-interactively:

```bash
eval "$(ssh-agent -s)"                 # only if no agent is running
ssh-add ~/.ssh/id_ed25519
uv run lain
```

#### Connecting with a password

`host`, `user` and `remote_root` must be set, or sync stays disabled:

```yaml
paths:
  local_root: ~/qe_simulations
  remote_root: /home/your_user/qe_simulations   # matching folder on the cluster

cluster:
  host: cluster.example.org
  port: 22
  user: your_user
  auth: password
  password_env: QE_STUDIO_SSH_PASSWORD   # name of the environment variable holding the password
  connect_timeout: 10
```

The password reaches Lain in one of three ways, most recommended first:

1. **Typed when asked (simplest).** With the variable unset, Lain asks for the password
   ("Senha do cluster") at the first sync and keeps it in memory for the session only; it is never
   saved. The start-up warning "auth: password, mas a variável … não está definida" is expected then.
2. **From the environment variable** named by `password_env`; Lain then asks nothing:

   ```bash
   export QE_STUDIO_SSH_PASSWORD='my_password'
   uv run lain
   ```

3. **Inline in `config.yaml` (discouraged).** `password: my_password` under `cluster:` works, but it
   is plain text on disk, and Lain warns about it.

Either way the password reaches ssh through `SSH_ASKPASS` (`qe-studio-askpass`) and never appears
on a command line or in logs; `sshpass` is not needed. After editing the file, use "Recarregar
config.yaml" or restart Lain.

#### "Authentication refused by the cluster"

ssh reached the cluster and the cluster said no, so host and port are right. Check, in order:

- `user` is your real login (not the `seu_usuario` placeholder of the example file).
- `auth` is exactly `key` or `password`, appears once, and does not contain the password.
- `key`: `key_path` exists and its public key is in `~/.ssh/authorized_keys` on the cluster; a
  passphrase-protected key is loaded in `ssh-agent`.
- `password`: the variable named by `password_env` is set in the environment that started Lain
  (an app launched from the desktop menu does not see a variable exported in another terminal).
- Lain reads the config you think it does (lookup order above); `uv run lain --verbose` logs it.

Test outside Lain with the same values; if this fails too, the problem is the credential, not the app:

```bash
ssh -p 22 -i ~/.ssh/id_ed25519 your_user@cluster.example.org   # drop -i for password login
```

### How sync decides

"Sincronizar" pulls the selected folder (or the whole project) from `remote_root`. rsync lists the
files that differ, comparing their content (`sync.checksum`, on by default: a file that is the same
on both sides is never listed, whatever its date); each one is then compared with the local copy:

| Situation | Action |
|---|---|
| file only on the cluster | downloaded |
| cluster copy newer, or same date and size but other content | you choose: overwrite this / overwrite all in this folder / keep local / cancel |
| local copy newer | kept, reported |

`sync.checksum: false` goes back to date and size, which is faster on very large trees: the
comparison reads every file on both sides. The upload never uses it.

A folder whose differing files are all newer locally is reported as "local is newer" and nothing
is transferred (PRD §5.2). Files that exist only locally, such as generated `plots/`, never block
a pull.

### Cluster jobs

With the cluster configured, the top bar shows your jobs left of the LED: "Executando: <name>" for
a job of yours that is running (with several, the name changes every `jobs_rotate_seconds`), or
"Nenhum job em execução". A click opens the whole queue of the cluster, in a green "Running" bar
and an amber "Queued" bar, with the name, owner, start or submission time (month/day and hour:minute,
as the cluster writes them, without the year or the seconds) and the cores of each job; yours are in
bold. The tooltip of a row keeps the job-ID, the queue and the full date. Lain reads it
by running `cluster.jobs_command` on the cluster over ssh, with the login and options of the sync,
when the window opens and then every `jobs_poll_seconds` while it is active. The last answer is kept
in memory for the session ("Atualizar" asks again); nothing is written to disk. Each query is a real
login, so it also turns the LED green or red.

```yaml
cluster:
  jobs_command: qstatus -a     # empty turns the indicator off
  jobs_poll_seconds: 300       # at least 30
  jobs_rotate_seconds: 5
```

The listing read is the one of `qstatus -a` (SGE): "Running jobs:" and "Waiting jobs:" sections,
one job per line. ssh runs the command without a terminal, so the `PATH` of your login shell may be
missing: if the indicator says "Jobs indisponíveis" with "comando … não foi encontrado", give the
full path (`which qstatus` on the cluster), e.g. `jobs_command: /opt/sge/bin/qstatus -a`. A refused
login or a missing command stops the automatic queries until "Atualizar" or "Recarregar
config.yaml". With `auth: password` and no password known, Lain asks for it only when you click the
indicator, and keeps it for the session as the sync does.

### Cluster mode

The sidebar's **Cluster** button (also "Cluster > Ver arquivos do cluster") shows the cluster's
folders in the tree and their files in the grid, on a red background, until it is clicked again:
then the local panels come back exactly as they were. Nothing local is read or changed meanwhile.

- The view starts at the cluster side of the local folder you were in (or the closest folder above
  it that the cluster has) and never goes above the selected project, or `remote_root`.
- Each folder is listed over ssh with `rsync --list-only`, with the login and options of the sync.
  A spinner shows while a folder has no answer yet. Listings are kept in memory for the session:
  a folder seen before shows at once, and is listed again in the background after 60 s. F5 and
  "Atualizar" list the folder shown again.
- The list shows name, size and date only: badges and file states need the files' content.
- Right-click an item for **Baixar** (one item at a time), **Plotar** (folders) or **Copiar
  caminho**. "Baixar" is the usual pull, with its preview and its questions before anything local is
  overwritten: of a folder into its local counterpart (created if missing), or of a single file of it.
- **Plotar**, and the sidebar's "Plot", "Gerar" and Ctrl+G while the mode is on, plot the selected
  folder (or the one shown, when nothing is selected) from a copy: the whole folder, less what
  `sync.exclude` leaves out, goes into `tmp_remote/` inside its local counterpart, and the figures
  and the `.plot` of the plot into `tmp_remote/plots_remote/` (named `<path>-tmp_remote-<plot>`). A
  bands folder and a PDOS folder selected together make the bands + DOS figure. Nothing else of the
  local folder is touched: each new plot overwrites the copy **without asking**, only inside
  `tmp_remote/`, and nothing in it is deleted. The preview shows only when a file is over 100 MB.
  The copies stay until you delete them; they show in the local tree, are never synced either way,
  and never mix into the detection of the folder that holds them. A project or the root is never
  copied.
- With `auth: password`, the password is asked when the mode is turned on, and kept for the
  session; a refused login is not retried until you ask ("Tentar de novo", "Atualizar", F5).
- Right-click a `.qsub` for **Submeter…** (spec 69). Lain lists the folder and asks the queue
  (`cluster.jobs_command`) again: if one of your running jobs has its `<name>.o<job-ID>` in that
  folder, nothing is submitted and a notice says which job; without the queue, nothing is submitted
  either. Otherwise a dialog shows the folder and the exact commands, `cd <folder> && chmod a+x
  <script> && qsub <script>`, and warns about a forgotten `*.EXIT` file (pw.x would stop at its
  first check). After "Submeter", the folder and the queue are checked once more, then the commands
  run over ssh; the notice says "Job <id> (<name>) submetido." and the queue on the top bar is asked
  again. The program is `cluster.submit_command` (`qsub`; empty turns the item off); a `qsub` that is
  not in the `PATH` of a non-interactive ssh needs its full path. Script and folder names (below
  `remote_root`) must use letters, digits, `.`, `_`, `+` and `-` only. The block relies on the job
  name in `qstatus` matching the `-N` of the script, and a job still in the queue leaves nothing in
  the folder, so it does not block.

## Usage

1. Pick a simulation folder in the explorer; badges show what was detected
   (BANDS, PDOS, RELAX, SCF, CALC), and outputs show `OK` / `INCOMPLETO`. Queue logs
   (`job.o12345`, `job.e12345`) show `SEM ERROS` when empty and `ERRO` otherwise; they and the
   submission scripts (`.qsub`, `.slurm`, `.pbs`) open read-only in a tab. A folder in the tree
   that holds a `CRASH` file or a non-empty `job.o<id>` gets a red `ERRO` tag (hover for the file
   that caused it), unless that log is a QE output that finished (`JOB DONE`: a job without
   `> scf.out`); the file icon in the tree's header lists the files in the tree too. The grid
   cards show only that state (list mode also shows sizes); `..`, Backspace or Alt+↑ go up a folder.
   The path in the top bar is clickable (long ones fold their middle levels into **…**; right-click
   copies it), and **Alt+←** / **Alt+→**, the ◀ ▶ buttons or the mouse side buttons walk back and
   forward through the folders visited. **Ctrl+F** in the explorer or the file grid opens a quick
   filter: part of a name (`*` and `?` are wildcards) and, under **Filtrar ▾**, the detected type of
   a folder (BANDS, PDOS…) or the state and kind of a file; **Esc** clears it. Folders added to
   **FAVORITOS** (right-click ▸ *Adicionar aos favoritos*) and the last 10 in **RECENTES** sit above
   the tree, remembered per project. Ctrl/Shift-click or Ctrl+A select several items in the grid:
   Enter opens the files, and the right-click menu offers **Abrir local de origem**, **Copiar** and,
   for two QE inputs, **Comparar**.
   Right-click a file or folder for **Abrir local de origem**, **Abrir com** (installed programs
   for its type, or any other), **Copiar** (paste it in the file manager or a terminal) and
   **Renomear** (never overwrites; tabs showing the item are closed). On an SCF output
   there is also **Plotar**, which previews its convergence (estimated accuracy against
   `conv_thr`, |ΔE| or total energy, and the magnetization of spin runs) without saving; the
   **Plotar SCF** button in the top bar does the same for the SCF output open in a tab.
   Every QE output (pw.x, bands.x, projwfc.x…) also has **Resumo**: a tab with its state
   (`Concluído` / `Incompleto` / `Erro`), WALL and CPU time, parallelization, memory, system,
   results (energies, Fermi / HOMO-LUMO and gap, magnetization, pressure and stress, forces, SCF and
   BFGS progress) and the warnings and errors, read from the file and never saved. **Copiar** puts
   it on the clipboard as text, **Atualizar** reads the file again (the job may still be running)
   and a double click on a row opens the output at the line it came from.
   Text files open in a viewer with line numbers, **Ctrl+F** search (F3 / Shift+F3 for the next and
   previous hit), coloured QE outputs (energies, errors, warnings, convergence) and **Ir à linha…**
   (Ctrl+L). A file above 4 MB shows its first 1 MB and last 2 MB (line numbers stay real); the
   banner offers **Abrir no editor externo** and **Carregar tudo** (up to 64 MB). Right-click a tab
   (or middle-click it to close it) for **Fechar** (Ctrl+W), **Fechar outras / à direita / todas**,
   **Copiar caminho** and **Revelar no explorador**.
   QE inputs get syntax colours and a check of how they are *written* (not of what the
   parameters mean): an unclosed quote, a namelist without its `/`, a line without `=`, an
   unbalanced parenthesis, a malformed logical or number, a misspelled namelist or card
   name, a bad card option. Problems are underlined in red, marked in the margin (hover for the
   message) and counted in a banner (**Ir ao primeiro**, **F8** / **Shift+F8**). Above the text, a
   strip of chips shows `calculation`, cutoffs, the `K_POINTS` grid and other key parameters (click
   one to go to its line). **Comparar com…** opens a tab that lists the parameters that differ
   (`1d-8` and `1.0e-8` are the same number) or shows the two files side by side.
   Any pw.x input (scf, nscf, bands, relax, vc-relax…) also has **Visualização 3D**: each click opens
   a window of its own (two clicks on the same file give two windows, each with its own settings) with
   the structure in 3D and, on the left, the panel of the clicked atom (named as QE numbers it, `O43`,
   with its species, mass, pseudopotential, positions, `if_pos`, starting magnetization and bonded
   neighbours), the display options (style, radius, bond factor, repetition, labels and their size,
   background, then the check boxes for bonds, cell, perspective and the **x, y, z** and **a, b, c**
   axes, each axes system with its own thickness), the species (colour, visibility) and the cell.
   Drag turns the view, Shift + drag or the middle button moves it, the wheel zooms; **R** or
   **Resetar vista** goes back to the initial view, **X**/**Y**/**Z** (the **Vista** menu) and
   **A**/**B**/**C** (keys only) look along an axis, **P** toggles the perspective. Under **Rotação**,
   **x+ x- y+ y- z+ z-** turn the structure 45° about that axis (right-hand rule) without changing the
   zoom. Clicking atoms never changes the zoom. A relax input shows its *input* geometry.
   Under **Medidas**, turn on **Distância** and click two atoms, or **Ângulos** and click three (the
   second is the vertex): each pair or trio adds a row to its table (`O43 - H59  0.965 Å`), in click
   order; **Copiar** puts them on the clipboard for a spreadsheet, **Apagar** removes the last measure
   made, **Limpar** removes all and Delete the selected rows. **Print** (above the view) saves the
   picture, as it is, at twice its pixels, to `plots/` of the calculation's folder as
   `<folders from the root>-<file>-3d.png` (a name that exists is never overwritten: `_2`, `_3`…).
   **Restaurar padrões**, at the foot of the panel, asks and then puts the options and the camera back
   to a new window's (the measures and the current atom stay).
   The view is remembered: closing a window whose options or camera you changed saves them in
   `view3d.plot`, in `plots/` of the calculation's folder, one section per file (two inputs of the same folder keep
   their own views), and the next window on that file opens as you left it. Opening and closing without
   a change writes nothing; **Restaurar padrões** followed by closing removes that file's section, and
   deleting `view3d.plot` brings every file of the folder back to the defaults. The measures are not saved.
   A pw.x input or output also has **Abrir com XCrysDen**, which starts the external
   [XCrySDen](http://www.xcrysden.org/) on the file (`xcrysden --pwi scf.in`, `--pwo` for an output).
   Put its install folder (or the `xcrysden` script) in `config.yaml`, under `paths:`, as
   `xcrysden_path`; while it is empty or wrong the item is disabled and its tooltip says why.
2. **Plot** in the activity bar brings an open plot to front and shows a folder plotted before (a
   `.plot` file or figures in `plots/`) as it was, without saving again; a folder never plotted is plotted
   and saved, or, with `ui.auto_generate_plot: false`, only the adjustments panel opens and its
   **Gerar Plot** button (also Ctrl+G) plots. Generating saves the figure into `plots/` and switches the left
   panel to the plot parameters (toggle back with **Árvore**). With a bands folder and a PDOS folder selected
   in the grid, **Plot** and **Gerar Plot** do the same with their **Bandas com DOS** figure (the one the
   right-click menu opens), saved into the bands folder's `plots/`. The tab area starts hidden and
   opens when a plot is generated or a file is opened. **Grids** (also in the
   activity bar) joins open plots in one figure; hide the plots with the **Gráficos** toggle.
3. Tune the plot. Zooming or panning with the toolbar updates the energy window, and
   **Exportar** (Ctrl+E) saves again. Hovering the plot shows the values under the cursor in the
   toolbar (k and energy with the nearest high-symmetry point, PDOS, relax step, SCF iteration). Your settings are kept in `<kind>.plot` (e.g. `bands.plot`)
   in the simulation's `plots/` folder and come back the next time you plot it; **Restaurar padrões**
   deletes it. A `.plot` that older versions left in the simulation folder itself is no longer read.
4. **Rsync** pulls the folder from the cluster.

## Language

The interface is in Portuguese or English. Set `ui.language` in `config.yaml`:

- `auto` (default): follows the system language, `pt_BR` for Portuguese (`pt*`) and `en` for anything else;
- `pt_BR` or `en`: fixed.

The environment variables `QE_STUDIO_LANGUAGE` and `LAIN_LANGUAGE` (`pt_BR`, `en` or `auto`) override the file; the first
wins when both are set. The language is chosen when Lain starts, so after changing it restart Lain ("Recarregar
config.yaml" only tells you so). The option reaches the command line too: `lain --help` is in the language
chosen.

What Lain writes follows the language of the interface only where the text is for you to read: the text inside the
figures (and their PNG, SVG and PDF), the `geracao.md` report of "Criar cálculo" and the text copied from the 3D
measures. Everything other tools or later versions read stays the same in both languages: the `.in` and `.qsub` files,
the CSV (`;` and a decimal comma), the `.plot` and `view3d.plot` files, the exported file names and the
`.lain/` data. Switching the language never changes a saved setting.

Want to translate Lain into another language or improve the English? See
[`src/qe_studio/locale/README.md`](src/qe_studio/locale/README.md).

## Development

```bash
uv run pytest            # unit, integration (real rsync and ssh) and headless UI tests
uv run pytest -m "not realdata and not perf"   # what CI runs
uv run pytest -m perf    # NFR §7 latency budget (CI reports it without blocking)
uv run ruff check . && uv run ruff format --check .
uv run python scripts/i18n.py check   # the English catalog is complete (CI runs it too)
QE_STUDIO_REAL_DATA=/path/to/runs:/other/runs uv run pytest -m realdata   # your own runs
uv run python scripts/screenshot.py --plot   # off-screen PNGs of both themes in screenshots/ (--scale N: font scale, --language en|pt_BR: the interface language, --text: text viewer, --input: an input with errors, --diff [text]: input comparison, --summary: output summary)
uv run python scripts/build_icons.py         # re-render the app icon PNGs after editing the SVG
```

CI (`.github/workflows/ci.yml`) runs lint, formatting and the tests on Python 3.11 and 3.12, and
a non-blocking `perf` job. `HYPOTHESIS_PROFILE=ci` makes the property tests lighter.

The sync tests drive the real `rsync` and `ssh` against a local SSH server built with paramiko
(`tests/ssh_server.py`) that serves a temp folder as the cluster; `ssh` runs with a temporary
`ssh_config`, so the tests never read your `~/.ssh`. They are skipped if `rsync` or `ssh` is
missing.

Code map: `src/qe_studio/core` holds the Qt-free logic: config loading (`core/config.py`), QE
parsers (`core/qe`), detection, calculation modules (`core/calculations`; add new plot types
there) and plotting/export. `core/sync` holds the rsync engine and the ssh askpass helper.
`src/qe_studio/ui` holds the app bootstrap (`ui/app.py`) and the widgets, and
`ui/resources/styles/**.qss` the modular stylesheets, which use `${token}` colours from
`ui/resources/themes/*.yaml`.

Fonts (Inter, JetBrains Mono: OFL) and Material Symbols icons (Apache-2.0) are vendored under
`src/qe_studio/ui/resources/`; `scripts/fetch_assets.py` refreshes them.

### Known MVP limitations

- Pull only (no push).
- Relaxation plots show energy and force only (no structure view; vc-relax |ΔE| uses the total
  energy, not the enthalpy).
- Spin: collinear runs (nspin = 2) only; non-collinear and spin-orbit runs keep a single channel
  without spin projections. k-resolved PDOS files are reported as unsupported.
- On Windows, rsync/ssh must come from cwRsync or MSYS2 (`sync.rsync_binary`,
  `sync.ssh_binary`). Linux is the primary target.
