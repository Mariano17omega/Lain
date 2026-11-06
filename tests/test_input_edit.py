"""Spec 24 R1: ``InputEditor`` edits an input in place and keeps everything else as written."""

from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint

from conftest import FIXTURES

BASE = """\
&CONTROL
   calculation = 'relax' ! what pw.x does
   prefix='si',
   outdir = './tmp'
/
&SYSTEM
   ibrav = 2, celldm(1) = 10.2, nat = 2
   ntyp = 1
/
ATOMIC_SPECIES
 Si 28.086 Si.UPF

ATOMIC_POSITIONS {alat}
 Si 0.00 0.00 0.00
 Si 0.25 0.25 0.25

K_POINTS automatic
 4 4 4 0 0 0
"""


def edited(text: str, *operations) -> str:
    editor = InputEditor.from_text(text)
    for name, *args in operations:
        getattr(editor, name)(*args)
    assert editor.issues == []
    return editor.text()


def test_without_operations_the_text_is_the_original():
    for text in (BASE, BASE.replace("\n", "\r\n"), "", "&control\n/", "no namelist at all"):
        assert InputEditor.from_text(text).text() == text


def test_get_reads_values_without_outer_quotes():
    editor = InputEditor.from_text(BASE)
    assert editor.get("control", "calculation") == "relax"
    assert editor.get("CONTROL", "prefix") == "si"
    assert editor.raw("control", "prefix") == "'si'"
    assert editor.get("system", "celldm (1)") == "10.2"
    assert editor.get("system", "ecutwfc") is None
    assert editor.get("ions", "x") is None
    assert editor.keys("system") == ["ibrav", "celldm(1)", "nat", "ntyp"]


def test_set_replaces_in_place_keeping_case_comment_and_comma():
    text = edited(
        BASE, ("set", "control", "calculation", "'scf'"), ("set", "control", "prefix", "'x'")
    )
    assert text == BASE.replace("'relax' ! what", "'scf' ! what").replace(
        "prefix='si',", "prefix='x',"
    )


def test_set_on_a_line_with_other_entries_changes_only_that_value():
    text = edited(BASE, ("set", "system", "nat", "8"))
    assert "   ibrav = 2, celldm(1) = 10.2, nat = 8\n" in text
    assert text.replace("nat = 8", "nat = 2") == BASE


def test_a_new_key_goes_at_the_end_of_its_namelist():
    text = edited(BASE, ("set", "system", "ecutwfc", "30"))
    assert "   ntyp = 1\n   ecutwfc = 30\n/\nATOMIC_SPECIES" in text
    assert InputEditor.from_text(text).get("system", "ecutwfc") == "30"


def test_a_new_key_in_a_namelist_closed_on_its_own_line_or_after_a_value():
    text = edited(
        "&ions /\n&cell press = 1 /\n", ("set", "ions", "a", "1"), ("set", "cell", "b", "2")
    )
    assert text == "&ions a = 1 /\n&cell press = 1, b = 2 /\n"
    assert lint(text).issues == []


def test_a_new_namelist_goes_where_pw_x_reads_it():
    text = edited(BASE, ("set", "electrons", "conv_thr", "1d-8"))
    assert "/\n&ELECTRONS\n  conv_thr = 1d-8\n/\nATOMIC_SPECIES" in text
    text = edited(text, ("set", "ions", "ion_dynamics", "'bfgs'"))
    assert text.index("&ELECTRONS") < text.index("&IONS") < text.index("ATOMIC_SPECIES")
    lower = "&control\n/\n&cell\n/\n"
    assert edited(lower, ("set", "ions", "x", "1")) == "&control\n/\n&ions\n  x = 1\n/\n&cell\n/\n"
    assert (
        edited("&SYSTEM\n/\n", ("set", "control", "x", "1")) == "&CONTROL\n  x = 1\n/\n&SYSTEM\n/\n"
    )
    assert edited("", ("set", "control", "x", "1")) == "&CONTROL\n  x = 1\n/\n"
    assert lint(text).issues == []


