# Spec 17: Sincronização com prévia do plano, escopo explícito e aviso não modal

| | |
|---|---|
| **Prioridade** | 17 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 15 (`SyncCoordinator`, helper de tarefas) |
| **Usada por** | nenhuma |
| **Esforço** | M |

## Itens de origem (`report.md` §3)

> **Feedback e estados.** Sucesso de sync **não** deveria ser modal (`main_window.py:989`, `QMessageBox.information`): usar aviso na barra/toast; modal só para erro/conflito.
>
> **Sincronização.** **Pré-visualizar o plano** (N novos, M conflitos, tamanho total) antes de transferir. A dry-run já existe; o usuário só vê o resultado. **Escopo explícito** no botão "Rsync": sincroniza a pasta atual, ou o projeto todo se nada estiver selecionado (`start_sync`, l.906). Mostrar no tooltip/diálogo.

## Situação atual

- `MainWindow.start_sync` (`ui/main_window.py:906-931`) sincroniza `current_folder()`: a pasta
  selecionada na árvore, a raiz quando nada está selecionado, e a pasta pai quando um arquivo está
  selecionado (`explorer.py:173-177`). O caminho remoto vem de `remote_dir_for`
  (`core/sync/rsync.py:47-56`). Nem o botão nem o diálogo dizem qual é o escopo.
- `SyncController` (`core/sync/controller.py`) é uma máquina de estados (`rsync --version` → dry-run →
  plano no worker → conflitos → transferência) que **nunca abre diálogos**: emite `conflict_needed` e
  espera `resolve()` (l.171, 270-278).
- O plano (`core/sync/planner.py`):
  - `SyncPlan` com `new`, `conflicts` (UPDATE) e `local_newer`;
  - cada `PlanItem` tem `path`, `action`, `size` e as datas;
  - `controller.plan` (l.150-152) existe, mas nada em `ui/` lê;
  - itens NOVOS são transferidos **sem perguntar** (`_start_transfer`, l.280-283).
- Fim do sync (`_on_sync_finished`, `main_window.py:968-991`): FAILED → `QMessageBox.critical`,
  LOCAL_NEWER → `warning`, CANCELLED → só rodapé, e DONE/UP_TO_DATE →
  **`QMessageBox.information`** (l.989), mais o rodapé por 6 s.
- `SyncDialog` (`ui/dialogs/sync_dialog.py:30-95`): modal da janela, com spinner, etapa, detalhe e
  origem/destino. `ConflictDialog` (l.98-141): um arquivo por vez.
- `SyncConfig` (`core/config.py:112-115`): `exclude`, `rsync_binary`, `ssh_binary`.

## Requisitos

### R1: Escopo explícito
1. O tooltip do botão "Rsync" da barra de atividades e o do item de menu "Cluster ▸ Sincronizar…" são
   atualizados a cada mudança de pasta:
   - pasta selecionada: "Baixar do cluster: `<pasta relativa>` (e subpastas)";
   - nada selecionado ou raiz: "Baixar do cluster: projeto inteiro";
   - sync desligado: "Sincronização desligada: configure cluster.host, cluster.user e
     paths.remote_root".
2. O texto do item de menu acompanha: "Sincronizar `<pasta>`" ou "Sincronizar projeto inteiro".
3. Novo item de menu "Cluster ▸ Sincronizar projeto inteiro", sempre disponível quando o sync está
   ligado, independente da seleção.
4. O cabeçalho do `SyncDialog` e o da prévia (R2) mostram o escopo com os dois caminhos: local
   (relativo ao projeto) e remoto (`host:caminho`).

### R2: Prévia do plano antes de transferir
1. Depois do dry-run e do plano, se houver algo a transferir, o controller emite
   `plan_ready(SyncPlan)` e **espera** `confirm_plan(accepted: bool)`, seguindo o padrão do
   `conflict_needed`/`resolve()`. Continua sem abrir diálogos.
2. Plano vazio (UP_TO_DATE) ou só LOCAL_NEWER: sem prévia. Segue direto para o fim, como hoje.
3. `PlanPreviewDialog` (UI), substituindo a etapa do `SyncDialog` enquanto espera:
   - resumo: "12 arquivos novos (35.2 MB) · 3 a atualizar (1.1 MB) · 2 mais recentes no computador
     (não serão alterados)";
   - lista agrupada por ação e por pasta, colapsável, com tamanho e data remota. Os UPDATE são marcados
     "pedirá confirmação";
   - botões "Baixar" (padrão), "Cancelar" e a caixa "Não mostrar a prévia novamente" (grava em
     QSettings, ver R2.5).
