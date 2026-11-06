"""core/qe/input_diff.py: comparing two inputs by parameter and line by line (spec 11 R6)."""

import pytest

from qe_studio.core.qe.input_diff import compare_params, normalize_value, text_rows
from qe_studio.core.qe.input_lint import lint

from conftest import FIXTURES

SI_SCF = (FIXTURES / "si_bands" / "si.scf.in").read_text()


def diff(a: str, b: str):
    return compare_params(lint(a), lint(b))


def rows(a: str, b: str, ignore: bool = False):
    return [(r.tag, r.a, r.b) for r in text_rows(a, b, ignore)]


# -- values ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1d-8", "1.0e-8"),
        ("1.0e-8", "1.E-8"),
        ("30", "30.0"),
        (".t.", ".true."),
        (".FALSE.", "F"),
        ("'Si'", "'si '"),
        ("'a'", '"A"'),
        ("3*1.0", "1.0 1.0 1.0"),
        ("1.0, 2.0", "1.0 2.0"),
    ],
)
def test_values_that_mean_the_same(a, b):
    assert normalize_value(a) == normalize_value(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("'scf'", "'nscf'"),
        ("1.0e-8", "1.0e-9"),
        (".true.", ".false."),
        ("'t'", ".true."),  # a quoted T is a string, not a logical
        ("1.0", "1.0 1.0"),
        ("1.0 2.0", "2.0 1.0"),
    ],
)
def test_values_that_differ(a, b):
    assert normalize_value(a) != normalize_value(b)


def test_huge_repeats_are_not_expanded():
    assert len(normalize_value("999999999*1.0")) == 1


# -- parameters --------------------------------------------------------------------------------
def test_only_the_changed_parameter_shows():
    other = SI_SCF.replace("ecutwfc = 25", "ecutwfc = 30").replace("1.0d-12", "1.0e-12")
    assert other != SI_SCF
    result = diff(SI_SCF, other)
    assert [(c.namelist, c.key, c.a, c.b, c.status) for c in result.params] == [
        ("system", "ecutwfc", "25", "30", "different")
    ]
    assert result.cards == ()
    assert (result.params[0].line_a, result.params[0].line_b) == (12, 12)


def test_identical_inputs_and_formatting_only_changes():
    assert diff(SI_SCF, SI_SCF).identical
    reformatted = SI_SCF.replace("ecutwfc = 25      ", "ECUTWFC=25.0").replace(
        "'silicon'", "'SILICON'"
    )
    assert diff(SI_SCF, reformatted).identical


def test_parameters_in_only_one_file():
    a = "&control\n calculation = 'scf'\n prefix = 'x'\n/\n&system\n nat = 1\n/\n"
    b = "&control\n calculation = 'scf'\n outdir = './t'\n/\n&electrons\n conv_thr = 1d-8\n/\n"
    result = diff(a, b)
    assert [(c.namelist, c.key, c.status) for c in result.params] == [
        ("control", "prefix", "only_a"),
        ("control", "outdir", "only_b"),
        ("system", "nat", "only_a"),
        ("electrons", "conv_thr", "only_b"),
    ]
    prefix = result.params[0]
    assert (prefix.a, prefix.b, prefix.line_a, prefix.line_b) == ("x", None, 3, None)


def test_inputs_with_write_errors_compare_too():
    broken = "&control\n calculation = 'scf'\n prefix = 'x\n&system\n nat = 2\n/\n"
    other = "&control\n calculation = 'nscf'\n prefix = 'x'\n/\n&system\n nat = 2\n/\n"
    result = diff(broken, other)
    assert [(c.key, c.a, c.b) for c in result.params] == [("calculation", "scf", "nscf")]


# -- cards -------------------------------------------------------------------------------------
POSITIONS = "ATOMIC_POSITIONS crystal\nSi 0.0 0.0 0.0\nSi 0.25 0.25 0.25\nO 0.5 0.5 0.5\n"


def test_card_with_changed_lines_is_one_row():
    a = f"&control\n/\n{POSITIONS}K_POINTS gamma\n"
    b = f"&control\n/\n{POSITIONS.replace('0.25', '0.30').replace('0.5 0.5 0.5', '0.6 0.5 0.5')}K_POINTS gamma\n"
    [change] = diff(a, b).cards
    assert change.name == "ATOMIC_POSITIONS" and change.status == "different"
    assert change.differing == 2
    assert change.summary == "ATOMIC_POSITIONS: 2 linhas diferem"
    assert change.detail == (
        ("Si 0.25 0.25 0.25", "Si 0.30 0.30 0.30"),
        ("O 0.5 0.5 0.5", "O 0.6 0.5 0.5"),
    )


