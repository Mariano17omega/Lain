# Spec 63: o "Baixar" compara os arquivos pelo conteúdo (`sync.checksum`, ligado por padrão)

| | |
|---|---|
| **Prioridade** | 63: pequena, independente; corrige dois casos medidos em que a comparação por data erra (pergunta "atualizar?" de um arquivo igual e deixa passar um arquivo diferente) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 17 (prévia do plano e etapas do pull), spec 27-3 (`recheck_local`), spec 58 (textos do sync em `_()`) |
| **Usada por** | spec 66 (a cópia de `tmp_remote` usa o mesmo dry run e herda a opção) |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): uma opção a mais num caminho que as specs 17 e 27 abriram (comando do rsync, planner, texto da etapa), com o comportamento medido abaixo |

## Itens de origem (`Ideias.md`, 25/10/2026)

> - Implementar checksum na sincronização.

Decisão do usuário (25/10/2026, depois da explicação abaixo): **comparar pelo conteúdo, ligado por padrão (`sync.checksum: true`, com
opção de desligar)**. A conferência de integridade **depois** da transferência não entra: o rsync já a faz em todo arquivo transferido.

## Situação atual

- **Conferência depois da transferência: já existe.** O rsync calcula um checksum do arquivo inteiro durante a transferência e o confere
  no destino; o `man rsync` da 3.5.0 instalada aqui diz que essa verificação só desliga com `--checksum-choice=none`. O Lain não passa essa
  opção (`grep checksum src/qe_studio/core/sync/` não acha nada).
- **Decidir o que baixar: só data e tamanho.** `core/sync/rsync.py:151` (`dry_run_command`) roda `rsync -n -rt -i --modify-window=1`
  (`:164`): o rsync lista o que difere em tamanho ou data. `core/sync/planner.py:101` (`build_plan`) decide por item: arquivo local que
  falta → `NEW`; local mais novo → `LOCAL_NEWER`; cluster mais novo ou tamanho diferente → `UPDATE` (`:117`); senão o item é descartado
  (`:120`, "same file within tolerance"). A etapa diz "Comparando datas de modificação…" (`core/sync/_process.py:47`, `PLANNING`).
- **Medido** com o rsync 3.5.0 local, num par de pastas de teste (`--out-format=%i|%l|%M|%n`, `LC_ALL=C.UTF-8`, `TZ=UTC`):

  | Caso | `-rt` (hoje) | `-rt --checksum` |
  |---|---|---|
  | mesmo conteúdo, data do cluster mais nova | `>f..t......`: vira `UPDATE` e o Lain pergunta "atualizar?" | `.f..t......`: `is_file` (`rsync.py:262`) o descarta |
  | mesma data e tamanho, conteúdo diferente | **não listado**: a diferença passa | `>fc........`: listado, mas `build_plan` o descarta em `:120` (datas e tamanho iguais) |
  | arquivo só no cluster | `>f+++++++++` → `NEW` | igual |

  A mesma lógica vale para um arquivo local só com a data mais nova (cópia, `touch`): hoje vira `LOCAL_NEWER` e o aviso "local mais
  recente" aparece à toa; com `--checksum` ele não é listado.
- O envio (`push_dry_run_command`, `rsync.py:197`) só manda arquivos que o cluster não tem (`--ignore-existing` na transferência,
  `core/sync/push_plan.py:is_new`); o checksum não muda o que vai.
- Os testes de integração montam conflitos com **conteúdo diferente** (`tests/test_sync_integration.py:70`, `:206`): continuam valendo com
  o checksum ligado (não verificado para toda a suíte: rodar).
- Tamanhos: `core/sync/rsync.py` 383, `core/sync/planner.py` 197, `core/sync/_process.py` 331, `core/sync/controller.py` 186,
  `core/config.py` 430.

## Requisitos

### R1: `sync.checksum` e o dry run do "Baixar"

1. `core/config.py:SyncConfig` (`:138`) ganha `checksum: bool = True`, com o comentário "Compare files by content (rsync --checksum) to
   decide what to download; false: by date and size (faster on big trees)." Nos dois `config.example.yaml`, em `sync:`, com o mesmo
   texto e o custo: "reads every file on both sides on each sync".
2. `core/sync/rsync.py:dry_run_command`: com `config.sync.checksum`, `--checksum` entra logo depois de `-rt`. `transfer_command`,
   `push_dry_run_command` e `push_transfer_command` **não** mudam.
3. Etapa do pull: com o checksum ligado, "Comparando o conteúdo dos arquivos…" no lugar de "Comparando datas de modificação…" (o
   `SyncController` escolhe o texto pelo config; o do push, `core/sync/push.py:28`, fica).
