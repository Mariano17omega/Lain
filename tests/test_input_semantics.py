"""core/qe/input_semantics.py: what a pw.x input means, from its text alone (spec 104)."""

from __future__ import annotations

import pytest

from qe_studio.core.qe import input_semantics
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.qe.input_semantics import (
    US_PAW_NAME,
    _check_input,
    check_input,
    semantic_issues,
)

from conftest import FIXTURES, own_fixtures
from qe_examples_helpers import PW, params, select

SI_STRUCTURE = "ibrav = 2, celldm(1) = 10.2, nat = 2, ntyp = 1"
SI_ROWS = "Si 0.00 0.00 0.00\nSi 0.25 0.25 0.25\n"


def pw(
    *,
    calculation: str = "scf",
    system: str = "ecutwfc = 30",
    structure: str = SI_STRUCTURE,
    pseudo: str = "Si.pz-vbc.UPF",
    positions: str = f"ATOMIC_POSITIONS alat\n{SI_ROWS}",
    kpoints: str = "K_POINTS automatic\n4 4 4 0 0 0\n",
    namelists: str = "",
) -> str:
    """A pw.x input that gives no issue as it stands; each argument replaces one piece."""
    return (
        f"&CONTROL\n  calculation = '{calculation}'\n/\n"
        f"&SYSTEM\n  {structure}\n  {system}\n/\n"
        f"&ELECTRONS\n/\n{namelists}"
        f"ATOMIC_SPECIES\nSi 28.086 {pseudo}\n"
        f"{positions}{kpoints}"
    )


def found(text: str) -> list[tuple[int, str, str, str]]:
    """(line, underlined text, severity, message) of every meaning issue."""
    lines = text.split("\n")
    return [
        (i.line, lines[i.line - 1][i.col_start : i.col_end], i.severity, i.message)
        for i in semantic_issues(lint(text), text)
    ]


def test_the_base_input_is_clean():
    assert found(pw()) == []
    assert check_input(pw()).issues == []


# -- R2: cutoffs ----------------------------------------------------------------------------------
def test_without_ecutrho_the_default_is_four_times():
    assert found(pw(system="ecutwfc = 30")) == []


def test_ecutrho_not_above_ecutwfc_stops_pw_x():
    text = pw(system="ecutwfc = 30, ecutrho = 30.0")
    assert found(text) == [
        (6, "30.0", "error", "ecutrho (30 Ry) não passa de ecutwfc (30 Ry): o pw.x para")
    ]


def test_ecutrho_below_four_times_is_a_warning():
    ((line, shown, severity, message),) = found(pw(system="ecutwfc = 30, ecutrho = 90"))
    assert (line, shown, severity) == (6, "90", "warning")
    assert message.startswith("ecutrho = 3 × ecutwfc, abaixo de 4 ×")


def test_us_paw_at_four_times_below_the_floor_is_a_warning_on_ecutrho():
    text = pw(system="ecutwfc = 30, ecutrho = 120", pseudo="Si.pbe-n-kjpaw_psl.1.0.0.UPF")
    assert found(text) == [
        (
            6,
            "120",
            "warning",
            "Pseudopotencial US/PAW (Si.pbe-n-kjpaw_psl.1.0.0.UPF) com ecutrho = 120 Ry "
            "(4 × ecutwfc): costuma precisar de 8 a 12 ×; confira o corte sugerido no UPF",
        )
    ]


def test_us_paw_without_ecutrho_points_at_ecutwfc():
    ((line, shown, severity, message),) = found(pw(system="ecutwfc = 40", pseudo="Si_US.van"))
    assert (line, shown, severity) == (6, "40", "warning")
    assert "sem ecutrho: o padrão é 4 × ecutwfc = 160 Ry" in message


def test_us_paw_below_four_times_gets_only_the_us_paw_warning():
    ((__, __, severity, message),) = found(
        pw(system="ecutwfc = 30, ecutrho = 90", pseudo="Si.pbe-rrkjus.UPF")
    )
    assert severity == "warning" and message.startswith("Pseudopotencial US/PAW")
    assert "(3 × ecutwfc)" in message


