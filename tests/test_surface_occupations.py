"""Spec 96: the occupations of the adsorbed system in "Molécula na superfície". The most permissive of
the two SCFs wins (``smearing`` in either gives ``smearing``), with the surface's broadening when it
has one, and a note when the two differ. The user's SCFs are edited in memory, never in ``fixtures/``."""

from __future__ import annotations

import pytest

from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.merge import merge_namelists
from qe_studio.core.calc_create.surface.occupations import (
    NO_DEGAUSS,
    SAME_OCCUPATIONS,
    merge_occupations,
)
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.qe.pw_input import fortran_float

from calc_helpers import JOBS, from_text
from surface_helpers import MOLECULE, SUPERCELL_001

# The surface's SCF is ``fixed`` without smearing; the molecule's is smearing, ``gauss``, 0.01.
METAL = {"occupations": "'smearing'", "smearing": "'mv'", "degauss": "0.02"}
FIXED = {"occupations": "'fixed'", "smearing": None, "degauss": None}


def edited(text: str, system: dict[str, str | None]) -> InputEditor:
    """``text`` with the ``&SYSTEM`` keys of ``system`` written as given (None: left out)."""
    editor = InputEditor.from_text(text)
    for key, value in system.items():
        if value is None:
            editor.remove("system", key)
        else:
            editor.set("system", key, value)
    return editor


def surface(**system: str | None) -> InputEditor:
    return edited(SUPERCELL_001.read_text(), system)


def molecule(**system: str | None) -> ScfInfo:
    return from_text(edited(MOLECULE.read_text(), system).text(), "scf-H3CHg.in")


def occupations(editor: InputEditor) -> tuple[str | None, str | None, float | None]:
    degauss = editor.get("system", "degauss")
    return (
        editor.get("system", "occupations"),
        editor.get("system", "smearing"),
        fortran_float(degauss) if degauss is not None else None,
    )


def kept(key: str, mine: str, theirs: str) -> str:
    return f"{key}: superfície '{mine}', molécula '{theirs}'; vale o da superfície"


def taken(mine: str) -> str:
    return (
        f"occupations: superfície '{mine}', molécula 'smearing'; "
        "valem o occupations, o smearing e o degauss da molécula"
    )


def test_a_metallic_surface_keeps_its_smearing():
    editor = surface(**METAL)
    notes = merge_namelists(editor, molecule(**FIXED))
    assert occupations(editor) == ("smearing", "mv", 0.02)
    assert notes == [kept("occupations", "smearing", "fixed"), SAME_OCCUPATIONS]


def test_the_surfaces_degauss_wins():
    editor = surface(**METAL)
    notes = merge_namelists(editor, molecule(degauss="0.001"))
    assert occupations(editor) == ("smearing", "mv", 0.02)
    assert notes == [
        kept("smearing", "mv", "gauss"),
        "degauss: molécula 0.001 Ry, superfície 0.02 Ry; vale o da superfície",
        SAME_OCCUPATIONS,
    ]


def test_a_spin_polarized_surface_keeps_its_smearing():
    """``fixed`` with ``nspin = 2`` and no ``tot_magnetization``: pw.x would stop (setup.f90:312-318)."""
    editor = surface(nspin="2", **METAL)
    merge_namelists(editor, molecule(**FIXED))
    assert occupations(editor) == ("smearing", "mv", 0.02)
    assert editor.get("system", "nspin") == "2"
    assert editor.get("system", "tot_magnetization") is None


def test_tetrahedra_never_come_from_the_molecule():
    editor = surface(**METAL)
    notes = merge_namelists(editor, molecule(occupations="'tetrahedra'"))
    assert occupations(editor) == ("smearing", "mv", 0.02)
    assert notes == [kept("occupations", "smearing", "tetrahedra"), SAME_OCCUPATIONS]


