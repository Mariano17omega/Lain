"""The "Criar cálculo" side of the L-04, L-05, L-07, L-10 and L-14 fixes of the Lain × QE checklist
(``Documentation/QE-73/07-lain-checklist.md``): what the plans warn about, edit or leave empty.

The reading side of the same items lives next to what it reads (``test_bands_x.py``,
``test_projwfc.py``, ``test_pdos_spin.py``, ``test_input_lint.py``).
"""

import dataclasses

import pytest

from qe_studio.core.calc_create.kpath import KPath, KPoint, repeated_points
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.calc_create.types.bandas import CONSTRAINED_NOTE, constrained_magnetization
from qe_studio.core.calc_create.types.pdos import TETRA_OPT_DEGAUSS
from qe_studio.core.qe.input_edit import InputEditor

from calc_helpers import AL_PATH, AL_SCF, JOBS, NI_SCF, al, from_text, ni


def plan(type_id, scf=None, mode="avancado", jobs=JOBS, **values):
    return by_id(type_id).plan(scf or al(), {"kpath": AL_PATH, **values}, jobs, mode)


def with_nk(nk: int):
    return JOBS.model_copy(update={"nk": nk})


def al_with(old: str, new: str):
    text = AL_SCF.read_text()
    assert old in text, old
    return from_text(text.replace(old, new))


def key_of(result, file_key: str, namelist: str, key: str):
    return InputEditor.from_text(result.by_key(file_key).text).get(namelist, key)


# -- L-04: bands.x refuses a constrained magnetization ---------------------------------------------
def test_l04_a_scf_with_tot_magnetization_gets_the_note():
    scf = ni()
    assert not constrained_magnetization(scf)
    constrained = from_text(
        NI_SCF.read_text().replace("nspin= 2,", "nspin= 2,\n tot_magnetization= 1,")
    )
    assert constrained_magnetization(constrained)
    assert CONSTRAINED_NOTE in plan("bandas", constrained).notes
    assert CONSTRAINED_NOTE not in plan("bandas", scf).notes


def test_l04_the_unset_value_of_pw_x_is_no_constraint():
    scf = from_text(
        NI_SCF.read_text().replace("nspin= 2,", "nspin= 2,\n tot_magnetization= -10000,")
    )
    assert not constrained_magnetization(scf)


def test_l04_the_note_changes_no_file():
    constrained = from_text(
        NI_SCF.read_text().replace("nspin= 2,", "nspin= 2,\n tot_magnetization= 1,")
    )
    result = plan("bandas", constrained)
    assert key_of(result, "bands", "system", "tot_magnetization") == "1"
    assert key_of(result, "scf", "system", "tot_magnetization") == "1"


# -- L-05: two equal consecutive k-points leave bands.x with an empty .gnu -------------------------
def path_with_repeat(breaks=frozenset()):
    gamma = KPoint("Gamma", (0.0, 0.0, 0.0), 10)
    x = KPoint("X", (-0.5, 0.0, -0.5), 10)
    return KPath((gamma, x, dataclasses.replace(x, label="X2"), gamma), breaks)


def test_l05_repeated_points_are_found_also_across_a_break():
    assert repeated_points(path_with_repeat()) == [1]
    assert repeated_points(path_with_repeat(frozenset({1}))) == [1]
    assert repeated_points(AL_PATH) == []


def test_l05_a_repeated_vertex_gets_a_note_in_the_plan():
    result = plan("bandas", kpath=path_with_repeat())
    notes = [note for note in result.notes if "são iguais" in note]
    assert len(notes) == 1 and "X" in notes[0] and "X2" in notes[0]
    assert not [note for note in plan("bandas").notes if "são iguais" in note]


# -- L-07: K_POINTS gamma cannot go with -nk > 1 ----------------------------------------------------
def gamma_scf(card: str = "K_POINTS gamma\n"):
    return al_with("K_POINTS automatic\n10 10 10 0 0 0", card.rstrip("\n"))


@pytest.mark.parametrize("type_id", ["scf", "relax", "vc-relax"])
def test_l07_gamma_with_pools_is_noted(type_id):
    result = plan(type_id, gamma_scf(), jobs=with_nk(2))
    notes = [note for note in result.notes if "Gamma-only" in note]
    assert len(notes) == 1 and f"{type_id}_al.in" in notes[0] and "nk = 2" in notes[0]


def test_l07_a_missing_card_is_gamma_too():
    scf = al_with("K_POINTS automatic\n10 10 10 0 0 0", "")
    assert any("Gamma-only" in note for note in plan("scf", scf, jobs=with_nk(2)).notes)


def test_l07_one_pool_or_a_mesh_has_no_note():
    assert not [n for n in plan("scf", gamma_scf(), jobs=with_nk(1)).notes if "Gamma-only" in n]
    assert not [n for n in plan("scf", jobs=with_nk(4)).notes if "Gamma-only" in n]


