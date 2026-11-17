# Carga

SCF e `pp.x` escrevendo a densidade de carga em XSF (para ver no XCrySDen).

- **Arquivos**: `charge.qsub`, cópia do SCF, `pp_<nome>_charge.in` (`<nome>` = nome da pasta digitado na etapa 1).
- **Padrão**: só o nome e o SCF. **Avançado**: `plot_num` (0 = densidade eletrônica; 6 = polarização de spin, só
  com `nspin = 2`), `iflag` (0–4; padrão 3 = grade 3D), `output_format` (padrão 5 = XSF; aparece só com `iflag` 2
  ou 3) e `fileout`, na pasta `cdd_xsf/`. O tooltip do `plot_num` lembra que, com PAW, 0 e 6 são pseudo-densidades
  (a all-electron é 17 ou 21).
- O script cria a pasta de `fileout` (o `pp.x` não cria) e roda o `pp.x` sem MPI.
- Um `disk_io` `minimal` ou `none` é tirado do SCF, com aviso: o `pp.x` lê a densidade de carga, que esses valores
  não gravam.

Código: `core/calc_create/types/charge.py`; templates `qe/charge/pp_charge.in.j2`, `qsub/charge.qsub.j2`.
