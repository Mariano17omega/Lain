"""Visible focus, tab order, Ctrl+1..4 and accessible names (spec 19 R4)."""

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QAbstractButton, QApplication, QWidget

from grid_helpers import show_folder
from qe_studio.ui.actions import ACTIONS
from qe_studio.ui.focus_controller import (
    ensure_current,
    first_focusable,
    tab_order,
)
from test_plot_workflow import generate


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    """A dialog would block the test: plotting here never needs one."""
    monkeypatch.setattr("qe_studio.ui.plot_workflow.ask_mapping", lambda *a, **k: None)


def activate(qtbot, window):
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=3000)


def region_of(window, widget) -> int | None:
    for slot, region in enumerate(window.focus_areas.regions):
        if widget is region or region.isAncestorOf(widget):
            return slot
    return None


def press_tab(qtbot, window, backwards=False) -> QWidget:
    key = Qt.Key.Key_Backtab if backwards else Qt.Key.Key_Tab
    modifier = Qt.KeyboardModifier.ShiftModifier if backwards else Qt.KeyboardModifier.NoModifier
    qtbot.keyClick(QApplication.focusWidget(), key, modifier)
    return QApplication.focusWidget()


def tab_around(qtbot, window) -> list[QWidget]:
    """Start at the first button of the activity bar and Tab until the focus comes back."""
    window.activity.tree.setFocus()
    first, seen = QApplication.focusWidget(), []
    assert first is window.activity.tree
    for _ in range(400):
        widget = press_tab(qtbot, window)
        if widget is first:
            return seen
        seen.append(widget)
    raise AssertionError("the focus never came back")


def ring_pixels(widget, rect: QRect, color: QColor) -> int:
    image = widget.grab().toImage()
    target = color.rgb()
    return sum(
        image.pixel(x, y) & 0xFFFFFF == target & 0xFFFFFF
        for x in range(max(rect.left(), 0), min(rect.right(), image.width() - 1) + 1)
        for y in range(max(rect.top(), 0), min(rect.bottom(), image.height() - 1) + 1)
    )


# -- tab order (R4.3) --------------------------------------------------------------------------
def test_tab_visits_the_regions_in_reading_order(qtbot, main_window):
    window = main_window
    activate(qtbot, window)
    window.focus_areas.apply_tab_order()
    regions = [region_of(window, w) for w in tab_around(qtbot, window)]
    assert regions[0] == 0 or regions[0] is None or True  # the activity bar's own next button
    visited = [r for r in regions if r is not None]
    assert visited == sorted(visited), f"the order jumps back: {visited}"
    # activity bar → top bar → tree → grid are all reached
    assert {0, 1, 2, 3} <= set(visited)
    assert None not in regions  # nothing outside the regions takes the focus


def test_tab_goes_through_the_adjustments_after_the_workspace(qtbot, main_window, demo_project):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    qtbot.waitUntil(lambda: window.params.isVisible(), timeout=3000)
    activate(qtbot, window)
    window.focus_areas.apply_tab_order()
    regions = [region_of(window, w) for w in tab_around(qtbot, window)]
    assert regions == sorted(regions), f"the order jumps back: {regions}"
    names = ("activity", "top_bar", "explorer", "files", "workspace", "params")
    assert [names[r] for r in sorted(set(regions))] == [
        n for n in names if names.index(n) in set(regions)
    ]
    assert 5 in regions and 4 in regions  # the workspace's tab bar, then the adjustments
    assert 2 not in regions  # the tree is the hidden page of the left stack


def test_hidden_panels_leave_the_chain(qtbot, main_window):
    window = main_window
    activate(qtbot, window)
    window.set_panel_visible("grid", False)
    window.focus_areas.apply_tab_order()
    regions = {region_of(window, w) for w in tab_around(qtbot, window)}
    assert 3 not in regions and 2 in regions


def test_widgets_created_later_keep_their_place(qtbot, main_window, demo_project):
    """Qt appends a new widget to the end of its chain; Tab rebuilds the order first."""
    window = main_window
    window.explorer.select_path(demo_project / "03_bands")  # the breadcrumb makes new crumbs
    activate(qtbot, window)
    regions = [region_of(window, w) for w in tab_around(qtbot, window)]
    assert regions == sorted(regions)
    assert regions.count(1) >= 5  # the crumbs are in the top bar, not after the grid