@pytest.mark.parametrize(
    "system", ["ecutwfc = 90, ecutrho = 360", "ecutwfc = 90", "ecutwfc = 30, ecutrho = 240"]
)
def test_us_paw_above_the_floor_or_at_eight_times_is_quiet(system):
    """The floor is the user's decision: their PAW runs at 90/360 are not flagged."""
    assert found(pw(system=system, pseudo="Si.pbe-nl-kjpaw_psl.1.0.0.UPF")) == []


def test_gipaw_is_a_norm_conserving_pseudopotential():
    ((__, __, __, message),) = found(
        pw(system="ecutwfc = 30, ecutrho = 90", pseudo="C.pbe-mt_gipaw.UPF")
    )
    assert message.startswith("ecutrho = 3 × ecutwfc")


@pytest.mark.parametrize(
    "name",
    [
        "Al.pbe-n-kjpaw_psl.1.0.0.UPF",
        "Fe.pbe-spn-rrkjus_psl.0.2.1.UPF",
        "mg_pbe_v1.4.uspp.F.UPF",
        "Cu_US_PBE_3pj_lowE.UPF",
        "O_US.van",
        "Ti.pbe-sp-van_ak.UPF",
        "Au.rel-pz-kjpaw.UPF",
        "Ar.paw.z_8.ld1.psl.v1.0.0-high.upf",
    ],
)
def test_us_and_paw_names(name):
    assert US_PAW_NAME.search(name)


@pytest.mark.parametrize(
    "name",
    [
        "Si.pz-vbc.UPF",
        "Si.pbe-rrkj.UPF",
        "Ag_ONCV_PBE-1.0.upf",
        "C.pbe-hgh.UPF",
        "Fe.pbe-mt_fhi.UPF",
        "Fe.lda-pseudoDojo.UPF",
        "C.pbe-mt_gipaw.UPF",
        "AgUSPBE.RRKJ3",  # an old US name: missed on purpose, the rule speaks only when it is sure
        "Bi.rel-pz-d-mt.UPF",
    ],
)
def test_norm_conserving_and_unknown_names(name):
    assert not US_PAW_NAME.search(name)


@pytest.mark.parametrize(
    "system", ["ecutrho = 120", "ecutwfc = 'x', ecutrho = 20", "ecutwfc = 30, ecutrho = 1.0.0"]
)
def test_without_a_readable_ecutwfc_or_ecutrho_the_cutoffs_say_nothing(system):
    assert found(pw(system=system)) == []


# -- R3: smearing and spin ------------------------------------------------------------------------
@pytest.mark.parametrize("degauss", ["", ", degauss = 0", ", degauss = -0.01"])
def test_smearing_needs_a_positive_degauss(degauss):
    text = pw(system=f"ecutwfc = 30, occupations = 'smearing'{degauss}")
    assert found(text) == [
        (6, "'smearing'", "error", "occupations = 'smearing' exige degauss > 0: o pw.x para")
    ]


def test_smearing_with_degauss_is_quiet():
    assert found(pw(system="ecutwfc = 30, occupations = 'smearing', degauss = 0.01")) == []


def test_nspin_2_without_a_starting_magnetization_stops_pw_x():
    text = pw(system="ecutwfc = 30, nspin = 2")
    assert found(text) == [
        (
            6,
            "2",
            "error",
            "nspin = 2 sem starting_magnetization nem tot_magnetization: o pw.x para",
        )
    ]


