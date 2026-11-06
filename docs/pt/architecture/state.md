# Estado e persistência

```mermaid
flowchart LR
    subgraph CFG[Configuração]
        Y[config.yaml<br/>pydantic AppConfig]
    end
    subgraph DATA["Pasta de dados (paths.data ou ~/.local/share/qe-studio)"]
        QS[settings.ini<br/>QSettings: janela, tema, última pasta]
        LOG[lain.log · lain.crash]
        SJ[submitted_jobs.log]
        LOCK[trava de instância]
    end
    subgraph ROOT["local_root/.lain/"]
        FM[folder memory]
        GR[grids]
        CO[compounds]
        NV[favoritos / recentes]
    end
    subgraph SIM["simulação/plots/"]
        PL[bands.plot · pdos.plot · …]
        EX[figuras PNG/SVG/PDF + CSV]
        V3[view3d.plot]
    end
    subgraph TMP["pasta/tmp_remote/"]
        CP[cópia de plot remoto]
        PR[plots_remote/]
    end
    CACHE[(~/.cache/qe-studio<br/>só o que se refaz)]
```

| Dado | Onde | Quem escreve |
|---|---|---|
| Config | `config.yaml` | o usuário (somente leitura para o Lain) |
| Estado da UI | QSettings (`<data>/settings.ini`) | `ui/*` |
| Dados por raiz | `<local_root>/.lain/` (`core/project/project_data.py` é o único que cita a pasta) | `core/project/*` |
| Ajustes e exportações | `<simulação>/plots/` | `core/plotting/*` |
| Cópia de plot remoto | `<pasta>/tmp_remote/` | `core/remote/scratch.py` (sobrescreve sem perguntar, só aqui) |
| Jobs enviados | `<data>/submitted_jobs.log` | `core/remote/submit_log.py` |
| Log | `<data>/lain.log` | `core/app/logs.py` |
| Estilos de gráfico | `resources/templates/plot_styles/*.yaml` | só leitura |

- **Integridade**: nunca sobrescrever arquivo do usuário sem perguntar (`core/files/unique_names.py`: sufixos `_2`);
  arquivos de dados são escritos inteiros com `core/appdirs.py:atomic_write_text`.
- Nada mais é gravado em pastas de simulação.
- O idioma não influencia nada que persiste (`.lain/`, `.plot`, exportações, QSettings) — verificado por teste.
