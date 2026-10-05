# Spec 29: Criar cálculo — densidade de carga (`pp.x`)

| | |
|---|---|
| **Prioridade** | 29 |
| **Status** | Proposta |
| **Depende de** | spec 28 (nomes do padrão, `outdir`/`pseudo_dir`, modo Padrão/Avançado) |
| **Usada por** | spec 30 (diferença de carga reaproveita o template e o script) |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): um tipo novo no registro, um template Jinja e um `.qsub`, seguindo o caminho que as specs 25 e 28 já abriram ("tipo novo = módulo + templates + registro"). O único ponto fora do padrão é o lint de inputs do `pp.x`, pequeno e bem delimitado. |

## Itens de origem (ideias de 05/10/2026)

> - "pp_<nome>_charge.in" e "pp_charge.in" para o cálculo de carga
>
> ## Para o cálculo de carga
> --- O input de "pp_<nome>_charge.in" onde nome se refere ao nome da unidade de simulação de carga:
> ```
> &INPUTPP
> prefix = <prefixo do scf>,
> outdir = './tmp/',
> filplot = '<prefixo do scf>.charge',
> plot_num = 0
> /
> &PLOT
> nfile = 1,
> filepp(1) = '<prefixo do scf>.charge',
> weight(1) = 1.0,
> iflag = 3,
> output_format = 5,
> fileout = 'cdd_xsf/<prefixo do scf>_charge.xsf'
> /
> ```
> --- O padrão para o NK e o NP do script do qsub são: NP = 64 e NK = 4.
> --- Assim para criar uma unidade de simulação [de carga] usando o modo "Padrão", o usuário só precisa informar:
> nome da pasta e SCF base.

(O texto da ideia diz "cálculo de PDOS" na última linha; é a seção de carga, lida como tal.)

## Situação atual

- **Tipos de "Criar cálculo":** `scf`, `relax`, `vc-relax`, `bandas`, `pdos` (`core/calc_create/types/__init__.py:26`).
  `dos.x`, cargas e ELF ficaram fora da v1 (spec 25, "Fora de escopo"); o registro foi feito para acrescentá-los.
- **Referência do cluster:** `Documentation/Referencia_de_scripts_QSUB/cargas.qsub` declara
  `PPCOMMAND="/opt/espresso-7.1/bin/pp.x"`, cria a pasta da saída (`mkdir -p cdd_xsf`), roda os `pw.x` com
  `${MPICOMMAND} ${PWCOMMAND}` e os `pp.x` **sem MPI** (`${PPCOMMAND} -i pp_X_charge.in > pp_X_charge.out`). O
  `pp.x` não cria a pasta de `fileout`: sem o `mkdir`, a escrita do `.xsf` falha.
- **Base dos scripts:** `qsub/_base.qsub.j2` tem os blocos `programs`, `body`, `post`; cada tipo estende com seus
  comandos (spec 25 R2). Depois da spec 28, os nomes de input entram como variáveis.
- **Lint e inputs do `pp.x`:** `core/qe/pw_input.py:21-26` (`PROGRAM_NAMELISTS`) conhece `pw`, `bands`, `projwfc`,
  `dos`; `&INPUTPP` e `&PLOT` não pertencem a nenhum. `input_lint` (`core/qe/input_lint.py:169-191`) usa esse mapa
  para "namelist desconhecida": um input do `pp.x` aberto no visualizador (spec 11) teria as duas namelists marcadas.
  `core/sniff.py:looks_like_input` (`:98-119`) aceita qualquer arquivo com `&nome`, exceto o `filband`
  (`bands_x._PLOT_HEADER = &plot nbnd= …, nks= … /`, `bands_x.py:118`), que um `&PLOT` do `pp.x` não casa.
- **Detecção:** não há módulo para saídas do `pp.x` nem para `.xsf`. Uma pasta de carga com `scf_<prefix>.out` recebe
  o badge informativo de SCF (módulos `fallback`).

## Requisitos

### R1: Tipo "Carga"
1. `core/calc_create/types/charge.py:ChargeType` registrado em `REGISTRY` depois de PDOS: `id = "charge"`, rótulo
   "Carga", `folder_prefix = "Charge"`, script `charge.qsub`.
2. Arquivos, na ordem das abas: `charge.qsub`, `scf_<prefix>.in` (cópia do SCF com as regras de R2 da spec 28),
   `pp_<nome>_charge.in`, onde `<nome>` é o nome da pasta digitado na Etapa 1; sem nome, `pp_charge.in`.
3. O `prefix` do SCF base vale em tudo (`<prefix>` abaixo); `outdir = './tmp/'` (spec 28 R2.1).

### R2: Template `qe/charge/pp_charge.in.j2`
1. Reproduz o template da ideia, com vírgulas e ordem iguais:
   `&INPUTPP prefix, outdir, filplot = '<prefix>.charge', plot_num = 0 /` e
   `&PLOT nfile = 1, filepp(1) = '<prefix>.charge', weight(1) = 1.0, iflag = 3, output_format = 5,
   fileout = 'cdd_xsf/<prefix>_charge.xsf' /`.
2. Variáveis: `prefix`, `outdir`, `filplot`, `plot_num`, `iflag`, `output_format`, `fileout` (as três últimas para o
   Avançado). `StrictUndefined` como os demais.
