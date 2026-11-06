import numpy as np
import pytest

from qe_studio.core.qe.projwfc import (
    PdosFormatError,
    aggregate,
    header_columns,
    load_pdos,
    parse_atm_name,
    read_pdos_file,
)

from conftest import FIXTURES

AL = FIXTURES / "al_pdos_flat"
NI = FIXTURES / "qe731_ni_spin_pdos"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pdos.dat.pdos_atm#1(Al)_wfc#1(s)", ("pdos.dat", 1, "Al", 1, "s", None)),
        ("ilite.dat.pdos_atm#93(Hg)_wfc#4(d)", ("ilite.dat", 93, "Hg", 4, "d", None)),
        ("x.pdos_atm#2(Pt1)_wfc#3(p_j1.5)", ("x", 2, "Pt1", 3, "p", 1.5)),
    ],
)
def test_atm_names(name, expected):
    meta = parse_atm_name(name)
    assert (meta.prefix, meta.atom, meta.species, meta.wfc, meta.l, meta.j) == expected


def test_non_pdos_names():
    assert parse_atm_name("pdos.dat.pdos_tot") is None
    assert parse_atm_name("scf.out") is None


def test_header_columns():
    assert header_columns("# E (eV)   ldos(E)   pdos(E)    pdos(E)\n") == ["ldos", "pdos", "pdos"]
    assert header_columns("# E (eV)  dosup(E)   dosdw(E)  pdosup(E)  pdosdw(E)")[:2] == [
        "dosup",
        "dosdw",
    ]
    with pytest.raises(PdosFormatError, match="resolvida em k"):
        header_columns("# ik    E (eV)  dos(E)    pdos(E)")
    with pytest.raises(PdosFormatError):
        header_columns("1.0 2.0 3.0")


def test_only_ldos_column_is_used():
    path = AL / "pdos.dat.pdos_atm#1(Al)_wfc#2(p)"
    energy, channel = read_pdos_file(path)
    raw = np.loadtxt(path, skiprows=1)
    np.testing.assert_allclose(channel.up, raw[:, 1])
    assert channel.down is None
    np.testing.assert_allclose(energy, raw[:, 0])


def test_load_al():
    data = load_pdos(sorted(AL.glob("*pdos_atm*")), AL / "pdos.dat.pdos_tot")
    assert not data.spin_polarized and not data.total_is_sum
    assert data.species == ["Al"]
    groups = aggregate(data)
    assert list(groups) == [("Al", "s"), ("Al", "p")]
    assert list(aggregate(data, "species")) == [("Al", "")]
    assert list(aggregate(data, "orbital")) == [("", "s"), ("", "p")]
    summed = aggregate(data, "species")[("Al", "")].up
    np.testing.assert_allclose(summed, groups[("Al", "s")].up + groups[("Al", "p")].up)


def test_load_ni_spin():
    data = load_pdos(sorted(NI.glob("*pdos_atm*")), NI / "ni.pdos_tot")
    assert data.spin_polarized
    assert data.total.down is not None
    groups = aggregate(data)
    assert list(groups) == [("Ni", "s"), ("Ni", "d")]
    assert groups[("Ni", "d")].down.shape == data.energy.shape


def test_total_falls_back_to_sum():
    data = load_pdos(sorted(AL.glob("*pdos_atm*")))
    assert data.total_is_sum
    assert any("pdos_tot ausente" in w for w in data.warnings)


def test_no_files():
    with pytest.raises(PdosFormatError):
        load_pdos([])
