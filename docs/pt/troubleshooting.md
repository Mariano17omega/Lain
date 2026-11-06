# Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Janela de boas-vindas, "sem config" | nenhum `config.yaml` encontrado | copie `config.example.yaml` — veja [ordem de busca](config.md) |
| `Configuração inválida` ao abrir | chave desconhecida ou valor fora do intervalo | leia a lista de problemas; corrija a chave (erros de digitação são rejeitados) |
| Sync desligado | falta `host`, `user` ou `remote_root` | preencha as três |
| "Authentication refused" | credencial | veja [SSH](ssh.md#autenticacao-recusada-pelo-cluster) |
| "Host key verification failed" | cluster fora do `known_hosts` | rode `ssh usuario@host` num terminal e aceite a chave uma vez |
| `Jobs indisponíveis` / "comando não foi encontrado" | `PATH` do ssh não interativo | use caminho completo em `jobs_command` (`which qstatus` no cluster) |
| "Submeter…" recusado | job seu rodando/na fila na pasta, ou nome com espaço | espere o job; renomeie para letras, dígitos, `.`, `_`, `+`, `-` |
| "Cancelar simulação…" sem efeito | não há job seu com `<nome>.o<id>` na pasta | confira a fila; a pasta deve ser a do job |
| Pasta sem selo / sem gráfico | falta um arquivo (ex.: SCF) | mapeie à mão (diálogo de mapeamento) ou coloque o SCF numa pasta `*scf*` irmã |
| PDOS vazia acima de certa energia | `nbnd` pequeno | aumente `nbnd` ou reduza `Emax` no "Criar cálculo" |
| Gráfico com fundo branco no tema escuro | por projeto: figuras não seguem o tema do app | escolha outro [estilo](plots/index.md#estilos) |
| "Abrir com XCrysDen" desabilitado | `paths.xcrysden_path` vazio ou errado | informe a pasta ou o script (a dica da opção diz o motivo) |
| Variável da senha não vista | app aberto pelo menu do desktop | exporte no ambiente que inicia o Lain, ou digite a senha quando pedida |
| `ui.language` não muda | só vale ao iniciar | reinicie o Lain |

## Onde olhar

- **Log**: *Ajuda ▸ Abrir log* (`lain.log`). Procure `session: config=` (qual config foi lido), `sync:`, `cluster:`.
  Use `log.level: debug` ou `lain --verbose` para detalhes.
- Um *crash* nativo fica em `lain.crash`, ao lado do log.
- Teste a conexão fora do Lain com o `ssh` do terminal (veja [SSH](ssh.md)).
