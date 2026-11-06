# Log

Lain writes `lain.log` in the data folder (`paths.data`, or `~/.local/share/qe-studio`). **Ajuda ▸ Abrir log** opens
the file; **Abrir pasta de dados** opens the folder.

```yaml
log:
  enabled: true     # false: no file; errors still reach the terminal
  max_size_mb: 10   # 1 to 1000: lain.log and the older lain.log.1 together
  level: info       # debug also records the details
```

`lain --verbose` asks for `debug` and prints it in the terminal. "Recarregar config.yaml" applies at once.

- **INFO** tells the session: version and config in use, menu actions, plots, exports, files created, and each action
  on the cluster with exit code, end of stderr and job ID.
- **DEBUG** adds what repeats or only reads: tasks, queue queries, detection, navigation.
- Failures carry a traceback at either level (including Qt warnings and exceptions in threads).
- A native crash (segfault) goes to `lain.crash` and into the log at the next start.
- Fixed `grep` keywords: `session:`, `action:`, `menu:`, `confirm:`, `plot:`, `export:`, `file:`, `sync:`,
  `command:`, `cluster:`, `task:`, `detection:`, `folder:`, `tab:`.

The log holds host, user name and paths (they explain a failed sync) but **never** a password or `jobs.myemail`.
Look it over before sending it to someone.

Code: `core/app/logs.py`.
