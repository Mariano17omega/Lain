# SCF

Gera o SCF numa pasta própria a partir do SCF de origem (útil para reaproveitar estrutura com outro `outdir`,
pseudopotenciais ou malha).

- **Arquivos**: `scf_<prefix>.in`, `scf.qsub`.
- **Campo**: malha k (`kmesh`, opcional; sem valor mantém a do SCF).
- **Script**: uma linha `mpiexec pw.x -nk $NK -i scf_<prefix>.in > scf_<prefix>.out`.
- `outdir = './tmp/'` e `pseudo_dir` de `jobs.pseudo_dir`, se definido.

Código: `core/calc_create/types/scf.py`; template `resources/templates/qsub/scf.qsub.j2`.
