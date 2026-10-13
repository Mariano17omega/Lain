# Relatório de análise: Lain: QE Studio

Data: 2026-09-30 · Base: `main` @ cec7c3f (+ WIP não commitado) · Leitura completa de `src/` (~9,2k linhas),
specs, README, CLAUDE.md, config e fixtures. Nada foi executado nem alterado.

Escala de esforço (igual a `specs/README.md`): **P** = horas · **M** = ~1 dia · **G** = mais de 1 dia.
Prioridade: **P1** alto valor/baixo risco · **P2** valor claro · **P3** opcional.

---

## 0. Diagnóstico

**Forças**
- `core/` sem widgets, `ui/` fina: base boa para CLI/batch. Detecção por conteúdo (`sniff` + `FileRole`) é robusta.
- Regras de thread claras, sync bem testado (rsync real + `fake_ssh`), 258 testes, fixtures reais QE 7.1/7.3.1.
- Tema por tokens, persistência `.plot` já resolve o "estado perdido" do `Ideias.md`.

**Lacunas**
- Só 3 tipos plotáveis (bandas, PDOS, relax). SCF/CALC são só badge (`core/calculations/info.py`).
- App é **estático**: nada atualiza sozinho (sem watcher; `TextViewer.reload()` em `workspace.py:107` nunca é chamado).
- Sem CI, sem ícone/`.desktop`, sem menu Ajuda, sem estado vazio/onboarding.
- Contrato "módulo novo sem código de UI" (CLAUDE.md, NFR §7) vaza em 4 pontos (ver A3).
- `MainWindow` = 991 linhas, 4 responsabilidades.

---

## 1. Novas funcionalidades (com justificativa)

### 1.1 Ciência / gráficos

| # | Funcionalidade | Justificativa (evidência) | Prio | Esf. |
|---|---|---|---|---|
| F1 | **Convergência SCF**: "estimated scf accuracy" e energia por iteração; marca `convergence NOT achieved` | SCF já é detectado mas só vira badge. Debugar SCF que não converge é a tarefa mais comum em QE. Parser é regex sobre saída pw.x (mesmo estilo de `qe/relax.py`). Módulo novo = `load/default_params/param_schema/render`, sem UI. | P1 | P |
| F2 | **DOS total (dos.x)** | `FileKind.DOS_IN/DOS_OUT` já são sniffados (`sniff.py:41-42`), `.dos` já é texto (`file_types.py`), mas nenhum módulo plota. Reaproveita eixo de energia/Fermi do PDOS. | P1 | P |
| F3 | **Exportar dados** (CSV/`.dat`) + **copiar imagem** p/ clipboard | Hoje só sai figura em `plots/`. Origin/Grace/LaTeX exigem números. `RenderInfo`/datasets já têm os arrays. | P1 | P |
| F4 | **vc-relax completo**: entalpia, volume, pressão, parâmetros de cela por passo; tabela estrutura inicial × final; exportar CIF/XSF | README admite: "|ΔE| usa energia total, não entalpia". Fixtures do usuário são kaolinita vc-relax e slabs (`kao_*`), onde cela e pressão decidem se relaxou. `read_structure` (ASE) já existe. | P1 | M |
| F5 | **Bandas + DOS combinados** (figura de artigo, eixo E compartilhado) | PRD §7 cita "combined Bands + PDOS". `infer_from_neighbours` já acha SCF em pastas irmãs; falta módulo com `GridSpec`. | P2 | M |
| F6 | **Bandas com spin** (dois canais) | Limitação declarada no README ("um único canal `.gnu`"). PDOS já espelha spin-down, então há convenção visual pronta. | P2 | M |
| F7 | **Predefinições de estilo** ("Salvar como predefinição", "Aplicar a…") | `.plot` é por pasta: 10 simulações de um artigo ficam com estilos divergentes. Presets em `~/.config/qe-studio/plot-presets/*.yaml`, mesmo schema do `.plot`; incluir presets de revista (coluna simples 3,4 in) e paleta daltônica. | P2 | P/M |
| F8 | **Painel Resumo** de saída pw.x: WALL/CPU, ecut, nat, k-pontos, pressão, magnetização, versão, nº MPI | Só existe o rótulo OK/INCOMPLETO. Para quem roda em cluster, tempo e custo importam. Parser regex de rodapé (`PWSCF : … CPU … WALL`). | P2 | P/M |
| F9 | **Comparar/sobrepor simulações** (multi-seleção): bandas de 2+ pastas, PDOS, E × ecutwfc / k-pontos | Teste de convergência e comparação de funcionais/strain são rotina. Exige multi-seleção na grade (hoje `SingleSelection`, `file_grid.py:220`) e módulo com datasets múltiplos. | P3 | G |

