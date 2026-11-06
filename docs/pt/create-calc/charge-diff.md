# Diferença de carga

Três SCFs e `pp.x` calculando Δρ = ρ(base) − ρ(clean) − ρ(isolated).

- **Arquivos**: o SCF base, `scf_<p>_clean.in` (sem os átomos escolhidos), `scf_<p>_isolated.in` (só esses átomos),
  um `pp.x` por densidade e `pp_charge_diff.in`, que subtrai. Os três SCFs compartilham célula, cutoffs e malha.
- **Campos**: a aba **Átomos** (átomos do fragmento isolado) é o essencial; no Avançado, formato dos `.xsf` e a pasta.
- **Script**: os três SCFs com MPI e os mesmos pools, depois os quatro `pp.x`.

Código: `core/calc_create/types/charge_diff.py`, `core/calc_create/fragments.py`;
templates `qe/charge_diff/pp_charge_diff.in.j2`, `qsub/charge_diff.qsub.j2`.
