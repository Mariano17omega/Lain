# Spec 56: Inglês do "Criar cálculo": janela, edição, pacote de superfícies e o relatório da geração

| | |
|---|---|
| **Prioridade** | 56: a janela e o que é comum a todos os tipos (passos, abas, formulário, prévia, editor de caminho k) e o pacote `surface/` (geometria, adsorção, relatório) que os tipos de superfície usam. Os **tipos** (Slab, Supercélula, Molécula na superfície, bandas, relax, SCF, PDOS…) e os seus campos ficam na 57. Independente de 53–55, 58 e 59. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 52 (portão, probe, glossário); specs 26, 28, 40–42 e 51 (o que a janela faz) |
| **Usada por** | 57 (usa os termos do formulário e o `report_file`), 60 |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): o contrato (`CalcType`, `FormField`) não muda; só texto e um arquivo gerado. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. […]

Área 56 de `AREAS` (spec 52 R2): `core/calc_create/*.py` (raiz), `core/calc_create/surface/`,
`ui/dialogs/calc_create/`, `ui/widgets/kpath_editor.py` e `ui/{calc_create_controller,derive_controller}.py`.
(`core/calc_create/types/` é da 57.)

## Situação atual

Contagem da 52 (`check --area 56`, 18/10/2026): **187 mensagens, 129 sem tradução**, 58 traduzidas e não revisadas
(`core/calc_create/` raiz 58/44 sem tradução, `surface/` 55/40, `ui/dialogs/calc_create/` 45/30, `kpath_editor` 16, controladores 8).

- **R1 (arquivo gerado em disco).** A Slab e a Supercélula (e a Molécula na superfície) gravam `geracao.md` na pasta nova:
  `core/calc_create/surface/report.py:35` `report_file(lines)` devolve um `PlannedFile` (`REPORT_NAME`) com
  `report_text(lines)` (`:31`), que começa em `TITLE = _("# Relatório da geração")` (`:22`) e usa `_()` nos rótulos das
  linhas (as listas `facts` de `types/slab.py:97` e `types/supercell.py:151`). **O conteúdo do arquivo muda com o idioma
  da interface**, e a pasta de simulação é sincronizada com o cluster. Não verificado: se algum código lê o `geracao.md`
  de volta (nenhum leitor foi achado por `grep` de `report_file`/`report_text`, só quem o escreve).
- **R2 (combos com valor e texto).** `ui/dialogs/calc_create/form.py:171` faz `combo.addItem(_(choice), choice)`: o texto
  é traduzido e o **valor** é o dado (a chamada dinâmica da 52 R4.3). `FormField.choices` é `tuple[str, ...]`
  (`core/calc_create/types/base.py:64`) e cada valor precisa estar em `N_()` na origem.
- **R3 (fragmentos de frase).** As validações compõem mensagens com um **rótulo** em português passado a
  `check_positive(work, chave, rótulo)` (`types/slab.py:103-104`, `types/adsorption.py:167-170`: `_("A distância de
  adsorção")`, `_("A folga mínima")`, `_("A tolerância de ligação")`). Em inglês o artigo some e o gênero não importa
  (`The adsorption distance` + `must be positive`), mas a regra é do texto composto, e a revisão precisa ver as duas
  metades juntas. Não verificado: todos os pontos onde `check_positive` e funções parecidas compõem o texto.
- **R4 (o que já é independente).** A pasta nova tem prefixo fixo em inglês por tipo (`folder_prefix`,
  `types/base.py:270`: `Bands`, `Relax`…), independente do idioma; a numeração "Numerar" (spec 51) conta pastas, não texto.
- **R5 (limites).** `ui/calc_create_controller.py` e `ui/derive_controller.py` já estão marcados; os diálogos usam
  `WA_DeleteOnClose` e o botão "Criar" fica desabilitado sem valor obrigatório (texto `"Criar"`, spec 26).

## Requisitos

### R1: Traduzir a área

1. Traduzir as 129 mensagens de `scripts/i18n.py check --area 56` e revisar as 58 já traduzidas (glossário da 52). Termos
   fixos do Criar cálculo (entram no `locale/README.md`): `Criar cálculo` → `Create calculation` (decidido na 52); `Continuar` → `Continue`;
   `Criar` → `Create`; `Padrão`/`Avançado` → `Standard`/`Advanced`; `Numerar` → `Number`; `Prévia` → `Preview`;
   `Arquivos` → `Files`; `Caminho k` → `k-path`. Os nomes dos tipos (`Slab`, `Supercélula`, `Molécula na superfície`) são da 57.
2. Mensagens compostas por fragmento (R3): traduzir o rótulo **e** a frase final juntos; se o inglês exigir outra
   ordem, trocar a composição por uma mensagem com `{campo}` (`_("{label} must be positive")`), com teste.
