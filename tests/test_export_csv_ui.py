"""Exporting from the window (spec 32 R3, R4): the name carries the path from the project root and
a CSV of the data goes next to the figures."""

import shutil

import pytest
from PyQt6.QtWidgets import QMessageBox

from project_helpers import config_of
from qe_studio.ui.dialogs.overwrite import OverwriteChoice

from conftest import FIXTURES

PREFIX = "ilita-Analise_1-Bandas"
FORMATS = ("csv", "pdf", "png", "svg")


@pytest.fixture
def bandas(raiz):
    """``raiz/ilita/Analise_1/Bandas`` holding a band structure: the bands of the Al fixture."""
    folder = raiz / "ilita" / "Analise_1" / "Bandas"
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.band.in", "bands.in"),
        ("al.band.out", "bands.out"),
        ("bands.out", "bands_pp.out"),
        ("bands.dat.gnu", "bands.dat.gnu"),
    ]:
        shutil.copy(FIXTURES / "al_bands" / old, folder / new)
    return folder


@pytest.fixture
def window(window_factory, raiz, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: pytest.fail("a warning box opened"))
    )
    return window_factory(config_of(raiz))


def plot_and_export(qtbot, window, folder) -> list:
    with qtbot.waitSignals([window.plot_ready, window.export_finished], timeout=20_000) as blocker:
        window.generate_plot_for(folder, auto_export=True)
    return next(
        e.args[0] for e in blocker.all_signals_and_args if "export_finished" in e.signal_name
    )


def test_the_files_are_named_from_the_project_and_a_csv_comes_with_them(qtbot, window, bandas):
    written = plot_and_export(qtbot, window, bandas)
    assert [p.name for p in written] == [
        f"{PREFIX}-bands.png",
        f"{PREFIX}-bands.svg",
        f"{PREFIX}-bands.pdf",
        f"{PREFIX}-bands.csv",
    ]
    assert sorted(p.name for p in (bandas / "plots").iterdir()) == [
        f"{PREFIX}-bands.{ext}" for ext in FORMATS
    ]
    header, first, *_ = (
        (bandas / "plots" / f"{PREFIX}-bands.csv").read_text("utf-8-sig").split("\n")
    )
    assert header.startswith("k (2π/alat);Banda 1 (E−E_F, eV);Banda 2")
    assert "," in first and "." not in first and ";" in first  # decimal commas, columns by ';'
    assert window.status.message.text() == "Salvo em plots/: " + ", ".join(p.name for p in written)


def test_a_second_export_asks_about_the_whole_set_and_the_new_version_has_a_csv_too(
    qtbot, window, bandas, monkeypatch
):
    asked = []

    def ask(parent, existing, new_stem):
        asked.append(([p.name for p in existing], new_stem))
        return OverwriteChoice.NEW_VERSION, False

    monkeypatch.setattr("qe_studio.ui.plot_export.ask_overwrite", ask)
    plot_and_export(qtbot, window, bandas)
    with qtbot.waitSignal(window.export_finished, timeout=20_000) as blocker:
        assert window.export_plot()
    assert asked == [
        ([f"{PREFIX}-bands.{ext}" for ext in ("png", "svg", "pdf", "csv")], f"{PREFIX}-bands_2")
    ]
    assert [p.name for p in blocker.args[0]][-1] == f"{PREFIX}-bands_2.csv"
    assert (bandas / "plots" / f"{PREFIX}-bands.csv").exists()  # the first one is untouched


def test_only_the_csv_left_over_still_asks_before_it_is_replaced(
    qtbot, window, bandas, monkeypatch
):
    asked = []
    monkeypatch.setattr(
        "qe_studio.ui.plot_export.ask_overwrite",
        lambda parent, existing, new: (
            asked.append([p.name for p in existing]) or (OverwriteChoice.CANCEL, False)
        ),
    )
    (bandas / "plots").mkdir()
    (bandas / "plots" / f"{PREFIX}-bands.csv").write_text("meu;arquivo\n")
    with qtbot.waitSignal(window.plot_ready, timeout=20_000):
        window.generate_plot_for(bandas, auto_export=False)
    assert not window.export_plot()  # cancelled in the dialog
    assert asked == [[f"{PREFIX}-bands.csv"]]
    assert (bandas / "plots" / f"{PREFIX}-bands.csv").read_text() == "meu;arquivo\n"


def test_the_root_of_the_session_is_the_one_the_name_starts_from(qtbot, window, bandas):
    window.use_session_root(bandas.parent.parent)  # ``ilita`` is now the project folder's root
    written = plot_and_export(qtbot, window, bandas)
    assert written[0].name == "Analise_1-Bandas-bands.png"


def test_a_pdos_gets_a_csv_and_a_scf_or_relax_does_not(
    qtbot, window_factory, demo_project, tmp_path
):
    window = window_factory()  # ``demo_project`` is the root: the folders are first level
    written = plot_and_export(qtbot, window, demo_project / "04_pdos")
    assert sorted(p.name for p in written) == [f"04_pdos-pdos.{ext}" for ext in FORMATS]
    assert written[-1].read_text("utf-8-sig").startswith("E − E_F (eV);Total")
    written = plot_and_export(qtbot, window, demo_project / "01_relax")
    assert {p.suffix for p in written} == {".png", ".svg", ".pdf"}
