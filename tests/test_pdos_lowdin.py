"""PDOS: the spilling in the status line and as a warning, the Löwdin charge of the chosen atoms
(spec 99, R3)."""

from __future__ import annotations

import dataclasses

from qe_studio.core.calculations.pdos import PdosModule
from spin_helpers import SPIN_PDOS
from test_bands_dos_render import AL_BANDS, combined
from test_plotting import load

from conftest import FIXTURES, copy_fixture

AL_PDOS = FIXTURES / "al_pdos_flat"


def high_spilling_copy(tmp_path):
    """The Al run with its projwfc.x output saying 6.12 % (the copy only: fixtures stay as they are)."""
    folder = copy_fixture("al_pdos_flat", tmp_path)
    out = folder / "al.projwfc.out"
    text = out.read_text()
    assert text.count("Spilling Parameter:   0.0143") == 1
    out.write_text(text.replace("Spilling Parameter:   0.0143", "Spilling Parameter:   0.0612"))
    return folder


def spilling_warnings(dataset) -> list[str]:
    return [warning for warning in dataset.warnings if "spilling" in warning]


def test_status_line_has_the_spilling():
    _module, dataset, params = load(AL_PDOS)
    assert dataset.lowdin is not None and dataset.lowdin.spilling == 0.0143
    assert "2 projeções · 1 espécies · spilling = 1.43 %" in PdosModule.summary(dataset, params)
    assert spilling_warnings(dataset) == []  # below 5 %


def test_selection_sums_the_lowdin_charges():
    _module, dataset, params = load(AL_PDOS)
    assert "Löwdin" not in PdosModule.summary(dataset, params)  # no selection: nothing to sum
    text = PdosModule.summary(dataset, dataclasses.replace(params, atoms=[1]))
    assert text.endswith("spilling = 1.43 % · 1 de 1 átomos · Löwdin = 2.9570 e")
    _module, spin, params = load(SPIN_PDOS)
    text = PdosModule.summary(spin, dataclasses.replace(params, atoms=[1]))
    assert "1 de 1 átomos · Löwdin = 9.8838 e (↑−↓ = 0.7103) · spin polarizado" in text
    none = PdosModule.summary(dataset, dataclasses.replace(params, atoms=[]))
    assert "0 de 1 átomos" in none and "Löwdin" not in none


def test_high_spilling_warns(tmp_path):
    _module, dataset, params = load(high_spilling_copy(tmp_path))
    (warning,) = spilling_warnings(dataset)
    assert warning.startswith("spilling de 6.12 %: a base atômica deixa de fora 6.12 % da carga")
    assert "pdos_tot" in warning
    assert "spilling = 6.12 %" in PdosModule.summary(dataset, params)


def test_without_projwfc_output_nothing_changes(tmp_path):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    (folder / "al.projwfc.out").unlink()
    _module, dataset, params = load(folder)
    assert dataset.lowdin is None and spilling_warnings(dataset) == []
    assert "spilling" not in PdosModule.summary(dataset, params)


def test_bands_dos_inherits_the_warning(tmp_path):
    _module, dataset, _params = combined(AL_BANDS, high_spilling_copy(tmp_path))
    assert any(w.startswith("DOS: spilling de 6.12 %") for w in dataset.warnings)
