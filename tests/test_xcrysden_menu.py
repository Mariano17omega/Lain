"""Spec 45 R3: "Abrir com XCrysDen" in the context menu of pw.x inputs and outputs: which files get it,
when it is enabled, what a click starts and that a config reload applies without a restart."""

import pytest
from PyQt6.QtCore import QPoint, QProcess
from PyQt6.QtWidgets import QMenu

from grid_helpers import menu_texts
from qe_studio.core.xcrysden import NOT_SET

ITEM = "Abrir com XCrysDen"
STRUCTURE = "Visualização 3D"
SCF = "Gerar SCF convergido"


@pytest.fixture
def menus(monkeypatch):
    shown: list[QMenu] = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


@pytest.fixture
def fake_xcrysden(tmp_path):
    """A stand-in XCrySDen install: a folder holding an executable ``xcrysden`` script."""
    folder = tmp_path / "xcrysden-install"
    folder.mkdir()
    script = folder / "xcrysden"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def menu_of(window, path, menus) -> QMenu:
    window.service.detect_now(path.parent)  # fills the sniff cache the menu reads
    window._show_item_menu([path], QPoint())
    return menus[-1]


def item(menu: QMenu):
    return next((a for a in menu.actions() if a.text() == ITEM), None)


def configure(window, where) -> None:
    window.config.paths.xcrysden_path = None if where is None else str(where)


PW_FILES = [
    ("03_bands", "bands.in", "--pwi"),  # pw.x inputs
    ("01_relax", "si.rel.in", "--pwi"),
    ("02_scf", "scf.out", "--pwo"),  # pw.x outputs
    ("03_bands", "bands.out", "--pwo"),
    ("04_pdos", "nscf.out", "--pwo"),
    ("01_relax", "si.rel.out", "--pwo"),
]


@pytest.mark.parametrize(("folder", "name", "option"), PW_FILES)
def test_the_item_is_in_pw_inputs_and_outputs(
    main_window, demo_project, menus, launched, fake_xcrysden, folder, name, option
):
    configure(main_window, fake_xcrysden.parent)
    path = demo_project / folder / name
    action = item(menu_of(main_window, path, menus))
    assert action is not None and action.isEnabled()
    assert action.toolTip() == ITEM  # Qt's default: no reason to give
    action.trigger()  # --pwi for an input, --pwo for an output
    assert launched == [(str(fake_xcrysden), [option, str(path)], str(path.parent))]


@pytest.mark.parametrize(
    ("folder", "name"),
    [
        ("03_bands", "bands_pp.out"),  # bands.x output
        ("04_pdos", "projwfc.out"),  # projwfc.x output
        ("03_bands", "bands.dat.gnu"),
        ("04_pdos", "pdos.dat.pdos_tot"),
    ],
)
def test_other_files_have_no_item(main_window, demo_project, menus, fake_xcrysden, folder, name):
    configure(main_window, fake_xcrysden.parent)
    assert item(menu_of(main_window, demo_project / folder / name, menus)) is None


def test_folders_and_selections_have_no_item(main_window, demo_project, menus, fake_xcrysden):
    configure(main_window, fake_xcrysden.parent)
    window = main_window
    window.service.detect_now(demo_project / "03_bands")
    window._show_item_menu([demo_project / "03_bands"], QPoint())
    assert item(menus[-1]) is None
    both = [demo_project / "03_bands" / "bands.in", demo_project / "03_bands" / "bands.out"]
    window._show_item_menu(both, QPoint())  # the multi-selection menu has no per-item actions
    assert item(menus[-1]) is None


def test_an_unsniffed_file_has_no_item_and_asks_for_detection(
    main_window, demo_project, menus, fake_xcrysden, monkeypatch
):
    configure(main_window, fake_xcrysden.parent)
    requested = []
    folder = demo_project / "02_scf"
    monkeypatch.setattr(main_window.service, "file_sniff", lambda path: None)
    monkeypatch.setattr(main_window.service, "results", lambda f: requested.append(f))
    main_window._show_item_menu([folder / "scf.out"], QPoint())
    assert item(menus[-1]) is None and requested == [folder]


