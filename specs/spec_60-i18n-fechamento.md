# Spec 60: Fechamento da internacionalização (catálogo completo, dados sem idioma, documentação)

| | |
|---|---|
| **Prioridade** | 60, por último: só faz sentido quando 53–59 fecharam as suas áreas. Remove o portão por área, prova que nenhum dado guardado depende do idioma e documenta. Fecha a `spec_end`. |
| **Status** | Rascunho para revisão |
| **Depende de** | 52, 53, 54, 55, 56, 57, 58, 59 (todas com a sua área em `DONE`) |
| **Usada por** | nenhuma |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): o que ela faz são testes transversais e documentação sobre o que as anteriores deixaram pronto. |

## Itens de origem (`Ideias.md`)

> Quero que crie uma série specs para concluir o processo de internacionalização e solucionar quaisquer problemas que possam ter surgido nas tentativas de implementação anteriores […]

Esta é a que "conclui": as anteriores traduzem uma área cada; esta tira o andaime e fecha as garantias que atravessam as áreas
(a `spec_end` R4 e R5 e os critérios de aceite que não são de uma área só).

## Situação atual

Estado esperado ao começar (não verificado hoje: depende de 52–59): `DONE = {53, …, 59}` em `tests/i18n_areas.py`,
`scripts/i18n.py check` sem pendência, `lain.mo` com as 1514+ mensagens traduzidas. Verificado hoje no que ela herda:

- **R1 (andaime).** O portão por área (`AREAS`, `DONE`, `check --area`) é da 52 e só existe para a transição (spec 52 R2.4).
- **R2 (dados guardados).** O Lain grava, na pasta do projeto e do usuário: `.lain/{folders,grids,compounds,navigation}.json`
  (spec 48), `<kind>.plot` e `view3d.plot` em `plots/`, os CSV e imagens exportados, e as chaves de QSettings
  (`params/sections/<kind>/<id>`, com leitura do título antigo em português: `remembered_section`, `ui/widgets/param_widgets.py:119`, `bb3b5a6`).
  Nenhum teste compara o que é gravado sob `pt_BR` com o gravado sob `en`.
- **R3 (porta de entrada).** `lain = "qe_studio.__main__:main"` (`pyproject.toml:20`) instala o idioma antes de importar a
  aplicação; `core/language.py:17-18` define `QE_STUDIO_LANGUAGE` e o apelido `LAIN_LANGUAGE`. `tests/test_language.py`
  cobre a escolha (auto, config, ambiente, linha de comando) e `test_qt_standard_buttons_follow_the_language` o Qt.
- **R4 (documentação).** `config.example.yaml` e a cópia em `src/qe_studio/resources/` já têm `language: auto` (`:101`) e
  são idênticos; `README.md` não tem a seção "Idioma"; `specs/spec_end-internacionalizacao.md` está na raiz de `specs/`
  como rascunho; o roadmap ainda a lista como `fim` e diz "implementadas (1–48 …)" (`specs/README.md:137`).
- **R5 (cabeçalho do `.po`).** O `lain.po` commitado traz marcadores do babel não preenchidos: `Last-Translator: FULL NAME
  <EMAIL@ADDRESS>`, `Report-Msgid-Bugs-To: EMAIL@ADDRESS`, `Project-Id-Version: Lain: QE Studio VERSION`, `PO-Revision-Date: YEAR-MO-DA…`.
- **R6 (CI).** `.github/workflows/ci.yml:40-43` roda `ruff`, `pyright` e a suíte; o catálogo é protegido só pelos testes.

## Requisitos

### R1: Tirar o andaime

1. Remover `tests/i18n_areas.py` e `AREAS`/`DONE`; `test_untranslated_only_in_pending_areas` vira `test_catalog_is_complete`:
   **nenhuma** mensagem do `en` sem tradução ou *fuzzy*. `scripts/i18n.py check` perde `--area` e a tabela por área, sai 0
   quando o catálogo está completo (o resto de `check` fica).
