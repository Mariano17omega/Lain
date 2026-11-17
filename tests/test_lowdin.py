"""Löwdin charges and the spilling parameter of projwfc.x outputs (spec 99, R1)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from qe_studio.core import cancel
from qe_studio.core.qe import lowdin
from qe_studio.core.qe.lowdin import LowdinReader, read_lines, read_lowdin, spilling_is_high
from test_cancel_loaders import FlaggedToken

from conftest import FIXTURES

AL = FIXTURES / "al_pdos_flat" / "al.projwfc.out"
NI = FIXTURES / "qe731_ni_spin_pdos" / "ni.pdos.out"
L = "spdf"


def numbered(text: str):
    reader = LowdinReader()
    for number, line in enumerate(text.splitlines(), 1):
        reader.feed(line, number)
    return reader.finish()


# -- QE's print_lowdin, in Python: formats 2000-2003 of PP/src/projwfc.f90:372-375 ----------------------
def _f(value: float) -> str:
    return f"{value:8.4f}"


def _pairs(charges: list[float]) -> str:
    return "".join(f", {L[l]} ={_f(q)}" for l, q in enumerate(charges))  # noqa: E741


def fortran_block(atoms: list[list[list[float]]], spilling: float) -> str:
    """``atoms[n][spin][l]``: the charges of each atom, one list per spin channel (1 or 2)."""
    lines = ["", "Lowdin Charges: ", ""]
    for n, channels in enumerate(atoms, 1):
        number = f"{n:3d}" if n < 1000 else "***"
        if len(channels) == 1:
            (charges,) = channels
            for l, q in enumerate(charges):  # noqa: E741
                lm = ", pz=  0.1000" if l else ""  # m components follow l > 0 (not read)
                lines.append(
                    f"     Atom # {number}: total charge = {_f(sum(charges))}, {L[l]} ={_f(q)}{lm}, "
                )
            continue
        up, down = channels
        both = [u + d for u, d in zip(up, down, strict=True)]
        lines.append(f"     Atom # {number}: total charge = {_f(sum(both))}{_pairs(both)}")
        for label, charges in (("spin up     ", up), ("spin down   ", down)):
            for l, q in enumerate(charges):  # noqa: E741
                lines.append(f"                 {label} = {_f(sum(charges))}, {L[l]} ={_f(q)}, ")
        pol = [u - d for u, d in zip(up, down, strict=True)]
        lines.append(f"                 polarization = {_f(sum(up) - sum(down))}{_pairs(pol)}")
    lines.append(f"     Spilling Parameter: {_f(spilling)}")
    return "\n".join(lines) + "\n"


# -- the fixtures ----------------------------------------------------------------------------------
def test_al_without_spin():
    found = numbered(AL.read_text())
    assert found is not None
    (atom,) = found.atoms
    assert (atom.atom, atom.total, atom.orbitals) == (1, 2.957, {"s": 0.9319, "p": 2.0251})
    assert atom.up is atom.down is atom.polarization is None and atom.line == 250
    assert (found.spilling, found.spilling_line) == (0.0143, 252)
    assert found.species == {1: "Al"} and found.channels == {1: frozenset("sp")}
    assert not found.spin_resolved and not found.spinor


def test_ni_with_spin():
    found = numbered(NI.read_text())
    assert found is not None
    (atom,) = found.atoms
    assert (atom.total, atom.up, atom.down, atom.polarization) == (9.8838, 5.297, 4.5868, 0.7103)
    assert atom.orbitals == {"s": 0.9412, "p": 0.0, "d": 8.9426}  # QE prints the p of lmax_wfc
    assert atom.orbitals_up == {"s": 0.4649, "p": 0.0, "d": 4.8321}
    assert atom.orbitals_down["d"] == 4.1105 and atom.orbitals_pol["s"] == -0.0114
    assert found.channels == {1: frozenset("sd")}  # the states have no p
    assert (found.spilling, found.spilling_line, atom.line) == (0.0116, 79, 71)
    assert found.spin_resolved


# -- the edges -------------------------------------------------------------------------------------
@pytest.mark.parametrize("spins", [1, 2])
def test_triple_star_atom_numbers(spins):
    """i3 overflows past atom 999: the order of the block numbers the atoms."""
    atoms = [[[n / 1000, 1.0]] * spins for n in range(1, 1003)]
    found = read_lines(fortran_block(atoms, 0.01).splitlines())
    assert found is not None
    assert [atom.atom for atom in found.atoms] == list(range(1, 1003))
    assert found.atoms[-1].orbitals["s"] == pytest.approx(1.002 * spins, abs=1e-4)


def test_cut_block_keeps_the_atoms_read():
    text = NI.read_text()
    found = read_lines(text[: text.index("     Spilling")].splitlines())
    assert found is not None
    assert [atom.total for atom in found.atoms] == [9.8838] and found.spilling is None


def test_last_block_wins():
    second = fortran_block([[[0.5, 1.5]], [[2.0]]], 0.02)
    found = read_lines((AL.read_text() + second).splitlines())
    assert found is not None
    assert [atom.total for atom in found.atoms] == [2.0, 2.0] and found.spilling == 0.02


def test_negative_spilling_is_kept():
    found = read_lines(fortran_block([[[1.0]]], -0.0213).splitlines())
    assert found is not None and found.spilling == -0.0213
    assert not spilling_is_high(found.spilling)


def test_no_block_is_none(tmp_path):
    assert read_lines((FIXTURES / "al_bands" / "bands.out").read_text().splitlines()) is None
    assert read_lowdin(FIXTURES / "al_pdos_flat" / "al.scf.out") is None


def test_spinor_from_s_z():
    states = (
        "     state #   1: atom   1 (Fe ), wfc  1 (l=0 m= 1 s_z= 0.5)\n"
        "     state #   2: atom   1 (Fe ), wfc  1 (l=0 m= 1 s_z=-0.5)\n"
    )
    found = read_lines((states + fortran_block([[[0.6], [0.4]]], 0.01)).splitlines())
    assert found is not None and found.spinor and found.species == {1: "Fe"}


@pytest.mark.parametrize("high", [0.0501, 0.2])
def test_spilling_threshold(high):
    assert spilling_is_high(high)
    assert not spilling_is_high(0.05) and not spilling_is_high(None)


# -- reading the file ------------------------------------------------------------------------------
def padded(tmp_path, block: str, filler_lines: int = 2000):
    path = tmp_path / "proj.out"
    path.write_text("     ==== e(   1) =    -5.12345 eV ==== \n" * filler_lines + block)
    return path


def test_read_lowdin_reads_only_the_tail(tmp_path, monkeypatch):
    text = NI.read_text()
    path = padded(tmp_path, text[text.index("Lowdin Charges") :])
    monkeypatch.setattr(lowdin, "TAIL_BYTES", 4000)
    found, whole = read_lowdin(path), read_lines(path.read_text().splitlines())
    assert found is not None and whole is not None
    assert found.atoms == whole.atoms and found.spilling == 0.0116
    assert found.atoms[0].line is None  # no numbers in this mode


def test_read_lowdin_falls_back_to_the_whole_file(tmp_path, monkeypatch):
    block = fortran_block([[[0.5, 1.5]] for _ in range(40)], 0.031)
    path = padded(tmp_path, block)
    monkeypatch.setattr(lowdin, "TAIL_BYTES", 300)  # the header is out of the tail
    found = read_lowdin(path)
    assert found is not None and len(found.atoms) == 40 and found.spilling == 0.031


def test_read_lowdin_without_block_in_the_tail_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(lowdin, "TAIL_BYTES", 300)
    assert read_lowdin(padded(tmp_path, "     JOB DONE.\n")) is None


def test_read_lowdin_is_cancellable(tmp_path, monkeypatch):
    block = fortran_block([[[0.5]] for _ in range(3 * cancel.CHECK_EVERY_LINES)], 0.01)
    path = padded(tmp_path, block, filler_lines=10)
    monkeypatch.setattr(lowdin, "TAIL_BYTES", 300)
    with cancel.bind(FlaggedToken()), pytest.raises(cancel.Cancelled):
        read_lowdin(path)


def test_charge_of_sums_the_selection():
    found = read_lines(fortran_block([[[0.5], [0.25]], [[1.0], [2.0]]], 0.0).splitlines())
    assert found is not None
    total, polarization = found.charge_of([1, 2, 7])  # 7 is not in the block
    assert total == pytest.approx(3.75) and polarization == pytest.approx(-0.75)
    assert found.charge_of([7]) is None
    al = read_lowdin(AL)
    assert al is not None and al.charge_of({1}) == (2.957, None)


# -- the property: what QE writes reads back -------------------------------------------------------
# Up to 20 e per l and channel: every sum still fits QE's f8.4 (a wider value prints stars).
charge = st.floats(0, 20, allow_nan=False).map(lambda value: round(value, 4))


@st.composite
def lowdin_charges(draw) -> list[list[list[float]]]:
    nat, lmax, spins = draw(st.integers(1, 4)), draw(st.integers(0, 3)), draw(st.integers(1, 2))
    row = st.lists(charge, min_size=lmax + 1, max_size=lmax + 1)
    return draw(st.lists(st.lists(row, min_size=spins, max_size=spins), min_size=nat, max_size=nat))


@given(lowdin_charges(), st.floats(-0.5, 0.5, allow_nan=False))
def test_fortran_lines_read_back(atoms, spilling):
    found = read_lines(fortran_block(atoms, spilling).splitlines())
    assert found is not None
    assert found.spilling == pytest.approx(spilling, abs=5.1e-5)
    assert [atom.atom for atom in found.atoms] == list(range(1, len(atoms) + 1))
    for atom, channels in zip(found.atoms, atoms, strict=True):
        both = [sum(qs) for qs in zip(*channels, strict=True)]
        assert atom.total == pytest.approx(sum(both), abs=5.1e-5)
        assert [atom.orbitals[L[l]] for l in range(len(both))] == pytest.approx(both, abs=5.1e-5)  # noqa: E741
        if len(channels) == 2:
            up, down = channels
            assert atom.up == pytest.approx(sum(up), abs=5.1e-5)
            assert atom.down == pytest.approx(sum(down), abs=5.1e-5)
            assert atom.polarization == pytest.approx(sum(up) - sum(down), abs=5.1e-5)
            assert [atom.orbitals_pol[L[l]] for l in range(len(up))] == pytest.approx(  # noqa: E741
                [u - d for u, d in zip(up, down, strict=True)], abs=5.1e-5
            )
        else:
            assert atom.up is None
