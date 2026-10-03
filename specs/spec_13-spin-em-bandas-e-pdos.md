# Spec 13: Spin (dois canais) nos gráficos de bandas e de PDOS

| | |
|---|---|
| **Prioridade** | 13 (feature grande; depende de fixture nova) |
| **Status** | Implementada. Desvios: o canal ↓ são papéis próprios (`gnu_down`, `filband_down`), não `multiple=True` nem `result.channels` (o diálogo de mapeamento, o `FolderMemory` e o painel funcionam sem código novo), e o pareamento roda no `finalize` (o SCF pode vir de uma pasta vizinha); o spin também vale quando só a saída pw.x de bandas tem spin; arquivos sem indício do canal (nem input, nem saída do bands.x, nem `up`/`dw` no nome) não são adivinhados pela ordem: só ↑ e um aviso pedindo o mapeamento manual; o layout lado a lado compartilha também o eixo X (`sharex`), assim o zoom de qualquer painel chega em `axes_limits[0]`; tolerância de 1e-3 eV na classificação das bandas; com duas E_F o resumo mostra `E_F↑ … · E_F↓ …`; a fixture são três pastas (`qe731_ni_spin_bands`, `_pdos`, `_fixed`, QE 7.3.1 rodado localmente, Ni PBE) e a `ni_pdos_spin` (6.0) foi removida: o QE 7.3.1 não imprime `Harris-Foulkes estimate`, então o teste dessa linha ficou com texto sintético; o canal ilegível ou ausente deixa o gráfico só com ↑ (dataset sem spin); `PdosDataset` ganhou `fermi_channels` e `magnetization` |
| **Depende de** | spec 8 (hooks `apply_limits` com vários eixos, `view_fields`, tipagem) |
| **Usada por** | spec 9 (a fixture com spin substitui a `ni.scf.out` 6.0 nos testes de magnetização) |
| **Esforço** | G |

## Itens de origem

> **F6. Bandas com spin** (dois canais). Limitação declarada no README ("um único canal `.gnu`"). PDOS já espelha spin-down, então há convenção visual pronta.

Pedido do usuário (30/09/2026):
> Faça a extensão do plot de bandas e plot de PDOS para o caso de sistemas com SPIN (Dois canais).

Regras de arquitetura do `CLAUDE.md` (30/09/2026) que valem aqui: nenhum arquivo com mais de ~500 linhas
que centralize tudo, e código em módulos. O `bands.py` já está no limite, então é dividido **antes** de
receber o spin (R0).

## Situação atual

**Tamanho dos módulos:** `core/calculations/bands.py` tem 504 linhas e mistura quatro coisas:
- detecção: papéis, `select`, `_named_by_bandsx` e `finalize` (l.103-212);
- parâmetros e schema (l.79-91, 214-305);
- carga e física: `load`, `_eigenvalues`, `_ticks`, `_band_edges`, `_bands_from_pw_output`
  (l.307-389, 491-504);
- render: `render`, `tick_labels`, `merged_ticks`, `summary` (l.391-484).

`core/calculations/pdos.py` tem 377 linhas e, com o spin, passaria de 500. Os testes importam
`BandsParams` e `merged_ticks` de `core.calculations.bands` e `PdosParams` de `core.calculations.pdos`.

**Bandas** (`core/calculations/bands.py`):
- Papéis (l.108-145): `scf_out`, `bands_in` (pw.x `calculation='bands'`), `bands_out`, `bandsx_out`,
  `filband` e `gnu`. Todos de arquivo único: `select` (l.147-158) escolhe **um** `.gnu`/filband,
  preferindo o nome citado na saída do bands.x (`_named_by_bandsx`, l.160-178).
- O input do bands.x (`&BANDS`, `FileKind.BANDSX_IN`) não é um papel. O `spin_component` dele nunca é
  lido.
- `BandsDataset.bands` (l.47-61) é um único `BandData(x, energies[band, k])`.
- `_band_edges` (l.377-389) sai cedo com `pw.spin_polarized`: sem VBM/CBM/gap com spin.
- `_bands_from_pw_output` (l.491-504) recusa spin: `"bandas com spin exigem o bands.x"` (l.497).
- `render` (l.391-443) desenha valência e condução em duas cores, com uma linha de Fermi.

**PDOS** (`core/calculations/pdos.py`, `core/qe/projwfc.py`):
- `read_pdos_file` (`projwfc.py:86-105`) lê `ldosup`/`ldosdw` (ou `dosup`/`dosdw`) em
  `Channel(up, down)`. `PdosData.spin_polarized` (l.126-128) é verdadeiro se alguma série tem `down`.
