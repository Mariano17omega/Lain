# Spec 24: Editor de inputs do pw.x e "Gerar SCF convergido"

| | |
|---|---|
| **Prioridade** | 24 (independente das specs 20–23; a spec 25 reaproveita o editor e os nomes sem sobrescrever) |
| **Status** | Implementada. Desvios:<br>- **`geometry_converged`:** `True` só com `bfgs converged`. `End of BFGS Geometry Optimization` sozinho não basta, porque o pw.x também o imprime quando esgota `nstep` (logo depois de "The maximum number of steps has been reached."). `False` com `bfgs failed`, com o fim de `nstep` ou com `End of BFGS` sem `bfgs converged`; `None` sem marcador.<br>- **vc-relax com `CELL_PARAMETERS (alat= x)`:** `celldm(1) = x` fica (o alat impresso, 8 casas), porque com `ibrav = 0` o card em `alat` precisa dele; `celldm(2..6)`, `A`, `B`, `C` e `cos*` saem. Com a célula em `angstrom`/`bohr` sai tudo. Posições em `alat` com a célula em `angstrom`/`bohr` dão erro: o alat do SCF seria outro e converter unidades está fora de escopo.<br>- **`pair_input`:** o papel `relax_in` só pareia se o `relax_out` do mesmo resultado é esta saída (numa pasta com dois relax, não pega o input errado).<br>- `&IONS`/`&CELL` saem **todas** as ocorrências (a fixture slab tem `&IONS` e `&ions`).<br>- `Entry` do lexer ganhou `value_start`/`value_end` (fora da igualdade); `InputEditor` ganhou `raw`, `keys` e `has_namelist`.<br>- `scf_from_relax(final, in_text, name)` recebe a `FinalStructure` já lida; `generate_scf_file` lê os arquivos no worker.<br>- Um input em latin-1 é lido como tal e gravado em UTF-8. |
| **Depende de** | spec 5 (menu de contexto), spec 11 (lexer de input), spec 17 (toast) |
| **Usada por** | spec 25 (geração dos inputs derivados do SCF) |
| **Esforço** | M |

## Itens de origem (`Ideias.md`)

> - No caso de relaxamento (relax e vc-relax), no caso do output desses calculos (convergidos!), e apenas neles, inclua a opção "Gerar SCF convergido" no menu do botão direito do mouse. Esse botão gera um scf usando os mesmos parametros usados no input, mas com as coodernadas e a celula já convergidas. O novo scf é salvo na mesma pasta do relaxante, mas com o nome 'scf_convergido<prefix>.in' e 'scf_convergido<prefix>.out', onde <prefix> é o prefix do input do calculo de relaxamento.

Decisão do usuário nesta rodada: gerar **só o input** (o `.out` é o nome que o `pw.x` dará ao rodar no cluster).
A mesma spec cria a base de edição de inputs que "Criar cálculo" (spec 25) usa para derivar NSCF, bandas e
relax a partir do SCF ("só copiar e editar `calculation`").

## Situação atual

- **Nada reescreve um input.** `parse_input` (`core/qe/pw_input.py:136-146`) passa pelo ASE, minúsculas e
  converte valores, perdendo a formatação; o escritor do ASE só emite `crystal_b` (`pw_input.py:5`). Não há
  `set_`, `replace_`, `rewrite_` em `core/`. O que serve de base é `core/qe/input_lexer.py`:
  `scan_line(text, LexState, lineno)` (l.365) devolve `LineScan` com `opens: NamelistOpen`, `closed`,
  `entries: [Entry(key, value_text, line, col)]`, `card: CardHeader(name, option, option_start, option_end)` e
  `tokens` (KEY/STRING/NUMBER/LOGICAL/COMMENT com início e fim). `input_lint.lint` (`input_lint.py:203`) não
  registra fim de card/namelist nem a coluna final do valor. `input_lexer.py` tem 427 linhas: o editor entra num
  módulo novo.
