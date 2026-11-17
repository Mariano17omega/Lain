"""Real QE inputs through the input readers: sniff, parser, lint, editor and 3D structure."""

import pytest

from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.qe.pw_input import parse_input
from qe_studio.core.sniff import FileKind, SniffCache
from qe_studio.core.structure3d.source import structure_of_text

from qe_examples_helpers import CASES, DOUBLE_QUOTE_GAPS, PW, number_setting, params, select

KINDS = {
    "pw.x": FileKind.PW_IN,
    "bands.x": FileKind.BANDSX_IN,
    "projwfc.x": FileKind.PROJWFC_IN,
    "dos.x": FileKind.DOS_IN,
    "pp.x": FileKind.PP_IN,
}
PW_CASES = select(PW)
# average.x announces itself as POST-PROC and reads plain numbers, no namelist: not a pp.x input.
NO_NAMELIST = [case for case in CASES if "&" not in case.input_text]
NAMELIST_CASES = [case for case in CASES if "&" in case.input_text]


@pytest.mark.parametrize("case", params(NAMELIST_CASES))
def test_is_sniffed_as_the_input_of_its_program(case):
    assert SniffCache().sniff(case.input_path).kind is KINDS[case.program]


@pytest.mark.parametrize("case", params(NO_NAMELIST))
def test_input_without_a_namelist_is_unknown(case):
    assert SniffCache().sniff(case.input_path).kind is FileKind.UNKNOWN


@pytest.mark.parametrize("case", params(PW_CASES, DOUBLE_QUOTE_GAPS))
def test_sniff_reads_the_calculation(case):
    assert SniffCache().sniff(case.input_path).calculation == case.calculation


@pytest.mark.parametrize("case", params(PW_CASES, DOUBLE_QUOTE_GAPS))
def test_parser_reads_the_calculation(case):
    parsed = parse_input(case.input_text)
    assert parsed.program == "pw"
    assert parsed.calculation == case.calculation


@pytest.mark.parametrize("case", params(CASES))
def test_has_no_lint_errors(case):
    errors = [issue for issue in lint(case.input_text).issues if issue.severity == "error"]
    assert errors == []


@pytest.mark.parametrize("case", params(CASES))
def test_editor_returns_the_text_unchanged(case):
    assert InputEditor.from_text(case.input_text).text() == case.input_text


@pytest.mark.parametrize("case", params(PW_CASES))
def test_edit_survives_a_round_trip(case):
    editor = InputEditor.from_text(case.input_text)
    editor.set("control", "calculation", "'scf'")
    assert editor.issues == []
    assert InputEditor.from_text(editor.text()).get("control", "calculation") == "scf"


@pytest.mark.parametrize("case", params(PW_CASES))
def test_structure_has_every_atom(case):
    structure = structure_of_text(case.input_text)
    assert len(structure.labels) == number_setting(case.input_text, "nat")
    assert len(structure.species) == number_setting(case.input_text, "ntyp")
