"""Spec 5: grid cards without sizes, the ".." shortcut and the file/folder context menu.

Spec 9 adds "Plotar" to the menu of an SCF output, spec 12 "Resumo" to every QE output."""

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox

from grid_helpers import menu_texts, rows, show_folder
from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.core.sniff import FileKind, FileSniff
from qe_studio.ui.dialogs.open_with import OpenWithDialog
from qe_studio.ui.dialogs.rename import RenameDialog
from qe_studio.ui.widgets import context_menu
from qe_studio.ui.widgets.fs_model import SORT_DATE, SORT_NAME, SORT_SIZE

from conftest import FIXTURES

MENU = ["Abrir local de origem", "Abrir com", "Copiar", "Renomear"]
# Folders also offer the star after "Copiar" (spec 16 R4.1).
FOLDER_MENU = [
    "Abrir local de origem",
    "Abrir com",
    "Copiar",
    "Adicionar aos favoritos",
    "Renomear",
]


def generate(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=False)
    return blocker.args[0]


# -- R1: grid without sizes ----------------------------------------------------------------------
def test_grid_cards_show_the_state_only(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    files = window.files
    delegate = files.view.itemDelegate()
    folder = demo_project / "03_bands"
    output = folder / "scf.out"
    cut = FileSniff(output, FileKind.PW_OUT, job_done=False)
    monkeypatch.setattr(window.service, "file_sniff", lambda p: cut if p == output else None)
    assert delegate._meta(folder / "bands.in", False, 5000) == ("", "text_meta")
    assert delegate._meta(output, False, 5000) == ("INCOMPLETO", "warning")

    show_folder(qtbot, window, folder)
    entries = [(files.proxy.path(i), files.proxy.fs.size(files.proxy.mapToSource(i))) for i in
               rows(files)[1:] if not files.proxy.is_dir(i)]  # fmt: skip
    metas = [delegate._meta(path, False, size)[0] for path, size in entries]
    assert metas and not any(unit in meta for meta in metas for unit in ("B", "KB", "MB"))
    files.set_grid_mode(False)  # list mode keeps the size (spec 5 R1.3)
    assert all("B" in delegate._meta(path, False, size)[0] for path, size in entries)
    assert delegate._meta(output, False, 5000) == ("4.9 KB · INCOMPLETO", "warning")


# -- R2: ".." ------------------------------------------------------------------------------------
def test_up_entry_is_first_in_any_order(qtbot, main_window, demo_project):
    window = main_window
    files = window.files
    show_folder(qtbot, window, demo_project / "03_bands")
    for column in (SORT_SIZE, SORT_DATE, SORT_NAME):
        files.set_sort(column)
        items = rows(files)
        assert files.proxy.is_up(items[0]) and files.proxy.path(items[0]) == demo_project
        assert not any(files.proxy.is_up(i) for i in items[1:])
    assert files.header.count.text() == f"({len(rows(files)) - 1})"  # ".." is not counted

    show_folder(qtbot, window, demo_project, up=False)  # the project root has no ".."
    assert not any(files.proxy.is_up(i) for i in rows(files))
    assert files.header.count.text() == f"({len(rows(files))})"


def test_up_entry_goes_to_the_parent(qtbot, main_window, demo_project):
    window = main_window
    files = window.files
    show_folder(qtbot, window, demo_project / "04_pdos" / "orbitals")
    files.view.activated.emit(rows(files)[0])
    assert files.folder == demo_project / "04_pdos"
    assert window.explorer.current_path() == demo_project / "04_pdos"  # the tree follows
    qtbot.waitUntil(lambda: files.proxy.is_up(rows(files)[0]), timeout=5000)
    files.view.activated.emit(rows(files)[0])
    assert files.folder == demo_project and window.current_folder() == demo_project
    assert window.status.path.full_text() == "."


def test_keyboard_goes_up(qtbot, main_window, demo_project):
    window = main_window
    window.show()
    qtbot.waitExposed(window)
    show_folder(qtbot, window, demo_project / "04_pdos" / "orbitals")
    window.files.view.setFocus()
    qtbot.keyClick(window.files.view, Qt.Key.Key_Backspace)
    assert window.files.folder == demo_project / "04_pdos"
    qtbot.keyClick(window.files.view, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    assert window.files.folder == demo_project
    qtbot.keyClick(window.files.view, Qt.Key.Key_Backspace)  # never above the project
    assert window.files.folder == demo_project


# -- R3: context menu ----------------------------------------------------------------------------
def test_right_click_requests_a_menu(qtbot, main_window, demo_project, monkeypatch):
    menus = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: menus.append(pos))  # never blocks
    window = main_window
    window.show()
    qtbot.waitExposed(window)
    files = window.files
    show_folder(qtbot, window, demo_project / "03_bands")
    up, item = rows(files)[:2]
    viewport = files.view.viewport()
    with qtbot.assertNotEmitted(files.item_menu_requested):
        files._on_context_menu(files.view.visualRect(up).center())
        files._on_context_menu(QPoint(viewport.width() - 2, viewport.height() - 2))  # empty
    with qtbot.waitSignal(files.item_menu_requested) as blocker:
        files._on_context_menu(files.view.visualRect(item).center())
    assert blocker.args[0] == [files.proxy.path(item)]

    tree = window.explorer
    index = tree.proxy.index_for(demo_project / "02_scf")
    with qtbot.waitSignal(tree.item_menu_requested) as blocker:
        tree._on_context_menu(tree.tree.visualRect(index).center())
    assert blocker.args[0] == [demo_project / "02_scf"]
    assert len(menus) == 2  # the main window showed both


def test_menu_has_exactly_the_expected_actions(main_window, demo_project, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMenu, "exec", lambda menu, pos: shown.append([(a.text(), a.isEnabled()) for a in menu.actions()])
    )  # fmt: skip
    window = main_window
    window.files.item_menu_requested.emit([demo_project / "03_bands" / "bands.in"], QPoint(5, 5))
    window.explorer.item_menu_requested.emit([demo_project / "04_pdos"], QPoint(5, 5))
    window._show_item_menu([demo_project], QPoint())
    assert [[text for text, _ in menu] for menu in shown] == [MENU, FOLDER_MENU, FOLDER_MENU]
    assert [enabled for _, enabled in shown[1]] == [True] * 5
    assert [enabled for _, enabled in shown[2]] == [True, True, True, True, False]  # the root


def detected(window, folder: Path) -> None:
    window.service.detect_now(folder)  # fills the sniff cache the menu reads


def test_scf_output_menu_starts_with_plotar(main_window, demo_project, monkeypatch):
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    window = main_window
    for folder in ("02_scf", "03_bands"):  # a bands folder also holds an SCF output
        detected(window, demo_project / folder)
        window._show_item_menu([demo_project / folder / "scf.out"], QPoint())
    assert [menu_texts(menu) for menu in shown] == [["Plotar", "Resumo", *MENU]] * 2
    assert shown[0].actions()[2].isSeparator() and len(shown[0].actions()) == 7


@pytest.mark.parametrize(
    "folder, name, top",
    [
        ("03_bands", "bands.out", ["Resumo"]),  # pw.x bands
        ("03_bands", "bands_pp.out", ["Resumo"]),  # bands.x
        ("03_bands", "bands.in", []),
        ("03_bands", "bands.dat.gnu", []),
        ("04_pdos", "nscf.out", ["Resumo"]),
        ("04_pdos", "projwfc.out", ["Resumo"]),
        ("01_relax", "si.rel.out", ["Resumo", "Gerar SCF convergido"]),  # spec 24
        ("01_relax", "si.rel.in", []),
    ],
)
def test_other_files_have_no_plotar_and_only_outputs_have_resumo(
    main_window, demo_project, monkeypatch, folder, name, top
):
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    detected(main_window, demo_project / folder)
    main_window._show_item_menu([demo_project / folder / name], QPoint())
    assert menu_texts(shown[0]) == [*top, *MENU]
    assert shown[0].actions()[len(top)].isSeparator() == bool(top)  # one group, then a separator
    main_window._show_item_menu([demo_project / folder], QPoint())  # folders have neither
    assert menu_texts(shown[1]) == FOLDER_MENU


def test_unsniffed_file_has_no_plotar_or_resumo_but_asks_for_detection(
    main_window, demo_project, monkeypatch
):
    window = main_window
    folder = demo_project / "02_scf"
    shown, requested = [], []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu_texts(menu)))
    monkeypatch.setattr(window.service, "file_sniff", lambda path: None)  # not in the cache
    monkeypatch.setattr(window.service, "results", lambda f: requested.append(f))
    window._show_item_menu([folder / "scf.out"], QPoint())
    assert shown == [MENU] and requested == [folder]


