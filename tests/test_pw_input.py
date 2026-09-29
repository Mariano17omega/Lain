import numpy as np
import pytest

from qe_studio.core.qe.pw_input import format_kpoint_label, parse_input, parse_kpoints

from conftest import FIXTURES


def read(rel: str):
    return parse_input((FIXTURES / rel).read_text())


def test_crystal_b_path_with_labels():
    parsed = read("al_bands/al.band.in")
    assert parsed.program == "pw"
    assert parsed.calculation == "bands"
    kp = parsed.kpoints
    assert kp.mode == "crystal_b" and kp.is_path
    assert kp.labels == ("L", "G", "X", "U", "G")
    assert kp.vertex_indices() == [0, 20, 50, 60, 90]
    assert kp.path_length == 91
    np.testing.assert_allclose(kp.points[2], [-0.5, 0.0, -0.5])


def test_explicit_list_has_no_labels():
    kp = read("si_bands/si.band.in").kpoints
    assert kp.mode == "crystal" and not kp.is_path
    assert len(kp.weights) == 200
    assert set(kp.labels) == {""}


@pytest.mark.parametrize(
    ("rel", "program", "calculation"),
    [
        ("al_bands/bands.in", "bands", None),
        ("al_pdos_flat/al.projwfc.in", "projwfc", None),
        ("al_bands/al.scf.in", "pw", "scf"),
        ("ni_pdos_spin/ni.dos.in", "pw", "nscf"),
        ("si_relax/si.rel.in", "pw", "relax"),
    ],
)
def test_program_and_calculation(rel, program, calculation):
    parsed = read(rel)
    assert parsed.program == program
    assert parsed.calculation == calculation


def test_default_calculation_is_scf():
    parsed = parse_input("&control\n prefix='x'\n/\n&system\n ibrav=2\n/\n")
    assert parsed.calculation == "scf"


def test_label_comment_styles():
    kp = parse_kpoints(
        [
            "K_POINTS tpiba_b",
            "4",
            "0.0 0.5 0.0 20   ! Y",
            "0.0 0.0 0.0 20 !Gamma",
            "0.5 0.0 0.0 1 # X",
            "-0.5 -0.5 0.5 1",
        ]
    )
    assert kp.mode == "tpiba_b"
    assert kp.labels == ("Y", "Gamma", "X", "")
    assert kp.vertex_indices() == [0, 20, 40, 41]


def test_other_modes():
    assert parse_kpoints(["K_POINTS gamma"]).mode == "gamma"
    auto = parse_kpoints(["K_POINTS (automatic)", "4 4 4 1 1 1"])
    assert auto.mode == "automatic"
    np.testing.assert_allclose(auto.points[0], [4, 4, 4])
    assert parse_kpoints(["ATOMIC_SPECIES", "Si 28 Si.UPF"]) is None


@pytest.mark.parametrize(
    ("raw", "formatted"),
    [
        ("G", r"$\Gamma$"),
        ("Gamma", r"$\Gamma$"),
        ("GAMMA", r"$\Gamma$"),
        ("Y2", "Y$_{2}$"),
        ("T_2", "T$_{2}$"),
        ("X", "X"),
        ("", ""),
        (r"$\Sigma$", r"$\Sigma$"),
    ],
)
def test_format_label(raw, formatted):
    assert format_kpoint_label(raw) == formatted
