"""Spec 78 R2: the energies of SCF outputs, the default equation and the report."""

import shutil
from pathlib import Path

import pytest

from qe_studio.core.analysis.adsorption_energy import (
    NO_ENERGY,
    RY_TO_EV,
    EnergyRow,
    Role,
    calculate,
    default_equation,
    parse_equation,
    read_rows,
    report_name,
    report_text,
    save_report,
)

from conftest import FIXTURES

SI, AL, NI = -15.86827608, -5.03855495, -85.89426253
SOURCES = {"si": "si_bands", "al": "al_bands", "ni": "qe731_ni_spin_fixed"}


@pytest.fixture
def outputs(tmp_path) -> Path:
    """The three SCF runs (input and output) side by side."""
    folder = tmp_path / "ads"
    folder.mkdir()
    for stem, source in SOURCES.items():
        for suffix in (".in", ".out"):
            shutil.copy(FIXTURES / source / f"{stem}.scf{suffix}", folder / f"{stem}.scf{suffix}")
    return folder


def paths(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.scf.out"))


def test_energies_prefixes_and_order(outputs):
    rows = read_rows(paths(outputs))
    assert [(r.path.name, r.prefix, r.name, r.atoms) for r in rows] == [
        ("si.scf.out", "silicon", "silicon", 2),  # most atoms: the complex
        ("al.scf.out", "al", "al", 1),  # a tie: by the file's name
        ("ni.scf.out", "nifix", "nifix", 1),
    ]
    assert [r.energy_ry for r in rows] == [SI, AL, NI]
    assert [r.role for r in rows] == [Role.COMPLEX, Role.SUBSTRATE, Role.ADSORBATE]
    assert all(r.problem is None for r in rows)


def test_the_prefix_without_an_input(outputs):
    (outputs / "al.scf.in").unlink()  # from the "output data dir …/al.save/" line
    out = outputs / "al.scf.out"
    rows = {r.path.name: r for r in read_rows(paths(outputs))}
    assert rows["al.scf.out"].prefix == "al"
    out.write_text("".join(line for line in out.open() if "output data dir" not in line))
    rows = {r.path.name: r for r in read_rows(paths(outputs))}
    assert rows["al.scf.out"].prefix == "al.scf"  # the file's name without its extension


def test_the_default_equation_and_its_value(outputs):
    rows = read_rows(paths(outputs))
    equation = default_equation(rows)
    assert equation == "E_ads = E(silicon) - E(al) - E(nifix)"
    outcome = calculate(equation, rows)
    value = SI - AL - NI
    assert outcome.name == "E_ads" and outcome.value_ry == pytest.approx(value)
    assert outcome.text == f"E_ads = {value:.8f} Ry = {value * RY_TO_EV:.4f} eV"
    assert pytest.approx(4.3597447222071e-18 / 1.602176634e-19 / 2, rel=1e-14) == RY_TO_EV


def test_a_repeated_prefix_gets_a_number(outputs):
    shutil.copy(outputs / "al.scf.out", outputs / "al2.scf.out")
    rows = read_rows(paths(outputs))
    assert [r.name for r in rows] == ["silicon", "al", "al_2", "nifix"]
    assert default_equation(rows) == "E_ads = E(silicon) - E(al) - E(al_2) - E(nifix)"


def test_an_output_without_the_final_energy_stays_out(outputs):
    out = outputs / "si.scf.out"
    lines = out.read_text().splitlines(keepends=True)
    out.write_text(
        "".join(lines[: next(i for i, line in enumerate(lines) if line.startswith("!"))])
    )
    rows = read_rows(paths(outputs))
    si = next(r for r in rows if r.path == out)
    assert si.energy_ry is None and si.problem == NO_ENERGY and si.role is None
    assert [r.role for r in rows if r is not si] == [Role.COMPLEX, Role.SUBSTRATE]
    assert default_equation(rows) == "E_ads = E(al) - E(nifix)"
    assert calculate("E(silicon)", rows).error == "E(silicon): sem energia total final"


def test_fewer_than_two_energies_say_what_is_missing(outputs):
    rows = read_rows([outputs / "al.scf.out"])
    assert default_equation(rows) == "E_ads = "
    assert "duas saídas" in (calculate(default_equation(rows), rows).error or "")


def test_the_equation_is_the_users(outputs):
    rows = read_rows(paths(outputs))
    assert calculate("E(xyz) - E(al)", rows).error == "E(xyz): prefixo desconhecido"
    formation = calculate("Formação = 2*E(al) - E(silicon)", rows)
    assert formation.name == "Formação" and formation.value_ry == pytest.approx(2 * AL - SI)
    assert calculate("E(al) -", rows).error == "Expressão incompleta"
    assert calculate("(E(al) + E(nifix)) / 2", rows).value_ry == pytest.approx((AL + NI) / 2)
    assert calculate("E(al", rows).error == "Expressão incompleta"
    assert parse_equation("E(al) - E(nifix)") == ("E_ads", "E(al) - E(nifix)")
    assert parse_equation(" = 1") == ("E_ads", "1")


def test_the_report(outputs):
    rows = read_rows(paths(outputs))
    assert report_name(rows) == "energia_ads_silicon_al_nifix.md"
    equation = default_equation(rows)
    text = report_text(rows, equation, calculate(equation, rows))
    assert text.startswith("# Energia de adsorção\n")
    assert "| Prefixo | Arquivo | Átomos | Energia total (Ry) |" in text
    assert "| silicon | si.scf.out | 2 | -15.86827608 |" in text
    assert f"```\n{equation}\n```" in text
    assert "E_ads = 75.06454140 Ry = 1021.3051 eV" in text


def test_the_reports_name_is_safe_and_short(outputs):
    rows = read_rows(paths(outputs))
    odd = [r.__class__(r.path, "a b/c", r.name, r.atoms, r.energy_ry) for r in rows[:1]]
    assert report_name(odd) == "energia_ads_a_b_c.md"
    long = [r.__class__(r.path, "x" * 150, r.name, r.atoms, r.energy_ry) for r in rows[:2]]
    name = report_name(long)
    assert len(name) == 200 + len(".md") and name.endswith(".md")


def test_saving_never_overwrites(outputs):
    rows = read_rows(paths(outputs))
    equation = default_equation(rows)
    outcome = calculate(equation, rows)
    first = save_report(outputs, rows, equation, outcome)
    second = save_report(outputs, rows, equation, outcome)
    assert first.name == "energia_ads_silicon_al_nifix.md"
    assert second.name == "energia_ads_silicon_al_nifix_2.md"
    assert first.read_text() == second.read_text() == report_text(rows, equation, outcome)


@pytest.mark.parametrize(
    "equation",
    ["E_ads = E(a) - _v0", "E(a)*0 + _v0 + E(b)", "E(a) - _v1 + E(b)", "E(a) - _\uff560"],
)
def test_an_internal_name_typed_by_hand_is_an_unknown_name(equation):
    """``_v0`` is what ``E(a)`` is replaced by: typed, it must not be read as that energy."""
    rows = [EnergyRow(Path(n), n, n, 1, e) for n, e in (("a", -1.0), ("b", -3.0))]
    outcome = calculate(equation, rows)
    assert outcome.value_ry is None
    assert (outcome.error or "").startswith("Nome desconhecido: _v")


def test_a_prefix_named_like_an_internal_name_is_still_a_prefix():
    rows = [EnergyRow(Path(n), n, n, 1, e) for n, e in (("_v0", -1.0), ("_v1", -3.0))]
    assert calculate("E(_v1) - E(_v0)", rows).value_ry == -2.0