4. **Testes** (`tests/test_sync_rsync.py`): `test_pull_dry_run_compares_content_by_default` (`--checksum` no comando com o config
   padrão), `test_checksum_off_is_todays_command` (sem `--checksum` com `checksum: false`; o resto do comando idêntico ao de hoje),
   `test_push_never_uses_checksum` (dry run e transferência do push sem a opção, com ela ligada). `tests/test_config.py`:
   `test_checksum_is_on_by_default_and_documented` (as duas cópias do exemplo têm a chave).

### R2: o plano entende "conteúdo diferente"

1. `core/sync/planner.py:build_plan`: um registro cujo código tem `c` na terceira posição (`>fc…`: checksum diferente, só com
   `--checksum`) é `UPDATE` quando as datas estão dentro da tolerância, mesmo com tamanho igual (hoje é descartado em `:120`). Local mais
   novo continua `LOCAL_NEWER`; cluster mais novo continua `UPDATE`. Um registro sem o `c` decide como hoje.
2. Nada muda depois do plano: prévia, pergunta arquivo a arquivo (PRD §5.4), `recheck_local` e relatório.
3. **Testes:**
   - `tests/test_sync_planner.py::test_same_dates_different_content_is_an_update`: `DryRunItem(">fc........", …)` com a mesma data e o
     mesmo tamanho do arquivo local vira `UPDATE` (falha hoje).
   - `tests/test_sync_integration.py` (rsync real, pastas locais como nas vizinhas, `write(..., mtime)` de `sync_helpers`):
     - `test_same_content_with_newer_date_is_up_to_date`: o arquivo do cluster com o mesmo conteúdo e data mais nova dá `UP_TO_DATE`, sem
       prévia nem pergunta (falha hoje: pergunta "atualizar?");
     - `test_same_date_and_size_but_other_content_asks`: mesmo tamanho e data, conteúdo diferente → a pergunta de conflito aparece e
       "Sobrescrever" traz o conteúdo do cluster (falha hoje: `UP_TO_DATE`);
     - `test_local_copy_with_newer_date_only_is_not_local_newer`: o aviso "local mais recente" não aparece para um arquivo igual;
     - `test_checksum_off_keeps_todays_decisions`: com `checksum: false`, os dois primeiros casos dão o resultado de hoje.
   - `tests/test_sync_ssh.py`: um pull pelo servidor SSH local (`tests/ssh_server.py`) com o checksum ligado termina `DONE` (o
     `--checksum` passa pelo `rsync --server` da lista permitida).

## Fora de escopo

- Conferir um hash depois da transferência e mostrá-lo no relatório: o rsync já confere (decisão do usuário).
- Checksum no envio: não muda o que é enviado (decisão 2).
- Escolher o algoritmo (`--checksum-choice`): o rsync negocia o mais forte que os dois lados têm.

## Decisões assumidas (confirmar na revisão)

1. **Ligado por padrão** (decisão do usuário). Quem tem árvores muito grandes desliga com `sync.checksum: false`.
2. **Só o "Baixar".** No envio, o `--checksum` só tiraria da prévia os arquivos iguais que já estão no cluster ("já existe"), ao custo de
   ler todos; o que é enviado não muda.
3. **Sem confirmação extra de custo:** a etapa "Comparando o conteúdo dos arquivos…" com o indicador de progresso de hoje basta.

## Notas de implementação

- Alterados: `core/config.py` (`SyncConfig.checksum`), `core/sync/rsync.py` (`dry_run_command`), `core/sync/planner.py` (`build_plan`),
  `core/sync/controller.py` (texto da etapa), os dois `config.example.yaml`, o catálogo `lain.po`/`.mo` (texto novo).
- Limites: nenhum arquivo perto do limite.
- Documentação ao implementar: `README.md`, "How sync decides" (`:175-188`: os arquivos são comparados pelo conteúdo antes das datas;
  `sync.checksum: false` volta à data e tamanho); `specs/Archived/spec_0-PRD.md` §5.2 (uma linha: com `sync.checksum`, só os arquivos
  de conteúdo diferente entram na comparação de datas).
- i18n: o texto da etapa em `_()`, depois `scripts/i18n.py update`, tradução e `compile`.

## Critérios de aceite e testes

- [ ] Com `checksum: false` o comando e as decisões são os de hoje (`test_checksum_off_is_todays_command`,
      `test_checksum_off_keeps_todays_decisions`); os testes de integração existentes passam sem mudar a expectativa.
- [ ] Ligado por padrão e documentado (`test_checksum_is_on_by_default_and_documented`, `test_pull_dry_run_compares_content_by_default`).
- [ ] Arquivo igual com outra data não pergunta nem avisa (`test_same_content_with_newer_date_is_up_to_date`,
      `test_local_copy_with_newer_date_only_is_not_local_newer`); arquivo diferente com a mesma data pergunta
      (`test_same_dates_different_content_is_an_update`, `test_same_date_and_size_but_other_content_asks`).
- [ ] O envio não muda (`test_push_never_uses_checksum`); o pull por SSH funciona com a opção (`tests/test_sync_ssh.py`).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes.
