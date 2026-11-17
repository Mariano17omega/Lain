"""The saw-like field and the dipole correction of the surface types (specs 98, 105): the ramp's
window, the fields of Slab, Supercélula and Molécula na superfície, and the inputs that keep them."""

from __future__ import annotations

import numpy as np
import pytest

from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.dipole import (
    MIN_MARGIN,
    dipole_window,
    flips_c,
    has_dipole,
    put_field,
    ramp_margin,
    remove_field,
    short_margin,
)
from qe_studio.core.calc_create.surface.fixing import NONE
from qe_studio.core.calc_create.surface.geometry import vacuum_gaps, widest_gap
from qe_studio.core.calc_create.surface.model import Model, model_of
from qe_studio.core.calc_create.surface.report import REPORT_KEY
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.calc_create.types.adsorption import SURFACE_WITH_DIPOLE, SURFACE_WITHOUT_DIPOLE
from qe_studio.core.calc_create.types.base import shown_fields
from qe_studio.core.calc_create.types.dipole_fields import (
    DIPFIELD,
    EAMP,
    EAMP_NOTE,
    EDIR,
    EDIR_NOTE,
    EDIR_PROBLEM,
    EMAXPOS,
    EOPREG,
    IDLE_NOTE,
    INSIDE_NOTE,
    INVALID_FACT,
    NEEDS_TEFIELD,
    NO_SYMMETRY,
    NOT_WRITTEN,
    ONE_SIDE,
    POLAR_NOTE,
    RANGE_PROBLEM,
    REMOVED_NOTE,
    TEFIELD,
    TSTRESS_NOTE,
    VC_STRESS_NOTE,
)
from qe_studio.core.calc_create.types.supercell import STACKED_DIPOLE
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.pw_input import fortran_float

from calc_helpers import AL_PATH, JOBS, al, from_text
from surface_helpers import BULK, MOLECULE, SLAB_001, SUPERCELL_001, model_from_plan, read

SLAB, SUPERCELL, ADSORPTION = by_id("slab"), by_id("supercell"), by_id("adsorption")
SLAB_001_EMAXPOS = 0.9455  # the middle of its vacuum, 0.9955, minus half the ramp (0.1)
KEYS = {"control": ("tefield", "dipfield"), "system": ("edir", "emaxpos", "eopreg", "eamp")}
ON = {TEFIELD: True, DIPFIELD: True}
OFF = {TEFIELD: False, DIPFIELD: False}
ALL_KEYS = "dipfield, tefield, edir, emaxpos, eopreg, eamp"
ONE_SIDED = POLAR_NOTE.format(reason=ONE_SIDE)


# -- helpers ----------------------------------------------------------------------------------------
def editor_of(result, key: str = "relax") -> InputEditor:
    return InputEditor.from_text(result.by_key(key).text)


def report(result) -> str:
    return result.by_key(REPORT_KEY).text


def written(editor: InputEditor) -> dict[str, str | None]:
    return {key: editor.get(namelist, key) for namelist, keys in KEYS.items() for key in keys}


def with_correction(scf: ScfInfo, emaxpos: float = 0.5, **extra: str) -> ScfInfo:
    """``scf`` with the correction written, its ramp at ``emaxpos``."""
    editor = InputEditor.from_text(scf.text)
    for key in KEYS["control"]:
        editor.set("control", key, ".true.")
    for key, value in (("edir", "3"), ("emaxpos", str(emaxpos)), ("eopreg", "0.1")):
        editor.set("system", key, value)
    editor.set("system", "eamp", "0.0")
    for key, value in extra.items():
        namelist, name = key.split("__")
        editor.set(namelist, name, value)
    return from_text(editor.text(), scf.name)


def ramp_distance(model: Model, emaxpos: float, eopreg: float) -> np.ndarray:
    """Each atom's distance along the normal (Å) to the ramp ``[emaxpos, emaxpos + eopreg]`` mod 1."""
    spacing = model.cell[2] @ np.cross(model.cell[0], model.cell[1])
    spacing /= np.linalg.norm(np.cross(model.cell[0], model.cell[1]))
    after = (model.frac[:, 2] - emaxpos) % 1.0  # 0 at the ramp's start
    inside = after <= eopreg
    distance = np.minimum(np.abs(after - eopreg), np.abs(1.0 - after))
    return np.where(inside, 0.0, distance * abs(spacing))


