# Spec 30: Criar cálculo — diferença de carga (SCFs "clean" e "isolated")

| | |
|---|---|
| **Prioridade** | 30 |
| **Status** | Implementada. Desvios:<br>- **Isolated sem MPI (decisão 2):** o SCF isolated roda com `${PWCOMMAND_SINGLE}` (pw.x sem `-nk` e sem `mpiexec`), como o `cargas.qsub` validado no cluster; base e clean seguem com MPI. O `.qsub` ganha a variável `PWCOMMAND_SINGLE`.<br>- **Avançado (R5.2):** os quatro `pp.x` têm nomes de saída diferentes, então não há um `fileout`: o campo é "Pasta dos .xsf" (`xsf_dir`, padrão `cdd_xsf`), que vale para os quatro (`<pasta>/<x>_charge.xsf`, `<pasta>/<p>_charge_diff.xsf`), com `iflag` e `output_format`; mesma regra de pasta relativa e dentro da pasta da spec 29, e o script faz `mkdir -p` dela. Sem campo `plot_num` (fixo em 0).<br>- **Campo `atoms`:** `FormField` ganhou `hint` (a legenda) e `data` (as linhas, `AtomRows`); o valor é a tupla dos números dos átomos marcados. Vazio é um valor válido: o erro "Selecione os átomos do fragmento isolado" vem de `split_input`, não do "Preencha" genérico. O plano sempre devolve os oito arquivos, mesmo com erro, para as abas não mudarem.<br>- **Editor:** além de `card_rows`, `replace_card_rows` e `remove_card`, `rename_key` (reindexar `starting_magnetization(3)` → `(1)` no lugar, mantendo a caixa e o espaçamento). `fragments.py` ficou com `species_keys.py` ao lado (chaves por espécie e card `HUBBARD`).<br>- **HUBBARD:** um índice de átomo maior que `nat` (imagem na supercélula 3×3×3) vira `novo + nat_novo·k`; é uma **suposição não verificada**: o `INPUT_PW` só diz "index of the atom I / J", a numeração da supercélula está no `Hubbard_input.pdf` (não lido) e não houve execução; o plano avisa com uma nota ("confira") quando renumera um índice assim. `Hubbard_V(i,j,k)` do `&SYSTEM` antigo só gera nota.<br>- **Tabela:** o cabeçalho mostra `Å` para `angstrom` e a unidade do card nos demais; "N de M átomos" na aba e "N de M marcados" na janela da PDOS.<br>- Como as 27-x, 28 e 29, a spec fica em `specs/`. |
| **Depende de** | spec 29 (template e script do `pp.x`), spec 28 (nomes, modo), spec 21 (tabela de átomos) |
| **Usada por** | nenhuma |
| **Esforço** | G |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): edição estrutural de inputs do pw.x (remover átomos e espécies, reindexar parâmetros por espécie e o card `HUBBARD`), casos de física que precisam de julgamento (spin, carga total, `nbnd`) e um widget extraído de um diálogo existente para uso em dois lugares. |

## Itens de origem (ideias de 05/10/2026)

