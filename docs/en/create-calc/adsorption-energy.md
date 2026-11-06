# Adsorption energy (a Create-calculation type)

Gathers **already prepared SCFs** (the complex, the clean surface, the isolated molecule…) in one folder and runs them
one after the other with a single script.

- **Step 1** takes a **list** of two or more SCFs. Each becomes `scf_<prefix>.in`, copied as it is — only
  `outdir = './tmp/'` and `jobs.pseudo_dir` change — in list order. Repeated names get `_2`, `_3`…
- **Script**: `ads_energy.qsub` runs the SCFs in order.
- **Block**: two SCFs with the same `prefix` block **Criar** (they would share `<prefix>.EXIT` and `<prefix>.save`);
  change the `prefix` by hand in Advanced mode.
- The energies and the equation are computed later, in the [Calcular adsorção…](../features/adsorption-energy.md)
  window.

Code: `core/calc_create/types/ads_energy.py`.
