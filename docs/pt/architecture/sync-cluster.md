# Sync e cluster (componentes)

```mermaid
flowchart TB
    subgraph UI[ui/cluster]
        SC[sync_coordinator]
        RC[remote_controller]
        JC[jobs_controller]
        RP[remote_plot]
        RT[remote_trash]
        JA[job_actions / job_cancel]
    end
    subgraph SYNC[core/sync]
        REQ[request.py]
        PL[planner.py + preview.py]
        PUSH[push.py / push_plan.py]
        RS[rsync.py<br/>ssh_command, child_env]
        CMD[command.py<br/>run_command, remote_command]
        MUX[mux.py<br/>ControlMaster]
        ASK[askpass.py]
        MON[monitor.py]
        RPATH[remote_path.py]
    end
    subgraph REMOTE[core/remote]
        LST[listing.py]
        JOBS[cluster_jobs.py]
        SUB[submit.py + submit_log.py]
        CAN[job_cancel.py]
        TR[trash.py + trash_dir.py]
        ACT[actions.py<br/>checked_name, run_action]
        SCR[scratch.py + download.py]
    end
    SC --> REQ --> PL --> RS
    SC --> PUSH --> RS
    RC --> LST --> RS
    JC --> JOBS --> CMD
    JA --> SUB --> ACT --> CMD
    JA --> CAN --> ACT
    RT --> TR --> ACT
    RP --> SCR --> RS
    CMD --> RS --> MUX
    RS --> ASK
```

## Papéis

| Módulo | Responsabilidade |
|---|---|
| `core/sync/rsync.py` | **único** lugar que monta opções do ssh (`ssh_command`) e o ambiente do filho (`child_env`); argumentos do rsync |
| `core/sync/command.py` | roda um comando remoto (`remote_command`), com timeout e cancelamento, sem stdin nem terminal |
| `core/sync/mux.py` | conexão compartilhada (`ControlMaster=auto`, `ControlPersist=120`, `ControlPath` curto e `0700`) |
| `core/sync/askpass.py` | helper `SSH_ASKPASS` (`qe-studio-askpass`) |
| `core/sync/planner.py`, `preview.py` | *dry run* do rsync → plano → prévia |
| `core/sync/push.py`, `push_plan.py` | envio só de arquivos novos |
| `core/sync/monitor.py` | sonda de alcance (LED) |
| `core/remote/actions.py` | validação (`checked_name`, `checked_dir`), execução, classificação de falhas |
| `core/remote/listing.py` | `rsync --list-only` |
| `core/remote/submit.py`, `job_cancel.py`, `trash.py` | os três comandos que alteram o cluster |
| `core/remote/scratch.py`, `download.py` | cópia para `tmp_remote/` |

## Classificação de falhas

`classify_failure` distingue: tempo esgotado (`connection`), autenticação recusada (`auth`), comando não encontrado
(`missing`, código 127), cluster inacessível (`connection`) e erro do próprio comando — cada um com uma mensagem
própria e, quando é o caso, a sugestão de usar o caminho completo do programa.

## Composição de um comando remoto

```mermaid
flowchart LR
    CFG[config.cluster<br/>host, user, port, auth] --> SSHC[ssh_command]
    SSHC --> RC[remote_command:<br/>ssh opts user@host 'comando']
    FIXED[palavras fixas<br/>cd · chmod a+x · touch · mkdir -p · test ! -e · mv] --> CMDSTR[linha do comando]
    CFGP[programas do config<br/>jobs/submit/delete_command] --> CMDSTR
    NAMES[nomes lidos do cluster] -->|checked_name + shlex.quote| CMDSTR
    CMDSTR --> RC
    RC --> RUN[run_command]
```