> - "pp_charge_diff.in" para o cálculo de diferença de carga
>
> ### Cálculo de diferença de carga
> Para a unidade de simulação de diferença de carga. O scf base gera 3 scfs, uma cópia exata do scf base, duas com os sufixos "clean" e "isolated". [...] "clean" é quando as cargas são subtraídas da célula unitária e "isolated".
>
> Na janela de criação de unidade de simulação de "diferença de carga", deve ter uma aba para configurar os scfs com os sufixos "clean" e "isolated".
>
> Nessa aba deve ter uma tabela de seleção de átomos, mostrando o tipo e as coordenadas de cada átomo. O usuário pode selecionar e desselecionar átomos, e deve ter um botão para selecionar todos os átomos.
>
> Esses átomos selecionados serão usados para gerar os scfs "clean" e "isolated" a partir do scf base.
>
> O scf "clean" é uma cópia do scf base só que sem os átomos selecionados. [...] E é add o sufixo "_clean" ao prefixo do scf base.
>
> O scf "isolated" é uma cópia do scf base só que com apenas os átomos selecionados. E é add o sufixo "_isolated" ao prefixo do scf base.
>
> Por exemplo, para uma estrutura de superfície de ilita com uma molécula de MeHg adsorvida na superfície, a diferença de carga seria. C_total = C_ilita - C_MeHg_isolated - C_isolated.
>
> O input de "pp_charge_diff.in" deve ter o prefixo do scf base [...]
> ```
> &INPUTPP
> prefix = <prefixo do scf>,
> outdir = './tmp/',
> filplot = '<prefixo do scf>_charge_diff',
> plot_num = 0
> /
> &PLOT
> nfile = 3,
> filepp(1) = '<prefixo do scf>.charge',
> filepp(2) = '<prefixo do scf>_clean.charge',
> filepp(3) = '<prefixo do scf>_isolated.charge',
> weight(1) = 1.0,
> weight(2) = -1.0,
> weight(3) = -1.0,
> iflag = 3,
> output_format = 5,
> fileout = 'cdd_xsf/<prefixo do scf>_charge_diff.xsf'
> /
> ```
> --- O padrão para o NK e o NP do script do qsub são: NP = 64 e NK = 4.
> --- [No modo "Padrão"] o usuário só precisa informar: nome da pasta, scf base e os átomos selecionados.

**Leitura da fórmula.** Os pesos do template (1, −1, −1) definem
**Δρ = ρ(base) − ρ(clean) − ρ(isolated)**. No exemplo: Δρ = ρ(ilita + MeHg) − ρ(ilita) − ρ(MeHg), com a MeHg
selecionada: "clean" = a superfície sem a molécula, "isolated" = a molécula sozinha na mesma célula. (A frase do
exemplo na ideia veio truncada; esta spec segue os pesos do template.)

## Situação atual

- **Referência do cluster:** `Documentation/Referencia_de_scripts_QSUB/cargas.qsub` é exatamente este fluxo:
  `mkdir -p cdd_xsf`; três `pw.x` (`scf_ilita_mehg`, `scf_ilita`, `scf_mehg`; o último **sem MPI**,
  `PWCOMMAND_SINGLE`); três `pp.x` (`pp_ilita_mehg_charge.in`, `pp_ilita_charge.in`, `pp_mehg_charge.in`); por fim
  `pp_charge_diff.in`. NP 32, `-nk 4`.
- **Template e script do `pp.x`:** `qe/charge/pp_charge.in.j2` e `qsub/charge.qsub.j2` (spec 29), renderizáveis por
  `prefix`.
- **Editor de inputs** (`core/qe/input_edit.py`, spec 24): `card(name)` (`:125`) devolve `Card(name, option, line,
  lines)` com o corpo **sem** comentários e linhas em branco; `replace_card` (`:148`, `:319-331`) troca do cabeçalho
  à última linha do corpo (comentários nesse trecho se perdem); `set`, `remove`, `keys`. Não há `remove_card` nem
  listagem de cards. **Nada** no código escreve `nat`, `ntyp` ou `ATOMIC_SPECIES`, nem trata chaves por espécie
  (`starting_magnetization(i)`); `scf_from_relax.py:126-141` troca posições mantendo o número de átomos.
- **Estrutura do SCF:** `ScfInfo.crystal` (`core/qe/lattice.py:34-37`: célula em Å, rótulos, frações) é `None` quando
  `structure_problem` (ex.: `crystal_sg`); `ScfInfo.species` são os rótulos de `ATOMIC_SPECIES`.
