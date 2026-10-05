# Spec 27-9: Pequenos defeitos — "Abrir com" de programas de terminal, pedido repetido de carga e dados pessoais no repositório

| | |
|---|---|
| **Prioridade** | 27-9 (última das correções da revisão de 04/10/2026) |
| **Status** | Proposta |
| **Depende de** | spec 5 (menu de contexto, "Abrir com"), spec 15 (`PlotWorkflow`), spec 7 (`config.example.yaml`) |
| **Usada por** | nenhuma |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): três correções pequenas e independentes, cada uma com arquivo, linha e teste identificados. |

## Itens de origem (`specs/report-04-10-26.md` e decisões do usuário)

- **B1 (Médio):** "Abrir com" lista (e lança sem terminal) programas `.desktop` com `Terminal=true` (vim, nano, htop…); nada acontece e não há mensagem. **Decisão do usuário: ocultar da lista.**
- **B6 (Baixo):** `PlotWorkflow._load` ignora em silêncio o pedido repetido (um "Remapear" feito durante uma carga é descartado).
- **S4 (Baixo):** dados pessoais no repositório (host, usuário e caminho do cluster, nomes e e-mails nos cabeçalhos dos scripts de referência). **Decisão do usuário: placeholders no
  `config.example.yaml` e cabeçalhos de `Documentation/` anonimizados.**

## Situação atual

- **B1.** `core/desktop_apps.py`: `DesktopApp` (`:25`) tem `id, name, exec, icon, mime_types, path` (6 campos); `parse_desktop_file` (`:95-113`) lê `Type`, `NoDisplay`, `Hidden`, `Exec`, `TryExec`,
  `Name`, `Icon` e `MimeType`; **`Terminal` não é lido em lugar nenhum**. `expand_exec(app, path)` (`:221-256`) monta o `argv` expandindo `%f %F %u %U %i %c %k`. Lançamento:
  `ItemActions.open_with` (`ui/widgets/context_menu.py:234`) → `_launch(expand_exec(app, path), path, app.name)` (`:251`) → `QProcess.startDetached(argv[0], argv[1:], str(path.parent))`;
  `open_default` (`:237`) usa `catalog().default_app(mime_types_for(path))` e, sem programa padrão, `QDesktopServices.openUrl`. Não há detecção de emulador de terminal. Testes: `tests/test_desktop_apps.py`
  (`write_app(data_dir, name, body)` `:8`, `write_list`, fixture `dirs`, `catalog(dirs)`; `app(exec_line, icon)` `:109` constrói `DesktopApp("x.desktop", "Prog", exec_line, icon, frozenset(),
  Path("/apps/x.desktop"))` **por posição**; `test_expand_exec` parametrizado em `:114-126`).
- **B6.** `ui/plot_workflow.py:259-262` (`_load`): `if key in self._loading: return`. O pedido repetido (um `remap` `:191-198` com mapeamento novo, um `auto_export=True`, uma recarga depois de sync ou
  invalidação) é descartado sem aviso. `_loads.submit` (`:267-270`) já cancela a tarefa anterior da mesma chave, mas o guarda impede de chegar lá. A chave só sai de `_loading` em `_finish_load` (`:299`,
  chamado por `_on_stored` e `_on_load_failed`). O carregador do grid usa chaves próprias (`name#gen:r,c`), sem colisão.
