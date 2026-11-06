# Adsorption energy

With **two or more** SCF outputs selected, the context menu offers **Calcular adsorção…** (compute adsorption).

1. The window lists each output's final total energy by its `prefix` (most atoms first).
2. The equation is editable and pre-filled as `E_ads = E(complexo) - E(substrato) - E(adsorvato)`; buttons insert
   `E(<prefix>)`. `+ - * /`, parentheses and numbers are accepted.
3. The result shows in Ry and eV as you type.
4. **Salvar resultado** writes `energia_ads_<prefixes>.md` beside the outputs (never overwrites).

To generate the calculations that feed this window, use **Criar cálculo ▸ Energia de adsorção**
([guide](../create-calc/adsorption-energy.md)).

Code: `core/analysis/adsorption_energy.py`, `core/analysis/expression.py` (safe evaluator),
`ui/dialogs/adsorption_energy.py`, `ui/tools/adsorption_energy_controller.py`.
