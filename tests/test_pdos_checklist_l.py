"""L-11 and L-12 of the Lain × QE checklist (``Documentation/QE-73/07-lain-checklist.md``): a PDOS set
that is cut short, incomplete or mixed, and the up/dw columns of a noncollinear run."""

import pytest

from qe_studio.core.calculations.base import LoadError
from qe_studio.core.qe.projwfc import (
    PdosFormatError,
    completeness_warnings,
    load_pdos,
    read_projwfc_states,
)
from spin_helpers import SPIN_PDOS, copy_fixture
from test_plotting import load

from conftest import FIXTURES

AL = FIXTURES / "al_pdos_flat"
S_FILE = "pdos.dat.pdos_atm#1(Al)_wfc#1(s)"
P_FILE = "pdos.dat.pdos_atm#1(Al)_wfc#2(p)"


def al_copy(tmp_path):
    return copy_fixture("al_pdos_flat", tmp_path)


def pdos_warnings(folder):
    return load(folder)[1].warnings


# -- L-11: a file that cannot be read ------------------------------------------------------------
def cut_short(path):
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:4]) + "\n   -24.9")  # cut inside the first number


def test_l11_a_truncated_projection_is_left_out_with_a_warning(tmp_path):
    folder = al_copy(tmp_path)
    cut_short(folder / P_FILE)
    __, dataset, __ = load(folder)
    assert [s.l for s in dataset.data.series] == ["s"]
    assert any(P_FILE in w and "ilegível, ignorado" in w for w in dataset.warnings)
    assert any("faltam 1 projeções" in w and "wfc 2" in w for w in dataset.warnings)  # and says so


def test_l11_no_readable_projection_still_fails(tmp_path):
    folder = al_copy(tmp_path)
    cut_short(folder / S_FILE)
    cut_short(folder / P_FILE)
    with pytest.raises(PdosFormatError, match="legível"):
        load_pdos(sorted(folder.glob("*pdos_atm*")))
    with pytest.raises(LoadError):
        load(folder)


def test_l11_a_garbled_total_falls_back_to_the_sum_of_the_projections(tmp_path):
    folder = al_copy(tmp_path)
    cut_short(folder / "pdos.dat.pdos_tot")
    __, dataset, __ = load(folder)
    assert dataset.data.total_is_sum
    assert any("pdos.dat.pdos_tot" in w and "soma das projeções" in w for w in dataset.warnings)


def test_l11_an_overflowed_number_is_a_warning_too(tmp_path):
    folder = al_copy(tmp_path)
    path = folder / S_FILE
    lines = path.read_text().splitlines()
    lines[5] = lines[5][:8] + "*" * 11 + lines[5][19:]  # ldos, the column that is read
    path.write_text("\n".join(lines) + "\n")
    assert any(S_FILE in w and "ilegível" in w for w in pdos_warnings(folder))


# -- L-11: is the set whole? ---------------------------------------------------------------------
def test_l11_the_states_projwfc_listed_are_read_from_its_output():
    assert read_projwfc_states(AL / "al.projwfc.out") == {(1, 1), (1, 2)}
    assert read_projwfc_states(SPIN_PDOS / "ni.pdos.out") == {(1, 1), (1, 2)}
    assert read_projwfc_states(AL / "al.projwfc.in") == set()


def test_l11_a_whole_set_has_no_warning(tmp_path):
    assert not [w for w in pdos_warnings(al_copy(tmp_path)) if "projeções" in w]


def test_l11_a_missing_projection_is_named(tmp_path):
    folder = al_copy(tmp_path)
    (folder / P_FILE).unlink()
    warnings = pdos_warnings(folder)
    assert any(
        "PDOS incompleta" in w and "faltam 1 projeções" in w and "átomo 1 wfc 2" in w
        for w in warnings
    )


def test_l11_a_projection_of_another_run_is_told(tmp_path):
    """The same ``filpdos`` twice: the new run overwrites only what it writes."""
    folder = al_copy(tmp_path)
    (folder / "pdos.dat.pdos_atm#1(Al)_wfc#3(d)").write_text((folder / P_FILE).read_text())
    warnings = pdos_warnings(folder)
    assert any("não constam na saída do projwfc.x" in w and "átomo 1 wfc 3" in w for w in warnings)


def test_l11_without_the_output_a_hole_in_the_numbering_is_found(tmp_path):
    folder = al_copy(tmp_path)
    (folder / "al.projwfc.out").unlink()
    (folder / S_FILE).unlink()
    warnings = pdos_warnings(folder)
    assert any("faltam 1 projeções" in w and "átomo 1 wfc 1" in w for w in warnings)


def test_l11_without_the_output_a_whole_set_says_nothing(tmp_path):
    folder = al_copy(tmp_path)
    (folder / "al.projwfc.out").unlink()
    assert not [w for w in pdos_warnings(folder) if "projeções" in w]


def test_l11_the_warning_names_a_few_pairs_and_counts_the_rest():
    data = load_pdos(sorted(AL.glob("*pdos_atm*")))
    listed = {(a, w) for a in range(1, 5) for w in range(1, 4)}
    (missing,) = [w for w in completeness_warnings(data.series, listed) if "faltam" in w]
    assert "faltam 10 projeções" in missing and missing.count("átomo") == 5 and "…" in missing


# -- L-12: the up/dw columns of a noncollinear run -----------------------------------------------
NONCOLLINEAR_LINE = "     Noncollinear calculation\n"


def test_l12_noncollinear_up_down_columns_are_flagged(tmp_path):
    folder = copy_fixture(SPIN_PDOS.name, tmp_path)
    scf = folder / "ni.scf.out"
    scf.write_text(NONCOLLINEAR_LINE + scf.read_text())
    __, dataset, __ = load(folder)
    assert dataset.data.spin_polarized
    assert any(
        "não colinear sem spin-órbita" in w and "componentes do spinor" in w
        for w in dataset.warnings
    )


def test_l12_a_collinear_spin_run_is_not_flagged(tmp_path):
    folder = copy_fixture(SPIN_PDOS.name, tmp_path)
    assert not [w for w in pdos_warnings(folder) if "não colinear" in w]


def test_l12_a_noncollinear_run_without_spin_columns_is_not_flagged(tmp_path):
    folder = al_copy(tmp_path)
    scf = folder / "al.scf.out"
    scf.write_text(NONCOLLINEAR_LINE + scf.read_text())
    assert not [w for w in pdos_warnings(folder) if "não colinear" in w]