### 1.2 Fluxo de trabalho e cluster

| # | Funcionalidade | Justificativa | Prio | Esf. |
|---|---|---|---|---|
| F10 | **Acompanhamento ao vivo**: `QFileSystemWatcher` (ou poll) marca abas como "desatualizada" + botão Recarregar; opção de auto-refresh e auto-pull a cada N s | Relax mostra "Em andamento" (`relax.py: summary`), mas o gráfico nunca se atualiza. Detecção fica em cache até F5/sync (`services.py`). `TextViewer.reload()` e `load_cached` (chave por mtime/size) já suportam. Modo "seguir fim" no texto. | P1 | M |
| F11 | **Monitor de jobs** (`qstat`/`squeue` via ssh BatchMode) ligado a `job.o<id>`; notificação e "sincronizar ao terminar" | Lain já entende `.qsub` e `job.o12345` (spec 4) e tem ssh/monitor. Falta fechar o ciclo submeter→acompanhar→baixar. Requer `cluster.scheduler: pbs\|slurm` no config. | P2 | G |
| F12 | **CLI headless**: `lain detect`, `lain plot <pasta> [--kind]`, `lain sync` + "Gerar gráficos de todas as subpastas" | `core/` é Qt-free e `detect_now` já serve scripts. Permite rodar no cluster/CI e regerar figuras em lote. | P2 | M |
| F13 | **Abrir pasta… / projetos recentes / assistente de primeira execução** | `local_root` é único, fixo no config; sem `config.yaml` a janela abre em `~/qe_simulations` inexistente só com aviso na barra. Decisão: lista `projects:` no config (pares local↔remoto) ou QSettings. | P2 | M |
| F14 | **Confiar na chave do host pela UI** (mostra impressão digital, TOFU explícito) e senha via keyring | Hoje exige `ssh usuario@host` no terminal (README). Manter "nunca aceitar automático": só com confirmação do usuário. Senha em texto puro no `config.yaml` já gera aviso; keyring (libsecret) é a saída. | P3 | M |
| F15 | **Visualizador de input**: realce de namelists/cards, diff entre dois inputs, extrato (ecutwfc, K_POINTS, calculation) | Comparar duas execuções é rotina; parser de input já existe (`qe/pw_input.py`). | P3 | M |
| F16 | Push (enviar inputs/`.qsub`) | PRD adiou de propósito. Só com pré-visualização e confirmação por arquivo (integridade §7). Não recomendo agora. | P3 | G |

---

## 2. Arquitetura e otimização

### 2.1 Achados de arquitetura

**A1. `MainWindow` acumula 4 responsabilidades** (`main_window.py`, 991 linhas): (a) layout dos painéis + `fit_widths` (l.135-163, 508-568); (b) fluxo de plot detectar→carregar→sessão→exportar + persistência `.plot` (`_unsaved`, `_flush_plot_files`, l.629-903); (c) orquestração de sync/senha/conflitos (l.906-991); (d) config reload/rename.
→ Extrair `LayoutController`, `PlotWorkflow`, `SyncCoordinator`; `MainWindow` fica como raiz de composição. Ganho: testar sem montar janela inteira; menos risco nas regras de thread. **P1, G.**

**A2. Boilerplate de worker repetido 5×**: `QRunnable` + objeto de sinais + "manter vivo até o próximo turno do loop" em `services.py:16-37,141-142`, `main_window.py:99-125,713-718`, `workspace.py:61-78`, `file_grid.py:43-61,297-299`, `controller.py:94-112,249-250`. É exatamente a regra frágil do CLAUDE.md (sinal na própria thread do objeto).
→ `ui/workers.py` com `run_in_pool(fn, on_done, on_error, pool=…)` que encapsula tokens, cancelamento e tempo de vida. **P1, M.**

**A3. Contrato do módulo vaza para a UI** (quebra "módulo novo sem código de UI"):
- `plot_session.py:59-77`: `reset_view`/`apply_limits` com `if kind == "bands"/"pdos"/"relax"`.
- `plot_params.py:420`: lista fixa de nomes que forçam `refresh_values`.
- `plot_file.py:139-147`: validação por heurística de nome (`endswith("color")`, `"_colors"`).
- `main_window.py:738-740`: rótulos legados só para `kind == "bands"`.
→ Hooks no `CalculationModule` (`apply_limits`, `reset_fields`, `legacy_params`) e flags no `ParamField` (`refreshes=True`; validar por `kind == "color"`). Módulo novo passa a ser 1 arquivo + registro. **P1, M.**

**A4. Tipagem frouxa**: `PlotSession.params/dataset: Any`, `render(figure, dataset, params, style)` sem tipos. → `CalculationModule(Generic[D, P])` + pyright no dev group. **P2, M.**

