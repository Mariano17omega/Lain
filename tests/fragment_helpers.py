"""Inputs for the fragment tests (spec 30): a small iron / oxygen / hydrogen SCF with spin, a
Hubbard card, comments and ``if_pos`` flags, and the kaolinite slab of the fixtures as an SCF."""

from __future__ import annotations

import difflib

from qe_studio.core.qe.input_lint import lint

from conftest import FIXTURES

# Atoms 1-2 are Fe, 3-4 O, 5-6 H; species 1 Fe, 2 O, 3 H.
SMALL = """&control
  calculation = 'scf'
  prefix = 'ilita'
  pseudo_dir = '/pseudo'
  outdir = './tmp'
/
&system
  ibrav = 0
  nat = 6
  ntyp = 3
  ecutwfc = 40
  ecutrho = 320
  nspin = 2
  nbnd = 40
  starting_magnetization(1) = 0.5
  starting_magnetization(2) = 0.0
  Starting_Magnetization(3) = 0.2
  starting_ns_eigenvalue(1,1,3) = 0.1
  lda_plus_u = .true.
/
&electrons
  conv_thr = 1d-8
/
ATOMIC_SPECIES
Fe 55.845 Fe.UPF
O 15.999 O.UPF
H 1.008 H.UPF

CELL_PARAMETERS angstrom
10 0 0
0 10 0
0 0 10

ATOMIC_POSITIONS angstrom
Fe 0 0 0  0 0 0 ! slab Fe 1
Fe 2 0 0
O 1 1 1 ! comment
! only a comment
O 3 1 1
H 1.5 1.5 1.5
H 3.5 1.5 1.5

K_POINTS automatic
2 2 1 0 0 0

HUBBARD ortho-atomic
U Fe-3d 5.0
U O-2p 1.0
V Fe-3d Fe-3d 1 2 0.2
V Fe-3d O-2p 1 3 0.5
V Fe-3d O-2p 2 4 0.3
V Fe-3d O-2p 2 9 0.1 ! an image: atom 3 of the next cell (9 = 3 + 6), as species_keys assumes
"""


def slab_scf() -> str:
    """The relaxed kaolinite slab (34 atoms: Al Si O H, ``if_pos`` on the Si and O of the layer) as
    an SCF named ``ilita``."""
    text = (FIXTURES / "kao_slab_relax" / "relax-kaolinite-slab-001.in").read_text()
    return text.replace("'relax'", "'scf'").replace("'kaolinite-slab-001'", "'ilita'")


def changes(before: str, after: str) -> tuple[list[str], list[str]]:
    """(lines only in ``before``, lines only in ``after``), blank lines left out."""
    removed, added = [], []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith("- ") and line[2:].strip():
            removed.append(line[2:])
        elif line.startswith("+ ") and line[2:].strip():
            added.append(line[2:])
    return removed, added


def lint_errors(text: str) -> list[str]:
    """What the input linter calls an error (warnings left out)."""
    return [issue.message for issue in lint(text).issues if issue.severity == "error"]