- **Saídas do pw.x:** `PwOutput` (`core/qe/pw_output.py:45-64`) não tem prefix, outdir, posições nem célula
  finais. `calculation` vem de marcadores (`_calculation`, l.91-105). `PwOutput.converged` (l.161-165) é a
  convergência do **SCF**, verdadeira mesmo se o BFGS esgotou os passos. A convergência da geometria está em
  `core/qe/relax.py` (`RelaxData.bfgs_converged`, l.32-35,140-142, e `read_relax(path)`, l.196, que lê o
  arquivo todo, só em worker). `"End of BFGS Geometry Optimization"` só aparece num regex do realce
  (`highlighters.py:63`).
- **Bloco final** (fixtures QE 7.1/7.3.1): relax de célula fixa (`kao_slab_relax/relax-kaolinite-slab-001.out:1350-1387`):
  `Begin final coordinates`, `ATOMIC_POSITIONS (crystal)` com `espécie x y z [if_pos]`, `End final coordinates`,
  **sem** `CELL_PARAMETERS`. Relax sem unidade no input (`si_relax/si.rel.out:2794-2799`): `(alat)`. vc-relax
  (`kao_vc_relax/vc-relax.out:1491-1535`): `new unit-cell volume`, `density`, `CELL_PARAMETERS (angstrom)` (3
  linhas), `ATOMIC_POSITIONS (crystal)`. O mesmo par é impresso a cada passo do BFGS: vale o que está **entre**
  `Begin` e `End`. Depois de `End final coordinates` vem `Final scf calculation at the relaxed structure.`
- As unidades espelham o input (`angstrom`, `bohr`, `alat`, `crystal`); `CELL_PARAMETERS (alat= 10.16863713)`
  tem o alat com 8 casas, ao contrário do `lattice parameter (alat) = 10.1686 a.u.` (4 casas, `_ALAT`,
  `pw_output.py:39`) que `PwOutput.alat_bohr` lê.
- **Input par da saída:** nenhuma função liga saída a input. `FileSniff` (`core/sniff.py:55-64`) só tem
  `calculation` e `program`. `RelaxModule` (`core/calculations/relax.py:98-114`) tem os papéis `relax_in`
  (`output_of(PW_IN, relax, vc-relax)`, globs `relax*.in`/`vc-relax*.in`, âncora) e `relax_out` (obrigatório,
  âncora); a escolha por papel (`_rank`, `base.py:403`: completo, mais novo, nome mais curto) não é
  necessariamente o par de **uma** saída.
- **Menu de contexto:** `ItemActions.file_actions_of(path)` (`ui/widgets/context_menu.py:89-98`) lê o sniff em
  cache e devolve `(kind do módulo, is_output)`; o `menu(...)` (l.100-127) mostra "Plotar" e "Resumo" acima das
  quatro ações da spec 5. O sniff de saídas grandes (> 16 MB) guarda só 256 KB de cabeça e 1 MB de rabo
  (`sniff.py:23-28`).
- **Nomes sem sobrescrever:** `file_ops.rename_item` recusa alvo existente (l.40-47); `config_template.create_config`
  usa `open(path, "x")`; `export.next_free_stem` (`export.py:35-40`) sufixa a partir de `_2`. Não há ajudante
  genérico que comece em `_1`.
- `tests/pw_output_golden.json` é comparado com `dataclasses.asdict(PwOutput)` em
  `test_pw_output_regression.py`; campo novo exige regenerar.
- Gerar texto é trabalho de `core/`; a GUI só chama em worker (`run_task`) e mostra o resultado (spec 15).

## Requisitos

