"""Spec 25 R5: the crystal of a pw.x input, with QE's own lattice vectors (port of latgen.f90)."""

import io
import re

import numpy as np
import pytest

from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.lattice import (
    BOHR_ANGSTROM,
    StructureError,
    cell_vectors,
    celldm_from_abc,
    crystal_from_editor,
)

from conftest import FIXTURES

AXIS = re.compile(r"a\(\d\) = \(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)")


def crystal_of(text: str):
    return crystal_from_editor(InputEditor.from_text(text))


def printed_axes(output) -> tuple[float, np.ndarray]:
    """alat (Bohr) and the crystal axes (units of alat) a pw.x output prints."""
    text = output.read_text()
    alat = float(re.search(r"lattice parameter \(alat\)\s*=\s*(\S+)", text).group(1))
    rows = [[float(v) for v in m.groups()] for m in AXIS.finditer(text)][:3]
    return alat, np.array(rows)


@pytest.mark.parametrize(
    "folder, stem",
    [("al_bands", "al.scf"), ("si_bands", "si.scf"), ("qe731_ni_spin_bands", "ni.scf")],
)
def test_ibrav_2_matches_the_axes_pw_x_printed(folder, stem):
    crystal = crystal_of((FIXTURES / folder / f"{stem}.in").read_text())
    alat, axes = printed_axes(FIXTURES / folder / f"{stem}.out")
    # the printed alat has 4 decimals; the axes 6
    np.testing.assert_allclose(crystal.cell / BOHR_ANGSTROM / alat, axes, atol=1e-5)


A, B, C = 10.0, 1.3, 1.7  # celldm(1), (2), (3)


def volume(cell):
    return abs(np.linalg.det(cell))


def triclinic(cos_a, cos_b, cos_g):
    return np.sqrt(1 - cos_a**2 - cos_b**2 - cos_g**2 + 2 * cos_a * cos_b * cos_g)


@pytest.mark.parametrize(
    "ibrav, celldm, expected",
    [
        (1, [A], A**3),
        (2, [A], A**3 / 4),
        (3, [A], A**3 / 2),
        (-3, [A], A**3 / 2),
        (4, [A, 0, C], np.sqrt(3) / 2 * A**3 * C),
        (5, [A, 0, 0, 0.3], A**3 * np.sqrt(1 - 3 * 0.3**2 + 2 * 0.3**3)),
        (-5, [A, 0, 0, 0.3], A**3 * np.sqrt(1 - 3 * 0.3**2 + 2 * 0.3**3)),
        (6, [A, 0, C], A**3 * C),
        (7, [A, 0, C], A**3 * C / 2),
        (8, [A, B, C], A**3 * B * C),
        (9, [A, B, C], A**3 * B * C / 2),
        (-9, [A, B, C], A**3 * B * C / 2),
        (91, [A, B, C], A**3 * B * C / 2),
        (10, [A, B, C], A**3 * B * C / 4),
        (11, [A, B, C], A**3 * B * C / 2),
        (12, [A, B, C, 0.2], A**3 * B * C * np.sqrt(1 - 0.2**2)),
        (-12, [A, B, C, 0, 0.2], A**3 * B * C * np.sqrt(1 - 0.2**2)),
        (13, [A, B, C, 0.2], A**3 * B * C * np.sqrt(1 - 0.2**2) / 2),
        (-13, [A, B, C, 0, 0.2], A**3 * B * C * np.sqrt(1 - 0.2**2) / 2),
        (14, [A, B, C, 0.1, 0.2, 0.3], A**3 * B * C * triclinic(0.1, 0.2, 0.3)),
    ],
)
def test_volume_of_every_bravais_lattice(ibrav, celldm, expected):
    # QE's sqrt(2) and sqrt(3) have 13 digits
    assert volume(cell_vectors(ibrav, celldm)) == pytest.approx(expected, rel=1e-11)


def test_vectors_written_in_the_qe_documentation():
    a, c = A, A * C
    hexagonal = cell_vectors(4, [A, 0, C])
    np.testing.assert_allclose(hexagonal, [[a, 0, 0], [-a / 2, a * np.sqrt(3) / 2, 0], [0, 0, c]])
    b, cos = A * B, 0.2
    sin = np.sqrt(1 - cos**2)
    np.testing.assert_allclose(
        cell_vectors(13, [A, B, C, cos]),
        [[a / 2, 0, -c / 2], [b * cos, b * sin, 0], [a / 2, 0, c / 2]],
    )
    np.testing.assert_allclose(
        cell_vectors(-13, [A, B, C, 0, cos]),
        [[a / 2, b / 2, 0], [-a / 2, b / 2, 0], [c * cos, 0, c * sin]],
    )
    trigonal = cell_vectors(5, [A, 0, 0, 0.3])
    lengths = np.linalg.norm(trigonal, axis=1)
    np.testing.assert_allclose(lengths, A, rtol=1e-11)
    assert trigonal[0] @ trigonal[1] / A**2 == pytest.approx(0.3, rel=1e-11)
    np.testing.assert_allclose(trigonal[:, 2], trigonal[0, 2])  # three-fold axis along z
    rotated = cell_vectors(-5, [A, 0, 0, 0.3])
    np.testing.assert_allclose(np.linalg.norm(rotated, axis=1), A, rtol=1e-11)
    triclinic_cell = cell_vectors(14, [A, B, C, 0.1, 0.2, 0.3])
    a1, a2, a3 = triclinic_cell
    assert a2 @ a3 / np.linalg.norm(a2) / np.linalg.norm(a3) == pytest.approx(0.1)
    assert a1 @ a3 / np.linalg.norm(a1) / np.linalg.norm(a3) == pytest.approx(0.2)
    assert a1 @ a2 / np.linalg.norm(a1) / np.linalg.norm(a2) == pytest.approx(0.3)