- **Tabela de átomos existente:** `ui/dialogs/atoms.py:AtomsDialog` (192 linhas), modal "Átomos da PDOS": colunas
  checkbox, #, Elemento, x/y/z (Å) (`:32`), barra "Marcar todos", "Desmarcar todos", "Inverter", "Só espécie ▸"
  (`:67-81`), contagem, Salvar/Cancelar. A tabela é construída dentro do diálogo (`_build_table`, `:108-151`) e não é
  um widget separado; o único chamador é `ui/widgets/params_body.py:250`. Os sítios vêm de `read_sites` (saída do
  pw.x, Å).
- **Abas da janela:** uma por `PlannedFile`; um `FormField` cujo `group` não é nome de arquivo cai na primeira aba
  (`tabs_page.py:97-104`).

## Requisitos

### R1: Tipo "Diferença de carga"
1. `core/calc_create/types/charge_diff.py:ChargeDiffType`, registrado depois de "Carga": `id = "charge_diff"`,
   rótulo "Diferença de carga", `folder_prefix = "Diff_Charge"`, script `charge_diff.qsub`.
2. Arquivos (`<p>` = `prefix` do SCF base), na ordem das abas:

   | arquivo | conteúdo |
   |---|---|
   | `charge_diff.qsub` | R4 |
   | `scf_<p>.in` | cópia do SCF (regras da spec 28 R2: `outdir`, `pseudo_dir`) |
   | `scf_<p>_clean.in` | sem os átomos selecionados, `prefix = '<p>_clean'` |
   | `scf_<p>_isolated.in` | só os átomos selecionados, `prefix = '<p>_isolated'` |
   | `pp_<p>_charge.in`, `pp_<p>_clean_charge.in`, `pp_<p>_isolated_charge.in` | template da spec 29 com cada prefix (`filplot = '<x>.charge'`, `fileout = 'cdd_xsf/<x>_charge.xsf'`) |
   | `pp_charge_diff.in` | template da ideia (`qe/charge_diff/pp_charge_diff.in.j2`), pesos 1, −1, −1 |

3. Os três SCFs compartilham célula, `ibrav`/`celldm`/`CELL_PARAMETERS`, `ecutwfc`, `ecutrho`, `nr1..3` e a malha de
   k: o `pp.x` só soma densidades na mesma grade FFT. Nada disso é editável neste tipo.

### R2: Fragmentos (`core/calc_create/fragments.py`, Qt-free)
1. `atom_rows(text) -> AtomRows`: os átomos do `ATOMIC_POSITIONS` do SCF **como escritos**: índice (1-based),
   rótulo, as três coordenadas em texto e a unidade do card (`alat`, `bohr`, `angstrom`, `crystal`). Não depende de
   `ScfInfo.crystal`, então funciona também com `structure_problem`. `crystal_sg` → erro "Posições em crystal_sg não
   são suportadas".
2. `split_input(text, selected: set[int]) -> Fragments(clean, isolated, notes, errors)`, com o `InputEditor`:
   - `ATOMIC_POSITIONS`: só as linhas dos átomos mantidos, **com o texto original de cada linha** (flags `if_pos`,
     comentário no fim da linha);
   - `nat` atualizado;
   - espécie sem nenhum átomo no fragmento: sai de `ATOMIC_SPECIES`, `ntyp` atualizado, e toda chave de `&SYSTEM`
     indexada por espécie é removida para ela e **reindexada** para as que ficam (`starting_magnetization(i)`,
     `starting_charge(i)`, `angle1(i)`, `angle2(i)`, `london_c6(i)`, `london_rvdw(i)`, o último índice de
     `starting_ns_eigenvalue(m,s,i)`);
   - card `HUBBARD` (QE ≥ 7.1): linhas de espécie removida saem; linhas `V` com índices de átomo são renumeradas e
     saem quando citam um átomo removido (com nota);
   - `ATOMIC_FORCES` e `ATOMIC_VELOCITIES` (um por átomo): filtrados como as posições;
   - `CONSTRAINTS` presente → erro "Restrições (CONSTRAINTS) não são suportadas na diferença de carga";
   - `nbnd` do SCF é removido dos dois fragmentos (padrão do pw.x), com nota.