4. "Baixar" → `confirm_plan(True)` → conflitos (UPDATE, um a um como hoje) → transferência. "Cancelar" →
   `confirm_plan(False)` → fim com CANCELLED, sem transferir nada.
5. Config: `sync.confirm_plan: bool = true` (`SyncConfig` e `config.example.yaml`). Com `false`, o
   controller pula o `plan_ready` e se comporta como hoje. A caixa da prévia grava em QSettings
   `sync/skip_preview = true`, que tem precedência. O menu "Cluster" ganha a ação marcável "Mostrar
   prévia antes de baixar" para desfazer.
6. A integridade de dados (PRD §7) continua garantida: a prévia não substitui a confirmação por
   arquivo dos UPDATE. Ela só acrescenta uma confirmação para os NOVOS.

### R3: Fim do sync não modal
1. DONE e UP_TO_DATE: **sem** `QMessageBox`. Mostram:
   - um aviso temporário (*toast*) no canto inferior direito da janela, por 6 s, com a primeira linha do
     relatório ("12 arquivo(s) baixado(s).") e o botão "Detalhes", que abre o relatório completo num
     diálogo **não modal**;
   - a mesma linha no rodapé, como hoje.
2. CANCELLED: só rodapé, como hoje.
3. FAILED: `QMessageBox.critical`, como hoje. LOCAL_NEWER: `QMessageBox.warning`, como hoje (precisa de
   atenção). Conflitos continuam com o `ConflictDialog`.
4. `Toast` é um widget reutilizável (`ui/widgets/toast.py`): fila de mensagens, um toast por vez,
   fecha ao clicar, níveis `info`/`success`/`warning`, com tokens existentes (`popover`, `success`,
   `warning`, `border_strong`). Outras specs podem usar (ex.: exportação concluída, spec 15).

## Fora de escopo
- Escolher na prévia quais arquivos baixar (seleção parcial). A prévia aceita ou cancela tudo.
- Push (F16, fora de escopo pelo PRD).
- Monitor de jobs / sync ao terminar o job (F11, adiado).

## Decisões assumidas (confirmar na revisão)
1. A prévia aparece sempre que há algo a transferir (R2.1), inclusive quando são só arquivos novos. Pode
   ser desligada pelo config ou pela caixa da prévia (R2.5).
2. "Não mostrar novamente" grava em QSettings, e não no `config.yaml`, porque o Lain não escreve no
   config do usuário (PRD §6). O config define o padrão do projeto, e o QSettings, a preferência local.
3. LOCAL_NEWER continua modal (R3.3), porque exige atenção do usuário.
4. Toast de 6 s, igual ao tempo atual do rodapé.

## Notas de implementação
- Alterados:
  - `core/sync/controller.py` (estado "aguardando confirmação do plano", `plan_ready`,
    `confirm_plan`, respeitando `_step()` e o cancelamento);
  - `core/config.py` (`SyncConfig.confirm_plan`), `config.example.yaml`;
  - `ui/sync_coordinator.py` (spec 15) ou `ui/main_window.py`;
  - `ui/dialogs/sync_dialog.py` (`PlanPreviewDialog`, cabeçalho com escopo);
  - `ui/widgets/bars.py` (tooltip do Rsync).
- Novo: `ui/widgets/toast.py`.
- Testes de integração com o `rsync` real e o fixture `ssh_server` (como os atuais, spec 7): o teste responde a
  `plan_ready` com `confirm_plan(True/False)` da mesma forma que responde a `conflict_needed`.

## Critérios de aceite e testes
- [ ] Tooltip do Rsync: com `a/b` selecionado, contém "a/b (e subpastas)". Com a raiz, "projeto
      inteiro". Com sync desligado, o texto de configuração.
- [ ] Controller: com 2 arquivos novos no "remoto", emite `plan_ready` com `len(plan.new) == 2` e não
      transfere nada até `confirm_plan`. `confirm_plan(False)` termina com CANCELLED e nenhum arquivo
      local criado.
- [ ] `sync.confirm_plan: false`: sem `plan_ready`, comportamento atual (testes existentes inalterados).
- [ ] Plano UP_TO_DATE: sem `plan_ready`.
- [ ] Fim DONE: nenhum `QMessageBox` (patch que falha se for chamado). O toast fica visível com a
      mensagem, e o rodapé também.
- [ ] Fim FAILED: `QMessageBox.critical` chamado (como hoje).
- [ ] "Sincronizar projeto inteiro" usa `local_root` mesmo com uma subpasta selecionada.