@pytest.mark.parametrize(
    "ibrav, celldm",
    [(2, [0]), (4, [A]), (5, [A, 0, 0, 1.0]), (14, [A, B, C, 0.9, 0.9, -0.9]), (15, [A])],
)
def test_impossible_lattices_raise(ibrav, celldm):
    with pytest.raises(StructureError):
        cell_vectors(ibrav, celldm)


def system(
    body: str, positions: str = "ATOMIC_POSITIONS crystal\n Si 0 0 0\n", nat: int = 1
) -> str:
    return (
        f"&control\n/\n&system\n  {body}\n  nat = {nat}, ntyp = 1\n/\n&electrons\n/\n"
        f"ATOMIC_SPECIES\n Si 28.08 Si.UPF\n{positions}K_POINTS automatic\n4 4 4 0 0 0\n"
    )


def test_a_b_c_give_the_same_cell_as_celldm():
    with_abc = crystal_of(system("ibrav = 4, A = 3.0, C = 5.0"))
    with_celldm = crystal_of(
        system(f"ibrav = 4, celldm(1) = {3.0 / BOHR_ANGSTROM}, celldm(3) = {5 / 3}")
    )
    np.testing.assert_allclose(with_abc.cell, with_celldm.cell)
    assert celldm_from_abc(12, 3.0, 4.0, 5.0, 0.1, 0.2, 0.3)[3:] == [0.1, 0.0, 0.0]
    assert celldm_from_abc(-12, 3.0, 4.0, 5.0, 0.1, 0.2, 0.3)[3:] == [0.0, 0.2, 0.0]
    assert celldm_from_abc(14, 3.0, 4.0, 5.0, 0.1, 0.2, 0.3)[3:] == [0.3, 0.2, 0.1]


@pytest.mark.parametrize(
    "positions",
    [
        "ATOMIC_POSITIONS crystal\n Si 0.25 0.5 0.0\n",
        "ATOMIC_POSITIONS {alat}\n Si 0.25 0.5 0.0\n",
        "ATOMIC_POSITIONS bohr\n Si 2.5 5.0 0.0 0 0 1\n",
        f"ATOMIC_POSITIONS angstrom\n Si {2.5 * BOHR_ANGSTROM} {5.0 * BOHR_ANGSTROM} 0.0\n",
    ],
)
def test_position_units(positions):
    crystal = crystal_of(system("ibrav = 1, celldm(1) = 10.0", positions))
    np.testing.assert_allclose(crystal.frac, [[0.25, 0.5, 0.0]], atol=1e-12)
    assert crystal.labels == ("Si",)


@pytest.mark.parametrize(
    "cell, alat",
    [
        ("CELL_PARAMETERS bohr\n 10 0 0\n 0 10 0\n 0 0 10\n", ""),
        (
            f"CELL_PARAMETERS angstrom\n {10 * BOHR_ANGSTROM} 0 0\n 0 {10 * BOHR_ANGSTROM} 0\n 0 0 {10 * BOHR_ANGSTROM}\n",
            "",
        ),
        ("CELL_PARAMETERS alat\n 1 0 0\n 0 1 0\n 0 0 1\n", ", celldm(1) = 10.0"),
    ],
)
def test_ibrav_0_cells_and_alat_positions(cell, alat):
    text = system(f"ibrav = 0{alat}", f"{cell}ATOMIC_POSITIONS alat\n Si 0.5 0.5 0.5\n")
    crystal = crystal_of(text)
    np.testing.assert_allclose(crystal.cell, np.eye(3) * 10 * BOHR_ANGSTROM)
    np.testing.assert_allclose(crystal.frac, [[0.5, 0.5, 0.5]])  # alat = |a1| without celldm


def test_kaolinite_ibrav_0_matches_ase():
    from ase.io.espresso import read_espresso_in

    text = (FIXTURES / "kao_vc_relax" / "vc-relax.in").read_text()
    atoms = read_espresso_in(io.StringIO(text))
    crystal = crystal_of(text)
    np.testing.assert_allclose(crystal.cell, atoms.cell.array, atol=1e-10)
    np.testing.assert_allclose(crystal.frac, atoms.get_scaled_positions(wrap=False), atol=1e-10)
    assert list(crystal.labels) == atoms.get_chemical_symbols()


@pytest.mark.parametrize(
    "text, message",
    [
        (
            system("ibrav = 1, celldm(1) = 10", "ATOMIC_POSITIONS crystal_sg\n Si 8a\n"),
            "crystal_sg",
        ),
        (system("ibrav = 1, celldm(1) = 10", nat=2), "nat = 2"),
        (system("ibrav = 1"), "celldm(1)"),
        (system("ibrav = 0, celldm(1) = 10"), "CELL_PARAMETERS"),
        (system("celldm(1) = 10"), "ibrav"),
        (
            system("ibrav = 1, celldm(1) = 10", "ATOMIC_POSITIONS crystal\n Si 0 zero 0\n"),
            "ilegível",
        ),
    ],
)
def test_unreadable_structures_raise(text, message):
    with pytest.raises(StructureError, match=re.escape(message)):
        crystal_of(text)