def window_of(editor: InputEditor) -> tuple[float, float]:
    emaxpos = fortran_float(editor.get("system", "emaxpos") or "")
    eopreg = fortran_float(editor.get("system", "eopreg") or "")
    assert emaxpos is not None and eopreg is not None
    return emaxpos, eopreg


def layer(*heights: float, c: float = 20.0, label: str = "Al") -> Model:
    """A square cell 3 × 3 × ``c`` Å with one atom of ``label`` at each fraction ``heights``."""
    frac = np.array([[0.0, 0.0, h] for h in heights])
    return Model(np.diag([3.0, 3.0, c]), tuple(label for _h in heights), frac)


# -- R1: the window ---------------------------------------------------------------------------------
def test_widest_gap_keeps_vacuum_gaps():
    assert widest_gap(np.array([])) == (0.0, 1.0)
    assert widest_gap(np.array([0.2, 0.9])) == pytest.approx((0.2, 0.7))
    assert widest_gap(np.array([0.1, 0.3])) == pytest.approx((0.3, 0.8))  # across the cell edge
    model = model_of(read(SLAB_001))
    assert vacuum_gaps(model.cell, model.frac)[2] == pytest.approx(15.07, abs=0.01)


def test_window_is_the_middle_of_the_vacuum():
    model = model_of(read(SLAB_001))
    window = dipole_window(model.cell, model.frac)
    assert window.emaxpos == pytest.approx(SLAB_001_EMAXPOS, abs=1e-4)
    assert window.eopreg == 0.1
    assert window.gap == pytest.approx(15.07, abs=0.01)
    assert window.margin > 6.0 and not short_margin(window)
    assert ramp_distance(model, window.emaxpos, window.eopreg).min() >= MIN_MARGIN


def test_window_off_centre():
    window = dipole_window(layer(0.1, 0.25, 0.4).cell, layer(0.1, 0.25, 0.4).frac)
    assert window.emaxpos == pytest.approx(0.70)  # the vacuum 0.4 → 1.1, its middle at 0.75
    assert window.margin == pytest.approx((0.7 - 0.1) / 2 * 20.0)


def test_short_vacuum_shrinks_the_ramp():
    model = layer(0.0, 0.2, 0.4, 0.6, 0.8, c=10.0)  # 2 Å between every pair of planes
    window = dipole_window(model.cell, model.frac)
    assert window.eopreg == pytest.approx(0.0667)  # a third of the gap, not pw.x's 0.1
    assert window.gap == pytest.approx(2.0)
    assert short_margin(window)


def test_emaxpos_is_never_zero():
    model = layer(0.5, 0.6)  # the vacuum 0.6 → 1.5: its middle 1.05, the ramp from 1.0 ≡ 0
    window = dipole_window(model.cell, model.frac)
    assert 0.0 < window.emaxpos < 1.0
    assert window.emaxpos == pytest.approx(0.0001)


def test_flips_c():
    assert flips_c(layer(0.45, 0.55).cell, layer(0.45, 0.55).frac, ("Al", "Al"))
    assert not flips_c(layer(0.45, 0.55).cell, layer(0.45, 0.55).frac, ("Al", "O"))
    kaolinite = model_of(read(SLAB_001))  # hydroxyls on one face, siloxane on the other
    assert not flips_c(kaolinite.cell, kaolinite.frac, kaolinite.labels)


def test_a_typed_window_is_kept():
    model = layer(0.4, 0.6)  # the vacuum 0.6 → 1.4: its middle at 0.0
    wide = dipole_window(model.cell, model.frac, eopreg=0.2)
    assert (wide.emaxpos, wide.eopreg) == (0.9, 0.2)  # the automatic start follows the typed width
    assert wide.margin == pytest.approx((0.8 - 0.2) / 2 * 20.0)
    moved = dipole_window(model.cell, model.frac, emaxpos=0.7)
    assert (moved.emaxpos, moved.eopreg) == (0.7, 0.1)
    assert moved.margin == pytest.approx(0.1 * 20.0)  # from 0.6 to the ramp's start
    inside = dipole_window(model.cell, model.frac, emaxpos=0.55, eopreg=0.1)
    assert inside.margin == 0.0 and short_margin(inside)
    assert ramp_margin(np.array([0.4, 0.6]), 0.95, 0.1) == pytest.approx(0.35)
    assert ramp_margin(np.array([]), 0.5, 0.1) == pytest.approx(0.45)


