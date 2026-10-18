# O que uma spec do Lain precisa responder

A fonte é o `CLAUDE.md` (as regras gerais) e, para a área que a ideia toca, o código e a spec arquivada em
`specs/Archived/` (guardam os invariantes que não cabem aqui). Esta
lista só transforma as regras em perguntas, para a spec não prometer o que o `test_architecture.py` ou a CI vão
recusar. Responda cada pergunta que se aplica; as que não se aplicam, ignore.

## Onde o código mora
- **Há lógica sem widget?** Então é `core/`, Qt-free, e entra em `QT_FREE` (`tests/test_architecture.py`).
  `ui/` só tem widget, layout, diálogo e ligação de sinais.
- **A `ui/` lê ou toca disco?** `open(`, `read_text`, `resolve`, `exists`, `stat`, `iterdir`, `glob`… na `ui/`
  são contados por `FS_ALLOWED` e a conta só diminui: a spec manda para `core/` ou para um worker.
- **Algum arquivo passa de ~500 linhas?** Meça com `wc -l` os que a spec vai tocar. `ui/main_window.py` tem
  limite 450. Perto do limite: a spec diz o que sai e para onde (precedentes: specs 27-3, 27-5, 32).
- **Há trabalho demorado?** Vai por `core/tasks.py` (`run_task` / `TaskGroup`); a GUI nunca lê arquivo. Laço
  novo em `core/` chama `cancel.check()`. Tarefa nova entra no desligamento (`ui/shutdown.py`).
- **Módulo de cálculo?** Contrato em `core/calculations/base.py`: nenhum `kind == "…"` na `ui/`; o que a UI
  precisa é ClassVar ou hook. Estender `DummyModule` em `tests/test_module_contract.py` quando o contrato cresce.

## Dados, configuração e arquivos
- **Parâmetro novo de gráfico?** Campo no dataclass + `ParamField` em `param_schema`; padrão que mantém as
  figuras de hoje (`test_figure_regression.py`, goldens); persiste em `<kind>.plot` só após edição do usuário.
- **Configuração nova?** Não há janela de ajustes (PRD §6): modelo pydantic em `core/config.py` **e** as duas
  cópias idênticas de `config.example.yaml` (raiz e `src/qe_studio/resources/`), com teste em `tests/test_config.py`.
- **Estado da interface?** QSettings (chaves `layout/*`, `files/*`…). Dado do projeto que sobrevive: arquivo JSON
  em `<local_root>/.lain/` (só `core/project_data.py` nomeia a pasta; escrita atômica por `core/appdirs.py`),
  **nunca** dentro de pasta de simulação (elas sincronizam), salvo `plots/` e `<kind>.plot`.
- **A spec escreve em disco?** Nunca sobrescreve sem perguntar (`core/unique_names.py`, `export.plan_export`);
  só em `plots/`, `<kind>.plot` ou na pasta que ela mesma cria.
- **Toca sincronização?** Pull e push passam pela prévia; push só envia arquivos novos; nada apaga no remoto.
- **QE:** versões 7.1 ou mais novas, nada para formatos antigos. Fixture nova = execução **real** aparada em
  `tests/fixtures/qe<versão>_<sistema>/` + linha em `test_qe_versions.py`. Nunca escrever em `tests/fixtures/`.

## Interface
- **Texto novo?** Português, exatamente como o usuário vê. Código, comentário, docstring e commit em inglês.
  Identificadores internos mantêm o nome antigo (`qe_studio`, `QE_STUDIO_*`, `qe-studio-askpass`): não renomear.
- **Cor nova?** Token nos **dois** arquivos de tema (`dark.yaml` e `light.yaml`), com contraste AA em
  `test_theme_contrast.py`. Tamanho que carrega texto vem da escala de fonte (`core/fontscale.py`).
- **Diálogo?** `WA_DeleteOnClose`, **exceto** modal rodado com `exec()` cuja resposta é lida depois (lê, depois
  `deleteLater()`). Não modal: feche em `shutdown.close_dialogs`. Sinais de longa vida em métodos, não em lambdas.
- **Ação nova?** Entra em `ui/actions.py:ACTIONS` (menu, atalho, caminho do slot); atalho de widget em
  `shortcut_help()`. Campo de formulário com rolagem: `NoWheel*`.
- **Foco e teclado?** Controle focável reserva borda de 1 px (`controls/focus.qss`).

## Testes
- Headless (`QT_QPA_PLATFORM=offscreen`), 60 s por teste, sem tocar o `$HOME`. Diálogos se trocam onde são
  importados. Os helpers existem (`grid_helpers`, `viewer_helpers`, `sync_helpers`, `plot_grid_helpers`,
  `calc_helpers`…): nomeie o que reaproveita.
- Modal com `exec()` real: `drive_modal`. Exportação e `.plot`: espere `export_finished` / `flush_now()`.
- Teste de desempenho ganha marca `perf` e orçamento escrito na spec.
- Defeito: teste que **falha antes** da correção.

## Documentação que muda ao implementar
`CLAUDE.md` (só se a spec cria ou muda uma regra geral), `README.md`, `specs/Archived/spec_0-PRD.md` (só se o PRD afirma o contrário),
`config.example.yaml`. A spec lista quais, em "Notas de implementação".
