# Log

O Lain escreve `lain.log` na pasta de dados (`paths.data`, ou `~/.local/share/qe-studio`). **Ajuda ▸ Abrir log** abre o
arquivo; **Abrir pasta de dados** abre a pasta.

```yaml
log:
  enabled: true     # false: nenhum arquivo; erros ainda vão ao terminal
  max_size_mb: 10   # 1 a 1000: lain.log e o antigo lain.log.1 juntos
  level: info       # debug registra também os detalhes
```

`lain --verbose` pede `debug` e imprime no terminal. "Recarregar config.yaml" aplica na hora.

- **INFO** conta a sessão: versão e config em uso, ações de menu, gráficos, exportações, arquivos criados, e cada ação
  no cluster com código de saída, fim do stderr e ID do job.
- **DEBUG** acrescenta o que se repete ou só lê: tarefas, consultas de fila, detecção, navegação.
- Falhas trazem *traceback* nos dois níveis (inclusive avisos do Qt e exceções em threads).
- Um *crash* nativo (segfault) vai para `lain.crash` e entra no log na próxima partida.
- Palavras-chave fixas para `grep`: `session:`, `action:`, `menu:`, `confirm:`, `plot:`, `export:`, `file:`, `sync:`,
  `command:`, `cluster:`, `task:`, `detection:`, `folder:`, `tab:`.

O log tem host, usuário e caminhos (explicam sync que falhou), mas **nunca** senha nem `jobs.myemail`. Revise antes de
enviar a alguém.

Código: `core/app/logs.py`.
