from importlib.resources import files

import pytest
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

from qe_studio.ui.theme.manager import (
    MODES,
    THEMES,
    ThemeManager,
    build_stylesheet,
    load_tokens,
    parse_color,
    style_files,
)


def test_token_sets_match():
    dark, light = (set(load_tokens(t)) for t in THEMES)
    assert dark == light


@pytest.mark.parametrize("theme", THEMES)
def test_every_placeholder_resolves(qapp, theme):
    manager = ThemeManager(theme)
    sheet = manager.stylesheet()
    assert "${" not in sheet
    for name, _text in style_files():
        assert f"/* ---- {name} ---- */" in sheet


def test_unknown_token_raises():
    with pytest.raises(KeyError):
        build_stylesheet({})


def test_styles_are_modular():
    names = [name for name, _ in style_files()]
    assert len(names) >= 10
    assert {name.split("/")[0] for name in names} >= {"base", "layout", "navigation", "workspace"}


@pytest.mark.parametrize("theme", THEMES)
def test_stylesheet_parses_without_qt_warnings(qapp, qtbot, theme):
    from PyQt6.QtWidgets import QComboBox, QPushButton, QTabWidget, QTreeView, QWidget

    messages = []

    def handler(kind, _context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg):
            messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        ThemeManager(theme).apply(qapp)
        host = QWidget()
        qtbot.addWidget(host)
        for widget in (QPushButton("x", host), QComboBox(host), QTabWidget(host), QTreeView(host)):
            widget.ensurePolished()
        host.show()
        qapp.processEvents()
    finally:
        qInstallMessageHandler(previous)
    assert not [m for m in messages if "style" in m.lower() or "parse" in m.lower()], messages


def test_parse_color():
    color = parse_color("rgba(0, 210, 255, 0.12)")
    assert (color.red(), color.green(), color.blue(), color.alpha()) == (0, 210, 255, 31)
    assert parse_color("#2563eb").name() == "#2563eb"


def test_all_icons_render(qapp):
    manager = ThemeManager("light")
    icons = [
        r.name[:-4]
        for r in files("qe_studio.ui.resources").joinpath("icons").iterdir()
        if r.name.endswith(".svg")
    ]
    assert len(icons) > 40
    for name in icons:
        assert not manager.icon(name, "accent").isNull()


def test_toggle_emits(qapp, qtbot):
    manager = ThemeManager("dark")
    with qtbot.waitSignal(manager.theme_changed) as blocker:
        assert manager.toggle() == "light"
    assert blocker.args == ["light"]


# -- mode "system" (spec 19 R1) ----------------------------------------------------------------
@pytest.fixture
def scheme(monkeypatch):
    """Fake the OS color scheme (offscreen always says Unknown): ``set`` changes it and emits."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication

    hints = QGuiApplication.styleHints()
    state = {"value": Qt.ColorScheme.Dark}
    monkeypatch.setattr(type(hints), "colorScheme", lambda self: state["value"])

    def set_scheme(value):
        state["value"] = value
        hints.colorSchemeChanged.emit(value)

    return set_scheme


def test_themes_are_the_concrete_ones_and_system_is_a_mode():
    assert THEMES == ("dark", "light")
    assert MODES == ("dark", "light", "system")


def test_system_follows_the_os_scheme(qapp, qtbot, scheme):
    from PyQt6.QtCore import Qt

    manager = ThemeManager("system")
    assert (manager.mode, manager.name) == ("system", "dark")
    with qtbot.waitSignal(manager.theme_changed) as blocker:
        scheme(Qt.ColorScheme.Light)
    assert blocker.args == ["light"]  # the concrete theme, never "system"
    assert (manager.mode, manager.name) == ("system", "light")
    assert manager.tokens == load_tokens("light")
    assert manager.label() == "Sistema (claro agora)"


def test_system_without_a_scheme_is_dark(qapp, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication

    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(type(hints), "colorScheme", lambda self: Qt.ColorScheme.Unknown)
    assert ThemeManager("system").name == "dark"


def test_a_fixed_mode_ignores_the_os(qapp, qtbot, scheme):
    from PyQt6.QtCore import Qt

    manager = ThemeManager("dark")
    with qtbot.assertNotEmitted(manager.theme_changed):
        scheme(Qt.ColorScheme.Light)
    assert manager.name == "dark"


def test_toggle_cycles_dark_light_system(qapp, qtbot, scheme):
    manager = ThemeManager("dark")
    modes = []
    manager.mode_changed.connect(modes.append)
    assert [manager.toggle() for _ in range(4)] == ["light", "system", "dark", "light"]
    assert modes == ["light", "system", "dark", "light"]


def test_leaving_system_stops_following_the_os(qapp, qtbot, scheme):
    from PyQt6.QtCore import Qt

    manager = ThemeManager("system")
    manager.set_mode("light")
    scheme(Qt.ColorScheme.Dark)
    assert manager.name == "light"


def test_an_unknown_mode_is_dark(qapp):
    assert ThemeManager("sepia").mode == "dark"
