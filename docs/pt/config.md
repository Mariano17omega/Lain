# Configuração (`config.yaml`)

Não há janela de configurações: tudo vem do `config.yaml`. Chaves desconhecidas são **rejeitadas** (erro de digitação
aparece como erro, não como valor padrão). O modelo completo e comentado é o
[`config.example.yaml`](https://github.com/Mariano17omega/Lain/blob/main/config.example.yaml).

## Onde o Lain procura o arquivo

Em ordem, o primeiro que existir:

1. `--config CAMINHO`
2. variável `$QE_STUDIO_CONFIG`
3. `./config.yaml` (pasta atual)
4. `config.yaml` na raiz do repositório (instalação editável)
5. `~/.config/qe-studio/config.yaml`

`config.yaml` é ignorado pelo git (pode ter credenciais). Menu *Ferramentas*: **Abrir config.yaml** e
**Recarregar config.yaml** (a maioria das chaves vale na hora; `ui.language` e `paths.data` pedem reinício).

## `paths`

| Chave | Significado |
|---|---|
| `local_root` | Pasta local com a árvore de simulações. Seus filhos de primeiro nível são os **projetos**. |
| `remote_root` | Pasta correspondente no cluster (caminho POSIX; um `~` inicial é deixado ao shell). |
| `xcrysden_path` | Pasta do XCrySDen ou o script `xcrysden`. Vazio: "Abrir com XCrysDen" fica desabilitado. |
| `data` | Pasta de dados do Lain (estado da interface, trava de instância, log). Relativa ao `config.yaml`; vazio usa os locais do sistema. Copiar a pasta leva o estado junto. |

## `cluster`

| Chave | Padrão | Significado |
|---|---|---|
| `host`, `port`, `user` | —, `22`, — | Onde e como quem entrar. Sem `host`+`user`+`remote_root` o sync fica desligado. |
| `auth` | `key` | `key` ou `password` — veja [SSH](ssh.md). |
| `key_path` | — | Chave **privada** (com `auth: key`). |
| `password_env` | `QE_STUDIO_SSH_PASSWORD` | **Nome** da variável de ambiente com a senha (com `auth: password`). |
| `password` | — | Senha em texto puro (desencorajado). |
| `connect_timeout` | `10` | Segundos para conectar. |
| `status_poll_seconds` | `300` | Intervalo da sonda de alcance (TCP, sem login). Mín. 30. |
| `jobs_command` | `qstatus -a` | Comando da fila, rodado no cluster por ssh. Vazio desliga o indicador. |
| `jobs_poll_seconds` | `300` | Intervalo das consultas da fila (só com a janela ativa). Mín. 30. |
| `jobs_rotate_seconds` | `5` | Tempo de cada job seu na barra. |
| `submit_command` | `qsub` | Programa de "Submeter…". Vazio desliga o item. |
| `delete_command` | `qdel` | Botão de cancelar job **em espera**. Vazio desliga. |
| `multiplex` | `true` | Uma conexão ssh compartilhada (`ControlMaster`). |

!!! tip "PATH do ssh não interativo"
    O ssh roda comandos sem terminal, então o `PATH` do seu login pode faltar. Se `qstatus`/`qsub` não forem achados,
    dê o caminho completo (`which qstatus` no cluster).

## `sync`

| Chave | Significado |
|---|---|
| `exclude` | Padrões `--exclude` do rsync (`tmp/`, `*.save/`, `*.wfc*`, `core.[0-9]*`…). |
| `rsync_binary`, `ssh_binary` | Executáveis (padrão `rsync`, `ssh`). |
| `confirm_plan` | `true`: mostra a prévia e espera "Baixar". Enviar ao cluster sempre mostra prévia. |
| `checksum` | `true`: compara por conteúdo (`rsync --checksum`); `false`: por data e tamanho (mais rápido). |
| `push_exclude` | Nunca sobem, além de `exclude`: `plots/` e `*.plot`. |
| `cygdrive_prefix` | Só no Windows: o que vem antes da letra da unidade nos caminhos do rsync. `/cygdrive` (padrão, cwRsync) ou `""` (MSYS2). |

## `plot`

`energy_min`/`energy_max` (janela de energia, eV), `shift_to_fermi`, e `export.formats` (`png`, `svg`, `pdf`) e
`export.dpi` (72–2400; 300 ou 600 na prática). O **visual** de um gráfico novo vem dos
[estilos de gráfico](plots/index.md#estilos), não daqui.

## `ui`

`theme` (`dark`/`light`/`system`), `language` (`auto`/`pt_BR`/`en`; também `$QE_STUDIO_LANGUAGE` / `$LAIN_LANGUAGE`),
`font_scale` (0,8–1,6), `hidden_dirs`, `tree_show_files`, `paranoid_refresh`, `auto_generate_plot`.

## `jobs` (defaults do "Criar cálculo")

| Chave | Significado |
|---|---|
| `cores` | Valor inicial do campo NP (padrão 64). |
| `nk` | Valor inicial de *pools* (`pw.x -nk`, padrão 4). NP deve ser múltiplo. |
| `pseudo_dir` | `pseudo_dir` gravado em todo input do `pw.x` gerado (caminho no cluster). |
| `myemail` | E-mail avisado pelo cluster quando o job começa e termina (`MYEMAIL` do `.qsub`). Nunca vai para o log. |

## `log`

`enabled`, `max_size_mb` (1–1000; `lain.log` + `lain.log.1`), `level` (`info`/`debug`). Veja [Log](features/log.md).

## Exemplo mínimo com cluster

```yaml
paths:
  local_root: ~/qe_simulations
  remote_root: /home/meu_usuario/qe_simulations
cluster:
  host: cluster.exemplo.org
  user: meu_usuario
  auth: key
  key_path: ~/.ssh/id_ed25519
jobs:
  cores: 64
  nk: 4
  pseudo_dir: /home/meu_usuario/pseudo
```
