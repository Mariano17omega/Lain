# Spec 11: Visualizador de input do QE (realce, erros de escrita, extrato e comparação)

| | |
|---|---|
| **Prioridade** | 11 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 10 (`CodeView`: margem, barra do visualizador, realce) |
| **Usada por** | spec 16 (multi-seleção: "Comparar" com 2 inputs) |
| **Esforço** | G |

## Itens de origem

> **F15. Visualizador de input**: realce de namelists/cards, diff entre dois inputs, extrato (ecutwfc, K_POINTS, calculation). Comparar duas execuções é rotina; parser de input já existe (`qe/pw_input.py`).

Pedido do usuário (30/09/2026):
> Quero o F15, gostei disso. Inclua um destaque em vermelho se o output tiver algum parametro escrito errado, tipo abrir aspas e não fechar, e coisas do tipo. Essa validação é de apenas de escrita dos cards, não é uma validação avançada, isso vai implementado separadamente no futuro.

Decisão confirmada: a validação é **só de escrita** (sintaxe). Um nome de parâmetro desconhecido (ex.:
`ecutwf`) **não** é marcado: isso é validação avançada, para uma spec futura. "Output" no pedido é lido
como "input", porque a validação é "da escrita dos cards".

## Situação atual

- Inputs abrem como texto simples no `TextViewer` (`ui/widgets/workspace.py:81-124`), sem nenhum
  realce. A spec 10 cria o `CodeView` com margem e barra.
- `core/qe/pw_input.py:113-120`, `parse_input`, usa `ase.io.espresso.read_fortran_namelist`, que é
  tolerante e silencioso:
  - uma aspa não fechada engole só o resto da linha (o estado de aspas é por linha);
  - sem o `/`, a namelist continua aberta, e as linhas dos cards seguintes viram pares chave=valor;
  - uma namelist repetida é ignorada sem aviso (vai para `_ignored`);
  - uma `'` antes do `=` gera `AttributeError` (ASE `espresso.py:906-908`).
- O único chamador que trata erro é o `sniff` (`core/sniff.py:174-177`): `except Exception` →
  `FileKind.UNKNOWN`. Um input quebrado deixa de ser reconhecido como input, e o usuário não vê nenhum
  erro.
- `tests/test_pw_input.py` não tem casos de erro.
- O sniff reconhece inputs pela namelist na cabeça (`_NAMELIST = ^\s*&(\w+)`, `sniff.py:75,127`) e
  classifica pelo programa (`QEInput.program`, `pw_input.py:52-61`): `pw`, `bands`, `projwfc`, `dos`.
- Não existe comparação entre arquivos.

## Requisitos

### R1: Leitor tolerante `core/qe/input_lint.py` (sem Qt)
1. Um tokenizador próprio, linha a linha, que **nunca levanta exceção**. Ele produz:
   - `namelists: dict[str, list[Entry]]` com `Entry(key, value_text, line, col)`;
   - `cards: list[Card(name, option, line, lines)]`;
   - `issues: list[LintIssue(line, col_start, col_end, severity, message)]`, com severidade `error` ou
     `warning`.
2. Entende:
   - vários pares por linha, separados por vírgula fora de aspas e parênteses;
   - comentários `!` (e `#` nos cards) fora de aspas;
   - continuação de valores em linhas que só têm valores, logo depois de uma linha terminada em `,`.
3. Programa: deduzido das namelists reconhecidas (mesma regra de `QEInput.program`). Namelists conhecidas:
   - pw.x: `CONTROL`, `SYSTEM`, `ELECTRONS`, `IONS`, `CELL`, `FCP`, `RISM`;
   - bands.x: `BANDS`;
   - projwfc.x: `PROJWFC`;
   - dos.x: `DOS`.
4. Cards conhecidos do pw.x 7.1+: `ATOMIC_SPECIES`, `ATOMIC_POSITIONS`, `K_POINTS`,
   `ADDITIONAL_K_POINTS`, `CELL_PARAMETERS`, `CONSTRAINTS`, `OCCUPATIONS`, `ATOMIC_VELOCITIES`,
   `ATOMIC_FORCES`, `SOLVENTS`, `HUBBARD`.