2. `.github/workflows/ci.yml`: um passo `uv run python scripts/i18n.py check` antes da suíte (falha com pendência ou `.mo`
   desatualizado).

### R2: Nenhum dado guardado depende do idioma

1. `tests/i18n_probe.py:persist` (cenário): numa cópia de `demo_project`, faz a mesma sequência de ações em `pt_BR` e em `en`:
   mapear dois arquivos a papéis (`Method.MANUAL`), renomear um rótulo de pasta, salvar um Grid, favoritar e abrir pastas,
   alterar parâmetros de bandas, PDOS, relax e SCF (um de cada tipo `choice`), ajustar uma janela 3D, exportar uma figura e
   criar um cálculo de Slab. Imprime o conteúdo dos arquivos de `.lain/`, os `*.plot`, os nomes dos arquivos de `plots/`, o CSV
   e as chaves de QSettings.
2. `test_persisted_data_is_language_independent`: a saída é **idêntica** nos dois idiomas (nenhum `.json`, `.plot`, nome de
   exportação, CSV ou chave de QSettings muda), exceto o texto que a spec marcou como seguindo a interface: o `geracao.md`
   (56) e o texto copiado das medidas (59), que o teste **exclui por nome** e confere à parte.
3. **Arquivos de antes da série.** Um `bands.plot`, um `pdos.plot`, um `view3d.plot` e um `folders.json` gravados pelo código do
   commit `13eeced` (anterior à série: gerados uma vez com o `demo_project` e guardados em `tests/fixtures/i18n_legacy/`, sem
   texto traduzido) carregam sem erro e **sem reescrita** nos dois idiomas; a chave de QSettings com o título da seção em
   português (`remembered_section`) ainda é lida quando o id não tem estado salvo.

### R3: Entrada real do programa

1. `test_entry_point_language[pt_BR|en|auto]`: `python -m qe_studio --help` em subprocesso, com `QE_STUDIO_LANGUAGE`, com
   `LAIN_LANGUAGE`, com `--config` (`ui.language`) e com `LANG`/`LC_ALL` (para `auto`), mostra a ajuda no idioma esperado;
   `QE_STUDIO_LANGUAGE` vence `LAIN_LANGUAGE`, que vence o config, que vence o sistema (ordem de `core/language.py`).
2. `test_qt_translator`: com `en` e `pt_BR`, os botões padrão do `QMessageBox` (`Yes`/`No`, `Cancel`) aparecem no idioma;
   o teste **pula** se o Qt não tem `qtbase_<idioma>.qm` instalado (o `install_qt_translator` devolve `False`); a pasta
   de traduções do Qt é a de `QLibraryInfo.TranslationsPath`.
3. "Recarregar config.yaml" com `ui.language` diferente do idioma em uso mostra o aviso de reinício (53 R3.3) e **não**
   troca nada na sessão.

### R4: Documentação e arquivamento

1. `README.md`: seção "Idioma": `ui.language: auto | pt_BR | en` (`auto` segue o idioma do sistema: `pt*` → `pt_BR`, o resto →
   `en`), as variáveis `QE_STUDIO_LANGUAGE` e `LAIN_LANGUAGE`, a troca só ao reiniciar, e que as exportações e o `geracao.md`
   seguem o idioma da interface no momento, enquanto CSV, `.plot` e inputs não mudam. Uma linha para quem quiser
   contribuir com a tradução (`locale/README.md`).
2. `config.example.yaml` (as duas cópias, idênticas): o comentário de `ui.language` descreve os três valores.
3. `CLAUDE.md`: conferir a regra de idioma da 52 R6.2 e acrescentar **uma** linha sobre o que o teste `test_i18n.py` garante (sem
   descrever a série).