@pytest.mark.parametrize(
    ("written", "shown"),
    [("'fixed'", "fixed"), (None, "fixed"), ("'tetrahedra_opt'", "tetrahedra_opt")],
)
def test_an_insulating_surface_takes_the_molecules_smearing(written, shown):
    editor = surface(occupations=written)
    notes = merge_namelists(editor, molecule())
    assert occupations(editor) == ("smearing", "gauss", 0.01)
    assert notes == [taken(shown), SAME_OCCUPATIONS]


def test_a_stray_smearing_of_the_surface_goes():
    """The molecule's smearing without ``smearing`` is pw.x's ``gaussian``, not the surface's ``mv``."""
    editor = surface(occupations="'fixed'", smearing="'mv'", degauss="0.05")
    notes = merge_namelists(editor, molecule(smearing=None, degauss="0.01"))
    assert occupations(editor) == ("smearing", None, 0.01)
    assert notes == [taken("fixed"), SAME_OCCUPATIONS]


def test_smearing_without_degauss_is_noted():
    editor = surface()
    notes = merge_namelists(editor, molecule(degauss=None))
    assert occupations(editor) == ("smearing", "gauss", None)
    assert notes == [taken("fixed"), SAME_OCCUPATIONS, NO_DEGAUSS]
    editor = surface(occupations="'smearing'", smearing="'mv'", degauss="0")  # pw.x wants > 0
    notes = merge_namelists(editor, molecule(**FIXED))
    assert occupations(editor) == ("smearing", "mv", 0.0)
    assert notes == [kept("occupations", "smearing", "fixed"), SAME_OCCUPATIONS, NO_DEGAUSS]


@pytest.mark.parametrize(
    ("smearing", "shown", "expected"), [("'gauss'", "gauss", "gauss"), (None, "gaussian", None)]
)
def test_a_surface_without_degauss_takes_the_molecules_pair(smearing, shown, expected):
    """Decided on 11/11/2026: the type of smearing follows the side its ``degauss`` comes from."""
    editor = surface(occupations="'smearing'", smearing="'mv'", degauss=None)
    notes = merge_namelists(editor, molecule(smearing=smearing))
    assert occupations(editor) == ("smearing", expected, 0.01)
    assert notes == [
        "degauss: a superfície não tem; valem o smearing e o degauss da molécula "
        f"('{shown}', 0.01 Ry)",
        SAME_OCCUPATIONS,
    ]


@pytest.mark.parametrize(
    ("mine", "theirs"),
    [
        (
            {"occupations": "'smearing'", "smearing": "'gaussian'", "degauss": "0.02"},
            {"smearing": "'gauss'", "degauss": "2.0d-2"},
        ),
        ({"occupations": "'fixed'"}, {"occupations": None}),
        ({"occupations": None}, {"occupations": "'FIXED'"}),
        ({"occupations": "'Smearing'", "smearing": "'gauss'", "degauss": "0.01"}, {}),
        ({"occupations": "'tetrahedra-opt'"}, {"occupations": "'tetrahedra_opt'"}),
    ],
)
def test_the_same_scheme_gives_no_note(mine, theirs):
    editor = surface(**mine)
    before = editor.text()
    assert merge_occupations(editor, molecule(**theirs)) == []
    assert editor.text() == before


def test_merge_namelists_uses_the_rule():
    """The real path: the plan of the type on a metallic surface with a ``fixed`` molecule."""
    scf = from_text(surface(**METAL).text(), "scf.in")
    values = {"molecule": molecule(**FIXED), "site": (43,), "remove_h": True}
    result = by_id("adsorption").plan(scf, values, JOBS, "avancado")  # type: ignore[arg-type]
    assert result.errors == ()
    text = result.by_key("relax").text
    assert occupations(InputEditor.from_text(text)) == ("smearing", "mv", 0.02)
    assert kept("occupations", "smearing", "fixed") in result.notes
    assert SAME_OCCUPATIONS in result.notes
    assert NO_DEGAUSS not in result.notes
    assert [i for i in lint(text).issues if i.severity == "error"] == []
