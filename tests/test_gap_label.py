"""The text of the energy gap legend entry (spec 20, R2): a pure function."""

import pytest

from qe_studio.core.plotting.gap_label import gap_handle, gap_label


def test_the_plain_label_has_three_decimals():
    assert gap_label(1.2344) == "$E_{gap}$ = 1.234 eV"
    assert gap_label(0.5) == "$E_{gap}$ = 0.500 eV"


@pytest.mark.parametrize(
    "channel, text",
    [
        ("up", "$E_{gap}$ ↑ = 1.234 eV"),
        ("down", "$E_{gap}$ ↓ = 1.234 eV"),
        ("global", "$E_{gap}$ global = 1.234 eV"),
    ],
)
def test_a_channel_is_named_before_the_equal_sign(channel, text):
    assert gap_label(1.234, channel) == text


def test_a_gap_read_off_a_curve_is_approximate_with_two_decimals():
    assert gap_label(1.2345, approx=True) == "$E_{gap}$ ≈ 1.23 eV"
    assert gap_label(1.2, "up", approx=True) == "$E_{gap}$ ↑ ≈ 1.20 eV"


def test_the_handle_draws_nothing_and_carries_the_text():
    handle = gap_handle("$E_{gap}$ = 1.234 eV")
    assert handle.get_label() == "$E_{gap}$ = 1.234 eV"
    assert handle.get_linestyle() == "None" and handle.get_marker() == "None"
    assert len(handle.get_xdata()) == 0