def test_plotar_opens_the_convergence_tab_without_saving(
    qtbot, main_window, demo_project, monkeypatch
):
    window = main_window
    folder = demo_project / "02_scf"
    shutil.copy(FIXTURES / "al_bands/al.scf.out", folder / "al.scf.out")
    detected(window, folder)
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: menu.actions()[0].trigger())  # "Plotar"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window._show_item_menu([folder / "al.scf.out"], QPoint())
    tabs = window.workspace.tabs
    assert tabs.tabText(tabs.currentIndex()) == "Convergência SCF · al.scf.out"
    assert not (folder / "plots").exists()


def test_renaming_an_scf_output_closes_its_plot_tab(qtbot, main_window, demo_project, new_names):
    window = main_window
    folder = demo_project / "02_scf"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.plot_file(folder / "scf.out", "scf")
    session = blocker.args[0]
    window.params.set_param("scale", "linear")  # pending settings travel with the rename
    new_names.append("scf-si.out")
    window.rename_path(folder / "scf.out")
    assert (folder / "scf-si.out").is_file() and window.workspace.widget_for(session.key) is None
    assert read_plot_file(folder, "scf")[0]["scale"] == "linear"


def open_with_menu(window, path):
    menu = window.item_actions.menu(path)
    submenu = menu.actions()[1].menu()
    submenu.aboutToShow.emit()
    return menu, submenu


