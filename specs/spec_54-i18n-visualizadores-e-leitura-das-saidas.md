# Spec 54: Inglês dos visualizadores (texto, input, diferença, Resumo) e da leitura das saídas do QE

| | |
|---|---|
| **Prioridade** | 54: depois da janela (53), a área onde o usuário passa mais tempo lendo: os visualizadores e o Resumo, e as mensagens de erro, aviso e *lint* que eles mostram. Independente de 55–59. |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 52 (portão por área, `check --area`, probe, glossário); a 53 só para o diálogo de atalhos, que mostra `TextViewer.shortcut_help` |
| **Usada por** | 60 |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): é o caminho da 53 em outra área; a parte de física é vocabulário do próprio QE, não cálculo. |

## Itens de origem (`Ideias.md`)

> Quero prosseguir com a localização para 'pt_BR' e 'en' de forma gradual. […]

Área 54 de `AREAS` (spec 52 R2): `core/qe/` (leitura de `pw.x`, `bands.x`, `projwfc.x`; Resumo; comparação e *lint* de
input), `core/{text_preview,textfile,qsub_lint}.py` e os widgets `text_viewer`, `diff_view`, `input_view`,
`summary_view`, `summary_widgets`, `markdown_view`, `code_view`.

## Situação atual

Contagem da 52 (`check --area 54`, 18/10/2026): **237 mensagens, 158 sem tradução**, 79 traduzidas e não revisadas;
`core/qe` sozinho tem 148 mensagens (101 sem tradução) em 13 arquivos (o `summary/` incluso).

- **R1 (mensagens que viram texto de tela).** Os erros de formato sobem pela exceção (`BandsFormatError`,
  `core/qe/bands_x.py:17`; `PdosFormatError`, `core/qe/projwfc.py:36`) e viram `LoadError` do módulo; o aviso de
  execução incompleta é `core/sniff.py:210` (`_("execução incompleta (sem JOB DONE)")`, área 53, mas é lido aqui no
  Resumo). Um `FileSniff` guarda os avisos como **texto** (`warnings: tuple[str, ...]`, `core/sniff.py:69`) e só testa se
  está vazio; nada compara o conteúdo.
- **R2 (mensagens de *lint*).** `core/qsub_lint.py:51-55` e `core/qe/input_lint.py` citam elementos do script e do input
  (`#!`, `-pe physica 64`, `-N`, `&SYSTEM`) dentro de frases portuguesas. Os pedaços de código ficam como estão nos
  dois idiomas; hoje ninguém os confere.
- **R3 (comparação de inputs).** `core/qe/input_diff.py:62-68` monta rótulos por `.format` (`"{name}: só em A"`,
  `"opção {a} ↔ {b}"`) e `:291` levanta `TooBigError` com texto.
- **R4 (plurais).** `core/qe/` tem 8 usos de `ngettext` (contagem). As 34 entradas plurais do catálogo exigem duas formas
  em inglês.
- **R5 (o que não muda).** O que o QE escreve nas saídas é inglês e é o que o app **lê**: nada disso é traduzido
  (a leitura casa com o texto do QE, não com a interface). O texto mostrado nos visualizadores é o conteúdo do arquivo.
- **R6 (atalhos).** `ui/widgets/text_viewer.py:178-180`: `shortcut_help()` devolve `(ação, teclas, onde)` com
  `_("Visualizador de texto")` como "onde" e as ações vindas de `SHORTCUTS`.
- **R7 (números).** O Resumo e a barra de status mostram números com ponto decimal (convenção do QE, `spec_end`);
  o rodapé em `en` traz "91 pontos k" em português hoje (sem tradução).

## Requisitos

### R1: Traduzir a área

1. Traduzir as 158 mensagens de `scripts/i18n.py check --area 54` e revisar as 79 já traduzidas contra o glossário.
2. **Vocabulário de física**, uma vez para a área e para a 55 (que o reusa): `pontos k` → `k-points`; `autovalores` →
   `eigenvalues`; `nível de Fermi` → `Fermi level`; `gap` → `gap`; `célula` → `cell`; `pseudopotencial` →
   `pseudopotential`; `ciclo SCF`/`iteração` → `SCF iteration`; `tempo de CPU`/`de parede` → `CPU time`/`wall time`;
   `paralelização` → `parallelization`; `energia total` → `total energy`; `força` → `force`; `pressão` → `pressure`.
   Os termos entram no glossário de `locale/README.md`.
