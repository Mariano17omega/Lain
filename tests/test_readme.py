"""Relative links in the READMEs must point at files that exist (the PRD link once broke), and the
README, which the public repository also shows, links nothing that only the development repository
has."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Only in the development repository: the public one gets release snapshots without them.
DEV_ONLY = ("specs/", "Documentation/", ".claude/")
DOCS = [
    ROOT / "README.md",
    *[doc for doc in [ROOT / "specs" / "README.md"] if doc.is_file()],
    ROOT / "tests" / "fixtures" / "README.md",
]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def local_links(doc: Path) -> list[str]:
    targets = LINK.findall(doc.read_text(encoding="utf-8"))
    return [t for t in targets if not t.startswith(("http://", "https://", "mailto:", "#"))]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_exist(doc):
    missing = [t for t in local_links(doc) if not (doc.parent / t.split("#")[0]).exists()]
    assert not missing, f"{doc.name} links to missing files: {missing}"


def test_the_readme_links_nothing_of_the_development_repository():
    links = local_links(ROOT / "README.md")
    assert [t for t in links if t.removeprefix("./").startswith(DEV_ONLY)] == []
