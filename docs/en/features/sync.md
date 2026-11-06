# Synchronization

*Cluster* menu: **Sincronizar pasta selecionada** (sync selected folder), **Sincronizar tudo** (sync all),
**Enviar ao cluster** (send), **Testar conexão** (test connection) and **Ver arquivos do cluster**
([cluster mode](../remote-mode.md)).

- **Download (pull)**: `rsync` in *dry run*, a preview (new, updates, sizes, large files) and only then the copy, with
  a cancellable progress dialog. Conflicts ask file by file.
- **Upload (push)**: only adds files the cluster does not have; never overwrites or deletes; always with a preview.
- **Comparison**: `sync.checksum: true` compares content; `false`, date and size.
- **Exclusions**: `sync.exclude` (`tmp/`, `*.save/`, `*.wfc*`…) plus the fixed ones (`.lain/`, `tmp_remote/`, `trash/`
  at the root).
- An LED shows cluster reachability (`status_poll_seconds`); beside it, your jobs ("Executando: name"). Click to open
  the whole queue (green bar = running, amber = waiting; ✕ on your waiting jobs).

Details and diagrams: [Remote mode](../remote-mode.md). Code: `core/sync/`, `ui/cluster/`.
