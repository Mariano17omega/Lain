"""Spec 52: the English catalog grows one area at a time (specs 53–59) and nothing it translates
already is shown in Portuguese.

- R1: the partial ``.mo`` and ``scripts/i18n.py check --area``;
- R2: the per-area gate (``tests/i18n_areas.py``), the ``.po`` following the code, the ``.mo`` the
  ``.po``;
- R3: the fields, tags, ``&`` and plural forms a translation keeps;
- R4: the traps of ``_()``: unmarked text, a local ``_``, the ``_()`` of a variable;
- R5: the leak probe, one process per language (``tests/i18n_probe.py``).
"""

from __future__ import annotations

import pytest
from babel.messages.mofile import read_mo

from i18n_areas import AREAS, DONE, area_of
from i18n_helpers import first_lines, leaks, probe_texts, script, untranslated_in_done
from i18n_static import (
    SOURCE,
    check_source,
    check_tree,
    dynamic_messages,
    python_files,
    shadowed_underscore,
)

tool = script()


@pytest.fixture(scope="module")
def po():
    return tool.read_catalog(tool.po_path("en"), "en")


@pytest.fixture(scope="module")
def updated():
    """The catalog after the code: what ``scripts/i18n.py update`` would write."""
    return tool.update(tool.extract(), "en")


def catalog(*entries, fuzzy=()):
    """An English catalog of ``(msgid, msgstr, file, …)``; a plural msgid and msgstr are tuples."""
    result = tool.new_catalog("en")
    for msgid, string, *files in entries:
        flags = ("fuzzy",) if msgid in fuzzy else ()
        result.add(msgid, string, locations=[(name, 1) for name in files], flags=flags)
    return result


def pairs(messages) -> dict:
    return {tool.sources(message): tool.forms(message) for message in messages}


# -- R1: partial .mo, check by area -------------------------------------------------------------
def test_compile_leaves_the_untranslated_out(tmp_path):
    source = catalog(
        ("Abrir", "Open", "ui/app.py"),
        ("Fechar", "", "ui/app.py"),
        (("{n} pasta", "{n} pastas"), ("", ""), "ui/app.py"),
        (("{n} arquivo", "{n} arquivos"), ("{n} file", "{n} files"), "ui/app.py"),
    )
    target = tmp_path / "lain.mo"
    assert tool.compile_catalog(source, target) == []
    with target.open("rb") as handle:
        compiled = pairs(tool.messages(read_mo(handle)))
    assert compiled == {
        ("Abrir",): ("Open",),
        ("{n} arquivo", "{n} arquivos"): ("{n} file", "{n} files"),
    }
    assert len(tool.messages(source)) == 4  # the catalog itself is left as it was


@pytest.mark.parametrize(
    "source",
    [
        catalog(("Abrir", "Open", "ui/app.py"), fuzzy={"Abrir"}),
        catalog(("Abrir {name}", "Open", "ui/app.py")),
    ],
    ids=["fuzzy", "markers"],
)
def test_compile_refuses_fuzzy_and_broken_markers(tmp_path, source):
    target = tmp_path / "lain.mo"
    assert tool.compile_catalog(source, target)
    assert not target.exists()


def test_check_area_lists_only_that_area(capsys):
    source = catalog(
        ("Abrir", "", "ui/app.py"),
        ("Enviar", "", "core/sync/request.py"),
        ("nenhum", "", "ui/help_controller.py", "core/sync/report.py"),
        ("Fechar", "Close", "core/sync/request.py"),
    )
    table = tool.by_area(source, area_of)
    assert (table[53].total, len(table[53].pending)) == (2, 2)  # the shared one counts in both
    assert (table[58].total, len(table[58].pending)) == (3, 2)
    assert tool.check("en", source, 58) == 1
    out = capsys.readouterr().out
    assert "en, area 58: 2 untranslated" in out
    assert "'Enviar' (core/sync/request.py)" in out and "'nenhum' (core/sync/report.py)" in out
    assert "Abrir" not in out and "Fechar" not in out
    assert tool.check("en", catalog(("Fechar", "Close", "core/sync/request.py")), 58) == 0