def test_open_with(main_window, demo_project, fake_apps, launched, monkeypatch):
    window = main_window
    path = demo_project / "03_bands" / "bands.in"
    _menu, submenu = open_with_menu(window, path)
    texts = ["Other (padrão)", "Fake", "", "Outro programa…"]
    assert [a.text() for a in submenu.actions()] == texts
    submenu.aboutToShow.emit()  # opening again does not add entries
    assert [a.text() for a in submenu.actions()] == texts
    submenu.actions()[1].trigger()
    submenu.actions()[0].trigger()
    folder = str(path.parent)
    assert launched == [
        ("fake-editor", [str(path)], folder),
        ("other", ["--open", path.as_uri()], folder),
    ]
    monkeypatch.setattr(context_menu, "ask_command", lambda parent, name: ["my prog", "--x"])
    submenu.actions()[3].trigger()
    assert launched[-1] == ("my prog", ["--x", str(path)], folder)
    monkeypatch.setattr(context_menu, "ask_command", lambda parent, name: ["broken"])
    submenu.actions()[3].trigger()
    assert window.status.message.text() == "Não foi possível abrir bands.in com broken."

    _menu, submenu = open_with_menu(window, demo_project / "04_pdos")  # inode/directory
    assert [a.text() for a in submenu.actions()] == ["Other (padrão)", "", "Outro programa…"]
    image = demo_project / "fig.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    _menu, submenu = open_with_menu(window, image)
    first = submenu.actions()[0]
    assert first.text() == "Nenhum programa encontrado" and not first.isEnabled()


def test_windows_variants(main_window, demo_project, launched, monkeypatch):
    monkeypatch.setattr(context_menu, "IS_WINDOWS", True)
    path = demo_project / "03_bands" / "bands.in"
    _menu, submenu = open_with_menu(main_window, path)
    assert [a.text() for a in submenu.actions()] == ["Escolher programa…"]
    submenu.actions()[0].trigger()
    main_window.item_actions.reveal(path)
    assert launched == [
        ("rundll32", ["shell32.dll,OpenAs_RunDLL", str(path)], str(path.parent)),
        ("explorer", [f"/select,{path}"], ""),
    ]


def test_copy_puts_the_item_on_the_clipboard(main_window, demo_project):
    path = demo_project / "03_bands" / "bands.in"
    main_window.item_actions.copy(path)
    data = QApplication.clipboard().mimeData()
    assert [url.toLocalFile() for url in data.urls()] == [str(path)]
    assert data.text() == str(path)
    assert bytes(data.data("x-special/gnome-copied-files")) == f"copy\n{path.as_uri()}".encode()
    assert main_window.status.message.text() == "Copiado: bands.in"


def test_reveal_in_file_manager(main_window, demo_project, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(opened.append))
    actions = main_window.item_actions
    path = demo_project / "03_bands" / "bands.in"
    asked = []
    monkeypatch.setattr(actions, "_show_items_dbus", lambda p: asked.append(p) or True)
    actions.reveal(path)
    assert asked == [[path]] and opened == []

    class FailedCall:  # no FileManager1 on this desktop: the answer is an error
        def isError(self):
            return True

        def error(self):
            return type("Error", (), {"message": lambda self: "ServiceUnknown"})()

        def deleteLater(self):
            pass

    call = FailedCall()
    actions._reveals[call] = [path]
    actions._on_reveal_finished(call)
    assert opened == [QUrl.fromLocalFile(str(path.parent))]
    monkeypatch.setattr(actions, "_show_items_dbus", lambda p: False)  # no session bus
    actions.reveal(demo_project / "04_pdos")
    assert opened[-1] == QUrl.fromLocalFile(str(demo_project))