### R2: Erros de escrita detectados
| # | Situação | Severidade | Mensagem (exemplo) |
|---|---|---|---|
| 1 | Aspa (`'` ou `"`) aberta e não fechada na linha | error | "Aspas não fechadas" |
| 2 | Namelist sem `/` antes do próximo `&`, de um card ou do fim do arquivo | error | "&SYSTEM não foi fechada com '/'" (marcada na linha do `&SYSTEM`) |
| 3 | Linha dentro de namelist sem `=` (e que não é continuação, R1.2) | error | "Esperado 'chave = valor'" |
| 4 | Valor vazio (`ecutwfc =` ou `ecutwfc = ,`) | error | "Valor ausente para ecutwfc" |
| 5 | Parênteses desbalanceados na chave ou no valor (`starting_magnetization(1 = 0.5`) | error | "Parêntese não fechado" |
| 6 | Lógico malformado (`.true`, `true.`, `.ture.`). Aceitos: `.true.`, `.false.`, `.t.`, `.f.`, `T`, `F`, sem diferenciar maiúsculas | error | "Valor lógico inválido: use .true. ou .false." |
| 7 | Número malformado (`1.0e`, `10..5`, `1.0d-`) | error | "Número inválido" |
| 8 | Namelist desconhecida **para o programa** deduzido, ou parecida com uma conhecida (distância de edição ≤ 2) | error | "Namelist desconhecida &CONTRL (quis dizer &CONTROL?)" |
| 9 | Card desconhecido: primeira palavra `^[A-Z][A-Z_]{3,}$` fora de namelist, com o resto da linha vazio, comentário ou opção (`{crystal}`, `(alat)`, `crystal`) | error | "Card desconhecido ATOMIC_POSITION (quis dizer ATOMIC_POSITIONS?)" |
| 10 | Opção de card desconhecida (ex.: `K_POINTS {automatc}`) para os cards com opções fixas (`ATOMIC_POSITIONS`, `K_POINTS`, `CELL_PARAMETERS`) | error | "Opção inválida para K_POINTS: automatc" |
| 11 | Namelist repetida | warning | "&ELECTRONS repetida: o pw.x lê só a primeira" |
| 12 | `/` fora de namelist, ou `&` sem nome | warning | "'/' sem namelist aberta" |

- Fora daqui (validação avançada, futura): parâmetro desconhecido, tipo/valor fora do permitido,
  coerência entre `nat` e as linhas de `ATOMIC_POSITIONS`, cards obrigatórios ausentes.
- Programas não reconhecidos (ph.x, pp.x, neb.x…): só as regras 1–7, 11 e 12. As regras 8–10 ficam
  desligadas, para não gerar falso positivo.

### R3: Realce de inputs
1. `InputHighlighter(QSyntaxHighlighter)` em `ui/widgets/highlighters.py` (spec 10), alimentado pelo
   tokenizador do R1, com tokens novos nos dois temas:
   | Elemento | Token |
   |---|---|
   | `&NAMELIST` e `/` | `syn_namelist` |
   | chave (com índice `(1)`) | `syn_key` |
   | string entre aspas | `syn_string` |
   | número (inclui expoente `d`/`D`) | `syn_number` |
   | lógico | `syn_logical` |
   | comentário | `syn_comment` |
   | nome de card | `syn_card` |
   | opção de card | `syn_card_option` |
2. Erros: sublinhado ondulado (`QTextCharFormat.UnderlineStyle.WaveUnderline`) na cor `error`, no
   intervalo `col_start..col_end`. Para `warning`, o sublinhado usa `warning`.
3. Na margem (spec 10, R3), um marcador (círculo) vermelho ou amarelo na linha. O tooltip, sobre o
   marcador ou sobre o trecho sublinhado, mostra a mensagem.
4. Banner do visualizador: "2 problemas de escrita no input" (nível `error`), com "Ir ao primeiro" (e
   as teclas F8 / Shift+F8 para próximo/anterior). Sem problemas, nenhum banner.

### R4: Quando o visualizador de input é usado
1. Para arquivos cujo sniff é `PW_IN`, `BANDSX_IN`, `PROJWFC_IN` ou `DOS_IN`, **ou** cuja cabeça (8 KB)
   tem uma linha `^\s*&\w+`, mesmo que o sniff seja `UNKNOWN` porque o ASE falhou. Assim, um input
   quebrado continua sendo exibido como input, com os erros marcados.
2. O lint roda no mesmo worker que carrega o texto (`_LoadText`). Inputs acima de 2 MB
   (`INPUT_READ_LIMIT`) abrem só com realce, sem lint, e o banner avisa.
3. O visualizador continua somente leitura (spec 4: `.qsub` e afins também).

