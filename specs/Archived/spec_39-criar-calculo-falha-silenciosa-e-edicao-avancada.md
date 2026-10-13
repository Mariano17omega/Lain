# Spec 39: Criar cálculo — "Continuar" que não responde (Diferença de carga) e edição dos arquivos no modo Avançado

| | |
|---|---|
| **Prioridade** | 39 (R1 é um defeito, não reproduzido; R2 é a maior das ideias e vem depois do verificador de script da spec 38) |
| **Status** | Implementada (12/10/2026); ver "Decisões na implementação". R1.5 (o SCF que falhou) segue com o usuário |
| **Depende de** | spec 26 (a janela), spec 28 (modos Padrão / Avançado), spec 30 (Diferença de carga), spec 24 (`InputEditor`), spec 38 (R2: `lint_script`, para a verificação do script editado; sem ela o script fica sem verificação) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: P; R2: M) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): R2 desfaz uma regra de projeto da spec 26 (a prévia nunca é editável) e cruza o replanejamento por campo, o `CreateRequest` e o que o `writer` grava. |

## Itens de origem (`Ideias.md`)

> - A Função de criar calculo da diferença de carga deu erro, não acontece nada depois de selecionar um scf e clicar no botão continuar.
>
> - Na janela de criação de calculo, se o usuario clicar no botão de 'Avançado', deve ser permitido editar os inputs e o script na propria janela de visualização, mas ó no modo Avançado.

## Situação atual

- **R1 (não reproduzido).** Tentei reproduzir de três jeitos, **todos chegam à etapa 2** sem erro (`charge_diff`, modos Padrão e Avançado):
  1. a `scf.in` real do usuário (`Documentation/Exemplo-bands-010-mehg-O1/scf.in`: 97 átomos, 7 espécies, `ibrav = 0`, `smearing`) pela janela
     (`CalcCreateDialog`, `set_type("charge_diff")`, `set_scf`, clique em "Continuar"): 8 abas
     (`script, scf, scf_clean, scf_isolated, pp_base, pp_clean, pp_isolated, pp_diff`) em 0,08 s;
  2. variantes dessa entrada: CRLF, comentário em latin-1, `nspin = 2` com `starting_magnetization`, `K_POINTS gamma`, tabulações, sem
     `\n` final, com `CONSTRAINTS`, com `HUBBARD ortho-atomic`, e a `jobs:` real do `config.yaml` do usuário (`cores 64`, `nk 4`);
  3. os 24 inputs `.in` / `.pwi` de `tests/fixtures/` e `Documentation/`, nas duas ordens (tipo antes do SCF e depois): os 7 SCFs chegam
     à etapa 2; os outros 17 (bandas, nscf, relax, projwfc) são **recusados** (`scf_ready(None)`) e "Continuar" fica desabilitado.
  O log do usuário (`~/.cache/qe-studio/qe_studio.log`, último registro em 08/10) **não tem nenhum erro de "Criar cálculo"**: só o de
  `Átomos…` da spec 32. Logo, ou não houve exceção, ou a entrada que falhou não é nenhuma destas.
  O que o código permite de "nada acontece": (a) `CalcCreateDialog.continue_` (`ui/dialogs/calc_create/dialog.py:150-157`) **retorna
  em silêncio** se `setup.problems()` não está vazio ou `_wanted()` é `None`; (b) com problemas o botão está **desabilitado** e a razão
  só aparece no tooltip (`:224-225`): quem clica num botão cinza não vê nada; `problems()` (`setup_page.py:170-177`) inclui, além do SCF,
  `validate_suffix` e `validate_parent`; (c) `_build_tabs` (`:176-188`) roda **dentro do slot do clique**, sem `try`: uma exceção
  vai para o `excepthook` (toast "erro inesperado" e log, spec 27-5), que o usuário pode ter perdido, e a janela fica na etapa 1.
  **Preciso do SCF que falhou** (ou o log da hora) para achar a causa: ver "Decisões assumidas".
