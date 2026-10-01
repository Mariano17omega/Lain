"""Relative links in the READMEs must point at files that exist (the PRD link once broke)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "specs" / "README.md", ROOT / "tests" / "fixtures" / "README.md"]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def local_links(doc: Path) -> list[str]:
    targets = LINK.findall(doc.read_text(encoding="utf-8"))
    return [t for t in targets if not t.startswith(("http://", "https://", "mailto:", "#"))]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_exist(doc):
    missing = [t for t in local_links(doc) if not (doc.parent / t.split("#")[0]).exists()]
    assert not missing, f"{doc.name} links to missing files: {missing}"


def test_readme_points_at_the_prd_and_the_spec_index():
    links = local_links(ROOT / "README.md")
    assert "specs/spec_0-PRD.md" in links and "specs/README.md" in links
    assert not (ROOT / "Documentation" / "PRD.md").exists()  # the old, removed location