### R1: Editor de inputs (`core/qe/input_edit.py`, Qt-free)
1. `InputEditor.from_text(text)` mantém o texto original por linha e as posições vindas de `scan_line`. Operações:
   - `get(namelist, key) -> str | None` (texto do valor, sem aspas externas quando é string);
   - `set(namelist, key, value_text)`: troca o valor **no lugar** (mesma linha, mesma caixa da chave, vírgula final
     preservada); se a chave não existe, acrescenta uma linha `  key = value` ao fim da namelist; se a namelist
     não existe, cria-a antes do primeiro card (ou no fim) na ordem padrão do pw.x (`&CONTROL`, `&SYSTEM`,
     `&ELECTRONS`, `&IONS`, `&CELL`);
   - `remove(namelist, key)`: apaga a entrada (a linha toda, ou só o trecho `key = valor,` se houver outras
     entradas na linha);
   - `remove_namelist(name)`: apaga da abertura ao `/` (ou `&end`);
   - `card(name) -> Card | None` e `replace_card(name, option, body_lines)`: troca cabeçalho e corpo do card (do
     cabeçalho até o próximo card, abertura de namelist ou fim); se não existe, acrescenta ao fim;
   - `text() -> str`: o resultado, com o mesmo terminador de linha do original.
2. Preserva comentários (`!`), linhas em branco, caixa dos nomes (`&ions`), espaços e tudo que não foi tocado.
   Tolera namelist repetida (age na **primeira**, como o pw.x lê), vírgula final (`prefix='si',`) e `&end`.
3. Nunca levanta em texto mal formado; no pior caso não altera (e `InputEditor.issues` lista o que não entendeu).
4. É a base do R3 e da spec 25; fica abaixo de 500 linhas (se crescer, separar `input_edit_cards.py`).

### R2: Nomes que não sobrescrevem (`core/unique_names.py`)
1. `next_free(path: Path, first: int = 1) -> Path`: devolve `path` se não existe, senão `path` com sufixo `_1`,
   `_2`… antes da extensão (arquivo) ou no fim do nome (pasta). Não cria nada.
2. `write_new(path, text) -> Path`: tenta `open(path, "x")` em laço com `next_free`, de forma segura contra
   corrida; devolve o caminho realmente escrito. O export de figuras **não muda** (continua em `_2`).

### R3: Estrutura final e convergência da geometria
1. `core/qe/final_structure.py:read_final_structure(path) -> FinalStructure | None` em **streaming** (não passa
   pelo cache do sniff): do primeiro `Begin final coordinates` ao `End final coordinates`, guarda
   `positions: FinalPositions(unit, lines)` (linhas como impressas: espécie, 3 coordenadas, `if_pos` se houver) e
   `cell: FinalCell(unit, alat, rows) | None` (`CELL_PARAMETERS (angstrom|bohr|alat= x)`, só no vc-relax).
   Sem bloco → `None`. Roda em worker.
2. `PwOutput.geometry_converged: bool | None`, preenchido no `parse_pw_output` a partir do **rabo**: `True` com
   `bfgs converged` / `End of BFGS Geometry Optimization`, `False` com `bfgs failed`, `None` quando o marcador
   não está no texto lido (saída enorme em que o rabo de 1 MB não alcança). Regenerar `pw_output_golden.json`.
3. `can_generate_scf(sniff: FileSniff) -> bool` (em `core/qe/scf_from_relax.py`): `sniff.is_output`, saída do pw.x,
   `calculation in ("relax", "vc-relax")` e `pw.geometry_converged is True` e `job_done`. Usa só o sniff em
   cache. Em saída enorme com `geometry_converged is None`, o item **fica oculto** (só se oferece o que está
   confirmado).

### R4: Geração do SCF (`core/qe/scf_from_relax.py`)
1. `pair_input(out_path, folder_result) -> Path | None`: primeiro o mesmo radical (`X.out` → `X.in`, se
   `looks_like_input`); senão o arquivo do papel `relax_in` da detecção da pasta; senão `None`.
