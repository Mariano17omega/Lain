"""``PwOutput`` of every real pw.x run of ``fixtures/qe_examples/`` must not change.

``qe_examples_golden.json`` was captured after ``test_qe_examples_pw`` checked those values against
QE's own text. Update it only when a field is *meant* to change, as ``test_pw_output_regression``
explains for the fixtures of the project's own runs.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.sniff import SniffCache

from qe_examples_helpers import PW, params, select

GOLDEN: dict[str, dict] = json.loads(
    (Path(__file__).parent / "qe_examples_golden.json").read_text(encoding="utf-8")
)
PW_CASES = select(PW)


def normalized(output) -> dict:
    """The dataclass as the JSON round trip sees it (tuples become lists)."""
    return json.loads(json.dumps(dataclasses.asdict(output)))


def test_golden_covers_every_pw_case():
    assert {case.id for case in PW_CASES} == set(GOLDEN)


@pytest.mark.parametrize("case", params(PW_CASES))
def test_parse_matches_golden(case):
    assert normalized(parse_pw_output(case.output_text)) == GOLDEN[case.id]


@pytest.mark.parametrize("case", params(PW_CASES))
def test_sniff_matches_golden(case):
    sniffed = SniffCache().sniff(case.output_path)
    assert sniffed.pw is not None
    assert normalized(sniffed.pw) == GOLDEN[case.id]
