# Spec 27-1: PDOS gerado — `mv` do script e ocupação × `degauss`

| | |
|---|---|
| **Prioridade** | 27-1 (primeira correção da revisão de 04/10/2026; antes da spec 28) |
| **Status** | Proposta |
| **Depende de** | spec 25 (templates de "Criar cálculo"), spec 26 (janela) |
| **Usada por** | spec 28 (nomes do padrão e modo Padrão/Avançado reaproveitam o `pdos.qsub` e o `projwfc.in` corrigidos) |
| **Esforço** | P |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): três ajustes pequenos e bem delimitados em dois templates, um tipo de cálculo e quatro testes existentes; o comportamento esperado já está descrito linha a linha abaixo. |

## Itens de origem (`specs/report-04-10-26.md`)

- **F1 (Alto, confirmado):** o `pdos.qsub` gerado termina em `mv *wfc* orbitals/`, que move também `projwfc.in` e
  `projwfc.out` (o nome contém "wfc").
- **Q1(a) (Médio):** os testes `test_calc_templates.py` e `test_calc_roundtrip.py` travam o comportamento errado.
- **F5 (Médio), duas das três partes:** (i) o `projwfc.in` sempre escreve `ngauss`/`degauss`, anulando a ocupação por
  tetraedros que o formulário oferece; (ii) a janela de energia (`Emin`/`Emax`) pode ser maior que as bandas calculadas.
  A terceira parte (malha do NSCF igual à do SCF) **não entra**: decisão do usuário em 05/10/2026, "manter sem avisar".

## Situação atual

- **F1.** `src/qe_studio/resources/templates/qsub/pdos.qsub.j2:10,14-15`:
  ```
  ${PROJWFCCOMMAND} -i "projwfc.in" > "projwfc.out"
  mkdir -p orbitals
  mv *wfc* orbitals/ 2>/dev/null
  ```
  O script de referência (`Documentation/Referencia_de_scripts_QSUB/PDOS.qsub`) usava `proj.in`/`proj.out`, sem "wfc" no
  nome. O template os renomeou para `projwfc.*` e manteve o glob. Resultado depois do job: `projwfc.in` e `projwfc.out`
  vão para `orbitals/`.
- **O que a detecção precisa** (`core/calculations/pdos/module.py:~60-110`): `pdos_atm` é obrigatório e múltiplo, com o único
  glob `orbitals/*pdos_atm#*_wfc#*` (arquivos soltos na pasta **não** são detectados); `pdos_tot` aceita `*pdos_tot` e
  `orbitals/*pdos_tot`; `projwfc_out` (`projwfc*.out`) é opcional e só é procurado na raiz. Os nomes que o projwfc.x escreve
  são `<filpdos>.pdos_tot` e `<filpdos>.pdos_atm#N(El)_wfc#M(l)` (`core/qe/projwfc.py:17,21`; fixtures `pdos.dat.pdos_tot`,
  `ni.pdos_atm#1(Ni)_wfc#2(d)`).
- **Testes que fixam o erro:**
  - `tests/test_calc_templates.py:101`: caso `("pdos", "PDOS.qsub", al, {"job_name": "pdo2"}, {"proj.": "projwfc."})`;
    `test_scripts_reproduce_the_reference` (`:104-112`) compara o corpo com a referência depois de aplicar o dicionário de
    renomeação, e a referência termina em `mv *wfc* orbitals/`.
  - `tests/test_calc_templates.py:120-124` exige `pdos.index("projwfc.out") < pdos.index("mkdir -p orbitals\nmv *wfc* orbitals/ 2>/dev/null")`.
  - `tests/test_calc_roundtrip.py:74-92` (`test_pdos_folder_is_detected`): coloca `projwfc.out` e `pdos.dat.pdos_tot` na raiz e
    copia só os `*pdos_atm*` para `orbitals/` (comentário `# what "mkdir -p orbitals; mv *wfc* orbitals/" leaves`): um layout que o
    script de hoje não produz, porque ele também move o `projwfc.out`.