4. Mover `specs/spec_end-internacionalizacao.md` para `specs/Archived/` com `Status: Implementada. Desvios: …` (gettext em
   vez de `tr()`; português como idioma-fonte; sondagem em subprocesso no lugar do fixture em processo; CSV e `.plot` fora do
   idioma; `.qsub` em português; ids estáveis nas seções) e ajustar o roadmap do `specs/README.md` (a linha `fim` e o parágrafo
   "Specs já implementadas"). As specs 52–59 se movem sozinhas ao serem implementadas (CLAUDE.md).
5. Cabeçalho do `lain.po`: `Project-Id-Version: Lain: QE Studio <versão de pyproject>`, tradutor e contato sem marcador de
   preenchimento (os do usuário), `Language-Team` real; `scripts/i18n.py:new_catalog` passa a preencher (e `update` não o
   desfaz). Teste: o `.po` não contém `EMAIL@ADDRESS` nem `FULL NAME`.

### R5: Aceite visual

1. Capturas `uv run python scripts/screenshot.py --language en` e `--language pt_BR`, nos dois temas, com `--plot`, `--text`,
   `--input`, `--diff`, `--summary`, `--nav`, `--spin` (as capturas **não** entram no repositório): conferidas à mão contra
   texto cortado ou sobreposto. Cada defeito vira uma linha numa spec nova (ou, se for um rótulo de uma palavra, vai nesta).
2. Passo manual de aceite final: `QE_STUDIO_LANGUAGE=en uv run lain` num projeto real, do início ao fim de um fluxo
   (abrir, plotar, exportar, criar cálculo, comparar inputs, medir em 3D, sincronizar em modo de teste).

## Fora de escopo

- Outros idiomas (a infraestrutura permite; não haverá catálogo).
- Traduzir as specs, o PRD, os comentários, o `README.md`, os `.qsub` e os comentários de input.
- Trocar o idioma sem reiniciar; vírgula decimal; localizar datas além do que o Qt faz.

## Decisões assumidas (confirmar na revisão)

1. As garantias transversais (dados sem idioma, ponto de entrada) ficam aqui e não nas áreas, porque dependem de todas.
2. `geracao.md` e o texto copiado das medidas são os únicos arquivos/saídas que **seguem** o idioma (56 R2, 59 R2); o teste os
   exclui por nome em vez de escondê-los.
3. O `README.md` continua em português: a seção "Idioma" explica o recurso, não o traduz.

## Notas de implementação

- Novos: nenhum arquivo de código; `persist` e o teste de entrada entram em `tests/i18n_probe.py` e `tests/test_i18n.py`
  (dividir em `tests/i18n_scenarios_<tema>.py` se passarem de 500 linhas).
- Alterados: `scripts/i18n.py` (`check`, `new_catalog`), `tests/test_i18n.py`, `tests/i18n_probe.py`, `.github/workflows/ci.yml`,
  `README.md`, `config.example.yaml` (raiz e `src/qe_studio/resources/`, idênticos: `tests/test_config.py`), `CLAUDE.md`,
  `src/qe_studio/locale/en/LC_MESSAGES/lain.po`, `specs/README.md`.
- Removidos: `tests/i18n_areas.py`.
- Limites: nenhum arquivo de código chega a 500 linhas.
- Ordem: R1 só depois de todas as áreas em `DONE`; R4.4 por último.

## Critérios de aceite e testes

- [ ] `test_catalog_is_complete` verde; `scripts/i18n.py check` sai 0; o passo novo do CI passa.
- [ ] `test_persisted_data_is_language_independent` verde (com as duas exclusões nomeadas) e o carregamento de arquivos antigos (R2.3).
- [ ] `test_entry_point_language` para os quatro caminhos de escolha; `test_qt_translator` (ou pulado com o motivo).
- [ ] `.po` sem marcadores de preenchimento; `uv build --wheel` traz o `.mo`.
- [ ] `README.md` com a seção "Idioma"; `config.example.yaml` idêntico nas duas cópias; a `spec_end` em `Archived/` e o roadmap coerente.
- [ ] Aceite visual de R5 feito e anotado (sem texto cortado, ou com os defeitos listados).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
