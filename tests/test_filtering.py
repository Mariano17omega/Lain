"""Spec 16 R3 without Qt: the name matcher and the category filter."""

import pytest

from qe_studio.core.filtering import NO_BADGE, NO_STATE, CategoryFilter, name_matcher


@pytest.mark.parametrize(
    "text, name, expected",
    [
        ("", "anything", True),
        ("scf", "scf.out", True),
        ("SCF", "al.scf.out", True),  # case-insensitive substring
        ("scf", "bands.out", False),
        ("sc*out", "my_scf.out", True),  # * is any run of characters
        ("sc*out", "scf.in", False),
        ("scf.?ut", "scf.out", True),  # ? is one character
        ("scf.?ut", "scf.ut", False),
        ("*.OUT", "scf.out", True),
        ("a.b", "aXb", False),  # a dot is a dot
        ("(x", "f(x)", True),  # nothing else is a pattern
        ("[a-z]+", "[a-z]+.in", True),
        ("é", "É.dat", True),
    ],
)
def test_name_matcher(text, name, expected):
    assert name_matcher(text)(name) is expected


def test_no_filter_accepts_everything():
    none = CategoryFilter()
    assert not none.active
    assert none.accepts_folder(["BANDS"]) and none.accepts_folder(None)
    assert none.accepts_file("OK", "dados") and none.accepts_file(None, "outros")


def test_badges_select_folders_and_hide_files():
    relax = CategoryFilter(badges=frozenset({"RELAX"}))
    assert relax.accepts_folder(["RELAX"]) and not relax.accepts_folder(["BANDS"])
    assert relax.accepts_folder(["SCF", "RELAX"])  # any of the folder's badges
    assert not relax.accepts_folder([])  # detected, no type
    assert not relax.accepts_file("OK", "saídas")  # only folders were asked for


def test_an_undetected_folder_stays_until_detection_decides():
    relax = CategoryFilter(badges=frozenset({"RELAX"}))
    assert relax.accepts_folder(None) and relax.is_pending(None)
    assert not relax.is_pending([]) and not relax.is_pending(["BANDS"])
    assert not CategoryFilter().is_pending(None)  # no badge filter: nothing is waited for
    files_only = CategoryFilter(states=frozenset({"OK"}))
    assert not files_only.accepts_folder(None) and not files_only.is_pending(None)


def test_no_type_is_a_badge_of_its_own():
    untyped = CategoryFilter(badges=frozenset({NO_BADGE}))
    assert untyped.accepts_folder([]) and not untyped.accepts_folder(["SCF"])


def test_states_and_visual_types_select_files_and_hide_folders():
    incomplete = CategoryFilter(states=frozenset({"INCOMPLETO"}))
    assert incomplete.accepts_file("INCOMPLETO", "saídas")
    assert not incomplete.accepts_file("OK", "saídas") and not incomplete.accepts_file(
        None, "dados"
    )
    assert not incomplete.accepts_folder(["BANDS"])
    stateless = CategoryFilter(states=frozenset({NO_STATE}))
    assert stateless.accepts_file(None, "dados") and not stateless.accepts_file("OK", "dados")
    both = CategoryFilter(states=frozenset({"OK", "AVISO"}), visuals=frozenset({"saídas"}))
    assert both.accepts_file("OK", "saídas") and not both.accepts_file("OK", "dados")
    assert not both.accepts_file("ERRO", "saídas")


def test_both_kinds_ticked_each_follows_its_own_rule():
    mixed = CategoryFilter(badges=frozenset({"BANDS"}), visuals=frozenset({"inputs"}))
    assert mixed.accepts_folder(["BANDS"]) and not mixed.accepts_folder(["PDOS"])
    assert mixed.accepts_file(None, "inputs") and not mixed.accepts_file(None, "dados")