- **F5 (i).** `templates/qe/pdos/projwfc.in.j2` escreve sempre `ngauss` e `degauss`; `types/pdos.py:52-55` dá os padrões `degauss = 0.01`,
  `ngauss = 0`; o NSCF tem `occupations` com padrão `tetrahedra` (`types/pdos.py:~20`, `DEFAULT_OCCUPATIONS`) e o tooltip diz
  "tetraedros dão uma DOS mais limpa". Documentação do QE (INPUT_PROJWFC, consultada em 05/10/2026): `degauss` tem padrão 0; se não for
  dado, o valor é lido do arquivo do pw.x; se o pw.x rodou com `occupations = 'tetrahedra'` e `degauss` não for dado, o projwfc.x usa o
  **método dos tetraedros**. Escrever `degauss` no `projwfc.in` desliga isso. Nas fixtures reais (`al_pdos_flat/projwfc.out:36`:
  `Gaussian broadening (read from file): ngauss,degauss= 0 0.010000`; `qe731_ni_spin_pdos/ni.pdos.in`: `ngauss=1, degauss=0.02` "read from
  input") só há casos com smearing; nenhum com tetraedros.
- **F5 (ii).** `Emin`/`Emax` padrão −25/+25 eV (`types/pdos.py:52-53`) são energias **absolutas** (a documentação do QE dá como padrão os
  extremos das bandas), e `nbnd` do NSCF vem de 1,2 × os estados do SCF (`types/fields.py:14,40-46`). `ScfInfo` guarda só a contagem de
  estados (`scf_bands`), sem autovalores (`scf_info.py:35-61`); o NSCF ainda nem rodou na criação, então não há como saber o teto em
  energia da banda `nbnd`.

## Requisitos

### R1: `mv` só das projeções
1. O passo final de `qsub/pdos.qsub.j2` passa a ser:
   ```
   mkdir -p orbitals
   mv *pdos_atm#* orbitals/ 2>/dev/null
   ```
   Só os arquivos `<filpdos>.pdos_atm#N(El)_wfc#M(l)` vão para `orbitals/` (é onde `orbitals/*pdos_atm#*_wfc#*` os procura). Ficam na pasta:
   `<filpdos>.pdos_tot`, `projwfc.in`, `projwfc.out`, `scf.*`, `nscf.*` e o `tmp/`. Um `filpdos` do usuário que contenha "wfc" deixa de
   afetar o resultado.
2. O comentário do template diz por que o glob é `*pdos_atm#*` (nomes do projwfc.x e da detecção).

### R2: Testes (Q1a)
1. `test_calc_templates.py:101`: o dicionário de renomeação da referência ganha a troca `mv *wfc* orbitals/` → `mv *pdos_atm#* orbitals/`
   (a referência em `Documentation/` não muda).
2. `test_calc_templates.py:120-124`: a linha exigida passa a ser a nova.
3. **Teste novo do glob:** extrai o padrão do `mv` do script renderizado, expande com `fnmatch` sobre os nomes que a pasta terá depois do
   job (`scf.in`, `scf.out`, `nscf.in`, `nscf.out`, `projwfc.in`, `projwfc.out`, `pdos.dat.pdos_tot`, `pdos.dat.pdos_atm#1(Al)_wfc#1(s)`,
   `pdos.dat.pdos_atm#1(Al)_wfc#2(p)`) e exige que **só** os `pdos_atm` casem. Variante com `filpdos = "wfc_teste.dat"`: ainda só os `pdos_atm`.
4. `test_calc_roundtrip.py:84-90`: a pasta montada imita o layout real (`projwfc.out` e `pdos.dat.pdos_tot` na raiz; só as projeções em
   `orbitals/`), e o teste exige que `found["pdos"]` seja plotável **e** que o papel `projwfc_out` seja encontrado.

### R3: `ngauss`/`degauss` × ocupação do NSCF (F5 i)
1. `projwfc.in.j2` recebe `broadening: bool`. Com `broadening` falso as linhas `ngauss` e `degauss` **não são escritas**.
2. `types/pdos.py`: `broadening = not occupations.startswith("tetrahedra")` (`tetrahedra`, `tetrahedra_opt`, `tetrahedra_lin`); com
   `smearing` ou `fixed` os dois são escritos, como hoje. Com tetraedros, os valores dos campos `degauss`/`ngauss` são ignorados e o plano
   acrescenta a nota: "projwfc.in sem ngauss/degauss: com tetraedros o projwfc.x usa o método dos tetraedros (um degauss no input o
   desligaria)".