- `render` (`pdos.py:294-365`) **sempre espelha**: desenha `-down` com a mesma cor e sem rótulo
  (l.321-324), usa limites simétricos (l.336-337) e uma linha guia em 0. Não há escolha de modo nem
  indicação ↑/↓ na legenda.
- O preenchimento dos estados ocupados usa uma única E_F (l.316-319).

**Fermi e magnetização** (`core/qe/pw_output.py`):
- `spin_fermi` (`the spin up/dw Fermi energies are`, l.22-25) vira a **média**, com o aviso "duas
  energias de Fermi (up/dw); usando a média" (l.65-66, 110-112).
- `_spin_polarized` (l.90-94) detecta spin colinear. `total magnetization` não é guardado.

**Fixtures:** a única com spin é `ni_pdos_spin/` (QE 6.0, só PDOS). Não há bandas com spin.

**Como o QE produz bandas com spin colinear (nspin = 2):** o bands.x roda **duas vezes**, com
`spin_component = 1` e `spin_component = 2` no `&BANDS`, e cada execução escreve o seu `filband` e o
`<filband>.gnu`. A saída do bands.x não diz qual componente é. Só o input diz.

## Requisitos

### R0: Dividir os módulos antes de estender (sem mudar comportamento)
1. `core/calculations/bands.py` vira o pacote `core/calculations/bands/`:
   | Arquivo | Conteúdo |
   |---|---|
   | `__init__.py` | reexporta `BandsModule`, `BandsDataset`, `BandsParams`, `merged_ticks` (os imports atuais continuam funcionando) |
   | `module.py` | `BandsModule`: papéis, `kind`/`badge`, e a ligação entre as partes abaixo |
   | `detection.py` | `select`, `_named_by_bandsx`, `finalize`, pareamento ↑/↓ (R1) |
   | `params.py` | `BandsParams`, `REFERENCES`, `Y_LABELS`, `param_schema`, `param_changed` |
   | `data.py` | `BandsDataset`, `load`, `_eigenvalues`, `_ticks`, bordas por canal (R2), reserva pw.x |
   | `render.py` | `render`, `merged_ticks`, `tick_labels`, `summary`, desenho com spin (R3–R4) |
2. `core/calculations/pdos.py` segue o mesmo padrão (`pdos/` com `module.py`, `params.py`, `data.py` e
   `render.py`) se, com o R5, passar de ~400 linhas. Senão, fica em um arquivo.
3. O R0 é um commit **só de mover código**: nenhuma mudança de comportamento, e a suíte inteira passa
   antes de começar o R1.
4. Nenhum arquivo novo ou alterado por esta spec passa de 500 linhas.
5. A lógica de spin fica toda em `core/`. Nenhum código de `ui/` muda por causa do spin: os parâmetros
   novos aparecem no painel pelo schema, e os eixos extras pelos hooks da spec 8.

### R1: Detecção dos dois canais nas bandas
1. Novo papel `bandsx_in` ("Entrada do bands.x"), `output_of(FileKind.BANDSX_IN)`, `multiple=True`,
   globs `("bands*.in", "*band*x*.in")`. É opcional e não é âncora.
2. Os papéis `gnu` e `filband` passam a `multiple=True`. Um `select` próprio monta **até dois** canais:
   1. pelo input: cada `bandsx_in` dá `filband` e `spin_component` (1 = ↑, 2 = ↓, ausente = 1). O
      `.gnu` do canal é `<filband>.gnu`;
   2. pela saída do bands.x (`_named_by_bandsx`), para o canal sem input;
   3. por nome, como reserva: `up`/`dw`/`down`/`dn` no nome (sem diferenciar maiúsculas);
   4. sem spin (o `scf_out` não tem `spin_polarized`): comportamento atual, um único arquivo.
3. `DetectionResult` guarda o canal de cada arquivo (`result.channels: dict[Path, Literal["up",
   "down"]]`, ou um papel separado `gnu_down`/`filband_down`; a escolha é registrada nas notas). O
   mapeamento manual (spec 3/PRD §3.2) ganha os papéis "Dados de bandas ↓ (.gnu)".
4. Avisos de detecção:
   - SCF com spin e só um canal encontrado: "só o canal ↑ foi encontrado: rode o bands.x com
     spin_component = 2";
   - os dois canais com números de pontos k diferentes: "os canais ↑/↓ têm pontos k diferentes";
   - a verificação de pontos k atual (`finalize`, l.193-212) vale para cada canal.
5. Reserva pw.x (`_bands_from_pw_output`): com `calc.get_number_of_spins() == 2`, lê os dois canais
   (`get_eigenvalues(kpt=k, spin=s)`) em vez de recusar.