def test_remove_drops_the_line_or_only_the_entry():
    text = edited(BASE, ("remove", "control", "calculation"))
    assert "calculation" not in text and "what pw.x does" not in text  # its comment went with it
    assert text == BASE.replace("   calculation = 'relax' ! what pw.x does\n", "")
    text = edited(BASE, ("remove", "system", "celldm(1)"))
    assert "   ibrav = 2, nat = 2\n" in text
    text = edited(BASE, ("remove", "system", "nat"))
    assert "   ibrav = 2, celldm(1) = 10.2, \n" in text
    assert lint(text).issues == []
    editor = InputEditor.from_text(BASE)
    assert not editor.remove("system", "ecutwfc") and editor.text() == BASE


def test_remove_on_the_opening_and_closing_lines_keeps_them():
    text = edited("&ions ion_dynamics='bfgs', x = 1 /\n", ("remove", "ions", "ion_dynamics"))
    assert text == "&ions x = 1 /\n"
    assert edited(text, ("remove", "ions", "x")) == "&ions /\n"


def test_remove_namelist_with_slash_or_end():
    text = "&control\n x=1\n/\n&ions\n  a = 1\n&end\n&cell\n/\nK_POINTS gamma\n"
    editor = InputEditor.from_text(text)
    assert editor.remove_namelist("ions") and not editor.remove_namelist("ions")
    assert editor.text() == "&control\n x=1\n/\n&cell\n/\nK_POINTS gamma\n"


def test_a_repeated_namelist_is_edited_in_its_first_occurrence():
    text = "&ions\n  a = 1\n/\n&ions\n  a = 2\n/\n"
    editor = InputEditor.from_text(text)
    assert editor.get("ions", "a") == "1"
    editor.set("ions", "a", "3")
    assert editor.text() == "&ions\n  a = 3\n/\n&ions\n  a = 2\n/\n"
    editor.remove_namelist("ions")
    assert editor.text() == "&ions\n  a = 2\n/\n"


def test_replace_card_keeps_brackets_and_the_lines_after_its_body():
    body = ["Si 0.0 0.0 0.0", "Si 0.24 0.24 0.24"]
    text = edited(BASE, ("replace_card", "ATOMIC_POSITIONS", "crystal", body))
    assert "ATOMIC_POSITIONS {crystal}\nSi 0.0 0.0 0.0\nSi 0.24 0.24 0.24\n\nK_POINTS" in text
    card = InputEditor.from_text(text).card("ATOMIC_POSITIONS")
    assert card is not None and card.option == "crystal" and card.lines == tuple(body)
    text = edited("K_POINTS\n1\n", ("replace_card", "K_POINTS", "gamma", []))
    assert text == "K_POINTS gamma\n"


def test_a_missing_card_is_added_at_the_end():
    rows = ["1 0 0", "0 1 0", "0 0 1"]
    text = edited(BASE, ("replace_card", "CELL_PARAMETERS", "bohr", rows))
    assert text == BASE + "CELL_PARAMETERS bohr\n1 0 0\n0 1 0\n0 0 1\n"
    assert edited("K_POINTS gamma", ("replace_card", "X", "", [])) == "K_POINTS gamma\nX"
    assert lint(text).issues == []


def test_crlf_files_keep_their_line_ends():
    crlf = BASE.replace("\n", "\r\n")
    text = edited(
        crlf,
        ("set", "system", "ecutwfc", "30"),
        ("remove", "control", "outdir"),
        ("replace_card", "CELL_PARAMETERS", "bohr", ["1 0 0"]),
    )
    assert "\n" not in text.replace("\r\n", "")
    assert text.endswith("CELL_PARAMETERS bohr\r\n1 0 0\r\n")


def test_real_inputs_survive_a_round_of_edits():
    for path in sorted(FIXTURES.rglob("*.in")):
        text = path.read_text(encoding="utf-8", errors="replace")
        editor = InputEditor.from_text(text)
        assert editor.text() == text
        editor.set("control", "calculation", "'scf'")
        editor.remove_namelist("ions")
        assert editor.issues == []
        assert InputEditor.from_text(editor.text()).get("control", "calculation") == "scf"