def test_l07_the_pools_of_the_form_count():
    result = plan("scf", gamma_scf(), jobs=with_nk(1), nk=2)
    assert any("Gamma-only" in note for note in result.notes)


# -- L-10: the energy window of projwfc.x -----------------------------------------------------------
def projwfc_of(result):
    return InputEditor.from_text(result.by_key("projwfc").text)


def test_l10_the_window_is_empty_by_default_and_not_written():
    fields = {f.id: f for f in by_id("pdos").fields(al(), JOBS)}
    assert fields["e_min"].default is None and fields["e_max"].default is None
    assert fields["e_min"].standard and fields["e_max"].standard
    assert fields["e_min"].hint == fields["e_max"].hint == "vazio = toda a faixa das bandas"
    projwfc = projwfc_of(plan("pdos"))
    assert projwfc.get("projwfc", "Emin") is None and projwfc.get("projwfc", "Emax") is None


def test_l10_a_typed_window_is_written_alone_or_together():
    only_max = projwfc_of(plan("pdos", e_max=40))
    assert only_max.get("projwfc", "Emin") is None and only_max.get("projwfc", "Emax") == "40.0"
    both = projwfc_of(plan("pdos", e_min=-60, e_max=40))
    assert (both.get("projwfc", "Emin"), both.get("projwfc", "Emax")) == ("-60.0", "40.0")


def test_l10_an_inverted_window_is_still_an_error():
    assert "Emin deve ser menor que Emax" in plan("pdos", e_min=5, e_max=-5).errors
    assert plan("pdos", e_min=5).ok


def test_l10_the_broadening_tooltips_say_they_replace_the_smearing_of_pw_x():
    tips = {f.id: f.tooltip for f in by_id("pdos").fields(al(), JOBS)}
    assert "substitui o smearing do pw.x" in tips["degauss"]
    assert "substitui" in tips["ngauss"]


def test_l10_tetrahedra_opt_with_a_degauss_by_hand_is_an_error():
    calc = by_id("pdos")
    result = plan("pdos", occupations="tetrahedra_opt")
    assert TETRA_OPT_DEGAUSS not in result.errors  # the form never writes the pair
    nscf, projwfc = result.by_key("nscf"), result.by_key("projwfc")
    edited = dataclasses.replace(projwfc, text=projwfc.text.replace("\n/", "\n  degauss = 0.01\n/"))
    assert calc.text_errors([nscf, edited]) == [TETRA_OPT_DEGAUSS]
    assert calc.text_errors([nscf, projwfc]) == []
    linear = plan("pdos", occupations="tetrahedra").by_key("nscf")
    assert calc.text_errors([linear, edited]) == []  # only the optimized method is stuck


# -- L-14: a disk_io that leaves no data for bands.x / projwfc.x -------------------------------------
def with_disk_io(value: str):
    return al_with("prefix='al',", f"prefix='al',\n    disk_io='{value}',")


@pytest.mark.parametrize("type_id, derived", [("bandas", "bands"), ("pdos", "nscf")])
@pytest.mark.parametrize("value", ["nowf", "minimal", "none"])
def test_l14_the_derived_run_never_keeps_a_disk_io_without_wavefunctions(type_id, derived, value):
    result = plan(type_id, with_disk_io(value))
    assert key_of(result, derived, "control", "disk_io") is None
    assert any(f"disk_io = '{value}' removido" in note for note in result.notes)


@pytest.mark.parametrize("type_id", ["bandas", "pdos"])
@pytest.mark.parametrize(
    "value, kept", [("nowf", True), ("minimal", False), ("none", False), ("high", True)]
)
def test_l14_the_scf_keeps_what_the_next_run_can_start_from(type_id, value, kept):
    """``nowf`` saves the charge density, so the SCF may keep it; ``minimal`` and ``none`` do not."""
    result = plan(type_id, with_disk_io(value))
    assert (key_of(result, "scf", "control", "disk_io") == value) is kept


@pytest.mark.parametrize("type_id, derived", [("bandas", "bands"), ("pdos", "nscf")])
@pytest.mark.parametrize("value", ["low", "medium", "high"])
def test_l14_a_sound_disk_io_stays_as_typed(type_id, derived, value):
    result = plan(type_id, with_disk_io(value))
    assert key_of(result, derived, "control", "disk_io") == value
    assert key_of(result, "scf", "control", "disk_io") == value
    assert not [note for note in result.notes if "disk_io" in note]


def test_l14_a_scf_without_disk_io_is_untouched():
    result = plan("bandas")
    assert key_of(result, "bands", "control", "disk_io") is None
    assert not [note for note in result.notes if "disk_io" in note]


def test_l14_the_quote_and_case_of_the_value_do_not_matter():
    scf = al_with("prefix='al',", "prefix='al',\n    disk_io = \"NoWF\",")
    assert key_of(plan("pdos", scf), "nscf", "control", "disk_io") is None