def test_window_along_another_axis():
    model = Model(np.diag([20.0, 3.0, 3.0]), ("Al", "Al"), np.array([[0.4, 0, 0], [0.6, 0, 0]]))
    window = dipole_window(model.cell, model.frac, axis=0)
    assert (window.emaxpos, window.eopreg) == (0.95, 0.1)
    assert window.gap == pytest.approx(16.0)


def test_put_and_remove():
    editor = InputEditor.from_text(al().text)
    model = layer(0.4, 0.6)
    assert put_field(editor, dipole_window(model.cell, model.frac)) == ()
    assert written(editor) == {
        "tefield": ".true.",
        "dipfield": ".true.",
        "edir": "3",
        "emaxpos": "0.95",
        "eopreg": "0.1",
        "eamp": "0.0",
    }
    assert has_dipole(editor.get)
    assert remove_field(editor) == ("dipfield", "tefield", "edir", "emaxpos", "eopreg", "eamp")
    assert set(written(editor).values()) == {None} and not has_dipole(editor.get)

    field = InputEditor.from_text(al().text)
    field.set("control", "dipfield", ".TRUE.")
    window = dipole_window(model.cell, model.frac)
    # the field alone: the correction's key goes, the amplitude and the direction are the caller's
    assert put_field(field, window, edir=1, eamp=0.01, dipfield=False) == ("dipfield",)
    assert written(field) == {
        "tefield": ".true.",
        "dipfield": None,
        "edir": "1",
        "emaxpos": "0.95",
        "eopreg": "0.1",
        "eamp": "0.01",
    }
    field.set("control", "dipfield", ".true.")
    assert remove_field(field, dipfield=False) == ("tefield", "edir", "emaxpos", "eopreg", "eamp")
    assert field.get("control", "dipfield") == ".true."


# -- the fields (spec 105) --------------------------------------------------------------------------
def defaults_of(calc_type, scf: ScfInfo) -> dict[str, object]:
    fields = {f.id: f for f in calc_type.fields(scf, JOBS)}
    return {key: fields[key].default for key in (TEFIELD, DIPFIELD, EDIR, EMAXPOS, EOPREG, EAMP)}


def test_the_fields_start_as_the_scf_has_them():
    plain = {TEFIELD: False, DIPFIELD: False, EDIR: 3, EMAXPOS: None, EOPREG: None, EAMP: 0.0}
    assert defaults_of(SLAB, read(BULK)) == plain  # a bulk's SCF never asks for the field
    assert defaults_of(SUPERCELL, read(SLAB_001)) == plain
    assert defaults_of(ADSORPTION, read(SUPERCELL_001)) == plain
    corrected = with_correction(read(SLAB_001))
    assert defaults_of(SUPERCELL, corrected) == {**plain, **ON}
    assert defaults_of(ADSORPTION, with_correction(read(SUPERCELL_001))) == {**plain, **ON}
    # a field of the user's, without the correction: the box, the direction and the amplitude
    applied = with_correction(
        read(SLAB_001), control__dipfield=".false.", system__eamp="0.01", system__edir="1"
    )
    assert defaults_of(SUPERCELL, applied) == {**plain, TEFIELD: True, EDIR: 1, EAMP: 0.01}
    # keys without ``tefield`` are read by nothing: they give no default
    stale = with_correction(read(SLAB_001), control__tefield=".false.", system__eamp="0.01")
    assert defaults_of(SUPERCELL, stale) == {**plain, DIPFIELD: True}


def test_the_numbers_show_only_with_tefield():
    fields = SLAB.fields(read(BULK), JOBS)
    numbers = {EDIR, EMAXPOS, EOPREG, EAMP}

    def shown(mode: str, **values) -> set[str]:
        return {f.id for f in shown_fields(fields, mode, values)} & {TEFIELD, DIPFIELD, *numbers}

    assert shown("padrao") == shown("avancado") == {TEFIELD, DIPFIELD}
    assert shown("avancado", **{TEFIELD: True}) == {TEFIELD, DIPFIELD, *numbers}
    assert shown("avancado", **{DIPFIELD: True}) == {TEFIELD, DIPFIELD}
    assert shown("padrao", **{TEFIELD: True}) == {TEFIELD, DIPFIELD}  # the numbers: ``avancado``


