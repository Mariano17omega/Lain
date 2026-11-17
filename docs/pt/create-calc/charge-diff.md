# Diferença de carga

Três SCFs e `pp.x` calculando Δρ = ρ(base) − ρ(clean) − ρ(isolated) ou, com `nspin = 2`,
Δm = m(base) − m(clean) − m(isolated), com m = ρ↑ − ρ↓.

- **Arquivos**: o SCF base, `scf_<p>_clean.in` (sem os átomos escolhidos), `scf_<p>_isolated.in` (só esses átomos),
  um `pp.x` por densidade e `pp_charge_diff.in`, que subtrai. Os três SCFs compartilham célula, cutoffs e malha.
- **Campos**: a aba **Átomos** (átomos do fragmento isolado) é o essencial; no Avançado, a grandeza (`plot_num`
  0 ou 6), o formato dos `.xsf` e a pasta. Com 6, os dados se chamam `<p>.spin`, `<p>_spin_diff.xsf`…, e um SCF
  sem `nspin = 2` bloqueia "Criar" (o `pp.x` escreveria só zeros).
- **Script**: os três SCFs com MPI e os mesmos pools, depois os quatro `pp.x`.
- Um `disk_io` `minimal` ou `none` é tirado dos três SCFs, com um aviso por arquivo: o `pp.x` lê as densidades de
  carga, que esses valores não gravam.

Código: `core/calc_create/types/charge_diff.py`, `core/calc_create/fragments.py`;
templates `qe/charge_diff/pp_charge_diff.in.j2`, `qsub/charge_diff.qsub.j2`.
