# Spec 17: Sincronização com prévia do plano, escopo explícito e aviso não modal

| | |
|---|---|
| **Prioridade** | 17 |
| **Status** | Implementada. Desvios: o texto do escopo fica em `core/sync/request.py` (`SyncScope`, `sync_scope`), o da prévia (grupos, resumo, linha de arquivos grandes) em `core/sync/preview.py` e o relatório completo em `core/sync/report.py` (`SyncReport.details`, do botão "Detalhes"), e não na UI (CLAUDE.md, spec 15 R5.3); o controller também emite `transfer_started`, que leva o `SyncDialog` à página de transferência (sem depender do texto da etapa); o aviso de LOCAL_NEWER também abre sobre o `SyncDialog`, que fecha depois dele, como em FAILED; o `SyncDialog` ganhou o botão de fechar (X), que equivale a Esc em todas as páginas (cancela); "Detalhes" fecha o toast; o tooltip do item de menu aparece porque os menus mostram tooltips (`setToolTipsVisible`); `SyncPlan.large` conta itens de qualquer ação, inclusive os mais recentes no computador, que não são baixados |
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
3. O próprio `SyncDialog` torna-se uma janela multi-etapas baseada em `QStackedWidget`, evitando empilhamento
   e abertura/fechamento sucessivo de popups (*dialog hell* / flicker):
   - **Página 0 (Conexão e Análise):** spinner, etapa atual ("Listando arquivos no cluster…", dry-run) e escopo;
   - **Página 1 (Prévia do Plano):** exibida ao emitir `plan_ready`:
     - resumo: "12 arquivos novos (35.2 MB) · 3 a atualizar (1.1 MB) · 2 mais recentes no computador (não serão alterados)";
     - lista agrupada por ação e por pasta, colapsável, com tamanho e data remota. Os UPDATE são marcados "pedirá confirmação";
     - **Destaque para arquivos volumosos:** arquivos grandes (> 100 MB, frequentes em `.wfc`, densidades de
       carga ou dados brutos de QE) permitem ao usuário identificar arquivos indesejados antes de esgotar o
       disco ou a banda:
       - o limiar é a constante `LARGE_FILE_BYTES = 100 * 1024**2` de `core/sync/planner.py`, com
         `PlanItem.is_large` e `SyncPlan.large`. A UI só lê esses valores, sem decidir o que é "grande";
       - cada item grande ganha ícone de alerta (token `warning`) e tamanho em negrito, com tooltip
         "Arquivo grande: confira o espaço em disco antes de baixar";
       - dentro de cada grupo (ação, pasta), os itens ordenam por tamanho decrescente, então os grandes
         ficam no topo. Um grupo que contém item grande abre expandido e os demais abrem recolhidos;
       - o resumo ganha uma linha de aviso (cor `warning`) quando `plan.large` não está vazio: "2 arquivos
         grandes somam 14.3 GB";
     - botões "Baixar" (padrão) e "Cancelar". Fechar a janela (Esc, X) na Página 1 equivale a "Cancelar";
   - **Página 2 (Transferência):** barra de progresso real da transferência após confirmação. Enquanto um
     `ConflictDialog` (filho de `SyncDialog`) espera resposta, a Página 2 mostra "Aguardando sua
     decisão…". Ao fim DONE/UP_TO_DATE, o `SyncDialog` fecha e o toast (R3) assume. Em FAILED, o
     `QMessageBox.critical` abre sobre o `SyncDialog`, que fecha depois dele;
   - Conflitos (`ConflictDialog`) continuam com diálogo próprio filho de `SyncDialog` quando necessário.
4. "Baixar" → `confirm_plan(True)` → conflitos (UPDATE, um a um como hoje) → transferência (Página 2). "Cancelar" →
   `confirm_plan(False)` → fecha diálogo, fim com CANCELLED, sem transferir nada.
5. A prévia sempre abre quando houver algo a transferir (sem opção de pular na interface). Config opcional
   para automação/testes: `sync.confirm_plan: bool = true` (`SyncConfig` e `config.example.yaml`). Com
   `false`, o controller pula o `plan_ready` e transfere diretamente.
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
4. `Toast` é um widget reutilizável (`ui/widgets/toast.py`):
   - fila de mensagens, um toast por vez, fecha ao clicar, níveis `info`/`success`/`warning`, com tokens existentes (`popover`, `success`, `warning`, `border_strong`);
   - **Ciclo de vida e posicionamento:** o `Toast` é um widget **filho** da `MainWindow` (nunca uma janela
     de topo), então mover a janela o leva junto sem código. Redimensionar é tratado por um `eventFilter`
     instalado no pai: em `QEvent.Type.Resize` (e `Show`) o toast se reposiciona no canto inferior direito,
     com margem de 16 px e acima do rodapé (`StatusBar`), e é limitado à largura do pai (`raise_()` após
     reposicionar). Remover o filtro e esconder o toast ao ser destruído ou fechado (sem `QTimer` solto
     que dispare depois da janela). A conta da posição é uma função pura
     `toast_position(parent_size, toast_size, margin, footer_height) -> QPoint`, testável sem exibir a janela;
   - **Feedback visual do tempo:** uma barra regressiva de 3 px na base do toast, de 100% a 0% em 6 s
     (`QPropertyAnimation`), e um *fade out* de opacidade de 300 ms (`QGraphicsOpacityEffect`) ao
     expirar. O mouse sobre o toast pausa a barra e o timer, e a retomada continua de onde parou. Clicar
     fecha na hora (sem fade). O próximo da fila aparece só depois do fade terminar;
   - Outras specs podem usar (ex.: exportação concluída, spec 15).