2. `scf_from_relax(out_text_or_path, in_text) -> ScfResult(text, warnings)`, sobre o `InputEditor`:
   - `calculation = 'scf'`;
   - remove `restart_mode` (volta ao padrão `from_scratch`), `nstep`, `&IONS` e `&CELL` inteiros;
   - troca o card `ATOMIC_POSITIONS` pelo do bloco final (unidade como impressa, `if_pos` preservado), conferindo
     `nat` (divergência → erro, nada gerado);
   - vc-relax: troca/insere `CELL_PARAMETERS` pela célula final **na unidade impressa** (com `alat= x` de 8
     casas quando for o caso), força `ibrav = 0` e remove `celldm(1..6)`, `A`, `B`, `C`, `cosAB`, `cosAC`,
     `cosBC`; relax de célula fixa: a célula do input não muda;
   - tudo mais (pseudopotenciais, `K_POINTS`, `ecutwfc`, `occupations`, `prefix`, `outdir`…) fica idêntico;
   - `prefix` e `outdir` **não mudam** (decisão assumida 3); `restart_mode` sai para o SCF recomeçar do zero.
3. O prefix do nome vem do input par (`get("control", "prefix")`, sem aspas); se não há `prefix`, usa `pwscf`
   (padrão do QE). Nome: `scf_convergido_<prefix>.in` na **mesma pasta** da saída, pelo `write_new` (R2): se
   existe, `scf_convergido_<prefix>_1.in`, `_2`…
4. Sem input par → o item de menu fica desabilitado, com tooltip "Input do relax não encontrado na pasta". Input
   par que não é um relax/vc-relax (ex.: o nome bate com um SCF) → idem, com o motivo.

### R5: Menu de contexto e fluxo
1. `ItemActions.menu` mostra "Gerar SCF convergido" **só** quando `can_generate_scf(sniff)` (cache). Aparece
   abaixo de "Resumo" e acima do separador das ações da spec 5. Nenhum `kind ==` em `ui/`.
2. Novo sinal `scf_from_relax_requested(Path)` → controlador pequeno `ui/derive_controller.py:
   DeriveController.for_window(window)` (≤ 3 linhas em `MainWindow`, que tem 475/500): em worker roda `pair_input`,
   `read_final_structure`, `scf_from_relax` e `write_new`; spinner "Gerando SCF convergido…" pelo `BusyTracker`.
3. Sucesso: `toast` "scf_convergido_si.in criado" (nível `success`, "Detalhes" lista avisos e o caminho),
   `files.refresh` da pasta. Falha (sem bloco final, `nat` divergente, sem permissão): `QMessageBox.warning`
   com o motivo; nada é escrito.
4. Nunca sobrescreve: arquivo existente → sufixo (R2). A mensagem do toast diz o nome efetivo.

## Fora de escopo
- Gerar o `.qsub` (decisão do usuário: só o input). "Criar cálculo" (spec 25) cria scripts.
- Copiar `pseudo_dir`, `outdir` ou o diretório `tmp/` do relax; rodar o SCF.
- Gerar SCF a partir de um relax **não convergido** (o item não aparece) ou de saída sem input.
- Editor visual de inputs ou edição de valores a pedido do usuário (só o editor em `core/`).
- Converter unidades das posições ou da célula (usa as impressas).

## Decisões assumidas (confirmar na revisão)
1. **Separador `_`:** `Ideias.md` escreve `scf_convergido<prefix>.in` sem separador; assumi
   `scf_convergido_<prefix>.in`, como os demais nomes do texto (`bandas_Al`, `relax_Si`, `scf.qsub`). Trocar é
   mudar uma constante.
2. "Convergido" = a geometria (BFGS), não só o SCF final, e o item só aparece quando isso está **confirmado** no
   texto lido; em saída enorme cujo marcador saiu do rabo de 1 MB o item fica oculto.
3. `prefix`/`outdir` ficam iguais ("mesmos parâmetros"). Rodar esse SCF na pasta do relax reaproveita
   `./tmp/<prefix>.save`; `restart_mode` é removido para recomeçar do zero.
4. Posições e célula entram na unidade que o QE imprimiu, com `if_pos` preservado.
5. Relax de célula fixa: a célula do input permanece; vc-relax força `ibrav = 0` porque a célula final deixa de
   ser descrita por `celldm`.