- **R2 (edição).** A prévia é somente leitura **por decisão**: `FilePreview` (`ui/dialogs/calc_create/preview.py:22-24`, "never editable:
  the user fills fields") sobre `CodeView`, que liga `setReadOnly(True)` (`ui/widgets/code_view.py:61`); a spec 26 registrou "A prévia é
  **somente leitura**: o usuário só mexe nos campos (pedido: 'não editar texto manualmente')"
  (`specs/Archived/spec_26-criar-calculo-janela.md:163`) e `tests/test_calc_create_dialog.py:165` fixa `nscf.isReadOnly()`. O pedido de agora
  é o contrário, só no modo Avançado. Como o texto nasce: `TabsPage.flush` (`tabs_page.py:197-215`) chama `CalcType.plan(...)` a **cada
  edição de campo** e repõe `PlannedFile.text` na prévia (`FilePreview.set_text`, que não mexe se o texto for igual); o
  `CreateRequest` leva o `CalcPlan` (`dialog.py:45-50, 242-243`) e `create_folder` escreve `planned.text` (`core/calc_create/writer.py:132`).
  `PlannedFile` e `CalcPlan` são imutáveis (`types/base.py:84-98`); `PlannedFile.key` é estável (o nome do arquivo pode mudar pelo campo
  "Nome do arquivo"). `TabsPage.dirty` (`:217-219`) é `_edited` ou notas. `tabs_page.py` tem 256 linhas, `dialog.py` 287, `preview.py` 109.

## Requisitos

### R1: "Continuar" nunca é mudo

1. **A razão fica à vista.** `SetupPage` mostra, abaixo do formulário, uma linha com `problems()[0]` enquanto "Continuar" está
   desabilitado ("Escolha o SCF", "Lendo o SCF…", a mensagem de `validate_suffix`…); o tooltip continua.
2. **Falha ao montar a etapa 2 aparece.** `CalcCreateDialog._build_tabs` roda sob `try`: uma exceção vai para o log com o traceback
   (`log.exception`), desmonta `self.tabs` / `self._built` e abre um `QMessageBox.warning` "Não foi possível montar os arquivos deste
   cálculo: `<erro>`. O log tem o detalhe (Ajuda ▸ Abrir log)."; a janela fica na etapa 1, sem travar nem fechar. O diálogo é uma função do
   módulo (`ask_failed`), trocável nos testes como `ask_discard`.
3. **`continue_` que não segue diz por quê** (a linha de R1.1 recebe o texto): nenhum `return` sem efeito visível.
4. **Rede de testes que faltava** (`tests/test_calc_create_matrix.py`, novo): **todo** `CalcType` do registro × todo SCF `.in` válido das
   fixtures (`tests/fixtures/**` filtrado por `calculation = scf`, mais o `SMALL` e o `HUBBARD` de `fragment_helpers.py`) chega à etapa 2
   e produz um plano com os arquivos da lista do tipo; a falha do plano de um tipo (`monkeypatch` de `CalcType.plan` levantando) mostra
   a mensagem de R1.2 e a janela segue utilizável; a razão de R1.1 aparece para cada problema de `problems()`.
5. **Passo manual de aceite (usuário):** repetir a "Diferença de carga" com o SCF que falhou; se ainda não responder, mandar o `.in` ou o
   trecho do log da hora. Com o arquivo, o defeito vira teste (`test_calc_charge_diff.py` / `test_fragments.py`) antes de qualquer correção.

### R2: Editar inputs e script na prévia, só no modo Avançado

1. **Quem pode editar.** No modo `avancado`, `FilePreview` fica editável para os arquivos de input e para o script; no `padrao` fica somente
   leitura, como hoje. A aba "Arquivos" continua somente leitura, e "Descrição" já é editável.
2. **O texto editado vence o replanejamento.** Novo módulo Qt-free `core/calc_create/overrides.py`: `apply_overrides(plan, texts)`
   devolve o `CalcPlan` com o `text` dos arquivos cuja **chave** (`PlannedFile.key`) está em `texts` trocado pelo digitado (chaves
   desconhecidas são ignoradas; `PlannedFile` imutável: `dataclasses.replace`); `normalized(text)` garante o `\n` final; um texto igual
   ao gerado **não** é edição. O nome do arquivo (campo "Nome do arquivo") e os erros do plano continuam vindo dos campos.
3. **`TabsPage` guarda `_edits: dict[str, str]`** (chave → texto): digitar na prévia grava; `flush()` planeja com os campos e aplica as
   edições antes de mostrar e de emitir `planned`; o `CreateRequest.plan` leva o texto editado e o `writer` **não muda**.
4. **A marca e o caminho de volta.** Um arquivo editado mostra "editado" no rótulo da aba e na lista de "Arquivos", e uma barra acima da
   prévia ("Editado manualmente. Os campos deste arquivo não o alteram mais.") com **"Restaurar do formulário"**, que remove a edição e
   volta ao texto gerado. A barra vale nos dois modos (um arquivo editado no Avançado continua marcado se o usuário volta ao Padrão).
5. **Campo depois da edição.** Mudar um campo **não** reescreve um arquivo editado (a edição vence); o formulário continua replanejando
   os demais e os erros do plano. A mudança de tipo ou de SCF reconstrói a etapa 2 e **descarta** as edições; a nota que a etapa 1 já mostra
   (`REBUILD_NOTE`, `setup_page.py:42`: "Esta mudança refaz a próxima etapa: os campos voltam aos padrões") passa a dizer também "e as
   edições dos arquivos se perdem" quando há alguma. Fechar a janela com edições pergunta `ask_discard` (`dirty`, abaixo).
6. **Verificação enquanto digita** (debounce de `DEBOUNCE_MS`): inputs com `input_lint.lint(text)` (sublinhado em onda e margem, via
   `InputHighlighter.set_issues` e `CodeView.set_diagnostics`, como o visualizador de input); o script com `core/qsub_lint.lint_script`
   (spec 38 R2) quando existir. Os problemas **avisam, não bloqueiam** "Criar": quem edita à mão responde pelo arquivo.
7. **`dirty`:** `TabsPage.dirty` inclui `bool(_edits)`; um clique em "Voltar" e "Continuar" sem trocar tipo ou SCF **mantém** as edições
   (`_stale` não reconstrói).
8. **Testes** (`tests/test_calc_create_edit.py`, novo; `test_calc_create_dialog.py:165` passa a testar os dois modos; `test_calc_create_ui.py`):
   `padrao`: `isReadOnly()`; `avancado`: editável; digitar muda `tabs.plan.by_key("scf").text` e o `CreateRequest.plan`; mudar um campo
   do mesmo arquivo não apaga a edição e os outros arquivos mudam; "Restaurar do formulário" volta ao gerado; um texto igual ao gerado
   não conta como edição; renomear o arquivo pelo campo mantém a edição (chave estável); `dirty`; voltar à etapa 1 e continuar mantém;
   trocar o SCF descarta e a nota de R2.5 aparece; o `lint` marca um `=` faltando; **criar a pasta grava o texto editado** (janela
   principal, `test_calc_create_ui.py`); `apply_overrides` em `tests/test_calc_overrides.py` (puro: chaves, `\n` final, igualdade).

## Fora de escopo
- Editar o texto no modo Padrão, ou editar a aba "Arquivos".
- Desfazer a edição de um arquivo **em partes** ("só esta linha"): é tudo ou nada por arquivo (o `Ctrl+Z` do editor serve para o resto).
- Reaplicar os campos sobre o texto editado (mesclar): a edição vence.
- Bloquear "Criar" por problemas de escrita do texto editado.
- Qualquer causa de R1 enquanto não houver o SCF que falhou.

## Decisões assumidas (confirmar na revisão)
1. **R1 sem causa conhecida:** a spec manda tornar a falha visível e montar a rede de testes, e **não** inventa uma correção. O SCF que
   falhou é o que falta: se o usuário o mandar, o defeito vira teste primeiro.
2. **A edição vence o formulário** (e não o contrário): é o que "editar o input na própria janela" quer dizer. A alternativa, mesclar,
   exigiria saber quais linhas vieram de quais campos. O preço: depois de editar um arquivo, os campos dele deixam de agir sobre ele (R2.4
   diz isso na tela).
3. **Edições persistem na troca de modo.** Voltar ao Padrão não as descarta (descartar seria perder trabalho sem aviso); a marca e o
   "Restaurar" continuam visíveis.
4. **A verificação não bloqueia "Criar".**
5. **O arquivo editado entra no `CreateRequest` como o `PlannedFile` de sempre**, sem o `writer` saber de edição.
6. A edição do **script** usa o `lint_script` da spec 38 se ele já existir; sem ele, o script é editável e sem verificação.

## Notas de implementação
- Novos: `core/calc_create/overrides.py` (entra em `QT_FREE`), `ui/dialogs/calc_create/edit_bar.py` (a barra "Editado manualmente"),
  `tests/test_calc_create_matrix.py`, `tests/test_calc_create_edit.py`, `tests/test_calc_overrides.py`.
- Alterados: `ui/dialogs/calc_create/dialog.py` (287: `_build_tabs` sob `try`, `ask_failed`, a linha da razão), `setup_page.py` (260: a
  linha), `tabs_page.py` (256: `_edits`, `flush`, `dirty`, o gancho de digitação; **mover a verificação para um helper** se passar de
  ~340), `preview.py` (109: `set_editable`, sinal `edited(str)`, a barra), `ui/widgets/code_view.py` (365: só `setReadOnly` por
  instância; já é o padrão), `tests/test_calc_create_dialog.py`.
- Limites: nenhum arquivo passa de ~420 linhas.
- Documentação ao implementar: `CLAUDE.md`, seção "Criar cálculo window (spec 26, spec 28 R5)": a prévia editável só no Avançado,
  `overrides.py` e a regra "a edição vence"; e a regra de R1.2 (falha ao montar a etapa 2 nunca é muda).

## Critérios de aceite e testes
- [x] "Continuar" desabilitado mostra a razão na tela, não só no tooltip; nenhum caminho do clique termina sem efeito visível.
- [x] Falha forçada na montagem da etapa 2: mensagem + log, janela utilizável (`test_calc_create_matrix.py`).
- [x] Todo tipo × todo SCF válido das fixtures chega à etapa 2.
- [x] Avançado: prévia editável; Padrão: somente leitura. O texto editado vai para o `CreateRequest` e para o arquivo criado.
- [x] Campo alterado depois da edição não apaga a edição; "Restaurar do formulário" volta ao gerado; trocar tipo/SCF descarta.
- [x] Lint ao digitar (input e, com a spec 38, script) marca sem bloquear "Criar".
- [ ] **Conferência manual (usuário):** "Diferença de carga" com o SCF que falhou.
- [x] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.

## Decisões na implementação

1. As decisões assumidas 1–6 ficaram como estavam: sem causa de R1 inventada, a edição vence o formulário, as edições ficam na
   troca de modo, a verificação não bloqueia "Criar", o `writer` não sabe de edição, e o script é verificado com o `lint_script`
   da spec 38 (já existia).
2. **R1 continua sem causa.** A rede de `test_calc_create_matrix.py` (7 tipos × 8 SCFs: os 6 SCFs de `tests/fixtures/`, o `SMALL`,
   que tem o card `HUBBARD` e spin, e `slab_scf()`; nos dois modos) passou de primeira. Não existe uma constante `HUBBARD` em
   `fragment_helpers.py`: o card está dentro do `SMALL`. O passo R1.5 (o SCF do usuário) fica em aberto.
3. **A linha da razão repete o texto do campo** quando o problema já tem a linha dele (SCF, nome, local): a spec pede
   `problems()[0]` abaixo do formulário, e a linha fica no estilo "hint" para não parecer um segundo erro.
4. **Uma montagem que falha descarta também a etapa 2 antiga** (já obsoleta: o tipo ou o SCF mudou), então a nota "Esta mudança
   refaz…" some e "Criar" fica desabilitado até uma montagem dar certo.
5. **Defeito que os testes acharam:** o `rehighlight` do `QSyntaxHighlighter` (ao marcar os problemas, ou na troca de tema) termina
   num bloco de edição, e o `textChanged` dispara com o texto igual; marcar os problemas de uma edição gerava outra "edição" e a
   verificação recursava. `FilePreview` compara com o último texto mostrado ou digitado (`_known`) e só então emite `edited`.
6. **O texto editado é gravado com `\n`** (o que o editor guarda) e com o `\n` final (`overrides.normalized`); um texto igual ao
   gerado com outro fim de linha ou sem o `\n` final não é edição. Esvaziar o arquivo é uma edição (um arquivo vazio).
7. **Também repintados ao digitar:** as linhas de um input pw.x que diferem do SCF (`FilePreview.paint_changes`) seguem o texto
   digitado, junto com a verificação, depois do `debounce_ms`.
8. **Sem verificação acima de `INPUT_READ_LIMIT`** (2 MB), como no visualizador; a verificação roda na thread da GUI sobre o texto
   em memória, depois do debounce.
9. O tooltip de "Avançado" diz que a prévia fica editável. `tabs_page.py` ficou com 345 linhas (a verificação mora em
   `core/calc_create/overrides.edit_issues` e a marcação em `FilePreview.show_issues`), `dialog.py` 316, `preview.py` 158.
10. `qtbot.keyClicks` com `"\n"` derruba o processo (abort): os testes digitam sem quebra de linha.
11. **O segfault "intermitente" de `test_calc_create_ui.py` tinha causa aqui.** `SetupPage` ligava
    `partial(busy.end, key)` ao próprio `destroyed`; quando o fixture apagava a janela principal com uma janela "Criar
    cálculo" ainda filha dela, o PyQt chamava o `partial` já liberado (`gdb`: `partial_vectorcall` ←
    `QObject::destroyed` ← `~QWidget` da `SetupPage`). O teste novo da janela principal o fazia cair em 3 de 5 rodadas;
    agora o spinner termina em `SetupPage.shutdown` (o `done` da janela), sem ligação ao `destroyed`, e 6 de 6 rodadas
    passaram.
