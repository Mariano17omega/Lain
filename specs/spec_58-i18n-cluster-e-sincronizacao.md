# Spec 58: Inglês do cluster e da sincronização (prévia, relatório, envio e falhas do ssh)

| | |
|---|---|
| **Prioridade** | 58: o texto que o usuário lê antes de **autorizar** uma cópia (prévia do pull e do envio) e ao entender uma falha de conexão; por isso a tradução é revisada contra as regras de segurança do sync. Independente de 53–57 e 59. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 52 (portão, probe, glossário); specs 17 (prévia e escopo) e 27 (envio ao cluster) e 27-3 (`StrictHostKeyChecking=yes`) |
| **Usada por** | 60 |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): área pequena e já marcada; o cuidado é com o sentido das frases que dizem o que será ou não alterado. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. […]

Área 58 de `AREAS` (spec 52 R2): `core/sync/`, `ui/sync_coordinator.py`, `ui/dialogs/{sync_dialog,sync_pages}.py`.

## Situação atual

Contagem da 52 (`check --area 58`, 18/10/2026): **104 mensagens, 59 sem tradução**, 45 traduzidas e não revisadas;
`core/sync/` tem 18 linhas com `ngettext` (contagens de arquivos).

- **R1 (valores que são dados).** `Action` (`core/sync/planner.py:24`: `NEW = "novo"`, `UPDATE = "atualizar"`,
  `LOCAL_NEWER = "local mais recente"`) e `PushAction` (`core/sync/push_plan.py:16`: `NEW = "enviar"`,
  `EXISTS = "já existe"`) têm valores em português que são dados; a prévia mostra os textos dos dicionários de
  `core/sync/preview.py:16-32` (`Novos`, `A atualizar`, `Mais recentes no computador`, `Serão enviados`, `Já existem no
  cluster, não serão alterados`, e as notas `pedirá confirmação` / `não será alterado`), todos por `_()`.
  `ConnectionState` (`core/sync/monitor.py:27`) já tem valores em inglês (`online`, `offline`…).
- **R2 (falhas do ssh).** `core/sync/rsync.py:324-330` (`FAILURE_HINTS`) casa o `stderr` do ssh/rsync **em inglês**
  (`"Host key verification failed"`, `AUTH_DENIED`, `"Could not resolve hostname"`…) e mostra a dica em português por
  `_()`. Os `rsync` filhos rodam com `LC_ALL=C.UTF-8` (CLAUDE.md), então o texto casado não depende do idioma do app.
  `SyncReport.auth_failed` (spec `end`, `bb3b5a6`) decide a falha de senha **sem** olhar o texto traduzido.
- **R3 (segurança).** A senha só chega ao ssh por `SSH_ASKPASS`, nunca em argumento nem em log; as chaves de host
  desconhecidas são sempre recusadas (`StrictHostKeyChecking=yes`); o envio só **adiciona** arquivos. Nada disso pode mudar
  de sentido ao traduzir: "não serão alterados" é uma garantia, não um enfeite.
- **R4 (menus e rodapé).** `ui/sync_coordinator.py` monta os textos "Sincronizar <pasta>", "Sincronizar projeto <nome>",
  "Sincronizar tudo" e "Enviar <pasta> ao cluster…" (`:139-143`, `TITLE`/`PUSH_TITLE` em `:45-46`, `cluster não
  configurado` em `:192`).
- **R5 (testes).** Os testes de sync rodam o `rsync` e o `ssh` de verdade contra `tests/ssh_server.py` (paramiko em
  `127.0.0.1`); `server.ssh_binary()` fixa o ssh num `ssh_config` temporário e não pode ser contornado.

## Requisitos

### R1: Traduzir a área

1. Traduzir as 59 mensagens de `scripts/i18n.py check --area 58` e revisar as 45 já traduzidas. Termos (glossário da 52):
   `Sincronizar` → `Sync`; `Baixar` → `Download` e `Enviar` → `Upload` (par decidido na revisão da 52, já no
   `locale/README.md`), os mesmos nos dois lugares em que aparecem (menu e prévia) e em toda a área. `Cluster`, `rsync`,
   `ssh`, `config.yaml`, `cluster.host`, `SSH_ASKPASS`, `StrictHostKeyChecking` ficam como estão.