3. O template é reutilizável: a spec 30 o renderiza uma vez por SCF (`<prefix>`, `<prefix>_clean`,
   `<prefix>_isolated`).

### R3: Script `qsub/charge.qsub.j2`
1. Estende `_base.qsub.j2`; bloco `programs` com `PPCOMMAND="{{ qe_bin }}/pp.x"`.
2. Corpo, na ordem: `mkdir -p cdd_xsf`; `${MPICOMMAND} ${PWCOMMAND} -i "scf_<prefix>.in" > "scf_<prefix>.out"`;
   `${PPCOMMAND} -i "pp_<nome>_charge.in" > "pp_<nome>_charge.out"` (sem MPI, como `cargas.qsub`).
3. A pasta de `fileout` usada no `mkdir` vem do valor de `fileout` (`cdd_xsf` no padrão): se o Avançado mudar o
   `fileout` para outra subpasta, o `mkdir` acompanha; `fileout` sem pasta → sem `mkdir`.

### R4: Campos
1. **Padrão:** nenhum além da Etapa 1 (nome da pasta e SCF base); NP = `jobs.cores`, NK = `jobs.nk` (spec 28).
2. **Avançado** (aba de `pp_…_charge.in`): `plot_num` (int, 0), `iflag` (choice 0–4, 3), `output_format` (choice,
   5 = XSF; os códigos do `INPUT_PP` do QE 7.1 com rótulo), `fileout` (texto, `cdd_xsf/<prefix>_charge.xsf`), além de
   "Nome do arquivo" (spec 28 R4) e dos campos do script.
3. Validação: `fileout` relativo e dentro da pasta (sem `..`, sem `/` inicial: pasta autossuficiente);
   `output_format` coerente com `iflag` (ex.: XSF 3D exige `iflag = 3`); erro bloqueia "Criar".

### R5: Inputs do `pp.x` no Lain
1. `PROGRAM_NAMELISTS` ganha `"pp": frozenset({"inputpp", "plot"})`; `deduce_program` reconhece o `pp.x` pela
   `&INPUTPP` (a `&PLOT` sozinha é ambígua com o `filband` e não decide nada).
2. O visualizador de input (spec 11) abre `pp_*.in` sem marcar `&INPUTPP`/`&PLOT` como desconhecidas; o realce é o de
   sempre. `looks_like_input` continua verdadeiro para eles e falso para o `filband` (teste dos dois).
3. Nada de detecção ou gráfico novo: a pasta mostra o badge de SCF quando a saída existe.

## Fora de escopo
- Visualizar a densidade (`.xsf`, isosuperfícies) ou detectar saídas do `pp.x` como tipo próprio.
- ELF (`pp_elf_3d.qsub`), potencial e outros `plot_num` com campos próprios: entram como tipos novos depois.
- Diferença de carga: spec 30.

## Decisões assumidas (confirmar na revisão)
1. `<nome>` do `pp_<nome>_charge.in` é o nome digitado para a pasta (não o `prefix`); sem nome, `pp_charge.in`.
2. O `pp.x` roda sem MPI, como em `cargas.qsub`.
3. O `pw.x` do SCF roda dentro da pasta de carga (a pasta é autossuficiente: não reaproveita o `tmp/` de outro SCF).
4. `iflag`, `output_format` e `fileout` só no Avançado; o Padrão é exatamente o template da ideia.

## Notas de implementação
- Novos: `core/calc_create/types/charge.py`, `resources/templates/qe/charge/pp_charge.in.j2`,
  `resources/templates/qsub/charge.qsub.j2`.
- Alterados: `core/calc_create/types/__init__.py` (registro), `core/qe/pw_input.py` (`PROGRAM_NAMELISTS`,
  `deduce_program`), testes de tipos, templates, lint (`test_input_lint*`/`test_properties.py` se o lexer for
  tocado) e `test_calc_roundtrip.py` (pasta `Charge_*` com a saída SCF de uma fixture → badge SCF).
- A janela não muda: tipo, abas e campos vêm do registro (spec 26) e do modo (spec 28).

## Critérios de aceite e testes
- [ ] Registro: "Carga" no combo de tipos; `ChargeType.plan` com prefix `Al` e nome `Al` → `charge.qsub`,
      `scf_Al.in`, `pp_Al_charge.in`; sem nome → pasta `Charge` e `pp_charge.in`.
- [ ] Template: render do Padrão igual, linha a linha, ao da ideia (com `prefix = 'Al'`); falta de variável levanta.
- [ ] Script: `mkdir -p cdd_xsf` antes do `pw.x`; `pp.x` sem `${MPICOMMAND}`; nomes de R3.2; `fileout` em outra
      pasta muda o `mkdir`.
- [ ] Avançado: `fileout` com `..` ou absoluto → erro; `iflag`/`output_format` incoerentes → erro.
- [ ] Lint: `pp_Al_charge.in` sem issues; uma `&INPUTPP` com erro de escrita continua marcada; `looks_like_input`
      verdadeiro para o input do `pp.x` e falso para um `filband`.
- [ ] Ida e volta: pasta `Charge_Al` com `scf_Al.out` de fixture recebe o badge SCF.