**A5. `FolderMemory` guarda caminho absoluto resolvido** (`detection.py:36`): mover a pasta do projeto ou usar outra máquina perde mapeamentos manuais e rótulos. → chave relativa a `local_root`. **P2, P.**

**A6. Sem CI**: não há `.github/`. → workflow com `uv sync`, `ruff check/format`, `pytest` (offscreen, rsync instalado), `-m perf` opcional. **P1, P.**

**A7. Higiene/empacotamento**: sem `setWindowIcon`/`desktopFileName` (ícone genérico na barra de tarefas); sem `.desktop`; README l.4 aponta `Documentation/PRD.md`, que não existe (é `specs/spec_0-PRD.md`); WIP não commitado (remoção do Relax-Viewer + docstrings + `extend-exclude`). **P1, P.**

**A8. Perf de exportação e render**: `export_plot` roda `export_figure` no thread GUI (`main_window.py:894`): PNG 600 DPI + SVG + PDF de PDOS congela a janela. → worker (Figure próprio + `FigureCanvasAgg`; matplotlib não é formalmente thread-safe, então serializar com lock global). **P2, M.**

### 2.2 Otimizações (todas com evidência no código; medir antes/depois)

| # | Problema | Onde | Correção | Esf. |
|---|---|---|---|---|
| O1 | `.gnu` é lido e parseado por completo **no sniff** (até 64 MB) e de novo no `load` | `sniff.py:129-134`, `bands.py:_eigenvalues` | Sniff só conta blocos/linhas para `shape`, ou compartilha o `BandData` via `load_cached` | P |
| O2 | `invalidate()` sem argumento limpa **todo** o `SniffCache` (`services.py:108-111`), mas as entradas já validam por (mtime, size): F5/sync relê até 16 MB por saída | `services.py` | Não limpar; descartar só `_results` e sniffs de arquivos que sumiram | P |
| O3 | `match()` sniffa todos os arquivos **por módulo** (×5) | `base.py:177` | Calcular `sniffs` uma vez em `detect_folder` e passar aos módulos | P |
| O4 | ASE (pesado) importado no start por `sniff.py:18` → `pw_input.py:16` | `pw_input.py` | Import tardio em `parse_input`/`read_structure`. Medir com `python -X importtime` | P |
| O5 | `parse_pw_output` varre até 16 MB com `finditer` por padrão (×4 Fermi, `_last`) | `pw_output.py:70-74`, `sniff.py:152` | Usar cabeça+cauda para saídas grandes (Fermi/JOB DONE no fim, calculation no início) ou `rfind` | M |
| O6 | `ParamsPanel.bind` **reconstrói todos os widgets** a cada troca de aba e perde estado das seções | `plot_params.py:187-222` | Um painel por sessão em `QStackedWidget`, ou reuso + `refresh_values` | M |
| O7 | Cursor global de ocupado (`setOverrideCursor`) com contabilidade manual em 3 lugares | `main_window.py:643,654,710,717` | Indicador local (spinner na aba/status) | P |
| O8 | Sem teste de latência da **detecção** (só plot tem `-m perf`) | `tests/` | `-m perf` com projeto sintético de ~500 pastas e saída de 200 MB | P |

### 2.3 Robustez e testes
- Fixtures cobrem QE 7.1 e 7.3.1: adicionar saídas 6.x / 7.2 / 7.4 (formatos de Fermi, versão de `.gnu`).
- Testes de propriedade (Hypothesis) para `parse_relax` e `read_gnu` com separadores/linhas truncadas.
- `TextViewer.reload` sem uso: remover ou passar a usar (F10).
- Remover `plot.export.theme` (já sem efeito) numa versão futura.

---

## 3. Interface do usuário

**Navegação**
- **Breadcrumb clicável** no lugar do `path_chip` elidido (`bars.py:151-154,190-195`) + **histórico** Alt+←/→. Hoje só há `..`.
- **Filtro rápido** (Ctrl+F) no explorador e na grade, e filtro por badge (BANDS/PDOS/RELAX) e por estado (INCOMPLETO/ERRO). Projetos com centenas de pastas não têm busca; só ordenação por nome/tamanho/data.
- **Favoritos/recentes**; **multi-seleção** na grade (pré-requisito de F9 e de "copiar vários"); **paleta de comandos** Ctrl+K.

**Workspace**
- **Visualizador de texto**: busca (Ctrl+F), realce (`!    total energy`, `JOB DONE`, `Error`), número de linha, "ir ao fim", **seguir arquivo**. Arquivo grande mostra só 1 MB do início + 2 MB do fim com o meio omitido (`workspace.py:23-42`): oferecer navegação paginada ou "Abrir no editor externo" no banner.
- **Menu de contexto da aba** (fechar outras/todas/à direita, copiar caminho, revelar no explorador) e fechar com botão do meio.
- **Divisão do workspace** (input ao lado do gráfico; dois gráficos) em vez de só abas.



