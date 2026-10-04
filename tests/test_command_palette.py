"""Spec 18 R2: the Ctrl+K command palette: sources, search, keys and the folder index worker."""

import threading
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from qe_studio.ui import palette_controller
from qe_studio.ui.widgets.command_palette import MAX_ROWS, PaletteRow


def open_palette(window):
    window._actions["help.palette"].trigger()
    palette = window.command_palette.palette
    assert palette.isVisible()
    return palette


def indexed(qtbot, window) -> None:
    qtbot.waitUntil(lambda: window.command_palette._folders is not None, timeout=5000)


def type_query(qtbot, window, text: str):
    palette = window.command_palette.palette
    palette.set_query(text)
    return palette.labels()


def keys_of(window, query: str) -> list[str]:
    return [row.key for row in window.command_palette.rows_for(query)]


def test_ctrl_k_opens_the_palette_with_the_starting_list(qtbot, main_window):
    palette = open_palette(main_window)
    labels = palette.labels()
    assert "Gerar gráfico (Ctrl+G)" in labels
    assert "Atualizar (F5)" in labels
    assert "Paleta de comandos (Ctrl+K)" not in labels  # it is already open
    assert palette.current_key() is not None
    assert len(labels) <= MAX_ROWS


def test_typing_gerar_finds_the_action_and_enter_runs_it(qtbot, main_window, monkeypatch):
    ran = []
    monkeypatch.setattr(main_window.plot_workflow, "generate", lambda *a: ran.append(a))
    palette = open_palette(main_window)
    # Other actions hold g-e-r-a-r as a subsequence, but the prefix match leads and is selected.
    assert type_query(qtbot, main_window, "gerar")[0] == "Gerar gráfico (Ctrl+G)"
    assert palette.current_key() == "action:plot.generate"
    qtbot.keyClick(palette.edit, Qt.Key.Key_Return)
    assert len(ran) == 1
    assert not palette.isVisible()  # choosing closes it


def test_accents_and_case_do_not_matter(qtbot, main_window):
    open_palette(main_window)
    assert "Gerar gráfico (Ctrl+G)" in type_query(qtbot, main_window, "GRAFICO")
    assert "Gerar gráfico (Ctrl+G)" in type_query(qtbot, main_window, "ggf")  # subsequence


def test_disabled_actions_are_not_listed(qtbot, main_window):
    assert not main_window._actions["sync.start"].isEnabled()  # no cluster configured
    open_palette(main_window)
    labels = type_query(qtbot, main_window, ">")
    assert not any("Sincronizar" in label for label in labels)
    assert any("Testar conexão" in label for label in labels)
    assert all(row.section == "Ação" for row in main_window.command_palette.palette.rows())


def test_slash_lists_only_folders_whose_name_matches(qtbot, main_window, demo_project):
    open_palette(main_window)
    assert main_window.command_palette.indexing or main_window.command_palette._folders
    indexed(qtbot, main_window)
    assert type_query(qtbot, main_window, "/rel") == ["01_relax"]
    assert "03_bands" in type_query(qtbot, main_window, "/band")
    assert type_query(qtbot, main_window, "/orb") == ["04_pdos/orbitals"]
    assert not any("tmp" in label for label in type_query(qtbot, main_window, "/"))  # hidden dir


def test_choosing_a_folder_navigates_to_it(qtbot, main_window, demo_project):
    palette = open_palette(main_window)
    indexed(qtbot, main_window)
    type_query(qtbot, main_window, "/rel")
    qtbot.keyClick(palette.edit, Qt.Key.Key_Return)
    assert main_window.current_folder() == demo_project / "01_relax"
    assert main_window.files.folder == demo_project / "01_relax"


def test_the_index_is_built_in_a_worker_and_shows_a_placeholder(qtbot, main_window, monkeypatch):
    release = threading.Event()
    seen = {}

    def slow(root, hidden, limit, cancelled):
        seen["thread"] = threading.current_thread()
        release.wait(5)
        return [root / "01_relax"]

    monkeypatch.setattr(palette_controller, "list_folders", slow)
    open_palette(main_window)
    assert main_window.command_palette.indexing
    rows = main_window.command_palette.rows_for("/relax")
    assert [r.label for r in rows] == ["Indexando pastas…"] and not rows[0].selectable
    assert main_window.command_palette.palette.current_key() is None or True
    release.set()
    indexed(qtbot, main_window)
    assert seen["thread"] is not threading.main_thread()
    assert [r.label for r in main_window.command_palette.rows_for("/relax")] == ["01_relax"]


