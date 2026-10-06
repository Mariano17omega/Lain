"""``ui.font_scale`` (spec 19 R2): QSS, painted fonts, text-holding heights and the config key."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QStyleOptionViewItem

from qe_studio.core.config import ConfigError, LoadedConfig, parse_config
from qe_studio.core.fontscale import (
    MAX_SCALE,
    MIN_FONT_PX,
    MIN_SCALE,
    SIZE_BASE,
    clamp_scale,
    scale_px,
    scale_qss,
    size_tokens,
)
from qe_studio.ui.painting import mono_font, ui_font
from qe_studio.ui.theme.manager import ThemeManager, style_files
from qe_studio.ui.theme.scale import scaled
from qe_studio.ui.widgets.file_card import card_size, meta_height, name_height, row_height

QSS = "QLabel {\n    font-size: 12px;\n    min-height: 22px;\n}\nQLabel#b { font-size: 9px; }"


# -- pure functions ----------------------------------------------------------------------------
def test_scale_qss_scales_only_font_sizes():
    out = scale_qss(QSS, 1.25)
    assert "font-size: 15px;" in out and "font-size: 11px;" in out  # 12 → 15, 9 → 11.25 → 11
    assert "min-height: 22px;" in out  # the rest does not change


def test_scale_one_leaves_the_text_untouched():
    assert scale_qss(QSS, 1.0) == QSS


def test_a_font_never_gets_smaller_than_the_minimum():
    assert "font-size: 8px;" in scale_qss(QSS, MIN_SCALE)  # 9 * 0.8 = 7.2 → 8


@given(st.integers(1, 40), st.floats(MIN_SCALE, MAX_SCALE))
def test_scale_px_rounds_to_whole_pixels_and_respects_the_minimum(px, scale):
    assert scale_px(px, scale, MIN_FONT_PX) >= MIN_FONT_PX
    assert scale_px(px, 1.0) == px


@given(st.lists(st.integers(1, 40), min_size=1, max_size=8), st.floats(MIN_SCALE, MAX_SCALE))
def test_scale_qss_changes_every_font_size_and_nothing_else(sizes, scale):
    text = "\n".join(f"A{i} {{ font-size: {px}px; color: red; }}" for i, px in enumerate(sizes))
    out = scale_qss(text, scale)
    assert out.count("color: red;") == len(sizes)
    for line, px in zip(out.splitlines(), sizes, strict=True):
        # At exactly 1.0 the text is left untouched (no minimum applied), as the test above says.
        expected = px if scale == 1.0 else scale_px(px, scale, MIN_FONT_PX)
        assert f"font-size: {expected}px;" in line


def test_clamp_scale():
    assert (clamp_scale(0.1), clamp_scale(9), clamp_scale(1.2)) == (MIN_SCALE, MAX_SCALE, 1.2)


def test_size_tokens_follow_the_scale():
    assert size_tokens(1.0) == {name: f"{px}px" for name, px in SIZE_BASE.items()}
    assert size_tokens(1.5)["row_h"] == "33px"


# -- the stylesheet ----------------------------------------------------------------------------
def test_stylesheet_scales_fonts_and_heights(qapp):
    base = ThemeManager("dark").stylesheet()
    scaled_sheet = ThemeManager("dark", font_scale=1.25).stylesheet()
    ThemeManager("dark")  # the scale is global: back to 1
    assert "font-size: 12px" in base and "font-size: 15px" in scaled_sheet
    assert "height: 22px" in base and "height: 28px" in scaled_sheet  # the tree rows, 27.5 → 28
    assert "${" not in scaled_sheet


def test_no_qss_font_size_escapes_the_regex():
    """Every font-size of the styles is ``Npx``; a ``pt`` or ``em`` would ignore the scale."""
    for name, text in style_files():
        for line in text.splitlines():
            if "font-size" in line:
                assert line.strip().endswith("px;"), f"{name}: {line.strip()}"


# -- painted fonts and heights -----------------------------------------------------------------
@pytest.fixture
def theme(qapp):
    manager = ThemeManager("dark", font_scale=1.25)
    manager.apply()
    yield manager
    manager.set_font_scale(1.0)  # the scale is global: leave it as other tests expect


def test_painted_fonts_follow_the_scale(theme):
    assert mono_font(11).pixelSize() == 14  # 13.75
    assert ui_font(12).pixelSize() == 15
    assert scaled(22) == 28


def test_a_manager_without_scale_is_scale_one(qapp):
    ThemeManager("dark", font_scale=1.6)
    ThemeManager("dark")  # the last one built wins, and it asks for the default
    assert mono_font(11).pixelSize() == 11


def test_changing_the_scale_reapplies_the_styles(theme, qtbot):
    with qtbot.waitSignal(theme.scale_changed) as blocker:
        theme.set_font_scale(1.5)
    assert blocker.args == [1.5]
    assert "font-size: 18px" in theme.stylesheet()
    with qtbot.assertNotEmitted(theme.scale_changed):
        theme.set_font_scale(1.5)


def test_the_scale_is_clamped(qapp):
    assert ThemeManager("dark", font_scale=5).font_scale == MAX_SCALE
    ThemeManager("dark")


@pytest.mark.parametrize("scale", [MIN_SCALE, 1.0, MAX_SCALE])
def test_the_card_holds_its_text_at_every_scale(qapp, scale):
    theme = ThemeManager("dark", font_scale=scale)
    try:
        name_h = QFontMetrics(mono_font(12, mono_font(12).weight())).height()
        assert name_height() >= name_h
        assert meta_height() >= QFontMetrics(mono_font(10)).height()
        # tile (7 + 34), the name, 1 gap and the meta line all fit under the top of the card
        assert card_size().height() >= 7 + 34 + 4 + name_height() + 1 + meta_height()
        assert row_height() >= QFontMetrics(mono_font(12)).height()
    finally:
        theme.set_font_scale(1.0)


def test_the_card_at_scale_one_keeps_its_size(qapp):
    ThemeManager("dark")
    assert (card_size().width(), card_size().height()) == (148, 86)
    assert row_height() == 26


# -- in the window -----------------------------------------------------------------------------
def test_reloading_the_config_rescales_the_window(qtbot, main_window):
    window = main_window
    grid_before = window.files.view.gridSize()
    delegate, index = window.explorer.tree.itemDelegate(), window.explorer.tree.rootIndex()
    tree_row = delegate.sizeHint(QStyleOptionViewItem(), index).height()
    config = parse_config(
        {"paths": {"local_root": str(window.root)}, "ui": {"font_scale": MAX_SCALE}}
    )
    try:
        window._apply_loaded(LoadedConfig(config, None))
        assert window.theme.font_scale == MAX_SCALE
        grid_after = window.files.view.gridSize()
        assert grid_after.height() > grid_before.height()
        assert grid_after == card_size()
        assert delegate.sizeHint(QStyleOptionViewItem(), index).height() == scaled(22) > tree_row
        assert window.activity.width() == scaled(56) > 56
        assert "font-size: 19px" in window.theme.stylesheet()  # 12 * 1.6
    finally:
        window.theme.set_font_scale(1.0)


# -- the config key ----------------------------------------------------------------------------
def test_the_config_accepts_a_scale_in_range():
    assert parse_config({}).ui.font_scale == 1.0
    assert parse_config({"ui": {"font_scale": 1.25}}).ui.font_scale == 1.25


@pytest.mark.parametrize("value", [0.5, 0.79, 1.61, 3, -1])
def test_the_config_rejects_a_scale_out_of_range(value):
    with pytest.raises(ConfigError):
        parse_config({"ui": {"font_scale": value}})


def test_the_config_accepts_the_system_theme():
    assert parse_config({"ui": {"theme": "system"}}).ui.theme == "system"
    with pytest.raises(ConfigError):
        parse_config({"ui": {"theme": "sepia"}})