@pytest.fixture
def new_names(monkeypatch):
    """Answers of the rename dialog, in order."""
    answers = []
    monkeypatch.setattr("qe_studio.ui.main_window.ask_rename", lambda parent, path: answers.pop(0))
    return answers


def selected_in_grid(window) -> Path | None:
    index = window.files.view.currentIndex()
    return window.files.proxy.path(index) if index.isValid() else None


def test_rename_file(qtbot, main_window, demo_project, new_names):
    window = main_window
    folder = demo_project / "03_bands"
    old, new = folder / "bands.in", folder / "bands-si.in"
    show_folder(qtbot, window, folder)
    window.open_file(old)
    new_names.extend([None, "bands-si.in"])
    window.rename_path(old)  # cancelled
    assert old.exists() and window.workspace.widget_for(str(old)) is not None
    window.rename_path(old)
    assert new.is_file() and not old.exists()
    assert window.workspace.widget_for(str(old)) is None  # its tab is closed
    assert window.status.message.text() == "Renomeado: bands.in → bands-si.in"
    qtbot.waitUntil(lambda: selected_in_grid(window) == new, timeout=5000)


def test_rename_folder_keeps_plot_settings_and_memory(qtbot, main_window, demo_project, new_names):
    window = main_window
    folder = demo_project / "03_bands"
    window.memory.set_labels(folder, ["G", "X"])
    session = generate(qtbot, window, folder)
    window.params.set_param("emin", -3.0)  # pending: the debounced write has not run yet
    assert window.plot_settings.is_dirty(session.key)
    new_names.append("03_bands_si")
    window.rename_path(folder)
    new = demo_project / "03_bands_si"
    stored, _ = read_plot_file(new, "bands")
    assert stored["emin"] == -3.0 and not window.plot_settings.is_dirty(session.key)
    assert window.workspace.widget_for(session.key) is None
    assert window.memory.labels(new) == ["G", "X"] and window.memory.labels(folder) is None


def test_rename_the_current_folder(qtbot, main_window, demo_project, new_names):
    window = main_window
    old = demo_project / "04_pdos"
    show_folder(qtbot, window, old / "orbitals")
    new_names.append("04_dos")
    window.rename_path(old)
    new = demo_project / "04_dos"
    qtbot.waitUntil(lambda: window.files.folder == new / "orbitals", timeout=5000)
    assert window.current_folder() == new / "orbitals"


def test_rename_failure_is_reported(main_window, demo_project, new_names, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a[2])))

    def refuse(path, name):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("qe_studio.ui.main_window.rename_item", refuse)
    window = main_window
    path = demo_project / "03_bands" / "bands.in"
    window.open_file(path)
    new_names.append("x.in")
    window.rename_path(path)
    assert warnings == ["Não foi possível renomear bands.in: Permission denied"]
    assert path.exists() and window.workspace.widget_for(str(path)) is not None


def test_rename_dialog_validates_in_place(qtbot, tmp_path):
    (tmp_path / "bands.in").write_text("x")
    (tmp_path / "scf.in").write_text("y")
    dialog = RenameDialog(tmp_path / "bands.in")
    qtbot.addWidget(dialog)
    assert dialog.edit.selectedText() == "bands"  # the extension is kept when typing
    dialog.edit.setText("scf.in")
    dialog.accept()
    assert not dialog.error.isHidden() and dialog.error.text() == "Já existe “scf.in” nesta pasta."
    assert dialog.result() != QDialog.DialogCode.Accepted and dialog.new_name is None
    dialog.edit.setText("nscf.in")
    assert dialog.error.isHidden()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted and dialog.new_name == "nscf.in"

    folder = tmp_path / "run.v2"
    folder.mkdir()
    dialog = RenameDialog(folder)
    qtbot.addWidget(dialog)
    assert dialog.edit.selectedText() == "run.v2"
    dialog.accept()  # unchanged: accepted, nothing to do
    assert dialog.result() == QDialog.DialogCode.Accepted and dialog.new_name is None


def test_open_with_dialog(qtbot):
    dialog = OpenWithDialog("bands.in")
    qtbot.addWidget(dialog)
    assert not dialog.ok.isEnabled()
    dialog.edit.setText('code "unclosed')
    dialog.accept()
    assert not dialog.error.isHidden() and dialog.argv is None
    dialog.edit.setText('"/opt/My App/app" --new-window')
    dialog.accept()
    assert dialog.argv == ["/opt/My App/app", "--new-window"]
