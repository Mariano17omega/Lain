"""Spec 16 R4: favorite and recent folders in the explorer, kept between sessions."""

import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtWidgets import QMenu

from grid_helpers import menu_texts

JSON = "navigation.json"


@pytest.fixture
def menus(monkeypatch):
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


def trigger(menu, text: str) -> None:
    next(a for a in menu.actions() if a.text() == text).trigger()


def favorite(window, folder: Path, menus) -> None:
    window._show_item_menu([folder], QPoint())
    trigger(menus[-1], "Adicionar aos favoritos")


def go(window, folder: Path) -> None:
    window.explorer.select_path(folder)
    assert window.files.folder == folder


def test_a_folder_menu_offers_favorites_after_copiar(main_window, demo_project, menus):
    window = main_window
    window._show_item_menu([demo_project / "03_bands"], QPoint())
    assert menu_texts(menus[-1]) == [
        "Abrir local de origem",
        "Abrir com",
        "Enviar ao cluster",  # spec 27; disabled here (no cluster configured)
        "Copiar",
        "Adicionar aos favoritos",
        "Renomear",
    ]
    window._show_item_menu([demo_project / "03_bands" / "bands.in"], QPoint())  # files: no star
    assert "Adicionar aos favoritos" not in menu_texts(menus[-1])


def test_adding_and_removing_a_favorite(main_window, demo_project, menus, tmp_path):
    window = main_window
    section = window.explorer.favorites
    assert section.isHidden()  # nothing to list yet
    favorite(window, demo_project / "03_bands", menus)
    assert not section.isHidden() and section.labels() == ["03_bands"]
    assert window.status.message.text() == "Adicionado aos favoritos: 03_bands"
    data = json.loads((tmp_path / JSON).read_text())  # saved at once, with relative paths
    assert list(data["projects"].values())[0]["favorites"] == ["03_bands"]
    assert str(demo_project) not in json.dumps(data["projects"][next(iter(data["projects"]))])

    window._show_item_menu([demo_project / "03_bands"], QPoint())
    assert "Remover dos favoritos" in menu_texts(menus[-1])
    trigger(menus[-1], "Remover dos favoritos")
    assert section.isHidden() and window.navigation.store.favorites() == []


def test_favorites_survive_a_restart(window_factory, demo_project, menus, tmp_path):
    first = window_factory()
    favorite(first, demo_project / "03_bands", menus)
    favorite(first, demo_project / "04_pdos" / "orbitals", menus)
    first.close()
    second = window_factory()  # a new window: the app started again
    section = second.explorer.favorites
    assert not section.isHidden()
    assert section.labels() == ["03_bands", "04_pdos/orbitals"]
    assert [e.path for e in section.entries] == [
        demo_project / "03_bands",
        demo_project / "04_pdos" / "orbitals",
    ]
    assert section.header.text() == "FAVORITOS (2)"


def test_clicking_a_favorite_navigates(main_window, demo_project, menus):
    window = main_window
    favorite(window, demo_project / "04_pdos", menus)
    section = window.explorer.favorites
    section._on_clicked(section.list.item(0))
    assert window.files.folder == demo_project / "04_pdos"
    assert window.explorer.current_path() == demo_project / "04_pdos"


def test_a_missing_favorite_is_dimmed_and_stays(window_factory, demo_project, menus, tmp_path):
    first = window_factory()
    favorite(first, demo_project / "02_scf", menus)
    first.close()
    (demo_project / "02_scf" / "scf.out").unlink()
    (demo_project / "02_scf").rmdir()
    window = window_factory()
    section = window.explorer.favorites
    assert section.labels() == ["02_scf"] and not section.entries[0].exists
    assert section.list.item(0).toolTip() == "não encontrada"
    section._on_clicked(section.list.item(0))  # does not navigate
    assert window.status.message.text() == "Pasta não existe mais: 02_scf"
    assert window.files.folder != demo_project / "02_scf"