# -- R2: the gate by area -----------------------------------------------------------------------
def test_untranslated_only_in_pending_areas(updated):
    found = untranslated_in_done(updated, DONE)
    assert not found, "translate (scripts/i18n.py check --area N):\n" + first_lines(found)


def test_the_gate_refuses_an_area_done():
    source = catalog(("Abrir", "", "ui/app.py"), ("Enviar", "", "core/sync/request.py"))
    assert untranslated_in_done(source, set()) == []
    assert untranslated_in_done(source, {53}) == ["area 53: 'Abrir' (ui/app.py)"]
    fuzzy = catalog(("Abrir", "Open", "ui/app.py"), fuzzy={"Abrir"})
    assert untranslated_in_done(fuzzy, set()) == ["fuzzy: 'Abrir'"]


def test_every_area_names_code():
    assert [prefix for prefix in AREAS if not (SOURCE / prefix).exists()] == []
    assert area_of("core/calc_create/types/slab.py") == 57  # the longest prefix
    assert area_of("core/calc_create/writer.py") == 56
    assert area_of("ui/app.py") == 53  # no prefix


def test_po_follows_the_code(po, updated):
    def ids(source):
        return {tool.sources(message) for message in tool.messages(source)}

    new, gone = ids(updated) - ids(po), ids(po) - ids(updated)
    assert not new and not gone, (
        f"{len(new)} new and {len(gone)} gone messages: run `uv run python scripts/i18n.py update`"
    )


def test_mo_follows_po(po):
    path = tool.mo_path("en")
    assert path.is_file(), "run `uv run python scripts/i18n.py compile`"
    with path.open("rb") as handle:
        compiled = pairs(tool.messages(read_mo(handle)))
    translated = pairs(message for message in tool.messages(po) if tool.is_translated(message))
    assert compiled == translated, "run `uv run python scripts/i18n.py compile`"


# -- R3: what a translation keeps ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("msgid", "msgstr"),
    [
        ("Abrir {name}", "Open"),
        ("Abrir", "Open {name}"),
        ("valor {value!r}", "value {value}"),
        ("<b>Abrir</b> a pasta", "Open the folder"),
        ("&SYSTEM sem ibrav", "SYSTEM without ibrav"),
        (("{n} pasta", "{n} pastas"), ("{n} folder", "")),
    ],
    ids=["field-lost", "field-added", "conversion", "tag", "ampersand", "one-plural-form"],
)
def test_a_broken_translation_is_a_problem(msgid, msgstr):
    assert tool.problems(catalog((msgid, msgstr, "ui/app.py")))


@pytest.mark.parametrize(
    ("msgid", "msgstr"),
    [
        ("Abrir {name}", "Open {name}"),
        ("{b} e {a}", "{a} and {b}"),
        ("valor {value!r:>8}", "value {value!r:>8}"),
        ("<b>Abrir</b> a pasta", "Open the <b>folder</b>"),
        ("&SYSTEM sem ibrav", "&SYSTEM without ibrav"),
        (("{n} pasta", "{n} pastas"), ("{n} folder", "{n} folders")),
        ("<pasta>/<nome>.xsf", "<folder>/<name>.xsf"),  # words, not tags
        ("${ sem } na linha", "${ without } on the line"),  # not a field
    ],
)
def test_a_faithful_translation_is_no_problem(msgid, msgstr):
    assert tool.problems(catalog((msgid, msgstr, "ui/app.py"))) == []


def test_the_catalog_has_no_problem(po):
    assert tool.problems(po) == []
    assert po.plural_forms == "nplurals=2; plural=(n != 1);"


# -- R4: the traps of _() -----------------------------------------------------------------------
def test_no_visible_text_outside_markers():
    assert [str(finding) for finding in check_tree()] == []