def test_an_empty_path_disables_the_item_with_the_reason(main_window, demo_project, menus):
    assert main_window.config.paths.xcrysden_path is None  # the default
    menu = menu_of(main_window, demo_project / "02_scf" / "scf.out", menus)
    action = item(menu)
    assert action is not None and not action.isEnabled()
    assert action.toolTip() == NOT_SET
    assert menu.toolTipsVisible()


@pytest.mark.parametrize("form", ["folder", "script"])
def test_the_folder_or_the_script_launches_xcrysden(
    main_window, demo_project, menus, launched, fake_xcrysden, form
):
    configure(main_window, fake_xcrysden.parent if form == "folder" else fake_xcrysden)
    scf_in = demo_project / "01_relax" / "si.rel.in"
    item(menu_of(main_window, scf_in, menus)).trigger()
    scf_out = demo_project / "02_scf" / "scf.out"
    item(menu_of(main_window, scf_out, menus)).trigger()
    assert launched == [
        (str(fake_xcrysden), ["--pwi", str(scf_in)], str(scf_in.parent)),
        (str(fake_xcrysden), ["--pwo", str(scf_out)], str(scf_out.parent)),
    ]


def test_a_wrong_path_is_disabled_with_its_reason(
    main_window, demo_project, menus, launched, tmp_path
):
    path = demo_project / "02_scf" / "scf.out"
    missing = tmp_path / "nowhere"
    empty = tmp_path / "empty"
    empty.mkdir()
    plain = tmp_path / "plain" / "xcrysden"
    plain.parent.mkdir()
    plain.write_text("#!/bin/sh\n", encoding="utf-8")
    plain.chmod(0o644)
    cases = [
        (missing, f"XCrysDen não encontrado: {missing}."),
        (empty, f"Não há o executável xcrysden em {empty}."),
        (plain, f"{plain} não é executável."),
    ]
    for where, reason in cases:
        configure(main_window, where)
        action = item(menu_of(main_window, path, menus))
        assert action is not None and not action.isEnabled(), where
        assert action.toolTip() == reason
        action.trigger()  # a disabled item does nothing
    assert launched == []


def test_a_config_reload_applies_without_restart(
    main_window, demo_project, menus, fake_xcrysden, tmp_path
):
    window = main_window
    path = demo_project / "02_scf" / "scf.out"
    config = tmp_path / "config.yaml"
    config.write_text(
        f"paths:\n  local_root: {demo_project}\n  xcrysden_path: {fake_xcrysden.parent}\n",
        encoding="utf-8",
    )
    window.load_config_file(config)
    assert window.config.paths.xcrysden_path == str(fake_xcrysden.parent)
    assert item(menu_of(window, path, menus)).isEnabled()
    config.write_text(
        f"paths:\n  local_root: {demo_project}\n  xcrysden_path: ''\n", encoding="utf-8"
    )
    window.reload_config()
    assert window.config.paths.xcrysden_path is None
    assert not item(menu_of(window, path, menus)).isEnabled()


def test_the_item_follows_visualizacao_3d_and_precedes_the_converged_scf(
    main_window, demo_project, fake_xcrysden
):
    configure(main_window, fake_xcrysden.parent)
    path = demo_project / "01_relax" / "si.rel.in"
    menu = main_window.item_actions.menu(
        path, summary=True, structure=True, scf="", xcrysden="--pwi"
    )
    assert menu_texts(menu)[:4] == ["Resumo", STRUCTURE, ITEM, SCF]
    assert menu.actions()[4].isSeparator()


def test_a_failed_start_is_reported(main_window, demo_project, menus, fake_xcrysden, monkeypatch):
    configure(main_window, fake_xcrysden.parent)
    monkeypatch.setattr(
        QProcess, "startDetached", staticmethod(lambda program, args=(), cwd="": (False, 0))
    )
    item(menu_of(main_window, demo_project / "02_scf" / "scf.out", menus)).trigger()
    message = main_window.status.message.text()
    assert message == "Não foi possível abrir scf.out com XCrysDen."