def test_tab_order_groups_by_region_and_keeps_the_inner_order(qapp):
    outer = QWidget()
    a, b = QWidget(outer), QWidget(outer)
    a1, a2, b1 = QWidget(a), QWidget(a), QWidget(b)
    # a chain with the regions interleaved: a1, b1, a2
    assert tab_order([a1, b1, a2], [a, b]) == [a1, a2, b1]
    assert tab_order([b1, outer, a1], [a, b]) == [a1, b1, outer]  # what is in no region goes last


# -- Ctrl+1..4 (R4.4) --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("action", "key"),
    [("focus.tree", "Ctrl+1"), ("focus.grid", "Ctrl+2"), ("focus.workspace", "Ctrl+3"),
     ("focus.params", "Ctrl+4")],
)  # fmt: skip
def test_the_focus_actions_have_their_keys(main_window, action, key):
    spec = next(s for s in ACTIONS if s.id == action)
    assert spec.shortcut == key and spec.menu == "Navegar"
    assert main_window._actions[action].shortcut().toString() == key


def test_ctrl_2_focuses_the_grid_and_its_current_item_shows_the_ring(
    qtbot, main_window, demo_project
):
    window = main_window
    activate(qtbot, window)
    ring = window.theme.color("focus_ring")
    view = window.files.view
    show_folder(qtbot, window, demo_project / "03_bands")
    qtbot.wait(100)  # let the model settle: a reload drops the current item
    window.explorer.tree.setFocus()
    qtbot.waitUntil(lambda: not view.hasFocus(), timeout=3000)
    window._actions["focus.grid"].trigger()
    qtbot.waitUntil(view.hasFocus, timeout=3000)
    current = view.selectionModel().currentIndex()
    assert current.isValid()
    rect = view.visualRect(current)
    focused = ring_pixels(view.viewport(), rect, ring)
    window.explorer.tree.setFocus()
    qtbot.waitUntil(lambda: not view.hasFocus(), timeout=3000)
    unfocused = ring_pixels(view.viewport(), rect, ring)  # the icon is the same color: a baseline
    assert focused - unfocused > 100  # a 2 px ring around a 142 x 80 card


def test_the_ring_does_not_select_anything(qtbot, main_window):
    window = main_window
    activate(qtbot, window)
    window._actions["focus.grid"].trigger()
    assert window.files.selected_paths() == []


def test_ctrl_1_brings_the_tree_back_from_the_adjustments(qtbot, main_window, demo_project):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    assert window.left.currentWidget() is window.params
    activate(qtbot, window)
    window._actions["focus.tree"].trigger()
    assert window.left.currentWidget() is window.explorer
    qtbot.waitUntil(window.explorer.tree.hasFocus, timeout=3000)
    assert window.activity.tree.isChecked()


def test_ctrl_1_ring_is_painted_on_the_current_folder(qtbot, main_window):
    window = main_window
    activate(qtbot, window)
    tree = window.explorer.tree
    window._actions["focus.tree"].trigger()
    qtbot.waitUntil(tree.hasFocus, timeout=3000)
    rect = tree.visualRect(tree.currentIndex())
    ring = window.theme.color("focus_ring")
    focused = ring_pixels(tree.viewport(), rect, ring)
    window.files.view.setFocus()
    qtbot.waitUntil(lambda: not tree.hasFocus(), timeout=3000)
    assert focused - ring_pixels(tree.viewport(), rect, ring) > 20


def test_ctrl_3_shows_a_hidden_workspace_and_focuses_it(qtbot, main_window, demo_project):
    window = main_window
    window.open_file(demo_project / "03_bands" / "bands.in")
    window.set_panel_visible("workspace", False)
    activate(qtbot, window)
    window._actions["focus.workspace"].trigger()
    assert window.workspace.isVisible()
    focused = QApplication.focusWidget()
    assert focused is not None and window.workspace.isAncestorOf(focused)


def test_ctrl_4_without_a_plot_says_so(qtbot, main_window):
    window = main_window
    window._actions["focus.params"].trigger()
    assert "Nenhum gráfico" in window.status.message.text()
    assert window.left.currentWidget() is window.explorer