- **S4.** Ocorrências verificadas em 05/10/2026:
  - `config.example.yaml` e `src/qe_studio/resources/config.example.yaml` (idênticos, `tests/test_config.py:199-203`): `remote_root: /home/mariano/qe_simulations` (l.9), `host: 10.220.200.1` (l.12),
    `user: mariano` (l.14). `test_example_config_validates` (`test_config.py:34-41`) carrega a cópia da raiz e exige `config.cluster.host == "10.220.200.1"` (l.36) e `config.sync_enabled`.
  - `scripts/screenshot.py:160-161`: `"remote_root": "/scratch/mariano/MoS2"`, `"host": "10.220.200.1"`, `"user": "mariano"`.
  - `specs/spec_0-PRD.md:120`: "Cluster Host/IP (e.g., `10.220.200.1`)".
  - `Documentation/Referencia_de_scripts_QSUB/PDOS.qsub:3-4`: `# Cicero Mota, mota@ufam.edu.br: Sep 1, 2018; Jun 29, 2022; Jul 18, 2022.` e `# Mariano S. onairam17@gmail.com: Apr 17, 2025.`
    (os outros `.qsub` de referência não têm nomes). `tests/test_calc_templates.py:68`: `_IGNORED = ("# Executa o programa", "# Cicero", "# Mariano", "PLOTCOMMAND=")` ignora essas linhas ao comparar
    o corpo do script gerado com a referência.
  - `Documentation/design system (UX)/qe_studio_interface_clean_integrada/code.html` e `…_tema_claro/code.html`: maquetes com o usuário e o IP.
  - `tests/fixtures/**`: saídas reais do QE com caminhos do usuário e do cluster (fora de escopo, ver abaixo).
  - `src/qe_studio/ui/dialogs/about.py:22` (`REPOSITORY = "https://github.com/Mariano17omega/Lain"`) e o selo de CI do `README.md:3` apontam para o repositório; isso é o endereço do projeto, **não** dado a
    esconder.
  - `config.yaml` real está no `.gitignore` (l.221).

## Requisitos

### R1: "Abrir com" sem programas de terminal (B1)
1. `DesktopApp` ganha `terminal: bool = False` como **último** campo, com padrão (os testes que constroem por posição continuam válidos). `parse_desktop_file` lê `Terminal` (valor `true`, sem diferenciar
   caixa, é verdadeiro; ausente ou outro valor é falso).
2. O catálogo mostra em "Abrir com" apenas `terminal == False`. Programas de terminal continuam no catálogo interno (`by_id`) para quem referencia o `.desktop` por id, mas não aparecem em listas.
3. `default_app(mime_types)`: um padrão do `mimeapps.list` que seja de terminal é **pulado**; vale o próximo candidato da lista de associações; sem nenhum, `open_default` cai em
   `QDesktopServices.openUrl` (comportamento de hoje sem programa padrão).
4. Testes (`test_desktop_apps.py`): `.desktop` com `Terminal=true` não aparece na lista de um tipo MIME que ele declara; `Terminal=false` e sem a chave aparecem; padrão de terminal é pulado e o seguinte
   vale; com só terminal, `default_app` devolve `None`; `DesktopApp` posicional de 6 argumentos continua funcionando; o campo é lido com `Terminal=True`/`true`/`TRUE`.

### R2: Pedido repetido de carga (B6)
1. `_load` deixa de descartar: um pedido novo para uma chave que já carrega **substitui** o anterior. `_loads.submit` cancela a tarefa em andamento (`TaskGroup`), `_loading[key]` guarda uma **geração**
   (inteiro crescente) e `_finish_load`/`_on_stored`/`_on_load_failed` ignoram o resultado de uma geração que não é a corrente (hoje a tarefa cancelada nem chama de volta; a geração protege o caso em que o
   resultado já estava na fila de entrega).
2. `auto_export` (e qualquer opção de pedido que dependa de quem pediu) é combinado: o pedido novo herda `auto_export = True` se o anterior pedia (OR), para não perder uma exportação.
3. O `busy` ("Carregando …") é mantido uma vez só por chave e termina quando a última geração termina.
4. Testes (`test_plot_workflow_unit.py`, `Rig` real): `remap` durante uma carga lenta (monkeypatch de `load_plot` com evento) usa o **segundo** mapeamento e a aba mostra o resultado dele; o primeiro resultado
   nunca chega à aba; `auto_export` do primeiro pedido sobrevive ao segundo; `busy` volta a zero; um pedido sem repetição se comporta como antes.

### R3: Dados pessoais (S4)
1. **`config.example.yaml`** (raiz e `src/qe_studio/resources/`, byte a byte iguais): `remote_root: /home/seu_usuario/qe_simulations`, `host: cluster.example.org`, `user: seu_usuario`. Os comentários que expliquem
   os campos continuam. `sync_enabled` segue verdadeiro com o exemplo (`test_config.py` continua exigindo).
