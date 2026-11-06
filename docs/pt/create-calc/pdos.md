# PDOS

SCF, NSCF numa malha e `projwfc.x`.

- **Arquivos**: SCF, NSCF, `projwfc.in`, `pdos.qsub`.
- **Campos** (Padrão: só `Emin`/`Emax`, padrão −25/25 eV absolutos): malha do NSCF (a do SCF quando automática),
  `occupations` (`tetrahedra` por padrão; também `smearing`, `tetrahedra_opt`, `tetrahedra_lin`, `fixed`), `DeltaE`
  (0,01), `ngauss`/`degauss` (0 e 0,000735 Ry ≈ 0,01 eV; omitidos com tetraedros, senão desligariam o método).
  `nbnd` acompanha o SCF — acima da última banda a DOS é zero, então aumente `nbnd` ou reduza `Emax`.
- **Script**: pw.x SCF → pw.x NSCF → `projwfc.x`; no fim `mkdir -p orbitals && mv *pdos_atm#* orbitals/` (o glob não
  move `projwfc.in/out`) e o status do `projwfc.x` é preservado para o e-mail.
- O resultado é detectado como `PDOS` — veja [PDOS](../plots/pdos.md).

Código: `core/calc_create/types/pdos.py`; templates `qe/pdos/projwfc.in.j2`, `qsub/pdos.qsub.j2`.