@pytest.mark.parametrize(
    ("calculation", "system"),
    [
        ("bands", "nspin = 2"),
        ("nscf", "nspin = 2"),
        ("scf", "nspin = 2, tot_magnetization = 2"),
        ("scf", "nspin = 2, occupations = 'from_input'"),
        ("scf", "nspin = 2, starting_magnetization(2) = 0.5"),
        ("scf", "nspin = 2, starting_magnetization(1) = 0.0"),  # set is set, as pw.x checks
        ("scf", "nspin = 2, constrained_magnetization = 'atomic'"),
        ("scf", "nspin = 1"),
    ],
)
def test_nspin_2_is_quiet_where_pw_x_does_not_ask_for_it(calculation, system):
    assert found(pw(calculation=calculation, system=f"ecutwfc = 30, {system}")) == []


# -- R4: namelists of a dynamics ------------------------------------------------------------------
IONS = "&IONS\n/\n"
CELL = "&CELL\n/\n"


@pytest.mark.parametrize("calculation", ["relax", "md"])
def test_relax_and_md_need_ions(calculation):
    assert found(pw(calculation=calculation)) == [
        (
            2,
            f"'{calculation}'",
            "error",
            f"calculation = '{calculation}' exige a namelist &IONS: o pw.x para",
        )
    ]


def test_vc_relax_needs_ions_and_cell():
    assert [message for *__, message in found(pw(calculation="vc-relax"))] == [
        "calculation = 'vc-relax' exige a namelist &IONS: o pw.x para",
        "calculation = 'vc-relax' exige a namelist &CELL: o pw.x para",
    ]


@pytest.mark.parametrize(
    ("calculation", "namelists"),
    [
        ("scf", ""),
        ("bands", ""),
        ("relax", IONS),
        ("vc-relax", IONS + CELL),
        ("vc-md", IONS + CELL),
    ],
)
def test_the_namelists_pw_x_reads_are_there(calculation, namelists):
    assert found(pw(calculation=calculation, namelists=namelists)) == []


def test_a_real_relax_with_a_repeated_ions_keeps_only_the_write_warning():
    text = (FIXTURES / "kao_slab_relax/relax-kaolinite-slab-001.in").read_text()
    assert [(i.line, i.severity, i.message) for i in check_input(text).issues] == [
        (30, "warning", "&IONS repetida: o pw.x lê só a primeira")
    ]


# -- R5: nat and the rows of ATOMIC_POSITIONS -----------------------------------------------------
def test_fewer_rows_than_nat_stops_pw_x():
    text = pw(structure="ibrav = 2, celldm(1) = 10.2, nat = 3, ntyp = 1")
    assert found(text) == [
        (5, "3", "error", "nat = 3, mas ATOMIC_POSITIONS tem 2 linhas: o pw.x para")
    ]


def test_a_single_row_is_said_in_the_singular():
    text = pw(positions="ATOMIC_POSITIONS alat\nSi 0.00 0.00 0.00\n")
    assert [message for *__, message in found(text)] == [
        "nat = 2, mas ATOMIC_POSITIONS tem 1 linha: o pw.x para"
    ]


def test_more_rows_than_nat_drops_atoms():
    text = pw(positions=f"ATOMIC_POSITIONS alat\n{SI_ROWS}Si 0.50 0.50 0.50\n")
    assert found(text) == [
        (5, "2", "error", "nat = 2, mas ATOMIC_POSITIONS tem 3 linhas: o pw.x ignora as que sobram")
    ]


def test_blank_lines_and_column_one_comments_are_not_rows():
    text = pw(positions="ATOMIC_POSITIONS alat\nSi 0.00 0.00 0.00\n\n# second\nSi 0.25 0.25 0.25\n")
    assert found(text) == []


# -- R6: one k point along a periodic axis --------------------------------------------------------
def orthorhombic(heights: list[float], c: float, mesh: str) -> str:
    """A cell of 3.84 × 3.84 × ``c`` Å with one Si at each crystal height."""
    rows = "".join(f"Si 0.0 0.0 {z}\n" for z in heights)
    return pw(
        structure=f"ibrav = 8, A = 3.84, B = 3.84, C = {c}, nat = {len(heights)}, ntyp = 1",
        positions=f"ATOMIC_POSITIONS crystal\n{rows}",
        kpoints=f"K_POINTS automatic\n{mesh}\n",
    )