2. `tests/test_config.py:36` passa a comparar com `"cluster.example.org"`; `scripts/screenshot.py:160-161` usa `"/scratch/usuario/MoS2"`, `"cluster.example.org"`, `"usuario"`.
3. `specs/spec_0-PRD.md:120`: o IP de exemplo vira `cluster.example.org`.
4. **`Documentation/Referencia_de_scripts_QSUB/PDOS.qsub:3-4`**: as duas linhas de crédito viram uma neutra, `# Script de referência do grupo de pesquisa (autoria omitida).`, sem nomes nem e-mails. Os demais
   `.qsub` não mudam. `tests/test_calc_templates.py:68` troca `"# Cicero", "# Mariano"` por `"# Script de referência"` em `_IGNORED`; o teste `test_scripts_reproduce_the_reference` continua comparando só o corpo.
5. As duas maquetes `code.html` do design system: o nome de usuário e o IP viram placeholders (`usuario`, `cluster.example.org`); nada mais muda (são mocks de tela).
6. Verificação: `grep -rniE "mariano|10\.220\.200|ufam|onairam" . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=fixtures` não encontra nada **exceto** o endereço do repositório
   (`REPOSITORY` em `about.py`, selo de CI do `README.md`, `CLAUDE.md` se citar) e o histórico do git, que esta spec não reescreve.

## Fora de escopo
- `tests/fixtures/**`: são saídas reais do QE (7.1 a 7.4) com caminhos, nomes de máquina e usuário; editá-las arrisca os parsers e `test_fixtures_untouched.py` proíbe. Se o repositório for aberto, um passo à
  parte deve limpar as fixtures com um script e regenerar os goldens (`pw_output_golden.json`).
- Reescrever o histórico do git (os valores antigos continuam nos commits antigos).
- Terminal embutido ou emulador de terminal para programas de terminal (decisão: ocultar).
- CI: Python 3.13, cobertura, `uv sync --locked`, pyright estrito (Q3 do relatório). Sem decisão; não fazem parte desta correção.
- `specs/Ideias.md` zerado (Q4): é estado do working tree do usuário, nada a corrigir no código.

## Decisões assumidas (confirmar na revisão)
1. O crédito do `PDOS.qsub` vira uma linha neutra; isso **remove a atribuição** de um colega citado no cabeçalho (Cicero Mota). Se a atribuição precisa ficar, manter só o nome (sem e-mail) é a alternativa
   mais leve; o usuário escolheu "anonimizados".
2. Programas de terminal são **pulados** como padrão do MIME (em vez de abrir um terminal), seguindo a escolha de ocultar.
3. O pedido repetido de carga **substitui** o anterior (o relatório pede "cancelar e reiniciar"); o `auto_export` do primeiro pedido é preservado.
4. O endereço do repositório no GitHub fica (é a identidade do projeto, não dado do cluster).

## Notas de implementação
- Alterados: `core/desktop_apps.py`, `ui/widgets/context_menu.py` (só se a lista filtrar ali), `ui/plot_workflow.py`, `config.example.yaml`, `src/qe_studio/resources/config.example.yaml`,
  `scripts/screenshot.py`, `specs/spec_0-PRD.md`, `Documentation/Referencia_de_scripts_QSUB/PDOS.qsub`, as duas `code.html`, `tests/test_desktop_apps.py`, `tests/test_plot_workflow_unit.py`,
  `tests/test_config.py`, `tests/test_calc_templates.py`.
- `tests/test_config.py:199-203` (cópia idêntica) continua verde se as duas cópias forem editadas juntas.

## Critérios de aceite e testes
- [ ] Programas `Terminal=true` não aparecem em "Abrir com" nem são o padrão; `DesktopApp` posicional de 6 argumentos continua válido.
- [ ] `Remapear` durante uma carga em andamento: vale o segundo mapeamento; `auto_export` preservado; `busy` termina.
- [ ] `config.example.yaml` (as duas cópias) com placeholders e idênticas; `test_config.py`, `scripts/screenshot.py`, `spec_0-PRD.md`, `PDOS.qsub` e `code.html` sem os dados pessoais.
- [ ] O `grep` de R3.6 só acha o endereço do repositório; `test_calc_templates.py` continua verde.
- [ ] `ruff`, `pyright`, `test_architecture.py`, suíte `-m "not realdata and not perf"` verdes.