3. Avisos (não bloqueiam), por arquivo: `nspin = 2` e nenhuma espécie com `starting_magnetization` no fragmento (o
   pw.x para com "some starting_magnetization MUST be set"); `tot_charge` ou `tot_magnetization` presentes (valem
   para o sistema inteiro, conferir no fragmento); fragmento isolado com mais de um átomo distante dos demais não é
   checado (é escolha do usuário).
4. Erros (bloqueiam "Criar"): nenhum átomo selecionado ("Selecione os átomos do fragmento isolado"); todos
   selecionados ("Deixe ao menos um átomo fora da seleção: o SCF clean ficaria vazio").
5. `InputEditor` ganha só o que faltar, sem quebrar a regra "nunca levanta, preserva o resto": por exemplo, o corpo
   bruto de um card (linhas com comentários) e `remove_card(name)`. Propriedades novas em `test_properties.py`.

### R3: Aba "Átomos"
1. O campo `atoms` (`FormField(kind="atoms", standard=True, required=True)`) tem aba própria **"Átomos"**, a primeira
   da Etapa 2. Mecanismo genérico: um `group` que não é nome de arquivo vira uma aba com esse rótulo, antes das abas
   de arquivo, na ordem em que o tipo declara os campos (hoje esse campo cairia na primeira aba).
2. `ui/widgets/atom_table.py:AtomTable(QWidget)`: tabela extraída do `AtomsDialog` (checkbox, #, Elemento, x, y, z
   com a unidade no cabeçalho) e a barra "Marcar todos" (o "selecionar todos" do pedido), "Desmarcar todos",
   "Inverter", "Só espécie ▸", mais a contagem "N de M átomos". Recebe linhas prontas (texto), não `Site`s, para
   servir aos dois usos. `AtomsDialog` passa a usar o `AtomTable` (comportamento da spec 21 inalterado; os testes dela
   continuam passando).
3. A aba mostra, ao lado da tabela, a legenda curta: "Selecionados → isolated (só eles); o resto → clean (sem eles).
   Δρ = ρ(base) − ρ(clean) − ρ(isolated)".
4. Cada mudança na seleção replaneja (mesmo debounce das edições); as abas `scf_<p>_clean.in` e
   `scf_<p>_isolated.in` mostram a prévia com as linhas alteradas destacadas (como as outras derivações).

### R4: Script `qsub/charge_diff.qsub.j2`
1. Estende `_base.qsub.j2` com `PPCOMMAND` (como a spec 29). Corpo, na ordem de `cargas.qsub`:
   `mkdir -p cdd_xsf`; `pw.x` de `scf_<p>.in`, `scf_<p>_clean.in`, `scf_<p>_isolated.in` (com `${MPICOMMAND}`);
   `pp.x` dos três `pp_*_charge.in` (sem MPI); `pp.x -i pp_charge_diff.in > pp_charge_diff.out`.
2. Nomes vindos do plano (variáveis), como a spec 28 R1.4.

### R5: Modos
1. **Padrão:** nome da pasta, SCF base e átomos. Tudo o mais fixo (templates da ideia, NP/NK do `config.yaml`).
2. **Avançado:** campos do script, "Nome do arquivo" de cada input e os campos do `pp.x` da spec 29
   (`iflag`, `output_format`, `fileout`), aplicados aos quatro inputs do `pp.x`.

## Fora de escopo
- Visualizar Δρ (`.xsf`) ou detectar saídas do `pp.x`.
- Escolher os átomos automaticamente (molécula vs. superfície por conectividade).
- Mais de dois fragmentos, pesos diferentes de 1/−1/−1, ou fragmentos com célula/malha próprias.
- Editar chaves arbitrárias dos fragmentos (o Avançado é "campos atuais", decisão da spec 28).

## Decisões assumidas (confirmar na revisão)
1. A aba começa **sem** átomos selecionados (o usuário escolhe o fragmento isolado); "Marcar todos" existe, mas
   selecionar todos é erro (clean vazio).
