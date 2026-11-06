"""Sums over results already computed (spec 78.5), without Qt.

- ``adsorption_energy``: the final energies of SCF outputs and the user's equation over them
  ("Calcular adsorção…", spec 78).
- ``expression``: the evaluator of that equation, over a whitelist of the AST (never ``eval``).
"""
