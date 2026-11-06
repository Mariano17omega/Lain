"""core/qe/input_lexer.py + input_lint.py: the tolerant reader and write-error checks (spec 11)."""

from __future__ import annotations

import pytest

from qe_studio.core.qe import input_lint
from qe_studio.core.qe.input_lexer import Kind, LexState, Mode, scan_line
from qe_studio.core.qe.input_lint import InputDoc, lint, neighbour_issue

from conftest import FIXTURES

INPUTS = sorted(FIXTURES.rglob("*.in"))


def found(text: str) -> list[tuple[int, str, str, str]]:
    """(line, underlined text, severity, message) of every issue, to read as a table."""
    lines = text.split("\n")
    return [
        (i.line, lines[i.line - 1][i.col_start : i.col_end], i.severity, i.message)
        for i in lint(text).issues
    ]


def pw(body: str = "", tail: str = "") -> str:
    """A well-formed pw.x input around ``body`` (lines inside &CONTROL) and ``tail`` (after it)."""
    return f"&CONTROL\n{body}/\n&SYSTEM\n/\n&ELECTRONS\n/\n{tail}"


# -- fixtures -----------------------------------------------------------------------------------
@pytest.mark.parametrize("path", INPUTS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_fixture_inputs_have_no_errors(path):
    errors = [i for i in lint(path.read_text()).issues if i.severity == "error"]
    assert errors == []


def test_repeated_namelist_in_a_real_input_is_a_warning():
    text = (FIXTURES / "kao_slab_relax/relax-kaolinite-slab-001.in").read_text()
    doc = lint(text)
    assert [(i.line, i.severity, i.message) for i in doc.issues] == [
        (30, "warning", "&IONS repetida: o pw.x lê só a primeira")
    ]
    assert doc.namelists["ions"] == []  # the first one (empty) is the one pw.x reads


def test_reads_what_the_file_says():
    doc = lint((FIXTURES / "al_bands/al.band.in").read_text())
    assert doc.program == "pw"
    assert doc.get("control", "calculation").value_text == "'bands'"
    assert doc.get("system", "CELLDM(1)").value_text == "7.630781648"
    k_points = doc.card("K_POINTS")
    assert k_points is not None and k_points.option == "crystal_b"
    assert k_points.lines[0] == "5"  # the count line, then the five rows
    assert len(k_points.lines) == 6
    assert doc.card("ATOMIC_SPECIES").line == 24


# -- R2: one minimal input per row --------------------------------------------------------------
def test_r2_1_unclosed_quote_keeps_the_rest_tokenized():
    text = "&control\n prefix = 'si\n calculation = 'scf'\n/\n&system\n/\n&electrons\n/\n"
    assert found(text) == [(2, "'si", "error", "Aspas não fechadas")]
    doc = lint(text)
    assert [e.key for e in doc.namelists["control"]] == ["prefix", "calculation"]
    assert doc.program == "pw"


def test_r2_1_double_quotes_too():
    assert found(pw(' prefix = "si\n')) == [(2, '"si', "error", "Aspas não fechadas")]


@pytest.mark.parametrize(
    ("text", "line", "span"),
    [
        ("&system\n nat = 1\n&electrons\n/\n", 1, "&system"),
        ("&control\n prefix = 'x'\nK_POINTS gamma\n", 1, "&control"),
        ("&control\n prefix = 'x'\n", 1, "&control"),
    ],
    ids=["next namelist", "card", "end of file"],
)
def test_r2_2_namelist_without_slash(text, line, span):
    [(at, underlined, severity, message)] = [item for item in found(text) if "fechada" in item[3]]
    assert (at, underlined, severity) == (line, span, "error")
    assert message == f"{span.upper()} não foi fechada com '/'"


def test_r2_3_line_without_equals():
    assert found(pw(" prefix\n")) == [(2, "prefix", "error", "Esperado 'chave = valor'")]


@pytest.mark.parametrize("value", ["ecutwfc =", "ecutwfc = ,", "ecutwfc =  ! later"])
def test_r2_4_missing_value(value):
    [(_, span, severity, message)] = found(pw(f" {value}\n"))
    assert (severity, message) == ("error", "Valor ausente para ecutwfc")
    assert span == "ecutwfc ="


def test_r2_5_unbalanced_parentheses():
    text = pw(" starting_magnetization(1 = 0.5\n")
    assert found(text) == [(2, "(1", "error", "Parêntese não fechado")]
    doc = lint(text)
    assert doc.get("control", "starting_magnetization(1").value_text == "0.5"  # no cascade
    assert found(pw(" celldm1) = 5\n")) == [(2, ")", "error", "Parêntese sem abertura")]


@pytest.mark.parametrize("bad", [".true", "true.", ".ture.", ".t", "f."])
def test_r2_6_malformed_logical(bad):
    assert found(pw(f" lflag = {bad}\n")) == [
        (2, bad, "error", "Valor lógico inválido: use .true. ou .false.")
    ]


@pytest.mark.parametrize("good", [".true.", ".FALSE.", ".t.", ".F.", "T", "f", "3*.true."])
def test_r2_6_accepted_logicals(good):
    assert found(pw(f" lflag = {good}\n")) == []


@pytest.mark.parametrize("bad", ["1.0e", "10..5", "1.0d-", "2.5.1", "1e+"])
def test_r2_7_malformed_number(bad):
    assert found(pw(f" conv_thr = {bad}\n")) == [(2, bad, "error", "Número inválido")]


@pytest.mark.parametrize(
    "good", ["1d-8", "1.0e-8", "1.E-8", "1.189179909610978E+002", ".5", "+3", "3*1.0", "10"]
)
def test_r2_7_accepted_numbers(good):
    assert found(pw(f" conv_thr = {good}\n")) == []


def test_r2_8_unknown_namelist_names_the_close_one():
    text = "&contrl\n/\n&system\n/\n&electrons\n/\n"
    assert found(text) == [
        (1, "&contrl", "error", "Namelist desconhecida &CONTRL (quis dizer &CONTROL?)")
    ]


def test_r2_8_unknown_namelist_without_a_suggestion():
    text = "&control\n/\n&system\n/\n&plasma\n/\n"
    assert found(text) == [(5, "&plasma", "error", "Namelist desconhecida &PLASMA")]


def test_r2_8_a_namelist_of_another_program_is_unknown_here():
    assert [m for *_, m in found("&control\n/\n&system\n/\n&projwfc\n/\n")] == [
        "Namelist desconhecida &PROJWFC"
    ]


def test_r2_8_near_miss_alone_still_counts():
    assert found("&contrl\n/\n") == [
        (1, "&contrl", "error", "Namelist desconhecida &CONTRL (quis dizer &CONTROL?)")
    ]


def test_r2_8_short_names_get_a_tighter_threshold():
    # `&dox` is one edit from `&dos`; `&ph` is two, and would match nearly any three-letter word.
    assert [m for *_, m in found("&dox\n/\n")] == ["Namelist desconhecida &DOX (quis dizer &DOS?)"]
    assert found("&ph\n/\n") == []


def test_r2_9_unknown_card():
    text = pw(tail="ATOMIC_POSITION crystal\nSi 0 0 0\n")
    assert found(text) == [
        (
            7,
            "ATOMIC_POSITION",
            "error",
            "Card desconhecido ATOMIC_POSITION (quis dizer ATOMIC_POSITIONS?)",
        )
    ]


@pytest.mark.parametrize("rest", ["", " ! note", " (alat)", " {crystal}", " crystal"])
def test_r2_9_unknown_card_forms(rest):
    assert [m.split(" (")[0] for *_, m in found(pw(tail=f"WHATEVER{rest}\n"))] == [
        "Card desconhecido WHATEVER"
    ]


def test_r2_9_card_body_lines_are_not_cards():
    tail = (
        "ATOMIC_SPECIES\nAl 26.98 Al.UPF\nATOMIC_POSITIONS crystal\nAl1 0 0 0\nCARB 0.0 0.0 0.0\n"
    )
    assert found(pw(tail=tail)) == []


@pytest.mark.parametrize(
    ("card", "option"),
    [
        ("K_POINTS {automatc}", "automatc"),
        ("ATOMIC_POSITIONS (crystl)", "crystl"),
        ("CELL_PARAMETERS angstrm", "angstrm"),
    ],
)
def test_r2_10_invalid_card_option(card, option):
    name = card.split()[0]
    assert found(pw(tail=f"{card}\n")) == [
        (7, option, "error", f"Opção inválida para {name}: {option}")
    ]


@pytest.mark.parametrize(
    "card",
    [
        "K_POINTS",
        "K_POINTS {tpiba_b}",
        "K_POINTS (automatic)",
        "ATOMIC_POSITIONS",
        "ATOMIC_POSITIONS {crystal_sg}",
        "CELL_PARAMETERS bohr",
        "atomic_species",
        "k_points CRYSTAL",
    ],
)
def test_r2_10_valid_card_options(card):
    assert found(pw(tail=f"{card}\n")) == []


def test_r2_11_repeated_namelist_is_a_warning_and_the_first_is_read():
    text = "&control\n calculation = 'scf'\n/\n&control\n calculation = 'nscf'\n/\n&system\n/\n&electrons\n/\n"
    assert found(text) == [(4, "&control", "warning", "&CONTROL repetida: o pw.x lê só a primeira")]
    assert lint(text).get("control", "calculation").value_text == "'scf'"


def test_r2_12_stray_slash_and_ampersand():
    assert found(pw(tail="/\n")) == [(7, "/", "warning", "'/' sem namelist aberta")]
    assert found(pw(tail="&\n")) == [(7, "&", "warning", "'&' sem nome de namelist")]
    assert found(pw(tail="&end\n")) == [(7, "&end", "warning", "'&end' sem namelist aberta")]


def test_a_slash_inside_a_card_row_is_not_a_stray_slash():
    assert found(pw(tail="ATOMIC_SPECIES\nSi 28.0 /opt/pseudo/Si.UPF\n")) == []


# -- other programs ----------------------------------------------------------------------------
def test_unrecognized_programs_only_get_the_write_rules():
    ph = "phonons of Al's lattice\n&inputph\n  tr2_ph = 1.0d-14,\n  prefix = 'al',\n/\n0.0 0.0 0.0\nWHATEVER\n"
    assert found(ph) == []
    broken = "title\n&inputph\n  prefix = 'al\n  tr2_ph = 1.0d-\n/\n"
    assert [(line, message) for line, _, _, message in found(broken)] == [
        (3, "Aspas não fechadas"),
        (4, "Número inválido"),
    ]


PP = """&INPUTPP
prefix = 'Al',
outdir = './tmp/',
filplot = 'Al.charge',
plot_num = 0
/
&PLOT
nfile = 1,
filepp(1) = 'Al.charge',
weight(1) = 1.0,
iflag = 3,
output_format = 5,
fileout = 'cdd_xsf/Al_charge.xsf'
/
"""


def test_pp_inputs_know_their_namelists():
    """Spec 29 R5: neither &INPUTPP nor &PLOT is unknown in a pp.x input."""
    doc = lint(PP)
    assert doc.program == "pp" and doc.issues == []
    assert lint("&inputpp\n prefix='x'\n/\n&plot\n iflag=3\n/\n").issues == []


def test_pp_inputs_still_get_the_write_rules():
    assert found(PP.replace("'./tmp/'", "'./tmp/")) == [
        (3, "'./tmp/,", "error", "Aspas não fechadas")
    ]
    assert found(PP.replace("iflag = 3,", "iflag = 3.x,")) == [
        (11, "3.x", "error", "Número inválido")
    ]
    assert [m for *_, m in found(PP.rstrip("/\n"))] == ["&PLOT não foi fechada com '/'"]


def test_pp_does_not_make_a_close_namelist_of_another_program_a_typo():
    """ph.x's &INPUTPH is one edit from &INPUTPP: it must stay unrecognized, not "corrected"."""
    assert found("&inputph\n prefix='al'\n/\n") == []
    assert found("&inputp\n/\n") == []
    assert lint("&plot nbnd=8, nks=60 /\n").program is None  # a bands.x filband header


def test_bands_projwfc_and_dos_inputs():
    assert lint("&bands\n prefix='x', filband='b.dat'\n/\n").program == "bands"
    assert lint("&projwfc\n DeltaE=0.1\n/\n").program == "projwfc"
    assert lint("&DOS\n fildos='d'\n/\n").program == "dos"
    assert found("&bands\n prefix='x'\n") == [
        (1, "&bands", "error", "&BANDS não foi fechada com '/'")
    ]


# -- reading forms -----------------------------------------------------------------------------
def test_several_pairs_per_line_with_or_without_commas():
    doc = lint("&system\n ibrav=2, celldm(1) =6.48, nat=1, ntyp=1,\n ecutwfc=30 nbnd=8\n/\n")
    assert [e.key for e in doc.namelists["system"]] == [
        "ibrav",
        "celldm(1)",
        "nat",
        "ntyp",
        "ecutwfc",
        "nbnd",
    ]
    assert doc.issues == []
    assert doc.get("system", "celldm(1)").value_text == "6.48"


def test_key_with_a_space_before_its_index():
    doc = lint("&system\n celldm (1) = 5.0\n/\n")
    assert doc.issues == []
    assert doc.get("system", "celldm(1)").value_text == "5.0"


def test_values_continue_on_the_next_line_after_a_comma():
    ok = "&system\n celldm = 1.0, 2.0,\n   3.0, 4.0\n/\n"
    assert found(ok) == []
    lonely = "&system\n celldm = 1.0, 2.0\n   3.0, 4.0\n/\n"
    assert [m for *_, m in found(lonely)] == ["Esperado 'chave = valor'"]


def test_comment_and_blank_lines_do_not_break_a_continuation():
    assert found("&system\n celldm = 1.0,\n\n ! pause\n 2.0\n/\n") == []


def test_namelist_on_one_line_and_end_closer():
    doc = lint("&control calculation='scf' prefix='x' /\n&system nat=1 &end\n&electrons\n/\n")
    assert doc.issues == []
    assert [e.key for e in doc.namelists["control"]] == ["calculation", "prefix"]
    assert [e.key for e in doc.namelists["system"]] == ["nat"]


def test_comments_hide_everything_after_them():
    doc = lint(
        "&control\n prefix = 'x' ! don't 'worry\n calculation = 'scf' # not a comment here\n/\n"
    )
    assert [i.message for i in doc.issues] == []
    assert doc.get("control", "prefix").value_text == "'x'"


def test_hash_comments_in_cards():
    assert (
        found(
            pw(
                tail="K_POINTS gamma # only gamma\nATOMIC_SPECIES # label  mass  file\nSi 28 Si.UPF # it's\n"
            )
        )
        == []
    )


def test_text_before_the_first_namelist_is_not_checked():
    assert found("Al's input\n! nothing\n&control\n/\n&system\n/\n&electrons\n/\n") == []


def test_crlf_gives_the_same_issues():
    text = "&control\n prefix = 'si\n/\n&system\n/\n&electrons\n/\n"
    assert found(text.replace("\n", "\r\n")) == found(text)


def test_an_input_ase_cannot_read_is_still_read():
    # ASE raises AttributeError on a quote before the `=`.
    text = "&control\n pre'fix = 'x'\n/\n&system\n/\n&electrons\n/\n"
    doc = lint(text)
    assert doc.program == "pw"
    assert any(i.severity == "error" for i in doc.issues)


def test_issues_are_sorted_by_position():
    text = "&control\n a = 1.0e\n b = .true\n/\n&system\n c = 1..\n/\n&electrons\n/\n"
    issues = lint(text).issues
    assert [(i.line, i.col_start) for i in issues] == sorted((i.line, i.col_start) for i in issues)
    assert len(issues) == 3


# -- API ---------------------------------------------------------------------------------------
def test_lint_never_raises_even_if_the_reader_does(monkeypatch):
    def boom(_text):
        raise RuntimeError("bug")

    monkeypatch.setattr(input_lint, "_lint", boom)
    assert lint("&control\n/\n") == InputDoc()


def test_neighbour_issue_wraps_around():
    issues = lint("&control\n a = 1.0e\n b = 2.0e\n c = 3.0e\n/\n").issues
    assert [i.line for i in issues] == [2, 3, 4]
    assert neighbour_issue(issues, 1).line == 2
    assert neighbour_issue(issues, 2).line == 3
    assert neighbour_issue(issues, 4).line == 2  # wraps
    assert neighbour_issue(issues, 3, forward=False).line == 2
    assert neighbour_issue(issues, 2, forward=False).line == 4  # wraps
    assert neighbour_issue([], 1) is None


def test_lex_state_round_trips_through_a_block_state():
    for mode in Mode:
        for comma in (False, True):
            state = LexState(mode, comma)
            assert LexState.from_code(state.code) == state
    assert LexState.from_code(-1) == LexState()  # Qt's state of the first block
    assert LexState.from_code(3) == LexState()  # no such mode: start over


def test_tokens_use_the_theme_token_names():
    scan = scan_line("&control", LexState(), 1)
    assert [(t.kind, t.kind.value) for t in scan.tokens] == [(Kind.NAMELIST, "syn_namelist")]
    scan = scan_line(" ecutwfc = 30.0, name = 'x', ok = .true. ! c", LexState(Mode.NAMELIST), 2)
    by_position = sorted(scan.tokens, key=lambda t: t.start)
    assert [t.kind.value for t in by_position] == [
        "syn_key", "syn_number", "syn_key", "syn_string", "syn_key", "syn_logical", "syn_comment",
    ]  # fmt: skip
    scan = scan_line("K_POINTS {automatic}", LexState(Mode.CARD), 3)
    assert [t.kind.value for t in scan.tokens] == ["syn_card", "syn_card_option"]
