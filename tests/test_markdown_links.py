"""Spec 38 R1.4: what a click on a link of a rendered Markdown file does, without Qt."""

import pytest

from qe_studio.core.markdown_links import LinkAction, heading_slug, heading_slugs, link_action


@pytest.mark.parametrize(
    "href, expected",
    [
        ("https://example.org/a?b=1", LinkAction("open", "https://example.org/a?b=1")),
        ("HTTP://example.org", LinkAction("open", "HTTP://example.org")),
        ("#resultados", LinkAction("anchor", "resultados")),
        ("#caf%C3%A9", LinkAction("anchor", "café")),
        ("outro.md", LinkAction("blocked", "outro.md")),
        ("../dados/run.out", LinkAction("blocked", "../dados/run.out")),
        ("file:///etc/passwd", LinkAction("blocked", "file:///etc/passwd")),
        ("/home/m/x.md", LinkAction("blocked", "/home/m/x.md")),
        ("javascript:alert(1)", LinkAction("blocked", "javascript:alert(1)")),
        ("mailto:a@b.c", LinkAction("blocked", "mailto:a@b.c")),
        ("ftp://host/x", LinkAction("blocked", "ftp://host/x")),
        ("https://", LinkAction("blocked", "https://")),  # no host: not an address
        ("http://[::1", LinkAction("blocked", "http://[::1")),  # unparsable
        ("", LinkAction("blocked", "")),
    ],
)
def test_link_actions(href, expected):
    assert link_action(href) == expected


def test_slug_of_a_heading_is_github_style():
    assert heading_slug("Resultados Finais") == "resultados-finais"
    assert heading_slug("  Passo 1: Gerar o SCF!  ") == "passo-1-gerar-o-scf"
    assert heading_slug("Cálculo de Bandas (Al)") == "cálculo-de-bandas-al"
    assert heading_slug("a_b - c") == "a_b---c"


def test_repeated_headings_get_a_number():
    assert heading_slugs(["Notas", "Uso", "Notas", "Notas"]) == [
        "notas",
        "uso",
        "notas-1",
        "notas-2",
    ]
    assert heading_slugs([]) == []