# -- R3: Slab ---------------------------------------------------------------------------------------
def test_slab_is_off_by_default_and_says_why_to_turn_it_on():
    result = SLAB.plan(read(BULK), {}, JOBS, "avancado")
    assert not result.errors
    assert set(written(editor_of(result)).values()) == {None}
    assert result.advice == {DIPFIELD: ONE_SIDED} and ONE_SIDED in result.notes
    assert "- **Correção de dipolo**: desligada" in report(result)
    # nothing fixed: no side differs, but no symmetry of the kaolinite turns c over either
    free = SLAB.plan(read(BULK), {"fix_rule": NONE}, JOBS, "avancado")
    assert free.advice == {DIPFIELD: POLAR_NOTE.format(reason=NO_SYMMETRY)}
    # one Al per layer, nothing fixed: a symmetry turns c over, so no dipole and no warning
    symmetric = SLAB.plan(al(), {"fix_rule": NONE}, JOBS, "avancado")
    assert not symmetric.errors and not symmetric.advice


def test_slab_writes_the_correction():
    result = SLAB.plan(read(BULK), ON, JOBS, "avancado")
    assert not result.errors and not result.advice
    editor = editor_of(result)
    values = written(editor)
    assert (values["tefield"], values["dipfield"], values["edir"]) == (".true.", ".true.", "3")
    assert fortran_float(values["eamp"] or "") == 0.0
    emaxpos, eopreg = window_of(editor)
    assert (
        result.auto[EMAXPOS] == emaxpos and result.auto[EOPREG] == eopreg
    )  # what the window shows
    model = model_from_plan(result.by_key("relax").text)
    assert ramp_distance(model, emaxpos, eopreg).min() >= MIN_MARGIN
    fact = f"- **Correção de dipolo**: tefield e dipfield: edir = 3, emaxpos = {emaxpos:.4f}"
    assert fact in report(result)
    standard = SLAB.plan(read(BULK), ON, JOBS, "padrao")  # the hidden numbers take their defaults
    assert written(editor_of(standard)) == values


def test_each_box_writes_its_own_key():
    field = SLAB.plan(read(BULK), {TEFIELD: True}, JOBS, "avancado")
    values = written(editor_of(field))
    assert (values["tefield"], values["dipfield"], values["edir"]) == (".true.", None, "3")
    assert values["emaxpos"] is not None and fortran_float(values["eamp"] or "") == 0.0
    assert field.advice == {TEFIELD: IDLE_NOTE, DIPFIELD: ONE_SIDED} and not field.errors
    assert "- **Correção de dipolo**: só tefield, sem correção de dipolo: edir = 3" in report(field)

    alone = SLAB.plan(read(BULK), {DIPFIELD: True}, JOBS, "avancado")
    assert written(editor_of(alone)) == {
        "tefield": None,
        "dipfield": ".true.",
        "edir": None,
        "emaxpos": None,
        "eopreg": None,
        "eamp": None,
    }
    assert alone.advice == {TEFIELD: NEEDS_TEFIELD} and not alone.errors
    assert EMAXPOS not in alone.auto
    assert "desligada: dipfield sem tefield" in report(alone)


def test_typed_numbers_are_written_as_they_are():
    values = {
        **ON,
        EMAXPOS: "0,9",
        EOPREG: 0.05,
        EAMP: 0.002,
        EDIR: 3,
    }  # a decimal comma is a point
    result = SLAB.plan(read(BULK), values, JOBS, "avancado")
    assert not result.errors
    text = written(editor_of(result))
    assert (text["emaxpos"], text["eopreg"], text["eamp"]) == ("0.9", "0.05", "0.002")
    assert EMAXPOS not in result.auto and EOPREG not in result.auto
    assert result.advice == {EAMP: EAMP_NOTE.format(value="0.002")}
    assert "eamp = 0.002" in report(result)
    # a typed width alone: the start is still the plan's, for that width
    wide = SLAB.plan(read(BULK), {**ON, EOPREG: 0.2}, JOBS, "avancado")
    automatic = SLAB.plan(read(BULK), ON, JOBS, "avancado")
    assert set(wide.auto) & {EMAXPOS, EOPREG} == {EMAXPOS}
    assert wide.auto[EMAXPOS] == pytest.approx(automatic.auto[EMAXPOS] - 0.05, abs=1e-4)