2. As frases que dizem o que **não** acontece (`Já existem no cluster, não serão alterados`, `não será alterado`, `pedirá
   confirmação`) mantêm a negação e o sujeito: `Already on the cluster, will not be changed`, `will not be changed`, `will
   ask for confirmation`. O teste de R3.3 as lê em inglês.
3. `ngettext` com as duas formas (as 18 linhas de `core/sync/`); `1 file`/`2 files`, `1 folder`/`2 folders`.
4. Os valores `Action`/`PushAction` **não mudam** (`Action.NEW.value == "novo"`); só os textos exibidos.

### R2: Falhas e logs

1. As dicas de `FAILURE_HINTS` em inglês, com a mesma ordem e o mesmo critério de casamento do `stderr`; a dica de senha
   recusada continua sendo escolhida por `SyncReport.auth_failed`.
2. O log continua em inglês e não é traduzido (decisão da `spec_end`); nenhuma mensagem traduzida entra no log com dado
   sensível (o teste de senha de `test_sync_*` roda em `en` e confere que a senha não aparece em nenhuma saída).

### R3: Cenários e testes em `en`

1. `tests/i18n_probe.py` ganha: `sync_preview_pull` (prévia com os três grupos de `ACTION_ORDER`), `sync_preview_push` (os dois
   de `PUSH_ORDER`), `sync_report` (relatório de uma sincronização e de uma falha de autenticação), `sync_menu` (as quatro
   ações do menu, em escopo de pasta e de projeto) e `sync_failures` (uma mensagem por `FAILURE_HINTS`).
   Os dados vêm dos helpers de `tests/sync_helpers.py`, **sem** abrir conexão.
2. `test_no_leaks_in_english[<cenário>]` para os cinco.
3. `test_sync_in_english_end_to_end` (subprocesso `en`, `tests/ssh_server.py` + `server.ssh_binary()`): um pull e um envio de
   `demo_project` terminam com o mesmo conjunto de arquivos copiados que em `pt_BR`; o envio não sobrescreve um arquivo que
   o cluster já tem (o texto `will not be changed` aparece na prévia desse arquivo).
4. `test_failure_hints_follow_stderr`: para cada `needle` de `FAILURE_HINTS`, um `stderr` sintético escolhe a dica certa em
   `en` e em `pt_BR`.

### R4: Fechar a área

1. `update`, `compile`, `DONE |= {58}`; `test_untranslated_only_in_pending_areas` passa.

## Fora de escopo

- Traduzir a saída do `rsync` e do `ssh` (vêm dos programas, em inglês).
- Mudar a política de segurança do sync ou o formato da prévia.
- O botão de sincronização da barra e o LED (área 53, se tiverem texto).

## Decisões assumidas (confirmar na revisão)

1. `Download`/`Upload` nos menus e na prévia (decidido pelo usuário na revisão da 52, 18/10/2026): mais claro para quem
   usa o programa que `Pull`/`Push`, que seguem só como nomes internos (código, CLAUDE.md, specs).
2. O teste de ponta a ponta de R3.3 roda só um pull e um envio: o resto da matriz do sync já é testada em `pt_BR` e o texto
   não participa da lógica (R2 de "Situação atual").

## Notas de implementação

- Novos: nenhum arquivo de código.
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `.mo`; `tests/i18n_areas.py`; `tests/i18n_probe.py`; `tests/test_i18n.py`.
- Limites: nenhum arquivo perto de 500 linhas; esta spec não altera código de `core/sync/`.
- Documentação ao implementar: nenhuma.

## Critérios de aceite e testes

- [ ] A suíte de sync de hoje passa sem alteração; `Action`/`PushAction` com os mesmos valores.
- [ ] `check --area 58` vazio; `test_untranslated_only_in_pending_areas` passa com a área em `DONE`.
- [ ] `test_failure_hints_follow_stderr` e `test_sync_in_english_end_to_end` verdes; a senha não aparece em nenhuma saída em `en`.
- [ ] `test_no_leaks_in_english` para os cinco cenários; plurais com as duas formas.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
