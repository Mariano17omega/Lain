# Adsorption energy

With **two or more** SCF outputs selected, the context menu offers **Calcular adsorção…** (compute adsorption).

1. The window lists each output's final total energy by its `prefix` (most atoms first), and the level of theory read
   from its header: **Cutoffs (Ry)** (`ecutwfc/ecutrho`), **Functional** (with the dispersion correction, if any; the
   tooltip lists the pseudopotentials), **Occupations**, **Spin** and **k-point mesh** (the one of the input with the
   same name; the tooltip gives the irreducible k-points).
2. The equation is editable and pre-filled as `E_ads = E(complexo) - E(substrato) - E(adsorvato)`; buttons insert
   `E(<prefix>)`. `+ - * /`, parentheses and numbers are accepted.
3. The result shows in Ry, eV and kJ/mol as you type.
4. Below the result, **warnings** check the outputs the equation uses: cutoffs, functional (by the codes pw.x prints,
   not by its name), dispersion, the pseudopotential of each element, occupations and spin; cell, dipole correction and
   k-point mesh between the complex and the substrate; and the **atom balance** per element (Σ coefficient × atoms = 0), which
   flags, for example, the H missing after a deprotonation (add ½ E(H₂) or your reference). The warnings **never
   block**: the result and the save button stay available.
5. **Salvar resultado** writes `energia_ads_<prefixes>.md` beside the outputs (never overwrites), with the table, the
   equation, the result, the warnings and notes for review: the energy is electronic (no ZPE, no thermal
   contribution), without dispersion physisorption is underestimated, and an isolated molecule only needs Γ.

To generate the calculations that feed this window, use **Criar cálculo ▸ Energia de adsorção**
([guide](../create-calc/adsorption-energy.md)).

Code: `core/analysis/adsorption_energy.py`, `core/analysis/expression.py` (safe evaluator),
`core/analysis/level_of_theory.py`, `core/analysis/consistency.py` (warnings and notes),
`core/analysis/adsorption_report.py`, `ui/dialogs/adsorption_energy.py`, `ui/tools/adsorption_energy_controller.py`.
