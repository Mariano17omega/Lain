"""``PwOutput`` of every fixture output must not change (spec 14 R5.3).

``pw_output_golden.json`` was captured from ``parse_pw_output(whole text)`` before the parser was
split into head and tail, for every ``Program PWSCF`` file under ``tests/fixtures/``. Update it only
when a field is *meant* to change.

A new ``PwOutput`` field (spec 24 added ``geometry_converged``): for every key of the JSON, parse
the fixture with ``parse_pw_output(whole text)``, check that ``normalized(...)`` differs from the
stored dict only in the new key, store it and write the file back with ``json.dumps(…, indent=1)``
plus a final newline, so the diff shows just the new lines.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES

GOLDEN: dict[str, dict] = json.loads(
    (Path(__file__).parent / "pw_output_golden.json").read_text(encoding="utf-8")
)


def normalized(output) -> dict:
    """The dataclass as the JSON round trip sees it (tuples become lists)."""
    return json.loads(json.dumps(dataclasses.asdict(output)))


def test_golden_covers_every_fixture_output():
    outputs = {
        path.relative_to(FIXTURES).as_posix()
        for path in FIXTURES.rglob("*")
        if path.is_file() and b"Program PWSCF" in path.read_bytes()[:2048]
    }
    assert outputs == set(GOLDEN)


@pytest.mark.parametrize("rel", sorted(GOLDEN))
def test_parse_matches_golden(rel):
    text = (FIXTURES / rel).read_text(encoding="utf-8", errors="replace")
    assert normalized(parse_pw_output(text)) == GOLDEN[rel]


@pytest.mark.parametrize("rel", sorted(GOLDEN))
def test_sniff_matches_golden(rel):
    sniffed = SniffCache().sniff(FIXTURES / rel)
    assert sniffed.pw is not None
    assert normalized(sniffed.pw) == GOLDEN[rel]
