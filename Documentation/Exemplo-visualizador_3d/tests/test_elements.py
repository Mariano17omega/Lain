import pytest

from viewer3d.core.elements import element_for_label, symbol_from_label


@pytest.mark.parametrize(
    ("label", "symbol"),
    [
        ("Fe1", "Fe"),
        ("Fe_up", "Fe"),
        ("C2", "C"),
        ("H_ads", "H"),
        ("Hg", "Hg"),
        ("O", "O"),
        ("si", "Si"),
        ("Al", "Al"),
        ("Cl", "Cl"),
        ("Ha", "H"),  # no element "Ha": fall back to the first letter
    ],
)
def test_label_rule(label, symbol):
    assert symbol_from_label(label) == symbol
    assert element_for_label(label).known


@pytest.mark.parametrize("label", ["X", "1Fe", "", "_", "Xx9"])
def test_unknown_labels_never_raise(label):
    info = element_for_label(label)  # "X" is Z=0 in ASE and must count as unknown
    assert not info.known
    assert info.z == 0
    assert info.color == (0.5, 0.5, 0.5)
    assert info.r_cov == 1.0
    assert info.r_vdw == 1.0


def test_known_element_data():
    hg = element_for_label("Hg")
    assert (hg.symbol, hg.z, hg.name) == ("Hg", 80, "Mercúrio")
    assert hg.r_cov == pytest.approx(1.32)
    assert min(hg.color) >= 0 and max(hg.color) <= 1
    assert element_for_label("H").r_cov == pytest.approx(0.31)


def test_vdw_nan_falls_back():
    for label in ("Pm", "Og", "Es"):  # elements without a vdW radius in ASE
        assert element_for_label(label).r_vdw > 0