### R2: Dados e física das bandas
1. `BandsDataset.bands` continua sendo o canal ↑ (ou o único), e entra `bands_down: BandData | None`.
   `spin = bands_down is not None`.
2. Bordas por canal, a partir da E_F (com spin não dá para usar `n_electrons/2`):
   - num canal, uma banda é de valência se `max ≤ E_F`, de condução se `min ≥ E_F`, e atravessa a E_F
     caso contrário;
   - se alguma banda do canal atravessa → canal metálico;
   - senão, `VBM_s = max(valência)`, `CBM_s = min(condução)` e `gap_s = CBM_s − VBM_s`;
   - gap global = `min(CBM↑, CBM↓) − max(VBM↑, VBM↓)`, quando os dois canais têm gap.
   Os campos ficam em `BandsDataset.edges: dict[str, ChannelEdges]`. As referências "VBM" e "Meio do
   gap" usam as bordas globais.
3. Duas energias de Fermi (`fermi_up_down`, magnetização fixa): cada canal usa a sua E_F para as bordas.
   A referência "E_F (SCF)" continua na média, e o aviso muda para "duas energias de Fermi (↑/↓):
   referência na média, linhas separadas no gráfico".
4. `PwOutput` ganha `total_magnetization` e `absolute_magnetization` (último valor; módulo do vetor no
   caso não colinear). Também é usado pela spec 12.

### R3: Figura das bandas com spin
1. Parâmetros novos em `BandsParams` (seção "Spin", que só entra no schema quando `dataset.spin`):
   | Campo | Rótulo | Tipo | Padrão |
   |---|---|---|---|
   | `spin_channels` | Canais | choice: `both` "Ambos", `up` "Só ↑", `down` "Só ↓" | `both` |
   | `spin_layout` | Disposição | choice: `overlay` "Sobrepostos", `side` "Lado a lado" | `overlay` |
   | `spin_coloring` | Cores por | choice: `channel` "Canal", `occupation` "Valência/condução" | `channel` |
   | `up_color` | Cor ↑ | color | `#2563eb` |
   | `down_color` | Cor ↓ | color | `#f97316` |
2. `overlay`: um eixo, ↑ em linha contínua e ↓ tracejada (`(0, (4, 2))`). Legenda "Spin ↑" / "Spin ↓".
   Com `occupation`, cada canal usa as cores de valência/condução, e o ↓ continua tracejado.
3. `side`: dois eixos lado a lado, com `sharey`, títulos "Spin ↑" e "Spin ↓", rótulos k nos dois e o
   rótulo de energia só no da esquerda. `apply_limits` (spec 8) grava o X a partir do eixo em que o
   zoom foi feito (os dois têm o mesmo caminho k).
4. Duas E_F: duas linhas horizontais (↑ contínua, ↓ tracejada) na cor `fermi_color`, com legenda
   `E_F↑`, `E_F↓`.
5. Sem spin: figura idêntica à atual (teste de regressão por imagem/estrutura de artistas).

### R4: Resumo do gráfico de bandas com spin
`E_F = 5.1234 eV · spin polarizado · gap ↑ 1.234 eV · ↓ metálico · M = 0.62 μB/célula · 12 bandas × 200
pontos k`. Com os dois canais com gap, acrescenta "gap global X eV".

### R5: PDOS com spin
1. Parâmetro `spin_mode` (seção "Projeções", só com `data.spin_polarized`):
   | Valor | Rótulo | Desenho |
   |---|---|---|
   | `mirror` | Espelhado (↓ negativo) | comportamento atual (padrão) |
   | `overlay` | Sobreposto | ↓ positivo, mesma cor, linha tracejada; preenchimento só do ↑ |
   | `up` | Só ↑ | só o canal ↑ |
   | `down` | Só ↓ | só o canal ↓, positivo |
   | `sum` | Soma (↑ + ↓) | `up + down` como um canal |
2. Indicação de canal:
   - em `mirror`, rótulos "↑" e "↓" discretos (texto no canto do eixo, cor `style.guide`), dos dois lados
     do zero;
   - em `overlay`, duas entradas de estilo na legenda: "↑ contínua" e "↓ tracejada".
3. `dos_lim`: simétrico só em `mirror`. Nos outros modos, começa em 0.
4. Duas E_F (`fermi_up_down` do SCF ou do NSCF): duas linhas de Fermi (↑ contínua, ↓ tracejada). O
   preenchimento dos estados ocupados de cada canal usa a sua E_F. A referência continua na média
   (mesma regra das bandas).
5. Resumo: acrescenta `M = 0.62 μB/célula` quando o SCF tem magnetização.
6. `apply_limits`: em `mirror`, como hoje (`dos_max = max(|lim|)`). Nos outros modos, `dos_max = lim
   superior`.