### R5: Extrato do input
1. Faixa no topo da aba de input, com "chips" mono, compacta e colapsável. Valores lidos do tokenizador
   do R1, então funciona mesmo com erros:
   - pw.x: `calculation`, `prefix`, `ecutwfc`/`ecutrho`, `K_POINTS` (modo e grade `8×8×8 (0 0 0)` ou "N
     pontos"), `nat`/`ntyp`, `nspin` (ou "não colinear"/"SO"), `occupations`/`smearing`/`degauss`,
     `conv_thr`, `pseudo_dir`;
   - bands.x: `filband`, `spin_component`, `lsym`;
   - projwfc.x: `filpdos`, `degauss`, `DeltaE`, `Emin`/`Emax`;
   - dos.x: `fildos`, `degauss`, `DeltaE`, `Emin`/`Emax`.
2. Um parâmetro ausente aparece como "padrão" esmaecido (ex.: `calculation: scf (padrão)`), só para os
   que têm padrão conhecido (`calculation`, `nspin`, `occupations`).
3. Clique num chip leva o cursor à linha do parâmetro.

### R6: Comparação de inputs ("Comparar com…")
1. Botão "Comparar com…" na barra do visualizador de input. Abre um `QFileDialog` na pasta do arquivo,
   filtrando `*.in *.inp *.pw* *` (todos), e o arquivo escolhido precisa passar pelo critério do R4.1.
2. Abre a aba "Diff · a ↔ b" (chave `diff:<a>|<b>`, ícone `difference`), com dois modos:
   - **Parâmetros** (padrão): tabela Namelist | Parâmetro | A | B, só com as diferenças, e uma coluna de
     estado ("só em A", "só em B", "diferente"). Normalização: números comparados como `float` (`1d-8`
     = `1.0e-8` = `1.E-8`), lógicos como bool (`.t.` = `.true.`) e strings sem diferenciar maiúsculas
     nem espaços nas pontas. Cards: uma linha por card que difere ("ATOMIC_POSITIONS: 3 linhas
     diferem"). Um clique expande o trecho;
   - **Texto**: lado a lado com `difflib.SequenceMatcher`, rolagem sincronizada, linhas
     adicionadas/removidas/alteradas com os tokens `diff_add_bg`, `diff_del_bg` e `diff_change_bg`, e a
     opção "Ignorar espaços e comentários".
3. A comparação roda no worker. Inputs com erros de escrita podem ser comparados, e o tokenizador
   tolerante garante isso.
4. A spec 16 acrescenta "Comparar" no menu de contexto quando exatamente 2 inputs estão selecionados.

## Fora de escopo
- Validação de nomes de parâmetros, tipos, faixas e coerência (spec futura).
- Editar o input dentro do Lain.
- Marcar inputs com erro na árvore ou na grade (rótulo de estado).
- Comparar saídas (só inputs).

## Decisões assumidas (confirmar na revisão)
1. "Output" no pedido foi lido como **input** (a validação é da escrita dos cards).
2. Erro de escrita fica só dentro do visualizador. A árvore e a grade não ganham rótulo "ERRO" para
   inputs (pode vir depois).
3. Namelist ou card desconhecido conta como erro de escrita (R2 #8–#10), porque é "nome escrito errado"
   de namelist/card, e não de parâmetro.
4. O tokenizador próprio (R1) **não substitui** o `parse_input` do ASE nos fluxos de detecção e plot.
   Ele serve só ao visualizador e ao diff, para não mudar o comportamento já testado.
5. A comparação de strings não diferencia maiúsculas (o QE normaliza a maioria das strings de controle).

## Notas de implementação
- Novos: `core/qe/input_lint.py`, `ui/widgets/input_view.py` (extrato + integração com o `CodeView`),
  `ui/widgets/diff_view.py`, `tests/test_input_lint.py`, `tests/test_input_view.py`.
- Alterados:
  - `ui/widgets/workspace.py` (escolha do visualizador pelo R4.1), `ui/widgets/highlighters.py`;
  - `ui/resources/themes/{dark,light}.yaml`: tokens `syn_*` e `diff_*`;
  - `ui/resources/styles/workspace/viewers.qss`.
- Casos de propriedade em `tests/test_properties.py` (spec 7): texto aleatório nunca faz o
  `input_lint` levantar exceção, e todo input das fixtures dá zero issues `error`.
- As fixtures existentes (`*.in` de `al_*`, `si_*`, `ni_*`, `kao_*`) servem de regressão: nenhum falso
  positivo.

## Critérios de aceite e testes
- [ ] Todos os inputs de `tests/fixtures/` produzem zero issues de severidade `error`.
- [ ] Para cada linha da tabela R2, um input sintético mínimo gera exatamente a issue esperada, na linha
      e na coluna certas.
- [ ] `prefix = 'si` → "Aspas não fechadas". O resto do arquivo continua tokenizado (a namelist fecha no
      `/` seguinte).
- [ ] Um input que faz o ASE falhar (`'` antes do `=`) abre no visualizador de input, com o erro marcado,
      apesar do sniff `UNKNOWN`.
- [ ] Realce: em `si.scf.in`, `&CONTROL` recebe `syn_namelist`, `ecutwfc` recebe `syn_key`, `'si'`
      recebe `syn_string` e `K_POINTS` recebe `syn_card`.
- [ ] Banner "N problemas de escrita" e a tecla F8 navegam até a linha do primeiro erro.
- [ ] Extrato de `al.scf.in`: `calculation`, `ecutwfc`, `K_POINTS` e `nat` batem com o arquivo.
- [ ] Diff "Parâmetros" entre `si.scf.in` e uma cópia com `ecutwfc` alterado e `conv_thr = 1d-8` versus
      `1.0e-8`: só `ecutwfc` aparece como diferente.
- [ ] Diff "Texto": linhas alteradas marcadas, e "Ignorar comentários" remove as diferenças que estão só
      nos comentários.
