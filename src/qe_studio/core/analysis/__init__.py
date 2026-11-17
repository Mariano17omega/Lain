"""Sums over results already computed (spec 78.5), without Qt.

- ``adsorption_energy``: the final energies of SCF outputs and the user's equation over them
  ("Calcular adsorção…", spec 78).
- ``level_of_theory``: what each output was computed with (cutoffs, functional, dispersion,
  pseudopotentials, occupations, spin, cell, k-points, composition), and its texts (spec 97).
- ``consistency``: the warnings when the energies of the equation are not comparable or the atoms do
  not balance, and the notes of the report (spec 97).
- ``adsorption_report``: the Markdown report of the window, never over a file.
- ``expression``: the evaluator of that equation, over a whitelist of the AST (never ``eval``).
"""
