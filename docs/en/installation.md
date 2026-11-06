# Installation

## Requirements

- **Python ≥ 3.11** and [uv](https://docs.astral.sh/uv/) (the environment manager the project uses).
- `rsync` (≥ 3.1) and `ssh` on `PATH` — needed only to talk to the cluster.
- Linux is the main target (the ssh/askpass code also has Windows paths).

## Install script

`install.sh` runs the steps of the next section in order, asking first wherever a choice is needed. On Linux, run
it in a terminal. On Windows, run it in **Git Bash**, which comes with [Git for Windows](https://git-scm.com/download/win):

```bash
curl -fsSL https://raw.githubusercontent.com/Mariano17omega/Lain/main/install.sh | bash
# or, from a clone:  bash install.sh
```

1. It checks for `git`, `ssh` and `rsync` (only `git` is required), and installs uv if it is missing.
2. It clones the repository (default folder `~/Lain`), or offers `git pull` when Lain is already there.
3. It copies `config.example.yaml` to `config.yaml` and fills in your answers:

    | Key | Default |
    |---|---|
    | `paths.local_root` | `LUCCI` in your Documents folder: `~/Documentos/LUCCI` on a Portuguese Linux desktop, `~/Documents/LUCCI` in English and on Windows (created if missing, after asking) |
    | `paths.remote_root` | `~/LUCCI` |
    | `paths.xcrysden_path` | where `$XCRYSDEN_TOPDIR` or `xcrysden` on `PATH` points; otherwise you type it, or leave it blank |
    | `paths.data` | blank (the system's default place) |
    | `cluster.host`, `cluster.user` | required |
    | `cluster.port` | `22` |
    | `cluster.auth` | `key` |
    | `cluster.key_path` | `~/.ssh/id_ed25519` |
    | `jobs.myemail` | blank (skipped) |

4. It offers to create the ssh key, copy it to the cluster and log in once, which makes ssh trust the cluster's host
   key (see [SSH connection](ssh.md)). Each step asks first; a skipped one is printed at the end.
5. It runs `uv tool install --editable --force .` and, on Linux, offers the application menu entry.

An existing `config.yaml` is changed only if you say so, and the old one is kept as `config.yaml.bak`. To answer the
questions again later: `bash install.sh --config-only`. With a password login, the password is never asked: Lain
reads it from `QE_STUDIO_SSH_PASSWORD`. `local_root`, `key_path` and `xcrysden_path` must be full paths (starting with
`/` or `~`, or a drive letter on Windows): Lain would read a relative one from the folder it runs in.

## Step by step

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if you do not have uv yet
source ~/.bashrc
git clone git@github.com:Mariano17omega/Lain.git && cd Lain
cp config.example.yaml config.yaml                 # then edit it (see Configuration)
uv tool install --editable .                       # installs the `lain` command
lain                                               # or: lain --config /path/config.yaml
```

Command-line options: `--config PATH` (configuration file) and `--verbose` (`debug` log, also in the terminal).

### Editable install (default)

The install is **editable**: code changes apply without reinstalling (use `--force` after changing dependencies or
entry points). From any folder, `lain` reads the `config.yaml` at the root of the repository, unless the current
folder has its own `config.yaml` — see the [lookup order](config.md).

### Non-editable install (optional)

```bash
uv tool install .
```

There is no repository to read the config from: keep it in `~/.config/qe-studio/config.yaml`, point
`$QE_STUDIO_CONFIG` at it, or pass `--config`. Code changes apply only after reinstalling.

### Without installing (development)

```bash
uv sync && uv run lain
```

Runs straight from the repository's environment; this is what you use to develop and test.

## Desktop integration (optional)

So the window manager shows Lain's icon and the application menu lists it:

```bash
uv run python scripts/install_desktop.py              # into ~/.local/share
uv run python scripts/install_desktop.py --prefix DIR # or into another directory
```

Nothing is installed unless you run this. It needs the `lain` command on `PATH`.

## XCrySDen (optional)

"Abrir com XCrysDen" (*Open with XCrySDen*) starts the external [XCrySDen](http://www.xcrysden.org/). Put its
install folder (or the `xcrysden` script) in `paths.xcrysden_path` — see [Configuration](config.md).

## First run

With no `config.yaml` at all, Lain opens in a welcome state that says where to put the file. See the
[Quick start](quickstart.md).