3. Pedaços de código dentro de frases (`&SYSTEM`, `-pe physica 64`, `#!`, `JOB DONE`, nomes de arquivo, `ecutwfc`) ficam
   **idênticos** à fonte. `tests/test_i18n.py::test_code_tokens_are_kept`: para cada mensagem da área, os trechos entre
   crases e os que casam com `&[A-Z_]+`, `-[A-Za-z]+ ` de linha de comando e `\bJOB DONE\b` aparecem iguais na tradução.
4. Plurais com `ngettext` e as duas formas (`1 iteration`, `2 iterations`).
5. `TooBigError`, `BandsFormatError` e `PdosFormatError` mantêm a mensagem como texto traduzido; o código nunca compara
   a mensagem (grep antes de acabar; o resultado vai nas notas da implementação).

### R2: Cenários do detector

1. Em `SCENARIOS` de `tests/i18n_probe.py`: `text_viewer` (saída do `pw.x` aberta, busca aberta, barra de problemas),
   `input_viewer` (input com erros de escrita, spec 11), `diff` (dois inputs, modos `params` e `text`), `summary`
   (o Resumo do vc-relax), `markdown`, `qsub` (script com os cinco problemas de `qsub_lint`).
2. `test_no_leaks_in_english[<cenário>]` para os seis.
3. Texto de posição (sublinhado de problema no editor, dica ao passar o mouse): não verificado se a dica é texto de
   widget; se for pintada, `test_issue_messages_are_translated` pergunta ao modelo de problemas (`input_lint`) o texto de
   cada código de problema em `en` e confere que nenhum coincide com o `msgid` em português.

### R3: Fechar a área

1. `update`, `compile`, `DONE |= {54}` em `tests/i18n_areas.py`.
2. `test_untranslated_only_in_pending_areas` passa com `DONE = {53, 54}` (ou `{54}` se a 53 ainda não saiu).
3. O diálogo de atalhos (cenário da 53) em `en` já não tem texto de visualizador em português.

## Fora de escopo

- Traduzir o que o QE escreve nas saídas ou o que o usuário digitou nos inputs.
- Mudar o formato de número (vírgula decimal): fora desde a `spec_end`.
- Os rótulos dos gráficos e do painel de ajustes: 55. A janela 3D: 59.
- Novo realce de sintaxe ou regra de *lint*: nada muda no que é detectado, só o texto mostrado.

## Decisões assumidas (confirmar na revisão)

1. O vocabulário de física de R1.2 usa os termos do próprio QE (`k-points`, `wall time`), para que quem lê a saída
   original reconheça o Resumo.
2. A mensagem de erro de formato é traduzida na origem (`core/qe`), não na tela, porque o mesmo texto vai para a barra de
   status, para o aviso e para o log da sessão; o **log** continua em inglês (decisão da `spec_end`).
3. As dicas de posição do editor só viram requisito de teste se forem texto pintado (R2.3).

## Notas de implementação

- Novos: nenhum; cenários e casos em `tests/i18n_probe.py` e `tests/test_i18n.py` (dividir em
  `tests/i18n_scenarios_<area>.py` se passarem de 500 linhas).
- Alterados: `locale/en/LC_MESSAGES/lain.po` e `.mo`, `tests/i18n_areas.py`, `locale/README.md` (vocabulário).
- Limites: nenhum arquivo de código perto de 500 linhas; `core/qe/` não muda de código, a não ser que o teste de R1.3 ache
  tradução que apaga um pedaço de código (aí é erro de tradução, corrigido no `.po`).
- Documentação ao implementar: nenhuma.

## Critérios de aceite e testes

- [ ] Goldens e suíte de hoje passam sem regenerar.
- [ ] `check --area 54` vazio; `test_untranslated_only_in_pending_areas` passa com a área em `DONE`.
- [ ] `test_code_tokens_are_kept` verde sobre o catálogo real, e vermelho num `Catalog` sintético que apaga `&SYSTEM`.
- [ ] `test_no_leaks_in_english` para os seis cenários novos; `test_portuguese_unchanged` ainda verde.
- [ ] Plurais da área com as duas formas.
- [ ] Passo manual de aceite: com `QE_STUDIO_LANGUAGE=en`, abrir a saída de um `vc-relax` real, o Resumo e a comparação de
      dois inputs; nenhum texto da área em português; os nomes do QE intactos.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