3. Plurais por `ngettext`, duas formas (contagens de átomos, camadas e cópias).

### R2: O relatório da geração (`geracao.md`) segue o idioma da interface

1. O `geracao.md` é escrito **no idioma da interface no momento da criação** (título, rótulos e frases); o **nome** do arquivo
   (`REPORT_NAME`) e a chave de aba (`REPORT_KEY`) ficam como são. É um documento para a pessoa, não um dado do app.
2. **Testes desta spec:** `report_text` com linhas sintéticas em subprocesso `en` devolve o título em inglês e as linhas como
   recebeu (o relatório não traduz o que lhe passam). O teste de ponta a ponta (a mesma Slab criada em `pt_BR` e em `en`:
   mesmas linhas, mesmos números, `pw.in`/`relax_*.in` idênticos byte a byte, nenhuma mensagem traduzida num `.in`) precisa
   dos rótulos das linhas, que são dos tipos: é o R2 da 57.
3. O texto do relatório é o mesmo que a aba "Arquivos" mostra na prévia (`PlannedFile.text`); o teste confere a igualdade
   com o que foi gravado.

### R3: Cenários do detector

1. `tests/i18n_probe.py` ganha: `calc_create_setup` (passo 1, modos Padrão e Avançado; os nomes dos tipos só ficam em inglês com a 57),
   `calc_create_files` (passo 2, abas e prévia de um tipo de superfície), `kpath_editor`, `derive` (o menu "Gerar SCF
   convergido" e o aviso de reaproveitar) e `calc_create_errors` (as mensagens comuns da janela, de `core/calc_create/*.py` da raiz: nome de pasta
   inválido ou já existente, SCF não escolhido; o texto aparece no rodapé). As validações de cada tipo são da 57.
2. `test_no_leaks_in_english[<cenário>]` para os cinco; os combos mostram o rótulo em inglês e o `currentData()` continua o
   valor (`test_combo_data_is_the_value`: para cada `FormField` de escolha, `currentData()` em `en` é igual ao de `pt_BR`).

### R4: Fechar a área

1. `update`, `compile`, `DONE |= {56}`; `test_untranslated_only_in_pending_areas` passa.
2. Passo manual: abrir a janela em `en`, passar pelos dois passos de um tipo qualquer e pela mensagem de cada erro de validação.

## Fora de escopo

- Os **tipos** de cálculo (os 10 de `REGISTRY`: SCF, Relax, vc-relax, Bandas, PDOS, Carga, Diferença de carga, Slab, Supercélula, Molécula na
  superfície), os seus campos e dicas (`types/*_fields.py`) e os rótulos das linhas do `geracao.md`: 57.
- Traduzir o `.qsub` e os comentários dos inputs gerados: ficam em português (ver 57, decisão 1).
- Mudar o conjunto de arquivos que um tipo gera, ou o texto do `geracao.md` além da tradução.

## Decisões assumidas (confirmar na revisão)

1. O `geracao.md` fica no idioma da interface na criação (R2). A alternativa, sempre em português ou sempre em inglês, torna o
   arquivo previsível para quem o lê em outro computador, ao custo de a interface e o arquivo divergirem; escolhi seguir
   a interface porque a prévia mostra o mesmo texto e o usuário o lê ali.
2. Os termos do Criar cálculo de R1.1 são propostas; `Supercell` e `Slab` ficam como nomes de campo conhecidos.
3. Fragmentos de frase são traduzidos juntos; a troca por `{campo}` só ocorre onde a ordem do inglês exige.

## Notas de implementação

- Novos: nenhum arquivo de código.
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `.mo`; `tests/i18n_areas.py`; `tests/i18n_probe.py` (5 cenários);
  `tests/test_i18n.py` (R2.2, R3.2); `core/calc_create/surface/report.py` só se R1.2 pedir.
- Limites: `ui/dialogs/calc_create/*.py` e `core/calc_create/surface/*.py` são conferidos com `wc -l` antes de editar;
  esta spec não adiciona linhas além de R1.2.
- Documentação ao implementar: nenhuma.

## Critérios de aceite e testes

- [ ] Goldens e suíte de hoje passam sem regenerar; os `.in` gerados em `pt_BR` não mudam.
- [ ] `check --area 56` vazio; `test_untranslated_only_in_pending_areas` passa com a área em `DONE`.
- [ ] `report_text` em `en`: título em inglês, linhas intactas (R2.2); o teste de ponta a ponta da Slab é da 57.
- [ ] `test_combo_data_is_the_value` verde; `test_no_leaks_in_english` para os cinco cenários.
- [ ] Plurais da área com as duas formas.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