def test_the_menu_of_several_folders(main_window, demo_project, menus):
    window = main_window
    go(window, demo_project)
    folders = [demo_project / "01_relax", demo_project / "02_scf"]
    window._show_item_menu(folders, QPoint())
    assert "Adicionar aos favoritos" in menu_texts(menus[-1])
    trigger(menus[-1], "Adicionar aos favoritos")
    assert window.explorer.favorites.labels() == ["01_relax", "02_scf"]
    window._show_item_menu(folders, QPoint())
    assert "Remover dos favoritos" in menu_texts(menus[-1])
    window._show_item_menu(
        [demo_project / "01_relax", demo_project / "03_bands" / "bands.in"], QPoint()
    )
    assert not {"Adicionar aos favoritos", "Remover dos favoritos"} & set(menu_texts(menus[-1]))
    trigger(menus[1], "Remover dos favoritos")
    assert window.explorer.favorites.isHidden()


# -- recents -------------------------------------------------------------------------------------
def test_recents_are_the_last_visited_folders_newest_first(main_window, demo_project):
    window = main_window
    section = window.explorer.recents
    for name in ("01_relax", "02_scf", "03_bands", "01_relax"):
        go(window, demo_project / name)
    go(window, demo_project)  # the root is never listed
    assert section.labels() == ["01_relax", "03_bands", "02_scf"]
    assert section.header.text() == "RECENTES (3)"


def test_recents_keep_the_last_ten(main_window, demo_project):
    store = main_window.navigation.store
    for n in range(12):
        (demo_project / f"r{n:02d}").mkdir()
        store.touch_recent(demo_project / f"r{n:02d}")
    assert len(store.recents()) == 10 and store.recents()[0] == demo_project / "r11"


def test_recents_come_back_after_a_restart_and_drop_the_missing(window_factory, demo_project):
    first = window_factory()
    for name in ("01_relax", "02_scf", "03_bands"):
        go(first, demo_project / name)
    first.close()  # flushes what the pause had not yet written
    (demo_project / "02_scf" / "scf.out").unlink()
    (demo_project / "02_scf").rmdir()
    second = window_factory()
    labels = second.explorer.recents.labels()
    assert "02_scf" not in labels and "01_relax" in labels  # gone from the list, and from the file


def test_recents_are_written_after_a_pause(qtbot, main_window, demo_project, tmp_path):
    window = main_window
    go(window, demo_project / "04_pdos")
    assert not (tmp_path / JSON).exists()  # not on every click
    qtbot.waitUntil(lambda: (tmp_path / JSON).exists(), timeout=3000)
    data = json.loads((tmp_path / JSON).read_text())
    assert next(iter(data["projects"].values()))["recents"][0] == "04_pdos"


# -- rename, sections, corrupt file --------------------------------------------------------------
def test_renaming_a_favorite_folder_moves_it(main_window, demo_project, menus, monkeypatch):
    window = main_window
    favorite(window, demo_project / "04_pdos", menus)
    go(window, demo_project / "04_pdos")
    monkeypatch.setattr("qe_studio.ui.rename_controller.ask_rename", lambda parent, path: "04_dos")
    window.rename_path(demo_project / "04_pdos")
    assert window.explorer.favorites.labels() == ["04_dos"]
    assert window.explorer.recents.labels() == ["04_dos"]
    assert window.explorer.favorites.entries[0].exists


def test_sections_remember_whether_they_are_open(window_factory, demo_project, menus, tmp_path):
    first = window_factory()
    favorite(first, demo_project / "03_bands", menus)
    first.explorer.favorites.header.click()  # collapse
    assert first.explorer.favorites.list.isHidden()
    first.close()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    assert settings.value("explorer/sections/favorites", True, type=bool) is False
    second = window_factory()
    assert second.explorer.favorites.list.isHidden()
    assert not second.explorer.favorites.isHidden()  # the header stays: it can be reopened


def test_a_corrupt_navigation_file_is_set_aside_with_a_message(window_factory, tmp_path):
    (tmp_path / JSON).write_text("{broken")
    window = window_factory()
    assert "estava corrompido" in window.status.message.text()
    assert list(tmp_path.glob("navigation.json.corrompido-*"))
    assert window.explorer.favorites.isHidden()


def test_right_click_on_a_favorite_opens_the_item_menu(main_window, demo_project, menus):
    window = main_window
    favorite(window, demo_project / "03_bands", menus)
    section = window.explorer.favorites
    shown = []
    window.explorer.item_menu_requested.connect(lambda paths, pos: shown.append(paths))
    section.menu_requested.emit([demo_project / "03_bands"], QPoint())
    assert shown == [[demo_project / "03_bands"]]
    assert "Remover dos favoritos" in menu_texts(menus[-1])
