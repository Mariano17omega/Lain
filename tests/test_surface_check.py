"""Spec 42 R1: a type that puts a molecule on a surface refuses a bulk's SCF, and a surface whose vacuum
is not along c, with the reason."""

from __future__ import annotations

from qe_studio.core.calc_create.surface.geometry import surface_problem
from qe_studio.core.calc_create.surface.model import model_of
from qe_studio.core.calc_create.types import by_id

from calc_helpers import from_text
from surface_helpers import BULK, MOLECULE, SLAB_001, SLAB_010, SUPERCELL_001, read, with_structure

BULK_TEXT = (
    "scf-kaolinite.in parece o SCF de um bulk: não há vácuo ao longo de c (maior intervalo vazio: "
    "1,85 Å). Escolha o SCF de uma superfície relaxada (Slab ou Supercélula)."
)


def test_a_bulk_is_refused_with_its_widest_gap():
    scf = read(BULK)
    assert surface_problem(scf, scf.name) == BULK_TEXT
    assert by_id("adsorption").check_scf(scf) == BULK_TEXT


def test_the_surfaces_pass():
    for path in (SLAB_001, SLAB_010, SUPERCELL_001):
        scf = read(path)
        assert surface_problem(scf, scf.name) is None, path.name
        assert by_id("adsorption").check_scf(scf) is None


def test_a_vacuum_along_b_is_said():
    model = model_of(read(SUPERCELL_001))
    swapped = model.replace(cell=model.cell[[0, 2, 1]], frac=model.frac[:, [0, 2, 1]])
    scf = with_structure(SUPERCELL_001, swapped)
    assert surface_problem(scf, "slab.in") == (
        "O vácuo de slab.in está ao longo de b; o Lain espera a superfície com o vácuo ao longo de "
        "c, como o Slab gera."
    )


def test_an_unreadable_structure_says_why():
    text = read(SUPERCELL_001).text.replace("CELL_PARAMETERS angstrom", "CELL_PARAMETERS nada")
    scf = from_text(text, "torto.in")
    assert scf.crystal is None
    assert surface_problem(scf, "torto.in").startswith("Estrutura de torto.in ilegível: ")


def test_the_other_types_refuse_nothing():
    """The hook's default: today's types and the molecule's box (vacuum everywhere) go on."""
    from qe_studio.core.calc_create.types import REGISTRY

    bulk = read(BULK)
    assert [t.id for t in REGISTRY if t.check_scf(bulk) is not None] == ["adsorption"]
    assert by_id("adsorption").check_scf(read(MOLECULE)) is None