def test_static_finds_unaccented_portuguese():
    old = 'ERROR_BADGE = "ERRO"  # a folder with a CRASH file\n'
    assert [finding.text for finding in check_source(old, "ui/widgets/explorer.py")] == ["ERRO"]
    for marked in ('ERROR_BADGE = _("ERRO")\n', 'ERROR_BADGE = N_("ERRO")\n'):
        assert check_source(marked, "ui/widgets/explorer.py") == []
    assert check_source('KIND = "dos"\nSHELL = "do"\nKEY = "sem_tipo"\n', "core/x.py") == []


OLD_PALETTE = """
from ..i18n import _


class PaletteController:
    def execute(self, key):
        kind, _, value = key.partition(":")
        return kind, value
"""


def test_no_local_underscore():
    found = [str(f) for text, name in python_files() for f in shadowed_underscore(text, name)]
    assert found == [], (
        "a module that translates with _() binds _ again (use _sep…):\n" + "\n".join(found)
    )


def test_a_local_underscore_is_found():
    assert [f.line for f in shadowed_underscore(OLD_PALETTE, "ui/palette_controller.py")] == [7]
    fixed = OLD_PALETTE.replace("kind, _, value", "kind, _sep, value")
    assert shadowed_underscore(fixed, "ui/palette_controller.py") == []
    gettext = "from ..i18n import _\n"
    for binding in (
        "for _ in range(3):\n    pass",
        "def f(_):\n    pass",
        "with open(path) as _:\n    pass",
        "try:\n    pass\nexcept OSError as _:\n    pass",
        "import os as _",
        "first, *_ = items",
    ):
        assert shadowed_underscore(gettext + binding + "\n", "ui/x.py"), binding
    # Scopes of their own, and a module that does not translate with _().
    allowed = gettext + "f = lambda _=False: 1\nrows = [[] for _ in range(3)]\n"
    assert shadowed_underscore(allowed, "ui/x.py") == []
    assert shadowed_underscore("for _ in range(3):\n    pass\n", "core/x.py") == []


# The marker calls whose message is not a literal. The extraction cannot see them: the data they get
# must be marked with N_ where it is defined, and the spec of the area tests it in English at run
# time (53: filter_bar; 55: param_widgets, Method.label; 56: form.py; 57: adsorption.py). A new one
# goes here, with that test.
DYNAMIC = [
    ("core/calc_create/types/adsorption.py", "FROM_COORDS"),
    ("core/calc_create/types/adsorption.py", "FROM_LIST"),
    ("core/calculations/base.py", "self.value"),
    ("ui/dialogs/calc_create/form.py", "choice"),
    ("ui/widgets/filter_bar.py", "value"),
    ("ui/widgets/filter_bar.py", "value"),
    ("ui/widgets/param_widgets.py", "title"),
    ("ui/widgets/param_widgets.py", "title"),
]


def test_dynamic_translations_are_declared():
    found = [call for text, name in python_files() for call in dynamic_messages(text, name)]
    assert sorted(found) == sorted(DYNAMIC)


# -- R5: the leak probe -------------------------------------------------------------------------
MENUS = ["Arquivo", "Navegar", "Cluster", "Gráficos", "Ferramentas", "Ajuda"]
SIDE_BAR = ["Árvore", "Grade", "Plot", "Grids", "Rsync", "Criar", "Tema"]


@pytest.fixture(scope="module")
def english():
    return probe_texts("en", "main", "plot")


@pytest.fixture(scope="module")
def portuguese():
    return probe_texts("pt_BR", "main")


@pytest.mark.parametrize("scenario", ["main", "plot"])
def test_no_leaks_in_english(english, po, scenario):
    found = leaks(english[scenario], po)
    assert found == [], "translated but shown in Portuguese (no _() on the way):\n" + first_lines(
        found
    )


@pytest.mark.parametrize("scenario", ["main"])
def test_portuguese_unchanged(portuguese, scenario):
    texts = set(portuguese[scenario])
    assert [text for text in MENUS + SIDE_BAR if text not in texts] == []