6. `nstep` (de `&CONTROL`) é removido junto com `&IONS` e `&CELL`; `forc_conv_thr` e `etot_conv_thr` ficam
   (inofensivos em SCF).
7. Sem toast com botão "Abrir": a pasta é atualizada e o usuário abre o arquivo pelo explorador.

## Notas de implementação
- Novos: `core/qe/input_edit.py`, `core/qe/final_structure.py`, `core/qe/scf_from_relax.py`,
  `core/unique_names.py`, `ui/derive_controller.py`. Os quatro de `core/` entram em `QT_FREE`
  (`tests/test_architecture.py`).
- Alterados: `core/qe/pw_output.py` (`geometry_converged`; `parse_pw_output`, l.141-188),
  `tests/pw_output_golden.json` (regenerar; o teste documenta como), `ui/widgets/context_menu.py` (item e sinal),
  `ui/main_window.py` (registro do controlador).
- O editor se apoia só em `scan_line`; se faltar a coluna final do valor, derivar dos `tokens` (KEY seguido dos
  tokens de valor) ou acrescentar `value_start/value_end` a `Entry` sem quebrar `input_lint`.
- Fixtures: `si_relax`, `kao_vc_relax`, `kao_slab_relax`; copiar com `copy_fixture` antes de gerar
  (`test_fixtures_untouched.py` falha se algo for escrito em `tests/fixtures/`).

## Critérios de aceite e testes
- [ ] `InputEditor`: `set` troca no lugar e preserva comentários, caixa, vírgulas e linhas não tocadas; chave nova
      vai ao fim da namelist; namelist nova na ordem do pw.x; `remove` de entrada única e de entrada numa linha
      com outras; `remove_namelist`; `replace_card` e card novo; namelist repetida age na primeira.
- [ ] Propriedades (Hypothesis, `test_properties.py`): `set` seguido de `get` devolve o valor; linhas fora da
      operação ficam byte a byte iguais; nunca levanta em texto arbitrário; `text()` do editor sem operações é
      igual ao original.
- [ ] `next_free` / `write_new`: livre → mesmo nome; ocupado → `_1`; `_1` ocupado → `_2`; duas escritas
      concorrentes não se sobrescrevem; pasta e arquivo.
- [ ] `read_final_structure` nas três fixtures: posições (`crystal`/`alat`/…) e célula (`angstrom` no vc-relax;
      ausente no relax); pega o bloco entre `Begin`/`End` e não o de um passo; sem bloco → `None`.
- [ ] `geometry_converged`: `True` em `si_relax`/`kao_vc_relax`, `False` em saída com `bfgs failed`, `None` quando o
      marcador não está no texto; golden regenerado e `test_pw_output_regression.py` passa.
- [ ] `scf_from_relax`: o texto gerado passa em `lint` sem erro, `parse_input` lê `calculation == 'scf'` e o mesmo
      `nat`; vc-relax tem `ibrav = 0` sem `celldm` e com `CELL_PARAMETERS`; relax de célula fixa não traz
      `CELL_PARAMETERS` novo; `&IONS`/`&CELL`/`restart_mode` ausentes; `if_pos` preservado; `nat` divergente → erro.
- [ ] `pair_input`: mesmo radical; fallback pelo papel `relax_in`; sem par → `None`.
- [ ] Menu: "Gerar SCF convergido" aparece só para saída relax/vc-relax **convergida**; não aparece para SCF,
      bandas, relax com `bfgs failed`, sem `JOB DONE`, nem com `geometry_converged is None`; desabilitado sem
      input par. Textos dos outros menus não mudam.
- [ ] Fluxo (`main_window`): clicar cria `scf_convergido_<prefix>.in` na pasta da saída, toast `success`, pasta
      atualizada; segundo clique cria `_1`; falha mostra `QMessageBox.warning` (patchado) e não escreve nada.
- [ ] `test_architecture.py`: módulos novos sem PyQt6, `ui/` sem `open(`/`read_text`, < 500 linhas.
