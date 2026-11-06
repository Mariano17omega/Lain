# Configuration (`config.yaml`)

There is no settings window: everything comes from `config.yaml`. Unknown keys are **rejected** (a typo shows as an
error, not as a silent default). The full commented template is
[`config.example.yaml`](https://github.com/Mariano17omega/Lain/blob/main/config.example.yaml).

## Where Lain looks for the file

In order, the first that exists:

1. `--config PATH`
2. the `$QE_STUDIO_CONFIG` variable
3. `./config.yaml` (current folder)
4. `config.yaml` at the repository root (editable install)
5. `~/.config/qe-studio/config.yaml`

`config.yaml` is git-ignored (it may hold credentials). *Tools* menu: **Abrir config.yaml** (open) and
**Recarregar config.yaml** (reload; most keys apply at once, `ui.language` and `paths.data` need a restart).

## `paths`

| Key | Meaning |
|---|---|
| `local_root` | Local folder with the simulation tree. Its first-level children are the **projects**. |
| `remote_root` | Matching folder on the cluster (POSIX path; a leading `~` is left to the shell). |
| `xcrysden_path` | XCrySDen's folder or the `xcrysden` script. Empty: "Abrir com XCrysDen" stays disabled. |
| `data` | Lain's data folder (interface state, instance lock, log). Relative to `config.yaml`; empty uses the system's places. Copying the folder takes the state along. |

## `cluster`

| Key | Default | Meaning |
|---|---|---|
| `host`, `port`, `user` | —, `22`, — | Where and as whom to log in. Without `host`+`user`+`remote_root` sync is off. |
| `auth` | `key` | `key` or `password` — see [SSH](ssh.md). |
| `key_path` | — | **Private** key (with `auth: key`). |
| `password_env` | `QE_STUDIO_SSH_PASSWORD` | **Name** of the environment variable holding the password (with `auth: password`). |
| `password` | — | Plain-text password (discouraged). |
| `connect_timeout` | `10` | Seconds to connect. |
| `status_poll_seconds` | `300` | Reachability probe interval (TCP only, no login). Min. 30. |
| `jobs_command` | `qstatus -a` | Queue command, run on the cluster over ssh. Empty turns the indicator off. |
| `jobs_poll_seconds` | `300` | Queue query interval (only while the window is active). Min. 30. |
| `jobs_rotate_seconds` | `5` | Time each of your jobs stays on the bar. |
| `submit_command` | `qsub` | Program of "Submeter…". Empty turns the item off. |
| `delete_command` | `qdel` | Cancel button of a job still **waiting**. Empty turns it off. |
| `multiplex` | `true` | One shared ssh connection (`ControlMaster`). |

!!! tip "PATH of a non-interactive ssh"
    ssh runs commands without a terminal, so your login `PATH` may be missing. If `qstatus`/`qsub` are not found, give
    the full path (`which qstatus` on the cluster).

## `sync`

| Key | Meaning |
|---|---|
| `exclude` | rsync `--exclude` patterns (`tmp/`, `*.save/`, `*.wfc*`, `core.[0-9]*`…). |
| `rsync_binary`, `ssh_binary` | Executables (default `rsync`, `ssh`). |
| `confirm_plan` | `true`: show the preview and wait for "Baixar". Sending to the cluster always shows a preview. |
| `checksum` | `true`: compare by content (`rsync --checksum`); `false`: by date and size (faster). |
| `push_exclude` | Never uploaded, on top of `exclude`: `plots/` and `*.plot`. |

## `plot`

`energy_min`/`energy_max` (energy window, eV), `shift_to_fermi`, and `export.formats` (`png`, `svg`, `pdf`) and
`export.dpi` (72–2400; 300 or 600 in practice). The **look** of a new plot comes from the
[plot styles](plots/index.md#styles), not from here.

## `ui`

`theme` (`dark`/`light`/`system`), `language` (`auto`/`pt_BR`/`en`; also `$QE_STUDIO_LANGUAGE` / `$LAIN_LANGUAGE`),
`font_scale` (0.8–1.6), `hidden_dirs`, `tree_show_files`, `paranoid_refresh`, `auto_generate_plot`.

## `jobs` (defaults of "Criar cálculo")

| Key | Meaning |
|---|---|
| `cores` | Initial value of the NP field (default 64). |
| `nk` | Initial value of pools (`pw.x -nk`, default 4). NP must be a multiple. |
| `pseudo_dir` | `pseudo_dir` written into every generated pw.x input (a path on the cluster). |
| `myemail` | E-mail the cluster notifies when the job starts and ends (`MYEMAIL` in the `.qsub`). Never goes to the log. |

## `log`

`enabled`, `max_size_mb` (1–1000; `lain.log` + `lain.log.1`), `level` (`info`/`debug`). See [Log](features/log.md).

## Minimal example with a cluster

```yaml
paths:
  local_root: ~/qe_simulations
  remote_root: /home/my_user/qe_simulations
cluster:
  host: cluster.example.org
  user: my_user
  auth: key
  key_path: ~/.ssh/id_ed25519
jobs:
  cores: 64
  nk: 4
  pseudo_dir: /home/my_user/pseudo
```