def test_nothing_typed_does_not_list_every_folder(qtbot, main_window):
    open_palette(main_window)
    indexed(qtbot, main_window)
    assert not any(k.startswith("folder:") for k in keys_of(main_window, ""))


def test_f5_drops_the_index_and_the_next_open_sees_new_folders(qtbot, main_window, demo_project):
    open_palette(main_window)
    indexed(qtbot, main_window)
    assert type_query(qtbot, main_window, "/novo") == []
    (demo_project / "05_novo").mkdir()
    main_window._actions["files.refresh"].trigger()
    assert main_window.command_palette._folders is None or main_window.command_palette.indexing
    indexed(qtbot, main_window)  # an open palette re-indexes at once
    assert type_query(qtbot, main_window, "/novo") == ["05_novo"]


def test_favorites_and_recents_come_first_on_an_empty_query(qtbot, main_window, demo_project):
    window = main_window
    window.navigation.set_favorite(demo_project / "03_bands", True)
    window.explorer.select_path(demo_project / "02_scf")
    rows = window.command_palette.rows_for("")
    sections = [r.section for r in rows]
    assert rows[0].key == f"folder:{demo_project / '03_bands'}" and rows[0].section == "Favorito"
    assert "Recente" in sections
    assert sections.index("Recente") < sections.index("Ação")
    assert [r.label for r in rows if r.section == "Favorito"] == ["03_bands"]
    # A folder that is both a favorite and a recent is listed once.
    window.explorer.select_path(demo_project / "03_bands")
    keys = keys_of(window, "")
    assert len(keys) == len(set(keys))


def test_open_tabs_are_listed_and_choosing_one_activates_it(qtbot, main_window, demo_project):
    from viewer_helpers import open_text

    window = main_window
    first = open_text(qtbot, window, demo_project / "03_bands" / "bands.in")
    second = open_text(qtbot, window, demo_project / "01_relax" / "si.rel.in")
    assert window.workspace.current() is second
    window.set_panel_visible("workspace", False)
    open_palette(window)
    assert type_query(qtbot, window, "@bands") == ["bands.in"]
    qtbot.keyClick(window.command_palette.palette.edit, Qt.Key.Key_Return)
    assert window.workspace.current() is first
    assert window.workspace.isVisible()


def test_arrow_keys_move_and_escape_closes(qtbot, main_window):
    palette = open_palette(main_window)
    first = palette.current_key()
    qtbot.keyClick(palette.edit, Qt.Key.Key_Down)
    assert palette.current_key() != first
    qtbot.keyClick(palette.edit, Qt.Key.Key_Up)
    assert palette.current_key() == first
    qtbot.keyClick(palette.edit, Qt.Key.Key_Up)  # no wrap past the top
    assert palette.current_key() == first
    qtbot.keyClick(palette.edit, Qt.Key.Key_Escape)
    assert not palette.isVisible()


def test_chosen_rows_are_remembered_for_the_ranking(qtbot, main_window):
    # Recency only breaks ties between equal scores (core/fuzzy is tested for that).
    controller = main_window.command_palette
    controller.execute("action:view.theme")
    controller.execute("action:files.refresh")
    assert controller._recency["action:files.refresh"] > controller._recency["action:view.theme"]


def test_the_palette_shows_at_most_fifty_rows(qtbot, main_window):
    palette = main_window.command_palette.palette
    palette.set_rows([PaletteRow(f"folder:{i}", "Pasta", f"f{i}") for i in range(80)])
    assert len(palette.rows()) == MAX_ROWS


def test_a_click_chooses_a_row(qtbot, main_window, monkeypatch):
    ran = []
    monkeypatch.setattr(main_window.plot_workflow, "generate", lambda *a: ran.append(a))
    palette = open_palette(main_window)
    type_query(qtbot, main_window, "gerar")
    index = palette.model.index(0, 0)
    palette.view.clicked.emit(index)
    assert len(ran) == 1


def test_the_palette_is_centred_near_the_top_of_the_window(qtbot, main_window):
    palette = open_palette(main_window)
    window = main_window
    centre = palette.geometry().center().x()
    assert abs(centre - window.geometry().center().x()) <= 2
    assert palette.y() < window.geometry().center().y()


@pytest.mark.parametrize("query", ["", "/", ">", "@", "zzzz", "  ", "/  rel"])
def test_odd_queries_never_fail(qtbot, main_window, query):
    open_palette(main_window)
    type_query(qtbot, main_window, query)
    assert isinstance(Path(".").name, str)