**Barra do gráfico**
- **Coordenadas do cursor**: `NavigationToolbar2QT(..., coordinates=False)` (`plot_view.py:109`) elimina a leitura de E/k sob o mouse. Reativar no `plotMessage`.
- Botões **Copiar imagem** e **Exportar dados** (F3).

**Feedback e estados**
- Sucesso de sync **não** deveria ser modal (`main_window.py:989`, `QMessageBox.information`): usar aviso na barra/toast; modal só para erro/conflito.
- Rodapé: `set_readout` (`bars.py:234`) não elide; em janelas estreitas o texto longo espreme a mensagem. Elidir + tooltip.
- **Estado vazio de primeira execução** (sem `config.yaml`/pasta inexistente): "Escolher pasta…", "Abrir config".
- **Menu Ajuda**: Atalhos (Ctrl+G/E/T e F5 não têm descoberta), Sobre (versão, caminho do log em `cache_dir()/qe_studio.log`), "Abrir log".
- Legenda dos badges/rótulos (BANDS, PDOS, RELAX, SCF, CALC, INCOMPLETO, AVISO) em tooltip.

**Tema e acessibilidade**
- Tema **"Sistema"** (`QStyleHints.colorScheme`, PyQt6 ≥ 6.7 já cobre) além de escuro/claro; `ui.font_scale` no config.
- Checar contraste de `text_dim` sobre `card` (10 px mono nos metadados da grade) com `contrast_ratio` que já existe em `plotting/style.py`; ordem de Tab e foco visível.

**Sincronização**
- **Pré-visualizar o plano** (N novos, M conflitos, tamanho total) antes de transferir. A dry-run já existe; o usuário só vê o resultado.
- **Escopo explícito** no botão "Rsync": sincroniza a pasta atual, ou o projeto todo se nada estiver selecionado (`start_sync`, l.906). Mostrar no tooltip/diálogo.

---

## 4. Roadmap sugerido (próximas specs, na ordem do `specs/README.md`)

| # | Spec proposta | Conteúdo | Esf. |
|---|---|---|---|
| 7 | Qualidade e higiene | A6 CI, A7 ícone/README/commit, O1-O4, sync sem modal, menu Ajuda, elidir rodapé | M |
| 8 | Refatoração do núcleo | A2 `workers.py`, A3 contrato do módulo, A1 divisão do `MainWindow`, A5 | G |
| 9 | Gráficos baratos | F1 SCF, F2 DOS total, F3 exportar dados/copiar imagem, coordenadas do cursor | M |
| 10 | Navegação e texto | Breadcrumb+histórico, filtro rápido, visualizador com busca/realce/seguir | M |
| 11 | Ao vivo | F10 watcher + reload + auto-pull; O5/O6 | M |
| 12 | Relax e bandas avançados | F4 vc-relax completo, F5 bandas+DOS, F6 spin | G |
| 13 | Estilo e comparação | F7 presets, ↺ por campo, F9 comparar | G |
| 14 | Cluster e automação | F11 jobs, F12 CLI, F13 multi-projeto | G |

Motivo da ordem: 7 e 8 reduzem custo e risco de tudo que vem depois (a spec 6 já mostrou que módulo novo é barato **quando** o contrato é limpo, e A3 é o ponto que ainda não é); 9-10 dão valor imediato com pouco risco; 11 muda o modelo mental (app deixa de ser estático); 12-14 são maiores e independentes.

---

## 5. Decisões que dependem de você

1. **Scheduler do cluster**: SGE (Sun Grid Engine).
2. **Multi-projeto** (F13): lista `projects:` no `config.yaml` (respeita "sem janela de configurações", PRD §6) ou estado em QSettings?
3. **Push** (F16): continua fora de escopo?
4. **Idioma**:  preparar `tr()` para inglês e português.
5. **Refatoração antes de features** (specs 7-8 primeiro) ou features baratas primeiro (spec 9)?

## 6. Riscos observados
- O2 (não limpar o `SniffCache`) assume que (mtime, size) basta; um arquivo reescrito com mesmo tamanho e mtime idêntico passaria despercebido. Improvável com rsync `-t`, mas registrar.
- A8 (exportar em thread): matplotlib não é formalmente thread-safe; usar lock ou processo.
- F14/F16 mexem em segurança e integridade de dados: exigir confirmação explícita por arquivo/chave.
- Claims de custo (O4, O5) são **hipóteses não medidas**; cada uma deve ganhar um teste `-m perf` (O8) antes da mudança.