def test_numbers_out_of_range_block():
    for key, value in ((EMAXPOS, 1.5), (EOPREG, 0.0), (EMAXPOS, -0.1)):
        result = SLAB.plan(read(BULK), {**ON, key: value}, JOBS, "avancado")
        assert result.problems == {key: RANGE_PROBLEM.format(key=key)}
        assert written(editor_of(result))["tefield"] is None
        assert f"- **Correção de dipolo**: {INVALID_FACT}" in report(result)
    result = SLAB.plan(read(BULK), {**ON, EDIR: 4}, JOBS, "avancado")
    assert result.problems == {EDIR: EDIR_PROBLEM} and EDIR_PROBLEM in result.errors
    hidden = SLAB.plan(read(BULK), {EMAXPOS: 1.5}, JOBS, "avancado")  # no field, no number
    assert not hidden.errors


def test_a_ramp_over_the_atoms_and_another_direction_only_warn():
    over = SLAB.plan(read(BULK), {**ON, EMAXPOS: 0.45}, JOBS, "avancado")  # the slab is at 0.5
    assert not over.errors and over.advice == {EMAXPOS: INSIDE_NOTE}
    assert written(editor_of(over))["emaxpos"] == "0.45"
    aside = SLAB.plan(read(BULK), {**ON, EDIR: 1}, JOBS, "avancado")  # no vacuum along a
    assert not aside.errors and written(editor_of(aside))["edir"] == "1"
    assert aside.advice[EDIR] == EDIR_NOTE.format(edir=1)
    assert EMAXPOS in aside.advice  # the ramp has no vacuum to sit in


def test_vc_relax_drops_tstress():
    scf = with_correction(read(BULK), control__tstress=".true.")
    assert scf.value("control", "tstress") == ".true."
    vc = SLAB.plan(scf, {"calculation": "vc-relax"}, JOBS, "avancado")
    assert editor_of(vc).get("control", "tstress") is None
    assert TSTRESS_NOTE in vc.notes and VC_STRESS_NOTE in vc.notes
    relax = SLAB.plan(scf, {}, JOBS, "avancado")  # pw.x computes no stress in a relax anyway
    assert editor_of(relax).get("control", "tstress") == ".true."
    assert VC_STRESS_NOTE not in relax.notes
    off = SLAB.plan(scf, {"calculation": "vc-relax", **OFF}, JOBS, "avancado")
    assert editor_of(off).get("control", "tstress") == ".true." and VC_STRESS_NOTE not in off.notes


def test_structure_not_built_writes_no_correction():
    result = SLAB.plan(read(BULK), {"vacuum_min": 0.0, **ON}, JOBS, "avancado")
    assert result.errors
    assert written(editor_of(result))["tefield"] is None
    assert f"- **Correção de dipolo**: {NOT_WRITTEN}" in report(result)
    assert EMAXPOS not in result.auto


# -- R4: Supercélula --------------------------------------------------------------------------------
def test_supercell_follows_the_scf():
    plain = read(SLAB_001)
    result = SUPERCELL.plan(plain, {}, JOBS, "avancado")
    assert written(editor_of(result))["tefield"] is None
    corrected = with_correction(plain, emaxpos=0.5)  # a ramp across the slab: written again
    result = SUPERCELL.plan(corrected, {}, JOBS, "avancado")
    assert not result.errors
    emaxpos, eopreg = window_of(editor_of(result))
    assert emaxpos == pytest.approx(SLAB_001_EMAXPOS, abs=1e-4)  # n1 × n2 keeps the fractions of c
    model = model_from_plan(result.by_key("relax").text)
    assert ramp_distance(model, emaxpos, eopreg).min() >= MIN_MARGIN


def test_supercell_keeps_a_field_of_the_user():
    applied = with_correction(read(SLAB_001), control__dipfield=".false.", system__eamp="0.01")
    result = SUPERCELL.plan(applied, {}, JOBS, "avancado")
    values = written(editor_of(result))
    # the SCF's own ``dipfield = .false.`` stays as it is written
    assert (values["tefield"], values["dipfield"], values["eamp"]) == (".true.", ".false.", "0.01")
    assert not any(note.startswith(REMOVED_NOTE.split("(")[0]) for note in result.notes)
    assert fortran_float(values["emaxpos"] or "") == pytest.approx(SLAB_001_EMAXPOS, abs=1e-4)
    assert result.advice[EAMP] == EAMP_NOTE.format(value="0.01") and not result.errors