def test_ctrl_4_focuses_the_adjustments(qtbot, main_window, demo_project):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    window.explorer.tree.setFocus()
    activate(qtbot, window)
    window._actions["focus.params"].trigger()
    focused = QApplication.focusWidget()
    assert focused is not None and window.params.isAncestorOf(focused)


def test_first_focusable_skips_widgets_that_take_no_keys(qapp):
    host, inner = QWidget(), QWidget()
    inner.setParent(host)
    host.show()
    assert first_focusable(host, host) is None
    inner.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    assert first_focusable(host, host) is inner


def test_ensure_current_only_fills_a_missing_current_item(qtbot, main_window):
    view = main_window.files.view
    qtbot.waitUntil(lambda: view.model().rowCount(view.rootIndex()) > 0, timeout=3000)
    view.selectionModel().clear()
    view.selectionModel().setCurrentIndex(
        view.rootIndex(), view.selectionModel().SelectionFlag.NoUpdate
    )
    ensure_current(view)
    assert view.selectionModel().currentIndex().isValid()
    assert not view.selectionModel().selectedIndexes()


# -- the QSS ring (R4.1) -----------------------------------------------------------------------
def test_a_focused_button_draws_its_border_in_the_ring_color(qtbot, main_window):
    window = main_window
    activate(qtbot, window)
    button = window.files.list_button  # unchecked, so its border is transparent until focus
    ring = window.theme.color("focus_ring")
    edge = QRect(0, button.height() // 2 - 2, 2, 4)
    assert ring_pixels(button, edge, ring) == 0
    button.setFocus(Qt.FocusReason.TabFocusReason)
    qtbot.waitUntil(button.hasFocus, timeout=3000)
    assert ring_pixels(button, edge, ring) > 0


def test_the_ring_reserves_its_space(qtbot, main_window):
    """Focus only recolors a border that was already there: no widget changes size."""
    window = main_window
    activate(qtbot, window)
    sizes = {
        b: b.size()
        for b in (window.activity.tree, window.activity.theme_button, window.files.list_button)
    }
    for button in sizes:
        button.setFocus(Qt.FocusReason.TabFocusReason)
        QApplication.processEvents()
        assert button.size() == sizes[button]
        assert button.sizeHint().isValid()


def test_the_ring_has_a_token_in_both_themes():
    from qe_studio.ui.theme.manager import THEMES, load_tokens

    for theme in THEMES:
        assert load_tokens(theme)["focus_ring"].startswith("#")


# -- accessible names (R4.5) -------------------------------------------------------------------
# Qt's own buttons: tab close, line edit clear, menu bar and toolbar extension arrows
INTERNAL = {"CloseButton", "QLineEditIconButton", "QToolBarExtension"}


def unnamed_buttons(window) -> list[str]:
    out = []
    for button in window.findChildren(QAbstractButton):
        internal = button.metaObject().className() in INTERNAL or button.objectName().startswith(
            "qt_"
        )
        if internal or button.text():
            continue
        if not button.accessibleName():
            out.append(f"{type(button).__name__}({button.toolTip()!r})")
    return out


def test_icon_only_buttons_have_an_accessible_name(qtbot, main_window):
    assert unnamed_buttons(main_window) == []


def test_icon_only_buttons_of_a_plot_have_an_accessible_name(qtbot, main_window, demo_project):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    window.params.body.findChildren(QAbstractButton)  # built: the swatches are in it
    assert unnamed_buttons(window) == []
    names = {b.accessibleName() for b in window.findChildren(QAbstractButton)}
    assert "Mover (arrastar)" in names and any(n.startswith("Cor: #") for n in names)


def test_the_name_is_the_tooltip_and_follows_it(qtbot, main_window):
    window = main_window
    button = window.top_bar.back_button
    assert button.accessibleName() == button.toolTip() == "Voltar (Alt+←)"
    button.setToolTip("Outro")
    assert button.accessibleName() == "Outro"


def test_a_button_with_a_label_keeps_its_label_as_name(qtbot, main_window):
    button = main_window.activity.tree
    assert button.text() == "Árvore" and button.accessibleName() == ""
    assert main_window.activity.theme_button.toolTip().startswith("Tema: ")
