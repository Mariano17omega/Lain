# Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Welcome window, "no config" | no `config.yaml` found | copy `config.example.yaml` — see the [lookup order](config.md) |
| `Configuração inválida` on start | unknown key or out-of-range value | read the list of problems; fix the key (typos are rejected) |
| Sync disabled | `host`, `user` or `remote_root` missing | fill in all three |
| "Authentication refused" | credential | see [SSH](ssh.md#authentication-refused-by-the-cluster) |
| "Host key verification failed" | cluster not in `known_hosts` | run `ssh user@host` in a terminal and accept the key once |
| `Jobs indisponíveis` / "command not found" | non-interactive ssh `PATH` | use the full path in `jobs_command` (`which qstatus` on the cluster) |
| "Submeter…" refused | a job of yours running/queued in the folder, or a name with a space | wait for the job; rename with letters, digits, `.`, `_`, `+`, `-` |
| "Cancelar simulação…" does nothing | no job of yours with `<name>.o<id>` in the folder | check the queue; the folder must be the job's |
| Folder without badge / no plot | a file (e.g. the SCF) is missing | map it by hand (mapping dialog) or put the SCF in a sibling `*scf*` folder |
| PDOS empty above some energy | small `nbnd` | raise `nbnd` or lower `Emax` in "Criar cálculo" |
| White plot background in the dark theme | by design: figures do not follow the app theme | pick another [style](plots/index.md#styles) |
| "Abrir com XCrysDen" disabled | `paths.xcrysden_path` empty or wrong | give the folder or the script (the item's tooltip says why) |
| Password variable not seen | app launched from the desktop menu | export it in the environment that starts Lain, or type the password when asked |
| `ui.language` does not change | applies only at start | restart Lain |

## Where to look

- **Log**: *Ajuda ▸ Abrir log* (`lain.log`). Look for `session: config=` (which config was read), `sync:`, `cluster:`.
  Use `log.level: debug` or `lain --verbose` for details.
- A native crash is left in `lain.crash`, beside the log.
- Test the connection outside Lain with the terminal's `ssh` (see [SSH](ssh.md)).