def test_supercell_off_removes_the_scf_correction():
    result = SUPERCELL.plan(with_correction(read(SLAB_001)), OFF, JOBS, "avancado")
    assert set(written(editor_of(result)).values()) == {None}
    assert REMOVED_NOTE.format(keys=ALL_KEYS) in result.notes
    field = SUPERCELL.plan(with_correction(read(SLAB_001)), {DIPFIELD: False}, JOBS, "avancado")
    assert written(editor_of(field))["dipfield"] is None
    assert REMOVED_NOTE.format(keys="dipfield") in field.notes


def test_stacked_copies_refuse_the_correction():
    values = {"n1": 1, "n2": 1, "n3": 2, **ON}
    result = SUPERCELL.plan(read(SLAB_001), values, JOBS, "avancado")
    assert result.problems[DIPFIELD] == STACKED_DIPOLE.format(n=3, copies=2)
    assert written(editor_of(result))["tefield"] is None
    field = SUPERCELL.plan(read(SLAB_001), {**values, DIPFIELD: False}, JOBS, "avancado")
    assert DIPFIELD not in field.problems  # a field alone runs over every copy


def test_bulk_supercell_has_no_dipole_field():
    bulk = with_correction(read(BULK))  # a field of the user's on a bulk passes as it is
    assert not {TEFIELD, DIPFIELD, EMAXPOS} & {f.id for f in SUPERCELL.fields(bulk, JOBS)}
    result = SUPERCELL.plan(bulk, {}, JOBS, "avancado")
    assert written(editor_of(result))["emaxpos"] == "0.5"


# -- R5: Molécula na superfície ---------------------------------------------------------------------
def adsorbed(scf: ScfInfo, **values):
    values = {"molecule": read(MOLECULE), "site": (43,), "remove_h": True, **values}
    return ADSORPTION.plan(scf, values, JOBS, "avancado")


def test_adsorbed_window_avoids_the_molecule():
    surface = with_correction(read(SUPERCELL_001), emaxpos=SLAB_001_EMAXPOS)
    result = adsorbed(surface)
    assert not result.errors
    emaxpos, eopreg = window_of(editor_of(result))
    assert emaxpos != pytest.approx(SLAB_001_EMAXPOS, abs=1e-3)  # the molecule fills that vacuum
    model = model_from_plan(result.by_key("relax").text)
    assert len(model) > len(model_of(surface))
    assert ramp_distance(model, emaxpos, eopreg).min() >= MIN_MARGIN
    assert f"; emaxpos da superfície: {SLAB_001_EMAXPOS}" in report(result)
    assert not result.advice


def test_adsorption_notes_a_different_choice():
    plain = read(SUPERCELL_001)
    on = adsorbed(plain, **ON)
    assert on.advice == {DIPFIELD: SURFACE_WITHOUT_DIPOLE.format(name=plain.name)}
    assert SURFACE_WITHOUT_DIPOLE.format(name=plain.name) in on.notes
    assert written(editor_of(on))["dipfield"] == ".true."
    corrected = with_correction(plain)
    off = adsorbed(corrected, **OFF)
    different = SURFACE_WITH_DIPOLE.format(name=corrected.name)
    assert off.advice == {DIPFIELD: f"{ONE_SIDED}\n{different}"}  # the molecule sits on one side
    assert ONE_SIDED in off.notes and different in off.notes
    assert set(written(editor_of(off)).values()) == {None}
    assert adsorbed(plain).advice == {DIPFIELD: ONE_SIDED}  # as the surface: off, and it says why


# -- R7: what derives from the SCF keeps the correction ---------------------------------------------
@pytest.mark.parametrize("type_id, values", [("bandas", {"kpath": AL_PATH}), ("pdos", {})])
def test_bands_and_pdos_keep_the_correction(type_id, values):
    scf = with_correction(al(), emaxpos=0.7)  # nscf and bands.x rebuild the potential from it
    result = by_id(type_id).plan(scf, values, JOBS, "avancado")
    pw_inputs = [f for f in result.files if "&control" in f.text.lower()]
    assert len(pw_inputs) == 2
    for planned in pw_inputs:
        editor = InputEditor.from_text(planned.text)
        assert has_dipole(editor.get) and editor.get("system", "emaxpos") == "0.7", planned.name