def test_numbers_in_cards_compare_as_numbers():
    a = "&control\n/\nATOMIC_POSITIONS crystal\nSi 0.0 0.0 0.0\n"
    b = "&control\n/\nATOMIC_POSITIONS crystal\nSi   0.00 0 0.0d0\n"
    assert diff(a, b).identical


def test_card_option_and_presence():
    a = "&control\n/\nK_POINTS automatic\n4 4 4 0 0 0\n"
    b = "&control\n/\nK_POINTS {automatic}\n4 4 4 0 0 0\nATOMIC_SPECIES\nSi 28 Si.UPF\n"
    [species] = diff(a, b).cards
    assert (species.name, species.status, species.summary) == (
        "ATOMIC_SPECIES", "only_b", "ATOMIC_SPECIES: só em B",
    )  # fmt: skip
    c = "&control\n/\nK_POINTS crystal\n4 4 4 0 0 0\n"
    [option] = diff(a, c).cards
    assert option.differing == 0 and option.summary == "K_POINTS: opção automatic ↔ crystal"


def test_card_with_added_lines():
    a = "&control\n/\nATOMIC_SPECIES\nSi 28 Si.UPF\n"
    b = "&control\n/\nATOMIC_SPECIES\nSi 28 Si.UPF\nO 16 O.UPF\n"
    [change] = diff(a, b).cards
    assert change.detail == ((None, "O 16 O.UPF"),) and change.differing == 1
    assert change.summary == "ATOMIC_SPECIES: 1 linha difere"


# -- line by line ------------------------------------------------------------------------------
def test_text_rows_mark_changed_added_and_removed_lines():
    a = "one\ntwo\nthree\nfour\n"
    b = "one\n2\nthree\nfour\nfive\n"
    assert rows(a, b) == [
        ("equal", (1, "one"), (1, "one")),
        ("change", (2, "two"), (2, "2")),
        ("equal", (3, "three"), (3, "three")),
        ("equal", (4, "four"), (4, "four")),
        ("add", None, (5, "five")),
    ]
    assert rows("a\nb\nc\n", "a\nc\n") == [
        ("equal", (1, "a"), (1, "a")),
        ("del", (2, "b"), None),
        ("equal", (3, "c"), (2, "c")),
    ]


def test_text_rows_of_equal_and_empty_texts():
    assert all(tag == "equal" for tag, _, _ in rows(SI_SCF, SI_SCF))
    assert rows("", "") == []
    assert rows("x\n", "") == [("del", (1, "x"), None)]
    assert rows("a\r\nb\r\n", "a\nb\n") == rows("a\nb\n", "a\nb\n")


def test_ignoring_comments_and_blanks_removes_those_differences():
    a = "&control\n calculation = 'scf' ! the usual\n prefix='x'\n/\n"
    b = "&control\n calculation='scf'\n\n ! a new comment\n prefix = 'x'   \n/\n"
    assert any(tag != "equal" for tag, _, _ in rows(a, b))
    kept = rows(a, b, ignore=True)
    assert {tag for tag, _, _ in kept} <= {"equal", "ignored"}
    assert [r for r in kept if r[0] == "equal"][1] == (
        "equal",
        (2, " calculation = 'scf' ! the usual"),
        (2, " calculation='scf'"),
    )
    # The lines that were only a blank or a comment are still shown, unmarked.
    assert [(t, y) for t, _, y in kept if t == "ignored"] == [
        ("ignored", (3, "")),
        ("ignored", (4, " ! a new comment")),
    ]


def test_ignoring_keeps_real_differences():
    a = "&control\n calculation = 'scf' ! note\n/\n"
    b = "&control\n calculation = 'nscf'\n/\n"
    assert [t for t, _, _ in rows(a, b, ignore=True)] == ["equal", "change", "equal"]


def test_card_comments_use_hash_and_bang():
    a = "K_POINTS gamma # only gamma\nATOMIC_SPECIES ! s\n"
    b = "K_POINTS gamma\nATOMIC_SPECIES\n"
    assert {t for t, _, _ in rows(a, b, ignore=True)} == {"equal"}
    assert {t for t, _, _ in rows(a, b)} == {"change"}


def test_both_sides_cover_every_line_once():
    a = "&control\n a = 1\n b = 2\n/\n! tail\n"
    b = "! head\n&control\n a = 1\n c = 3\n/\n"
    for ignore in (False, True):
        result = text_rows(a, b, ignore)
        assert [r.a[0] for r in result if r.a] == [1, 2, 3, 4, 5]
        assert [r.b[0] for r in result if r.b] == [1, 2, 3, 4, 5]
