# Carga

SCF e `pp.x` escrevendo a densidade de carga em XSF (para ver no XCrySDen).

- **Arquivos**: `charge.qsub`, cópia do SCF, `pp_<nome>_charge.in` (`<nome>` = nome da pasta digitado na etapa 1).
- **Padrão**: só o nome e o SCF. **Avançado**: `plot_num` (0 = densidade eletrônica), `iflag` (0–4; padrão 3 = grade
  3D), `output_format` (padrão 5 = XSF) e `fileout`, na pasta `cdd_xsf/`.
- O script cria a pasta de `fileout` (o `pp.x` não cria) e roda o `pp.x` sem MPI.

Código: `core/calc_create/types/charge.py`; templates `qe/charge/pp_charge.in.j2`, `qsub/charge.qsub.j2`.
