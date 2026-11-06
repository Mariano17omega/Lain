"""Shared by the spin tests (spec 13): the Ni fixtures and small helpers, like ``sync_helpers``."""

import shutil
from pathlib import Path

import numpy as np

from qe_studio.core.detection import detect_folder
from qe_studio.core.qe.bands_x import read_gnu
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES, copy_fixture

SPIN_BANDS = FIXTURES / "qe731_ni_spin_bands"
SPIN_PDOS = FIXTURES / "qe731_ni_spin_pdos"
SPIN_FIXED = FIXTURES / "qe731_ni_spin_fixed"
FIXED_FERMI = (13.8484, 14.1389)  # what the fixed-magnetization SCF prints (↑, ↓)

__all__ = [
    "FIXED_FERMI",
    "FIXTURES",
    "SPIN_BANDS",
    "SPIN_FIXED",
    "SPIN_PDOS",
    "copy_fixture",
    "detect_one",
    "names",
    "spin_bands_copy",
    "with_fixed_magnetization",
    "write_gnu",
]


def detect_one(folder: Path, kind: str | None = None):
    results = detect_folder(folder, sniff=SniffCache().sniff)
    if kind is None:
        (result,) = results
        return result
    return next(r for r in results if r.kind == kind)


def names(result, role: str) -> list[str]:
    return sorted(p.name for p in result.files.get(role, []))


def spin_bands_copy(tmp_path: Path, remove: tuple[str, ...] = ()) -> Path:
    """A copy of the spin bands fixture without the named files."""
    folder = copy_fixture(SPIN_BANDS.name, tmp_path)
    for name in remove:
        (folder / name).unlink()
    return folder


def with_fixed_magnetization(folder: Path) -> Path:
    """``folder`` with its SCF output replaced by the fixed-magnetization one (two E_F)."""
    shutil.copy(SPIN_FIXED / "ni.scf.out", folder / "ni.scf.out")
    return folder


def write_gnu(path: Path, x: np.ndarray, bands: list[np.ndarray]) -> None:
    """A ``.gnu`` file: one (x, E) block per band, blank line between blocks."""
    blocks = [
        "\n".join(f"{xi:10.4f}{e:10.4f}" for xi, e in zip(x, band, strict=True)) for band in bands
    ]
    path.write_text("\n\n".join(blocks) + "\n")


def gnu_energies(path: Path) -> np.ndarray:
    return read_gnu(path).energies