### R6: Persistência
`bands.plot` e `pdos.plot` (spec 3) ganham os campos novos sem código especial (`CommonParams` + schema).
Arquivos antigos sem esses campos usam os padrões.

## Fora de escopo
- Bandas não colineares/spin-órbita com projeção de spin (cores por ⟨σ_z⟩).
- Bandas desdobradas, "fat bands" (projeção orbital nas bandas).
- Gráfico combinado bandas + PDOS (F5, adiado).
- DOS total do dos.x (F2, adiado).

## Decisões assumidas (confirmar na revisão)
1. O padrão do PDOS continua **espelhado** (comportamento atual, R5.1).
2. O padrão das bandas é **sobreposto, cores por canal** (↑ azul, ↓ laranja tracejado).
3. Com duas E_F, a referência de energia é a **média** (como hoje), e as duas linhas são desenhadas.
4. O canal sem `spin_component` no input é ↑ (padrão do bands.x).
5. Não colinear: continua com um único canal (sem mudança).

## Pendência (resolvida)
- **Fixture real com spin, QE ≥ 7.1** (obrigatória para esta spec): um sistema magnético pequeno (ex.:
  Fe bcc ou Ni fcc), com:
  - `scf.in/out` (nspin = 2);
  - `bands.in/out` (pw.x bands);
  - dois inputs do bands.x (`spin_component = 1` e `2`), com as saídas e os `.gnu`;
  - `nscf` + `projwfc` com alguns `pdos_atm#…` e `pdos_tot`.

  Reduzida como as demais e documentada em `tests/fixtures/README.md`. Uma variante com
  `tot_magnetization` (duas E_F) é desejável. Ela substitui a `ni_pdos_spin` (QE 6.0) nos testes de
  PDOS e de magnetização (specs 7 e 9).

## Notas de implementação
- Novos: o pacote `core/calculations/bands/` (R0.1) e, se for o caso, `core/calculations/pdos/` (R0.2).
- Removido: `core/calculations/bands.py` (vira o pacote).
- Alterados:
  - `core/calculations/__init__.py` (import do pacote, se necessário);
  - `core/calculations/pdos.py` (modo de spin, Fermi por canal);
  - `core/qe/pw_output.py` (magnetização);
  - `core/qe/pw_input.py` (nada: `parse_input` já lê `&BANDS`);
  - `ui/dialogs/mapping.py` (os papéis novos aparecem sozinhos se o diálogo for gerado de `roles`;
    verificar);
  - `README.md` (remover a limitação "um único canal `.gnu`").
- O teste de regressão sem spin compara os artistas da figura (número de `LineCollection`, cores e
  limites) antes e depois.
- Performance (NFR §7): duas vezes 100 bandas abaixo de 500 ms, num caso `@pytest.mark.perf`.

## Critérios de aceite e testes
- [ ] R0: depois da divisão e antes de qualquer mudança de spin, a suíte inteira passa sem alterar
      nenhum teste. `from qe_studio.core.calculations.bands import BandsParams, merged_ticks` continua
      funcionando.
- [ ] Nenhum arquivo em `core/calculations/` passa de 500 linhas (`wc -l`).
- [ ] Nenhum arquivo de `ui/` foi alterado por esta spec, exceto se o diálogo de mapeamento não for
      gerado dos papéis (ver notas).
- [ ] Detecção na fixture com spin: `bandsx_in` com os 2 inputs, os 2 `.gnu` atribuídos a ↑/↓ pelo
      `spin_component`, sem avisos.
- [ ] Removendo o `.gnu` do ↓ (cópia): aviso "só o canal ↑ foi encontrado…", e o gráfico sai só com ↑.
- [ ] Pastas sem spin (`al_bands`, `si_bands`): detecção, dataset e figura iguais aos de antes.
- [ ] Bordas: no canal metálico, sem gap. No canal isolante, o gap confere com o calculado à mão a partir
      do `.gnu`.
- [ ] `spin_layout=side` → 2 eixos com `sharey`. `overlay` → 1 eixo, linhas ↓ tracejadas.
- [ ] Texto sintético com `the spin up/dw Fermi energies are`: duas linhas de Fermi, e o aviso novo.
- [ ] PDOS na fixture com spin: os 5 modos de `spin_mode` geram figuras sem erro. `mirror` tem limites
      simétricos, e os demais começam em 0.
- [ ] `pdos.plot` antigo, sem `spin_mode`, carrega com `mirror`.
- [ ] Resumo das bandas e da PDOS com `M = … μB/célula` na fixture com spin.
