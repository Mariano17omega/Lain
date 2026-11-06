# Sync and cluster (components)

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

## Roles

| Module | Responsibility |
|---|---|
| `core/sync/rsync.py` | the **only** place that builds ssh options (`ssh_command`) and the child's environment (`child_env`); rsync arguments |
| `core/sync/command.py` | runs a remote command (`remote_command`), with timeout and cancellation, no stdin or terminal |
| `core/sync/mux.py` | shared connection (`ControlMaster=auto`, `ControlPersist=120`, short `0700` `ControlPath`) |
| `core/sync/askpass.py` | `SSH_ASKPASS` helper (`qe-studio-askpass`) |
| `core/sync/planner.py`, `preview.py` | rsync *dry run* → plan → preview |
| `core/sync/push.py`, `push_plan.py` | upload of new files only |
| `core/sync/monitor.py` | reachability probe (LED) |
| `core/remote/actions.py` | validation (`checked_name`, `checked_dir`), execution, failure classification |
| `core/remote/listing.py` | `rsync --list-only` |
| `core/remote/submit.py`, `job_cancel.py`, `trash.py` | the three commands that change the cluster |
| `core/remote/scratch.py`, `download.py` | copy into `tmp_remote/` |

## Failure classification

`classify_failure` tells apart: timeout (`connection`), refused authentication (`auth`), command not found
(`missing`, code 127), unreachable cluster (`connection`) and the command's own error — each with its own message and,
when relevant, the hint to use the program's full path.

## How a remote command is composed

```mermaid
flowchart LR
    CFG[config.cluster<br/>host, user, port, auth] --> SSHC[ssh_command]
    SSHC --> RC[remote_command:<br/>ssh opts user@host 'command']
    FIXED[fixed words<br/>cd · chmod a+x · touch · mkdir -p · test ! -e · mv] --> CMDSTR[command line]
    CFGP[config programs<br/>jobs/submit/delete_command] --> CMDSTR
    NAMES[names read from the cluster] -->|checked_name + shlex.quote| CMDSTR
    CMDSTR --> RC
    RC --> RUN[run_command]
```
