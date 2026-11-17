"""Spec 97 R1–R2: what the Summary's scanner reads for the level of theory, and each adsorption row's."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from qe_studio.core.analysis.adsorption_energy import arrange, read_rows
from qe_studio.core.analysis.level_of_theory import (
    MISSING,
    LevelOfTheory,
    cutoffs_text,
    k_points_tip,
    level_of_theory,
    mesh_text,
    occupations_text,
    pseudos_tip,
    spin_text,
    xc_text,
)
from qe_studio.core.qe.summary.scan import Facts, Scanner

from adsorption_helpers import SI, copy_scf_outputs, scf_paths
from conftest import FIXTURES

KAOLINITE = FIXTURES / "kao_slab_relax/relax-kaolinite-slab-001.out"
MBD = FIXTURES / "qe_examples/test-suite/pw_vdw/vdw-mbd-vc-relax.out"
PBE = (1, 4, 3, 4, 0, 0, 0)


def scan(path: Path) -> Facts:
    scanner = Scanner()
    with open(path, encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            scanner.feed(number, line)
    return scanner.finish()


def si_edited(tmp_path: Path, edit: Callable[[list[str]], None]) -> Path:
    lines = (SI / "si.scf.out").read_text().splitlines(keepends=True)
    edit(lines)
    out = tmp_path / "si.scf.out"
    out.write_text("".join(lines))
    return out


def after_the_sites(line: str) -> Callable[[list[str]], None]:
    def edit(lines: list[str]) -> None:
        assert "tau(   2)" in lines[88]
        lines.insert(89, line)

    return edit


def after_the_energy(line: str) -> Callable[[list[str]], None]:
    def edit(lines: list[str]) -> None:
        at = next(i for i, text in enumerate(lines) if text.startswith("!"))
        lines.insert(at + 1, line)

    return edit


# -- R1: the scanner --------------------------------------------------------------------------------
def test_the_functional_is_read_by_its_codes():
    si = scan(SI / "si.scf.out")
    al = scan(FIXTURES / "al_bands/al.scf.out")
    ni = scan(FIXTURES / "qe731_ni_spin_fixed/ni.scf.out")
    assert si.xc_codes == (1, 1, 0, 0, 0, 0, 0)
    assert al.xc_codes == ni.xc_codes == PBE  # the same PBE under two names
    al_name, ni_name = al.hit("xc", first=True), ni.hit("xc", first=True)
    assert al_name and ni_name and al_name.groups[0] != ni_name.groups[0]


def test_a_line_without_codes_after_the_functional(tmp_path):
    def drop_codes(lines: list[str]) -> None:
        assert lines[52].strip() == "(   1   1   0   0   0   0   0)"
        del lines[52]

    facts = scan(si_edited(tmp_path, drop_codes))
    assert facts.xc_codes is None
    assert len(facts.axes) == 3  # the line after it is still read


def test_the_dispersion_corrections(tmp_path):
    assert scan(KAOLINITE).dispersion == "DFT-D3 (3 corpos)"
    assert scan(MBD).dispersion == "MBD"  # it prints the lines of TS too
    for path in (SI / "si.scf.out", FIXTURES / "al_bands/al.scf.out"):
        assert scan(path).dispersion is None
    assert scan(FIXTURES / "qe731_ni_spin_fixed/ni.scf.out").dispersion is None
    d2 = after_the_sites("     Parameters for Dispersion (Grimme-D2) Correction:\n")
    assert scan(si_edited(tmp_path, d2)).dispersion == "DFT-D2"
    xdm = after_the_energy("     Dispersion XDM Correction =      -0.01000000 Ry\n")
    assert scan(si_edited(tmp_path, xdm)).dispersion == "XDM"
    d3 = after_the_sites("     DFT-D3 Dispersion Correction (no 3-body):\n")
    assert scan(si_edited(tmp_path, d3)).dispersion == "DFT-D3"


def test_the_crystal_axes_of_the_header():
    assert scan(SI / "si.scf.out").axes == ((-0.5, 0.0, 0.5), (0.0, 0.5, 0.5), (-0.5, 0.5, 0.0))
    assert scan(MBD).axes[0] == (0.58013, 0.0, 0.814524)  # vc-relax: the first cell, not the last


def test_tetrahedra(tmp_path):
    def tetrahedra(lines: list[str]) -> None:
        assert lines[90].strip() == "number of k points=    29"
        lines[90] = "     number of k points=    29 (tetrahedron method)\n"

    facts = scan(si_edited(tmp_path, tetrahedra))
    assert facts.tetrahedra
    assert facts.hit("kpoints", first=True).groups == ("29", None, None)  # type: ignore[union-attr]
    assert not scan(SI / "si.scf.out").tetrahedra
    theory = level_of_theory(facts, None, None)
    assert occupations_text(theory) == "tetrahedra"


# -- R2: each row's level of theory -----------------------------------------------------------------
@pytest.fixture
def rows(tmp_path):
    return {row.name: row for row in read_rows(scf_paths(copy_scf_outputs(tmp_path / "ads")))}


def test_each_row_has_its_level_of_theory(rows):
    si, al, ni = (rows[name].theory for name in ("silicon", "al", "nifix"))
    assert si is not None and al is not None and ni is not None
    assert [(t.ecutwfc, t.ecutrho) for t in (si, al, ni)] == [(25, 118.918), (100, 143), (30, 240)]
    assert [t.xc_name for t in (si, al, ni)] == ["LDA", "PBE", "SLA PW PBE PBE"]
    assert [t.smearing for t in (si, al, ni)] == [None, "Gaussian", "Marzari-Vanderbilt"]
    assert [t.degauss for t in (si, al, ni)] == [None, 0.01, 0.02]
    assert [t.nspin for t in (si, al, ni)] == [1, 1, 2]
    assert ni.magnetization == 0.5
    assert [t.k_points for t in (si, al, ni)] == [29, 47, 16]
    assert [t.k_mesh for t in (si, al, ni)] == [
        "automatic 8×8×8 (0 0 0)",
        "automatic 10×10×10 (0 0 0)",
        "automatic 6×6×6 (0 0 0)",
    ]
    assert si.composition == (("Si", 2),) and ni.composition == (("Ni", 1),)
    assert si.pseudos == (("Si", "Si.pz-rrkj.UPF"),)
    assert si.cell == pytest.approx(
        [(10.1686 * x, 10.1686 * y, 10.1686 * z) for x, y, z in scan(SI / "si.scf.out").axes]
    )
    assert not any(t.tetrahedra or t.dispersion for t in (si, al, ni))


def test_the_texts(rows):
    si, al, ni = (rows[name].theory for name in ("silicon", "al", "nifix"))
    assert [cutoffs_text(t) for t in (si, al, ni)] == ["25/118.918", "100/143", "30/240"]
    assert [xc_text(t) for t in (si, al, ni)] == ["LDA", "PBE", "SLA PW PBE PBE"]
    assert [occupations_text(t) for t in (si, al, ni)] == [
        "sem smearing",
        "smearing Gaussian, 0.0100 Ry",
        "smearing Marzari-Vanderbilt, 0.0200 Ry",
    ]
    assert [spin_text(t) for t in (si, al, ni)] == [
        "não polarizado",
        "não polarizado",
        "colinear (nspin=2), 0.50 μB",
    ]
    assert mesh_text(si) == "automatic 8×8×8 (0 0 0)"
    assert k_points_tip(si) == "29 k-pontos irredutíveis"
    assert pseudos_tip(si) == "Pseudopotenciais:\nSi: Si.pz-rrkj.UPF"
    for text in (cutoffs_text, xc_text, occupations_text, spin_text, mesh_text):
        assert text(None) == MISSING
    assert k_points_tip(None) == pseudos_tip(None) == ""


def test_without_the_input_the_mesh_is_the_k_point_count(tmp_path):
    folder = copy_scf_outputs(tmp_path / "ads")
    (folder / "si.scf.in").unlink()
    theory = next(r for r in read_rows(scf_paths(folder)) if r.path.name == "si.scf.out").theory
    assert theory is not None and theory.k_mesh is None
    assert mesh_text(theory) == "29 k-pontos"
    assert mesh_text(LevelOfTheory(k_points=1)) == "1 k-ponto"


def test_a_functional_with_dispersion_and_other_labels(tmp_path):
    shutil.copy(KAOLINITE, tmp_path / "slab.out")
    (row,) = read_rows([tmp_path / "slab.out"])
    assert row.theory is not None
    assert xc_text(row.theory) == "SLA PW PBX PBC + DFT-D3 (3 corpos)"
    assert not row.theory.nonlocal_functional
    assert LevelOfTheory(xc_codes=(1, 4, 4, 0, 1, 0, 0)).nonlocal_functional  # vdW-DF


def test_the_composition_is_by_element():
    facts = Facts(species={"Fe1": 2, "O": 3, "Fe_up": 1, "Xx": 1})
    theory = level_of_theory(facts, None, None)
    assert theory.composition == (("Fe", 3), ("O", 3), ("Xx", 1))  # Xx: no element, as it is
    assert theory.nspin is None and theory.cell is None and spin_text(theory) == MISSING


def test_arrange_keeps_the_level_of_theory(rows):
    shuffled = arrange(reversed(list(rows.values())))
    assert [r.theory for r in shuffled] == [
        rows[name].theory for name in ("silicon", "al", "nifix")
    ]