# -- the raw rows of a card, removing a card, renaming a key (spec 30 R2.5) -------------------------
SPIN = """\
&SYSTEM
   nat = 3, ntyp = 2
   starting_magnetization(1) = 0.5 ! first
   Starting_Magnetization (2)= 0.1
/
ATOMIC_SPECIES
 Fe 55.8 Fe.UPF
 O 16 O.UPF

ATOMIC_POSITIONS angstrom
 Fe 0 0 0  0 0 0 ! flags and a comment
 ! a line of its own
 O 1 1 1

 O 2 2 2
K_POINTS gamma
"""


def test_card_rows_are_the_rows_as_written():
    editor = InputEditor.from_text(SPIN)
    assert editor.card_rows("ATOMIC_POSITIONS") == [
        " Fe 0 0 0  0 0 0 ! flags and a comment",  # the comment stays: ``Card.lines`` drops it
        " O 1 1 1",
        " O 2 2 2",
    ]
    card = editor.card("ATOMIC_POSITIONS")
    assert card is not None and card.lines[0] == "Fe 0 0 0  0 0 0"
    assert editor.card_rows("K_POINTS") == []
    assert editor.card_rows("CELL_PARAMETERS") is None
    assert InputEditor.from_text("").card_rows("K_POINTS") is None


def test_replace_card_rows_changes_the_body_and_nothing_else():
    rows = [" Fe 0 0 0  0 0 0 ! flags and a comment", " O 2 2 2"]
    text = edited(SPIN, ("replace_card_rows", "ATOMIC_POSITIONS", rows))
    old = " Fe 0 0 0  0 0 0 ! flags and a comment\n ! a line of its own\n O 1 1 1\n\n O 2 2 2\n"
    assert text == SPIN.replace(old, " Fe 0 0 0  0 0 0 ! flags and a comment\n O 2 2 2\n")
    header = edited(
        "ATOMIC_POSITIONS {Angstrom}  ! unit\n Si 0 0 0\n",
        (
            "replace_card_rows",
            "ATOMIC_POSITIONS",
            [" Si 1 1 1"],
        ),
    )
    assert header == "ATOMIC_POSITIONS {Angstrom}  ! unit\n Si 1 1 1\n"  # the header: byte for byte
    emptied = edited(SPIN, ("replace_card_rows", "ATOMIC_SPECIES", []))
    assert "ATOMIC_SPECIES\n\nATOMIC_POSITIONS" in emptied
    grown = edited("K_POINTS crystal_b\n", ("replace_card_rows", "K_POINTS", ["2", "0 0 0 1"]))
    assert grown == "K_POINTS crystal_b\n2\n0 0 0 1\n"
    editor = InputEditor.from_text(SPIN)
    assert editor.replace_card_rows("HUBBARD", ["U Fe-3d 5"]) is False  # no card: nothing added
    assert editor.text() == SPIN and editor.issues == []


def test_remove_card_takes_the_header_and_the_body():
    text = edited(SPIN, ("remove_card", "ATOMIC_POSITIONS"))
    assert "ATOMIC_POSITIONS" not in text and "O 2 2 2" not in text
    assert text.endswith("O 16 O.UPF\n\nK_POINTS gamma\n")
    assert edited("K_POINTS gamma\n", ("remove_card", "K_POINTS")) == ""
    editor = InputEditor.from_text(SPIN)
    assert editor.remove_card("HUBBARD") is False and editor.text() == SPIN


def test_rename_key_changes_the_name_where_it_stands():
    text = edited(
        SPIN,
        ("rename_key", "system", "starting_magnetization(2)", "starting_magnetization(1)"),
    )
    assert "   Starting_Magnetization (1)= 0.1\n" in text  # spacing, value and the case it had
    assert "starting_magnetization(1) = 0.5 ! first" in text  # the other entry is untouched
    editor = InputEditor.from_text(SPIN)
    assert editor.rename_key("system", "angle1(1)", "angle1(2)") is False
    assert editor.rename_key("ions", "x", "y") is False and editor.text() == SPIN
    shared = edited(
        "&system\n  nat = 2, ntyp(1) = 3 /\n", ("rename_key", "system", "ntyp(1)", "ntyp(2)")
    )
    assert shared == "&system\n  nat = 2, ntyp(2) = 3 /\n"
    assert lint(text).issues == []