## Fora de escopo
- Escolher na prévia quais arquivos baixar (seleção parcial). A prévia aceita ou cancela tudo.
- Push (F16, fora de escopo pelo PRD).
- Monitor de jobs / sync ao terminar o job (F11, adiado).

## Decisões assumidas (confirmar na revisão)
1. A prévia aparece sempre que há algo a transferir (R2.1), inclusive quando são só arquivos novos, sem
   opção de pular na interface (garantindo previsibilidade total antes de transferir).
2. O `SyncDialog` unifica análise, prévia e transferência em `QStackedWidget` para garantir estabilidade visual.
3. LOCAL_NEWER continua modal (R3.3), porque exige atenção do usuário.
4. Toast de 6 s, com acompanhamento de geometria da janela e barra regressiva.
5. O limiar de arquivo grande (100 MB) é constante em `core/sync/planner.py`, sem chave no `config.yaml`:
   é um aviso, não uma regra. Se alguém precisar ajustar, vira `sync.large_file_mb` numa spec própria.

## Notas de implementação
- Alterados:
  - `core/sync/controller.py` (estado "aguardando confirmação do plano", `plan_ready`,
    `confirm_plan`, respeitando `_step()` e o cancelamento);
  - `core/config.py` (`SyncConfig.confirm_plan`), `config.example.yaml`;
  - `ui/sync_coordinator.py` (spec 15) ou `ui/main_window.py`;
  - `core/sync/planner.py` (`LARGE_FILE_BYTES`, `PlanItem.is_large`, `SyncPlan.large`, soma em bytes);
  - `ui/dialogs/sync_dialog.py` (só a janela, o `QStackedWidget` e a troca de página por sinal do
    controller; cabeçalho com escopo);
  - `ui/widgets/bars.py` (tooltip do Rsync).
- Novos:
  - `ui/dialogs/sync_pages.py` (as três páginas: busca, prévia e transferência) e, se a prévia passar de
    ~200 linhas, `ui/dialogs/plan_preview.py` (árvore agrupada, ícone e ordenação). `test_architecture`
    exige cada arquivo abaixo de 500 linhas, e `sync_dialog.py` hoje já tem ~140 antes de ganhar a prévia;
  - `ui/widgets/toast.py` (`Toast`, fila, `eventFilter` do pai, fade e barra regressiva) e a função pura
    `toast_position`.
- Testes de integração com o `rsync` real e o fixture `ssh_server` (como os atuais, spec 7): o teste responde a
  `plan_ready` com `confirm_plan(True/False)` da mesma forma que responde a `conflict_needed`.

## Critérios de aceite e testes
- [x] Tooltip do Rsync: com `a/b` selecionado, contém "a/b (e subpastas)". Com a raiz, "projeto
      inteiro". Com sync desligado, o texto de configuração.
- [x] Diálogo unificado: `SyncDialog` usa `QStackedWidget`, mantendo a mesma janela estável desde a listagem até o progresso, sem fechar/reabrir janelas entre o dry-run e a prévia.
- [x] Controller: com 2 arquivos novos no "remoto", emite `plan_ready` com `len(plan.new) == 2` e não
      transfere nada até `confirm_plan`. `confirm_plan(False)` termina com CANCELLED e nenhum arquivo
      local criado.
- [x] Planner (sem Qt): `PlanItem.is_large` é falso em exatamente 100 MB e verdadeiro em 100 MB + 1 byte.
      `SyncPlan.large` lista só os itens acima do limiar, de qualquer ação.
- [x] Destaque de arquivos grandes: na prévia, o item de 150 MB tem ícone de alerta e tooltip, o de 1 KB
      não. O grupo vem ordenado por tamanho decrescente, e o resumo mostra a linha "arquivos grandes
      somam …" só quando há algum.
- [x] `sync.confirm_plan: false`: sem `plan_ready`, comportamento direto (testes existentes inalterados).
- [x] Plano UP_TO_DATE: sem `plan_ready`.
- [x] Fim DONE: nenhum `QMessageBox` (patch que falha se for chamado). O toast fica visível com a
      mensagem, barra regressiva de 6 s, e o rodapé também.
- [x] Toast responsivo: ao redimensionar a `MainWindow`, o Toast reposiciona-se no canto inferior direito
      (a posição acompanha `toast_position` para o novo tamanho). `toast_position` é testada sem Qt
      visível, inclusive com janela menor que o toast (fica limitado à largura do pai).
- [x] Toast, ciclo de vida: ao mover a janela o toast continua no mesmo canto (é filho, não janela de topo).
      Fechar a `MainWindow` com um toast aberto não dispara timer nem animação depois (sem erro no log).
- [x] Toast, tempo: a barra regressiva termina em 6 s e o fade de 300 ms vem em seguida (testes com a
      duração injetada, sem esperar 6 s reais). Com dois avisos na fila, o segundo só aparece depois do
      fade do primeiro. Clique fecha na hora.
- [x] `SyncDialog`: ao fim DONE a janela fecha e o toast aparece. Esc na Página 1 equivale a "Cancelar"
      (`confirm_plan(False)`, CANCELLED).
- [x] Fim FAILED: `QMessageBox.critical` chamado (como hoje).
- [x] "Sincronizar projeto inteiro" usa `local_root` mesmo com uma subpasta selecionada.