3. Os tooltips de `occupations`, `degauss` e `ngauss` passam a dizer isso ("ignorado com tetraedros"; o de `degauss` cita a unidade, Ry).
4. Os padrões `degauss = 0.01` e `ngauss = 0` continuam (a spec 28 muda o `degauss` para 0,000735 no modo Padrão e mantém esta regra: o par fixo
   só vale quando a ocupação não é tetraedros).

### R4: `Emin`/`Emax` × `nbnd` (F5 ii), só texto
1. Os tooltips de `nbnd` (NSCF) e de `Emax` explicam: "Emin/Emax são energias absolutas em eV; acima da energia da última banda calculada
   (`nbnd`) a DOS é zero. Aumente `nbnd` ou reduza `Emax`".
2. **Sem aviso calculado:** na criação não existem autovalores do NSCF, e os do SCF cobrem menos bandas que o NSCF (1,2 ×). Registrado como
   limitação conhecida (ver "Decisões assumidas").

## Fora de escopo
- Malha do NSCF (decisão do usuário: igual à do SCF, sem aviso).
- Nomes de arquivo do padrão, `outdir`, `pseudo_dir` e valores fixos do modo Padrão: spec 28 (o antigo R6 dela, o `mv`, passa a ser esta spec).
- Mudar o formato de `pdos_tot`/`orbitals/` ou a detecção da PDOS.
- Ler autovalores do SCF/NSCF para estimar o teto de energia.

## Decisões assumidas (confirmar na revisão)
1. O glob é `*pdos_atm#*` (sem `_wfc#*`): o projwfc.x só escreve `pdos_atm#` com `_wfc#`, e o glob mais curto não depende do formato do
   sufixo `(l_j)` dos cálculos com spin-órbita.
2. Com tetraedros o par `ngauss`/`degauss` **não** é escrito (em vez de escrever `degauss = 0`): o QE diz que o valor ausente faz o projwfc.x
   usar o método do pw.x, e é esse comportamento que o tooltip já promete.
3. `fixed` continua escrevendo `ngauss`/`degauss` (um isolante com ocupação fixa tem `degauss = 0` no arquivo do pw.x e a DOS sairia em deltas).
4. O aviso de `Emax` × `nbnd` fica só em texto (R4): qualquer estimativa com os autovalores do SCF daria falso conforto no caso comum
   (`nbnd` do NSCF > estados do SCF).

## Notas de implementação
- Alterados: `src/qe_studio/resources/templates/qsub/pdos.qsub.j2`, `templates/qe/pdos/projwfc.in.j2`, `core/calc_create/types/pdos.py`
  (variável `broadening`, nota, tooltips), `tests/test_calc_templates.py`, `tests/test_calc_roundtrip.py`.
- Nenhuma dependência nova; nenhum arquivo de `ui/`.
- A nota de R3.2 entra em `CalcPlan.notes` (aparece em "Arquivos"); não bloqueia.

## Critérios de aceite e testes
- [ ] `pdos.qsub` gerado termina em `mkdir -p orbitals` + `mv *pdos_atm#* orbitals/ 2>/dev/null`.
- [ ] O glob do `mv`, expandido sobre os nomes da pasta pós-job, casa só os `pdos_atm` (inclusive com `filpdos` contendo "wfc").
- [ ] `test_scripts_reproduce_the_reference` passa com a troca de glob no dicionário de renomeação.
- [ ] Ida e volta: layout real (`projwfc.out`, `pdos_tot` na raiz; `pdos_atm` em `orbitals/`) é detectado como PDOS plotável e acha `projwfc_out`.
- [ ] `occupations = tetrahedra`: `projwfc.in` sem `ngauss`/`degauss` e com a nota; `smearing` e `fixed`: com os dois, valores do formulário.
- [ ] Tooltips de `occupations`, `degauss`, `ngauss`, `nbnd` e `Emax` com os textos de R3.3 e R4.1.
- [ ] `ruff`, `pyright` e `test_architecture.py` sem regressão.