def test_one_k_point_along_a_short_periodic_axis_is_a_warning():
    text = pw(kpoints="K_POINTS automatic\n4 4 1 0 0 0\n")
    ((line, shown, severity, message),) = found(text)
    assert (line, shown, severity) == (15, "K_POINTS", "warning")
    assert message == (
        "K_POINTS com 1 ponto ao longo de c, que não tem vácuo e mede 3.1 Å: "
        "a amostragem fica rala nessa direção"
    )


def test_a_bulk_layer_stack_is_flagged_and_the_same_cell_with_vacuum_is_not():
    bulk = orthorhombic([0.0, 0.25, 0.5, 0.75], 12.0, "6 6 1 0 0 0")
    slab = orthorhombic([0.0, 0.1], 12.0, "6 6 1 0 0 0")
    assert [message for *__, message in found(bulk)] == [
        "K_POINTS com 1 ponto ao longo de c, que não tem vácuo e mede 12.0 Å: "
        "a amostragem fica rala nessa direção"
    ]
    assert found(slab) == []


@pytest.mark.parametrize(
    "text",
    [
        pw(kpoints="K_POINTS automatic\n1 1 1 0 0 0\n"),  # a deliberate Γ
        orthorhombic([i / 10 for i in range(10)], 25.0, "6 6 1 0 0 0"),  # a long periodic axis
        pw(kpoints="K_POINTS gamma\n"),
        pw(kpoints="K_POINTS automatic\n4 4 x 0 0 0\n"),
        pw(structure="nat = 2, ntyp = 1", kpoints="K_POINTS automatic\n4 4 1 0 0 0\n"),  # no ibrav
    ],
)
def test_the_mesh_rule_stays_quiet(text):
    assert found(text) == []


# -- R1: which inputs, and check_input ------------------------------------------------------------
def test_cp_x_inputs_get_no_rule():
    text = pw(calculation="cp", system="ecutwfc = 30, ecutrho = 20, nspin = 2")
    assert lint(text).program == "pw"  # cp.x shares the namelists
    assert found(text) == []


def test_other_programs_get_no_rule():
    assert found("&inputph\n  tr2_ph = 1.0d-14\n/\n0.0 0.0 0.0\n") == []
    assert found("&inputpp\n  prefix = 'si'\n  plot_num = 0\n/\n") == []


def test_check_input_merges_the_write_and_meaning_issues_in_order():
    text = pw(calculation="relax", system="ecutwfc = 30, ecutrho = 30\n  nspin = 2, bad = .tru.")
    doc = check_input(text)
    keys = [(i.line, i.col_start, i.col_end) for i in doc.issues]
    assert keys == sorted(keys)
    assert {i.message.split(":")[0] for i in doc.issues} >= {
        "calculation = 'relax' exige a namelist &IONS",
        "ecutrho (30 Ry) não passa de ecutwfc (30 Ry)",
        "nspin = 2 sem starting_magnetization nem tot_magnetization",
    }
    written = lint(text).issues
    assert written and all(issue in doc.issues for issue in written)  # .tru. is kept


def test_check_input_never_raises(monkeypatch):
    def boom(doc, text):
        raise RuntimeError("bug")

    monkeypatch.setattr(input_semantics, "semantic_issues", boom)
    text = pw(calculation="relax")
    assert check_input(text).issues == lint(text).issues
    with pytest.raises(RuntimeError):
        _check_input(text)


# -- real inputs ------------------------------------------------------------------------------------
def errors_of(text: str) -> list[str]:
    return [i.message for i in semantic_issues(lint(text), text) if i.severity == "error"]


@pytest.mark.parametrize("path", own_fixtures("*.in"), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_own_fixtures_have_no_meaning_errors(path):
    assert errors_of(path.read_text()) == []


@pytest.mark.parametrize("case", params(select(PW)))
def test_qe_examples_have_no_meaning_errors(case):
    assert errors_of(case.input_text) == []
