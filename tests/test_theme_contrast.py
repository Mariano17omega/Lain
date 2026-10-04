"""WCAG 2 contrast of the theme tokens in both themes (spec 19 R3)."""

from pathlib import Path

import pytest

from qe_studio.core.colors import composite, contrast_ratio
from qe_studio.core.plotting import style
from qe_studio.ui.theme.manager import THEMES, load_tokens

AA_TEXT = 4.5
AA_COMPONENT = 3.0  # WCAG 1.4.11: focus ring and other component boundaries
READING = ("text", "text_secondary", "text_muted")
READING_BACKGROUNDS = ("window", "panel", "card", "panel_alt", "popover", "input")
CARD_BACKGROUNDS = ("card", "panel")
STATE_TEXT = ("success", "warning", "error", "accent_text")
EDITOR_PREFIXES = ("hl_", "syn_")  # painted over the workspace
EDITOR_BACKGROUND_TOKENS = (
    "search_match_bg",
    "search_current_bg",
    "diff_add_bg",
    "diff_del_bg",
    "diff_change_bg",
)


def ratio(tokens: dict[str, str], foreground: str, background: str) -> float:
    ground = tokens[background]
    return contrast_ratio(composite(tokens[foreground], ground), ground)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("background", READING_BACKGROUNDS)
@pytest.mark.parametrize("token", READING)
def test_reading_text_passes_aa(theme, token, background):
    tokens = load_tokens(theme)
    assert ratio(tokens, token, background) >= AA_TEXT


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("background", (*CARD_BACKGROUNDS, "window", "card_hover", "accent_soft"))
def test_meta_text_passes_aa_where_it_is_painted(theme, background):
    """The grid and tree metadata sit on the card, on its hover and on the selected card."""
    tokens = load_tokens(theme)
    ground = composite(tokens[background], tokens["card"])
    assert contrast_ratio(tokens["text_meta"], ground) >= AA_TEXT


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("background", CARD_BACKGROUNDS)
@pytest.mark.parametrize("token", STATE_TEXT)
def test_state_text_passes_aa(theme, token, background):
    assert ratio(load_tokens(theme), token, background) >= AA_TEXT


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("background", READING_BACKGROUNDS)
def test_focus_ring_is_visible(theme, background):
    assert ratio(load_tokens(theme), "focus_ring", background) >= AA_COMPONENT


@pytest.mark.parametrize("theme", THEMES)
def test_editor_highlight_passes_aa_on_the_workspace(theme):
    tokens = load_tokens(theme)
    names = [t for t in tokens if t.startswith(EDITOR_PREFIXES)]
    assert len(names) >= 14
    failing = {
        n: round(ratio(tokens, n, "workspace"), 2)
        for n in names
        if ratio(tokens, n, "workspace") < AA_TEXT
    }
    assert not failing


@pytest.mark.parametrize("theme", THEMES)
def test_text_stays_readable_over_translucent_backgrounds(theme):
    """Search hits and diff rows are composed over the workspace before measuring."""
    tokens = load_tokens(theme)
    for background in EDITOR_BACKGROUND_TOKENS:
        ground = composite(tokens[background], tokens["workspace"])
        assert contrast_ratio(tokens["text"], ground) >= AA_TEXT, background


@pytest.mark.parametrize("theme", THEMES)
def test_line_numbers_pass_aa(theme):
    tokens = load_tokens(theme)
    for token in ("gutter_fg", "gutter_current_fg"):
        assert ratio(tokens, token, "gutter_bg") >= AA_TEXT


@pytest.mark.parametrize("theme", THEMES)
def test_badges_pass_aa_on_their_own_background(theme):
    tokens = load_tokens(theme)
    foregrounds = [t for t in tokens if t.startswith("badge_") and t.endswith("_fg")]
    assert len(foregrounds) == 6
    for fg in foregrounds:
        ground = composite(tokens[fg.replace("_fg", "_bg")], tokens["card"])
        assert contrast_ratio(tokens[fg], ground) >= AA_TEXT, fg


def test_text_dim_is_not_for_informative_text():
    """text_dim stays below AA on purpose (disabled and placeholder only): nothing may read it."""
    for theme in THEMES:
        assert ratio(load_tokens(theme), "text_dim", "card") < AA_TEXT


def test_contrast_ratio_keeps_its_old_import_path():
    assert style.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_composite_blends_rgba_over_the_background():
    assert composite("rgba(0, 0, 0, 0.5)", "#ffffff") == "#808080"
    assert composite("#2563eb", "#ffffff") == "#2563eb"


# The only files that may still read text_dim: disabled states, placeholder and status LEDs.
TEXT_DIM_ALLOWED = {
    "ui/theme/manager.py",  # placeholder, disabled palette group, disabled icon
    "ui/widgets/bars.py",  # status LED colors, not text
    "ui/widgets/command_palette.py",  # rows that cannot be chosen
    "ui/resources/styles/base/app.qss",  # QMenu::item:disabled
    "ui/resources/styles/controls/buttons.qss",  # :disabled
    "ui/resources/styles/controls/inputs.qss",  # :disabled
    "ui/resources/styles/workspace/viewers.qss",  # :disabled
}


def test_text_dim_is_only_read_by_disabled_states():
    import qe_studio

    root = Path(qe_studio.__file__).parent
    users = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.suffix in (".py", ".qss") and "text_dim" in path.read_text(encoding="utf-8")
    }
    assert users <= TEXT_DIM_ALLOWED, (
        f"text_dim for informative text: {sorted(users - TEXT_DIM_ALLOWED)}"
    )