2. O SCF "isolated" roda **com MPI**, como os outros (em `cargas.qsub` ele roda serial, `PWCOMMAND_SINGLE`; se isso era
   necessário no cluster, vira um campo "Isolado sem MPI" no Avançado).
3. Os `pp_*_charge.in` usam o prefix de cada SCF no nome (`pp_<p>_clean_charge.in`), como `cargas.qsub`; o
   `pp_<nome>_charge.in` da spec 29 usa o nome da pasta, que aqui não identifica os três.
4. `pp_charge_diff.in` é o template da ideia sem mudanças, inclusive o `&INPUTPP` com `plot_num = 0`, que recalcula
   a densidade do base em `<p>_charge_diff` antes de somar (inofensivo; mantido por ser o template validado no
   cluster).
5. A unidade dos números na tabela é a do card (não converte para Å), para mostrar o que vai para o arquivo.
6. `nbnd` sai dos fragmentos; `tot_charge`/`tot_magnetization` ficam, com aviso.

## Notas de implementação
- Novos: `core/calc_create/fragments.py`, `core/calc_create/types/charge_diff.py`,
  `resources/templates/qe/charge_diff/pp_charge_diff.in.j2`, `resources/templates/qsub/charge_diff.qsub.j2`,
  `ui/widgets/atom_table.py`.
- Alterados: `core/qe/input_edit.py` (o mínimo para R2.5), `types/__init__.py`, `types/base.py` (kind `atoms`),
  `ui/dialogs/calc_create/{tabs_page,form}.py` (aba por grupo e widget `atoms`), `ui/dialogs/atoms.py` (usa
  `AtomTable`).
- `fragments.py` entra em `QT_FREE` de `test_architecture.py`.
- Fixtures: um SCF com duas espécies e átomos separáveis (ex.: um slab pequeno com uma molécula) feito em `tmp_path`
  a partir das fixtures, nunca escrito em `tests/fixtures/`; casos com `nspin = 2`, `HUBBARD` com `U` e `V`, `if_pos`
  e comentários nas posições.

## Critérios de aceite e testes
- [ ] Plano: prefix `ilita` → os 8 arquivos de R1.2 com os prefixos `ilita`, `ilita_clean`, `ilita_isolated`;
      `pp_charge_diff.in` igual, linha a linha, ao template da ideia.
- [ ] Fragmentos: `nat` de clean + isolated = `nat` do base; espécie ausente sai de `ATOMIC_SPECIES` e `ntyp`;
      `starting_magnetization(i)` reindexado; `HUBBARD` `U` da espécie removida sai e `V` é renumerado; `if_pos` e
      comentários de linha preservados; célula, cortes e `K_POINTS` idênticos ao base (diff só nas linhas esperadas);
      lint sem erros nos dois.
- [ ] Erros e avisos: seleção vazia e total bloqueiam; `CONSTRAINTS` bloqueia; `nspin = 2` sem magnetização no
      fragmento, `tot_charge` e `nbnd` removido geram notas.
- [ ] Script: `mkdir -p cdd_xsf`, três `pw.x` com MPI, três `pp.x` e o da diferença sem MPI, nessa ordem.
- [ ] Janela: aba "Átomos" primeiro; "Marcar todos", "Desmarcar todos", "Inverter", "Só espécie"; a contagem e as
      prévias de clean/isolated mudam com a seleção; "Criar" desabilitado com seleção vazia ou total (tooltip do
      motivo).
- [ ] Spec 21: `AtomsDialog` com `AtomTable` passa nos testes de átomos da PDOS sem mudança de comportamento.
- [ ] Propriedades: `split_input` com seleção aleatória nunca levanta e mantém `nat`/`ntyp` coerentes com os cards.
- [ ] `test_architecture.py`: arquivos < 500 linhas; `fragments.py` sem PyQt6.
