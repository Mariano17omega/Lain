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

import ast
import re
import tempfile
from pathlib import Path

import pytest
from babel.messages.mofile import read_mo

from i18n_areas import AREAS, DONE, area_of
from i18n_helpers import (
    CODE_TOKENS,
    first_lines,
    fragment_leaks,
    leaks,
    lost_code_tokens,
    lost_negations,
    probe_texts,
    script,
    untranslated_in_done,
)
from i18n_scenarios_57 import TYPE_IDS
from i18n_static import (
    ACCENTED,
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


# -- spec 54 R1.3: the pieces of code a translation keeps --------------------------------------------
@pytest.mark.parametrize(
    ("msgid", "msgstr", "lost"),
    [
        ("faltam celldm(1) ou A no &SYSTEM", "celldm(1) or A missing in SYSTEM", "&SYSTEM"),
        ("-pe pede o ambiente (ex.: -pe physica 64)", "pe needs the environment", "-pe"),
        ("execução incompleta (sem JOB DONE)", "incomplete run (no job done)", "JOB DONE"),
        ("Falta o #! na primeira linha", "Missing shebang on the first line", "#!"),
        ("`prefix` repetido", "prefix repeated", "`prefix`"),
        ("sem CELL_PARAMETERS", "without the cell parameters", "CELL_PARAMETERS"),
        ("lê o \\r como comando", "reads the \\\\r as a command", "\\r"),
    ],
    ids=["namelist", "option", "job-done", "shebang", "backticks", "card", "backslash"],
)
def test_a_lost_code_token_is_found(msgid, msgstr, lost):
    source = catalog((msgid, msgstr, "core/qe/lattice.py"))
    assert lost_code_tokens(source, {54}) == [f"{msgid!r}: lost {lost!r}"]
    assert lost_code_tokens(source, {53}) == []  # only the areas given are checked


def test_a_faithful_translation_keeps_its_code_tokens():
    faithful = catalog(
        ("faltam celldm(1) ou A no &SYSTEM", "&SYSTEM lacks celldm(1) or A", "core/qe/lattice.py"),
        ("-pe pede slots (ex.: -pe physica 64)", "-pe needs slots (e.g. -pe physica 64)", "core/qsub_lint.py"),
        ("Divisão de k-pontos (npool)", "k-point division (npool)", "core/qe/summary/build.py"),
        ("{name} não é um relax/vc-relax", "{name} is not a relax/vc-relax", "core/qe/scf_from_relax.py"),
        ("lê o \\r como comando", "reads the \\r as a command", "core/qsub_lint.py"),
    )  # fmt: skip
    assert lost_code_tokens(faithful, {54}) == []


def test_code_tokens_are_kept(po):
    """Every translated message of a finished area keeps its namelists, options, cards and escapes."""
    found = lost_code_tokens(po, DONE)
    assert found == [], "a translation changed a piece of code:\n" + first_lines(found)


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
# time (53: filter_bar; 55: param_widgets, Method.label, the relax thresholds' "QE default"; 56:
# form.py, the rule of the fixed atoms; 57: the rules and the coordination in the tooltips and in
# geracao.md, the label of a pp.x code, the title of a tab of fields). A new one goes here, with that
# test.
DYNAMIC = [
    ("core/calc_create/surface/fixing.py", "rule"),
    ("core/calc_create/types/adsorption.py", "FROM_COORDS"),
    ("core/calc_create/types/adsorption.py", "FROM_LIST"),
    ("core/calc_create/types/adsorption.py", "mode"),
    ("core/calc_create/types/charge.py", "labels[code]"),
    ("core/calc_create/types/surface_fields.py", "BOTTOM"),
    ("core/calc_create/types/surface_fields.py", "NONE"),
    ("core/calc_create/types/surface_fields.py", "SPECIES"),
    ("core/calc_create/types/surface_fields.py", "rule"),
    ("core/calculations/base.py", "self.value"),
    ("core/calculations/relax_panels.py", "QE_DEFAULT"),
    ("ui/dialogs/calc_create/form.py", "choice"),
    ("ui/dialogs/calc_create/tabs_page.py", "group"),
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
# Spec 54: the viewers (text, input, diff, Markdown, .qsub) and the Resumo.
AREA_54 = ["text_viewer", "input_viewer", "diff", "summary", "markdown", "qsub"]
# Spec 55: the plots (adjustments panel of each module), the atoms, the Grids, the export and the
# roles of the detected files. ``figures`` and ``csv`` are facts: what is drawn and written.
AREA_55 = [
    "params_bands",
    "params_pdos",
    "params_bands_dos",
    "params_relax",
    "params_scf",
    "atoms_dialog",
    "grid_dialog",
    "export",
    "files_roles",
]
FACTS_55 = ["figures", "csv"]
# Spec 56: the "Criar cálculo" window (step 1 in both modes, step 2 of a Slab, its messages), the
# k-path editor and "Gerar SCF convergido". The facts: the notes of preview.py, geracao.md, the combos.
AREA_56 = ["calc_create_setup", "calc_create_files", "kpath_editor", "derive", "calc_create_errors"]
FACTS_56 = ["calc_create_notices", "report_text", "combo_data"]
# Spec 57: step 2 of each type (its fields) and what each type refuses; the files of a Slab (facts).
AREA_57 = [
    *(f"calc_create_{type_id}" for type_id in TYPE_IDS),
    *(f"calc_create_validation_{type_id}" for type_id in TYPE_IDS),
]
FACTS_57 = ["slab_files"]
# Spec 58: the sync window of a download and of an upload (preview, progress, conflict), how a run
# ends, the menu and the failures. Each also returns facts: the cells of the preview, the reports.
AREA_58 = ["sync_preview_pull", "sync_preview_push", "sync_report", "sync_menu", "sync_failures"]
# The scenarios with texts to check for leaks: spec 52's two, spec 53's eleven (the window, its
# menus and the general dialogs), spec 54's six, spec 55's nine, spec 56's five, spec 57's twenty,
# spec 58's five. The next specs of the series add theirs.
LEAK_SCENARIOS = [
    "main",
    "plot",
    "shortcuts",
    "about",
    "palette",
    "context_menu",
    "open_with",
    "rename",
    "new_project",
    "overwrite",
    "toast",
    "tree",
    *AREA_54,
    *AREA_55,
    *AREA_56,
    *AREA_57,
    *AREA_58,
    "first_run",
]
# What no widget shows (the probe's "facts"). They run before ``first_run``, whose overlay stays on.
FACT_SCENARIOS = ["menus", "cli", "config", "restart", "type_filter", "lint"]


@pytest.fixture(scope="module")
def english():
    order = [
        *LEAK_SCENARIOS[:-1],
        *FACT_SCENARIOS,
        *FACTS_55,
        *FACTS_56,
        *FACTS_57,
        LEAK_SCENARIOS[-1],
    ]
    return probe_texts("en", *order)


@pytest.fixture(scope="module")
def portuguese():
    dialogs_55 = AREA_55[5:]  # the scenarios whose facts are compared with the English ones
    return probe_texts(
        "pt_BR",
        "main",
        "shortcuts",
        "tree",
        *AREA_54,
        *FACT_SCENARIOS,
        *dialogs_55,
        *FACTS_55,
        *AREA_56,
        *FACTS_56,
        *AREA_57,
        *FACTS_57,
        *AREA_58,
    )


@pytest.mark.parametrize("scenario", LEAK_SCENARIOS)
def test_no_leaks_in_english(english, po, scenario):
    found = leaks(english[scenario], po)
    assert found == [], "translated but shown in Portuguese (no _() on the way):\n" + first_lines(
        found
    )


@pytest.mark.parametrize("scenario", ["main"])
def test_portuguese_unchanged(portuguese, scenario):
    texts = set(portuguese[scenario])
    assert [text for text in MENUS + SIDE_BAR if text not in texts] == []


# -- spec 53: what the window says outside its widgets ---------------------------------------------
def test_en_menus(english, portuguese):
    assert english["menus#facts"] == ["File", "Navigate", "Cluster", "Plots", "Tools", "Help"]
    assert portuguese["menus#facts"] == MENUS


def test_the_help_option_follows_the_language(english, portuguese):
    shown = "\n".join(english["cli#facts"])
    assert "path to config.yaml" in shown and "detailed log" in shown
    assert "caminho do config.yaml" not in shown
    shown = "\n".join(portuguese["cli#facts"])
    assert "caminho do config.yaml" in shown and "log detalhado" in shown


def test_an_invalid_config_is_reported_in_the_language(english, portuguese):
    """Our messages follow the language; the pydantic ones would stay as the library writes them."""
    head, *problems = english["config#facts"]
    assert head.startswith("Invalid configuration (")
    assert problems == [
        "• plot: energy_min must be less than energy_max",
        "• ui.bogus: unknown key",
    ]
    head, *problems = portuguese["config#facts"]
    assert head.startswith("Configuração inválida (")
    assert problems == [
        "• plot: energy_min deve ser menor que energy_max",
        "• ui.bogus: chave desconhecida",
    ]


def test_a_reload_that_changes_the_language_says_to_restart(english, portuguese):
    assert english["restart#facts"] == ["The language changes when Lain restarts."]
    assert portuguese["restart#facts"] == ["O idioma muda ao reiniciar o Lain."]


def test_the_painted_error_badge_is_translated(english, portuguese):
    """The badge of a folder with a CRASH file is painted, not a widget: ask what was painted."""
    assert "ERROR" in english["tree#facts"] and "ERRO" not in english["tree#facts"]
    assert "ERRO" in portuguese["tree#facts"] and "ERROR" not in portuguese["tree#facts"]


def test_the_type_filter_compares_the_data_not_the_label(english, portuguese):
    """ "outputs" and "saídas" are the same stored value: both languages list the same files."""
    assert english["type_filter#facts"] == portuguese["type_filter#facts"] != []
    assert "outputs" in english["type_filter"] and "saídas" not in english["type_filter"]
    assert "saídas" in portuguese["type_filter"]


def test_the_plurals_of_the_area_have_both_forms(po):
    forms = {tool.sources(message): tool.forms(message) for message in tool.messages(po)}
    assert forms[("{n} item", "{n} itens")] == ("{n} item", "{n} items")
    assert forms[("Copiado: {name}", "Copiados: {n} itens")] == (
        "Copied: {name}",
        "Copied: {n} items",
    )

    # Spec 54: the counts of the viewers and of the reading of the outputs.
    assert forms[("{count} linha difere", "{count} linhas diferem")] == (
        "{count} line differs",
        "{count} lines differ",
    )
    assert forms[("Convergiu em {count} iteração", "Convergiu em {count} iterações")] == (
        "Converged in {count} iteration",
        "Converged in {count} iterations",
    )
    assert forms[("{n} problema de escrita no input", "{n} problemas de escrita no input")] == (
        "{n} syntax problem in the input",
        "{n} syntax problems in the input",
    )
    lattice = ("nat = {nat}, mas ATOMIC_POSITIONS tem {count} linha",)
    [(source, strings)] = [(k, v) for k, v in forms.items() if k[0] == lattice[0]]
    assert len(source) == len(strings) == 2 and all(strings)

    # Spec 55: the counts of the plots (grid, relax, SCF).
    assert forms[("{drawn} gráfico", "{drawn} gráficos")] == ("{drawn} plot", "{drawn} plots")
    assert forms[("{moves} passo BFGS", "{moves} passos BFGS")] == (
        "{moves} BFGS step",
        "{moves} BFGS steps",
    )
    assert forms[("{count} iteração", "{count} iterações")] == (
        "{count} iteration",
        "{count} iterations",
    )
    assert forms[
        (
            "{truncated_steps} passo incompleto ignorado",
            "{truncated_steps} passos incompletos ignorados",
        )
    ] == ("{truncated_steps} incomplete step ignored", "{truncated_steps} incomplete steps ignored")
    area_55 = [
        message
        for message in tool.messages(po)
        if len(tool.sources(message)) == 2
        and any(area_of(filename) == 55 for filename, _line in message.locations)
    ]
    assert area_55  # the area has plurals, and each has two forms that differ
    assert [tool.sources(m)[0] for m in area_55 if len(set(tool.forms(m))) != 2] == []

    # Spec 56: the folder's files and the k-points of a mesh.
    assert forms[
        ("Pasta {name} criada com {count} arquivo", "Pasta {name} criada com {count} arquivos")
    ] == ("Folder {name} created with {count} file", "Folder {name} created with {count} files")
    assert forms[
        (
            "{n1}×{n2}×{n3} = {count} k-point na rede (o pw.x reduz pela simetria)",
            "{n1}×{n2}×{n3} = {count} k-points na rede (o pw.x reduz pela simetria)",
        )
    ] == (
        "{n1}×{n2}×{n3} = {count} k-point in the mesh (pw.x reduces it by symmetry)",
        "{n1}×{n2}×{n3} = {count} k-points in the mesh (pw.x reduces them by symmetry)",
    )
    area_56 = [
        message
        for message in tool.messages(po)
        if len(tool.sources(message)) == 2
        and any(area_of(filename) == 56 for filename, _line in message.locations)
    ]
    assert len(area_56) >= 3  # the lines of ATOMIC_POSITIONS (shared with 54), the files, the mesh
    assert [tool.sources(m)[0] for m in area_56 if len(set(tool.forms(m))) != 2] == []

    # Spec 57: the anchor atoms of the report and the bonds a slab's cut leaves open.
    assert forms[("Átomo âncora", "Átomos âncora")] == ("Anchor atom", "Anchor atoms")
    area_57 = [
        message
        for message in tool.messages(po)
        if len(tool.sources(message)) == 2
        and any(area_of(filename) == 57 for filename, _line in message.locations)
    ]
    assert len(area_57) == 3
    assert [tool.sources(m)[0] for m in area_57 if len(set(tool.forms(m))) != 2] == []

    # Spec 58: the counts of the sync (the files of a preview, a report, a progress).
    assert forms[("{count} arquivo baixado.", "{count} arquivos baixados.")] == (
        "{count} file downloaded.",
        "{count} files downloaded.",
    )
    assert forms[("{done}/{total} arquivo", "{done}/{total} arquivos")] == (
        "{done}/{total} file",
        "{done}/{total} files",
    )
    assert forms[("Enviando {count} arquivo…", "Enviando {count} arquivos…")] == (
        "Uploading {count} file…",
        "Uploading {count} files…",
    )
    area_58 = [
        message
        for message in tool.messages(po)
        if len(tool.sources(message)) == 2
        and any(area_of(filename) == 58 for filename, _line in message.locations)
    ]
    assert len(area_58) == 14
    # The two forms differ, but for a sentence with no word that changes with the number.
    assert sorted(tool.sources(m)[0] for m in area_58 if len(set(tool.forms(m))) != 2) == [
        "{count} já existe no cluster (não será alterado)",
        "{count} mais recente no computador (não será alterado)",
    ]


# -- spec 54: the viewers and the reading of the QE outputs ------------------------------------------
def test_the_shortcuts_dialog_names_the_viewer_in_english(english, portuguese):
    """The dialog lists ``TextViewer.shortcut_help``: its actions and its "where" follow the language."""
    rows = english["shortcuts#facts"]
    assert "Search in text | Ctrl+F | Text viewer" in rows
    assert "Next syntax problem | F8 | Text viewer" in rows
    assert not [row for row in rows if "Visualizador de texto" in row or "ocorrência" in row]
    assert "Buscar no texto | Ctrl+F | Visualizador de texto" in portuguese["shortcuts#facts"]


def test_the_viewer_buttons_follow_the_language(english, portuguese):
    shown = set(english["text_viewer"])
    assert {"Go to line", "Line:", "Go to line…", "Go to start (Ctrl+Home)", "Rendered"} <= shown
    assert {"Show the file text", "Show or hide the input extract"} <= shown
    assert not {"Ir à linha", "Linha:", "Renderizado", "Extrato"} & shown
    assert {"Ir à linha", "Linha:", "Renderizado"} <= set(portuguese["text_viewer"])


def test_the_banners_of_the_text_viewer(english, portuguese):
    assert english["text_viewer#facts"] == [
        "Empty file: the job logged no errors.",
        "The job logged error messages.",
        "Large file (760 B): showing the first 100 B and the last 200 B.",
        "Complete file (760 B).",
        "[ … section omitted by the viewer … ]",
        "Large input (174 B): syntax was not checked, only highlighted.",
        "Large script (172 B): syntax was not checked, only highlighted.",
        "Large Markdown (140 B): shown as text, not rendered.",
    ]
    assert portuguese["text_viewer#facts"] == [
        "Arquivo vazio: o job não registrou erros.",
        "O job registrou mensagens de erro.",
        "Arquivo grande (760 B): exibindo o primeiro 100 B e os últimos 200 B.",
        "Arquivo completo (760 B).",
        "[ … trecho omitido pelo visualizador … ]",
        "Input grande (174 B): a escrita não foi verificada, só o realce.",
        "Script grande (172 B): a escrita não foi verificada, só o realce.",
        "Markdown grande (140 B): exibido como texto, sem renderizar.",
    ]


def test_the_problems_bar_counts_in_the_language(english, portuguese):
    assert english["input_viewer#facts"][0] == "4 syntax problems in the input"
    assert english["qsub#facts"] == ["8 syntax problems in the script"]
    assert portuguese["input_viewer#facts"][0] == "4 problemas de escrita no input"
    assert portuguese["qsub#facts"] == ["8 problemas de escrita no script"]
    assert "nspin: 1 (default) | Go to line 7" in english["input_viewer#facts"]
    assert "nspin: 1 (padrão) | Ir à linha 7" in portuguese["input_viewer#facts"]


def test_issue_messages_are_translated(english, portuguese, po):
    """The editor shows the linters' messages in a hover tip (``QToolTip``), not in a widget: ask
    the linters. A Portuguese message cannot hide among them, whatever its fields."""
    in_english, in_portuguese = english["lint#facts"], portuguese["lint#facts"]
    assert len(in_english) == len(in_portuguese) >= 30  # the input has to reach every rule
    assert [a for a, b in zip(in_english, in_portuguese, strict=True) if a == b] == []
    assert leaks(in_english, po) == []
    assert "Unclosed quotes" in in_english and "Aspas não fechadas" in in_portuguese
    assert "Unknown namelist &CONTRL (did you mean &CONTROL?)" in in_english


def test_the_diff_labels_follow_the_language(english, portuguese):
    cells = english["diff#facts"]
    assert "control | prefix | x | — | only in A" in cells
    assert "system | ecutrho | — | 160 | only in B" in cells
    assert "system | ecutwfc | 30 | 40 | different" in cells
    assert "card | ATOMIC_SPECIES: 2 lines differ |  |  | different" in cells
    assert "card | K_POINTS: option automatic ↔ gamma, 1 line differs |  |  | different" in cells
    assert " | line | 4 4 4 0 0 0 | — | " in cells
    assert "card | CELL_PARAMETERS: only in A |  |  | only in A" in cells
    assert cells[-1] == "Could not compare: b.in: file too large to compare"
    cells = portuguese["diff#facts"]
    assert "control | prefix | x | — | só em A" in cells
    assert "card | ATOMIC_SPECIES: 2 linhas diferem |  |  | diferente" in cells
    assert "card | K_POINTS: opção automatic ↔ gamma, 1 linha difere |  |  | diferente" in cells
    assert cells[-1] == "Não foi possível comparar: b.in: arquivo grande demais para comparar"


def test_the_summary_follows_the_language(english, portuguese):
    rows = english["summary#facts"]
    titles = [row for row in rows if row.isupper()]
    assert titles == ["GENERAL", "SYSTEM", "RESULTS", "WARNINGS AND ERRORS"]
    for row in (
        "Status: Finished",
        "Wall time: 1h 15min 00s",
        "CPU time: 1h 10min 00s",
        "Parallelization: MPI, 64 processors",
        "k-point division (npool): 8",
        "Irreducible k-points: 52",
        "k-point mesh: automatic 6×4×4 (0 0 0)",
        "Spin: unpolarized",
        "Pressure: 0.08 kbar",
        "Total force: 0.000433 Ry/Bohr",
        "SCF: Converged in 35 iterations",
        "BFGS: Converged (25 SCF cycles, 24 BFGS steps)",
        "Volume (initial → final): 2218.2317 → 2253.94778 a.u.^3",
        "Messages: No warnings or errors",
    ):
        assert row in rows
    rows = portuguese["summary#facts"]
    titles = [row for row in rows if row.isupper()]
    assert titles == ["GERAL", "SISTEMA", "RESULTADOS", "AVISOS E ERROS"]
    for row in (
        "Estado: Concluído",
        "Malha k: automatic 6×4×4 (0 0 0)",
        "SCF: Convergiu em 35 iterações",
        "BFGS: Convergiu (25 ciclos SCF, 24 passos BFGS)",
        "Pressão: 0.08 kbar",  # the decimal point is QE's, in both languages
    ):
        assert row in rows


def test_a_refused_markdown_link_says_so_in_the_language(english, portuguese):
    assert english["markdown#facts"] == ["Link not opened: outro.md"]
    assert portuguese["markdown#facts"] == ["Link não aberto: outro.md"]


# -- spec 55: the plots, the atoms, the Grids and the export ---------------------------------------
LABELS_55 = {"Valence", "Conduction", "BFGS step", "PDOS (states/eV)", "SCF iteration"}
SOURCE_LABELS_55 = {"Valência", "Condução", "Passo BFGS", "PDOS (estados/eV)", "Iteração SCF"}


def test_figure_text_in_english(english, portuguese, po):
    """The text *inside* the figures follows the language (spec_end): no widget shows it, so the
    probe asks matplotlib for the text of every artist."""
    drawn = set(english["figures#facts"])
    assert leaks(english["figures#facts"], po) == []
    assert drawn >= LABELS_55
    assert {"Sum of the selected atoms", "No panel selected", "↑ solid", "↓ dashed"} <= drawn
    assert any(text.startswith("Plot unavailable: ") for text in drawn)
    # A threshold the run did not state is named in the legend with the data token translated.
    assert any(text.endswith("(QE default)") for text in drawn)
    assert not [text for text in drawn if "padrão do QE" in text]
    assert not SOURCE_LABELS_55 & drawn
    # What is maths or a unit is the same in both languages.
    assert {"$E - E_F$ (eV)", "|ΔE| (Ry)", "Spin ↑", "Spin ↓"} <= drawn
    in_portuguese = set(portuguese["figures#facts"])
    assert any(text.endswith("(padrão do QE)") for text in in_portuguese)
    assert in_portuguese >= SOURCE_LABELS_55 and not LABELS_55 & in_portuguese


def test_the_csv_and_the_export_names_do_not_follow_the_language(english, portuguese):
    """A script that reads the columns of an old CSV keeps finding them (spec 55 R2): the header and
    the whole text (a digest), and the files ``plan_export`` names, are the same in both languages."""
    assert english["csv#facts"] == portuguese["csv#facts"]
    shown = "\n".join(english["csv#facts"])
    for column in (
        "Banda 1 (E−E_F, eV)",
        "Total (estados/eV)",
        "Soma dos átomos selecionados (estados/eV)",
        "↓ (estados/eV, espelhado)",
    ):
        assert column in shown
    assert not re.search(r"\b(Band \d|states/eV|mirrored|Sum of)", shown)
    names = ["name: 03_bands-bands.png", "name: 03_bands-bands.svg", "name: 03_bands-bands.pdf"]
    for facts in (english["export#facts"], portuguese["export#facts"]):
        assert [f for f in facts if f.startswith("name:")] == [
            *names,
            "name: 03_bands-bands.csv",
            "name: next 03_bands-bands_2",
        ]
    assert "message: Export cancelled." in english["export#facts"]
    assert "message: Exportação cancelada." in portuguese["export#facts"]


def test_no_translation_in_the_modules_that_make_tables():
    """The columns of a CSV are data: the modules that name them never call ``_()`` (R2.1)."""
    modules = sorted(SOURCE.glob("core/calculations/**/table.py")) + [
        SOURCE / "core/plotting/table.py"
    ]
    assert len(modules) >= 4
    markers = {"_", "N_", "ngettext", "pgettext"}
    found = [
        f"{path.relative_to(SOURCE)}:{node.lineno}"
        for path in modules
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) in markers
    ]
    assert found == []


@pytest.fixture(scope="module")
def plot_files(tmp_path_factory):
    """The ``plot_files`` facts: ``pt_BR`` writes a ``<kind>.plot`` per module (every choice
    changed), then ``en`` reads those files and writes them again."""
    where = tmp_path_factory.mktemp("plot_files")
    first = probe_texts("pt_BR", "plot_files", plot_dir=where)["plot_files#facts"]
    second = probe_texts("en", "plot_files", plot_dir=where)["plot_files#facts"]
    return first, second


def test_the_plot_files_do_not_follow_the_language(plot_files):
    """A ``.plot`` written in Portuguese is read and written again in English byte for byte (R3.1):
    values, choices and the header are data. The last fact is the real way, ``flush_now``."""
    in_portuguese, in_english = plot_files
    assert in_english == in_portuguese
    *cases, window = in_english
    assert len(cases) == 21  # seven modules, three facts each
    for changed, original, again in zip(cases[0::3], cases[1::3], cases[2::3], strict=True):
        assert changed.endswith("]") and not changed.endswith(" []"), changed  # choices did change
        file_before, file_after = original.partition(":\n")[2], again.partition(":\n")[2]
        assert file_before == file_after and file_before.startswith("# Lain: ajustes do gráfico.")
    assert window.partition(":\n")[2] == cases[1].partition(":\n")[2]


def test_choice_values_are_not_labels(po):
    """A ``choice`` is saved by value and shown by label, so no value of a module may be the English
    label of a choice: a Portuguese value that equalled one would mean the data was translated
    (spec 55 R3.2)."""
    from i18n_scenarios_55 import CASES, build

    english = {
        tool.sources(message)[0]: tool.forms(message)[0]
        for message in tool.messages(po)
        if tool.is_translated(message)
    }
    choices = []  # (where, value, label)
    with tempfile.TemporaryDirectory(prefix="lain-i18n-choices-") as where:
        for case in CASES:
            session = build(case, Path(where))
            for field in session.module.param_schema(session.dataset):
                if field.kind == "choice":
                    choices += [(f"{case}.{field.name}", v, label) for v, label in field.choices]
    shown = {english.get(label, label) for _where, _value, label in choices}
    assert len(choices) > 40 and "Absolute" in shown  # there is something to compare
    assert [
        f"{where}: {value!r}"
        for where, value, _label in choices
        if isinstance(value, str) and value in shown
    ] == []


def test_method_label_in_english(english, portuguese):
    """``Method.label`` is shown, ``.value`` is the data (it stays Portuguese) and never reaches
    the screen (spec 55 R3.3)."""
    assert english["files_roles#facts"][:4] == [
        "nome = name",
        "conteúdo = content",
        "inferido = inferred",
        "manual = manual",
    ]
    assert portuguese["files_roles#facts"][:4] == [
        "nome = nome",
        "conteúdo = conteúdo",
        "inferido = inferido",
        "manual = manual",
    ]
    shown = english["files_roles"]
    assert any(text.endswith("(detected by name)") for text in shown)
    assert any(text.endswith("(detected by content)") for text in shown)
    assert not [text for text in shown if re.search(r"\(detected by (nome|conteúdo)", text)]
    assert any(text.endswith("(detectado por nome)") for text in portuguese["files_roles"])


def test_the_atoms_and_grids_windows_speak_english(english, portuguese):
    assert english["atoms_dialog#facts"] == [
        "Atoms of Al",
        "0 of 1 marked",
        "Mark at least one atom",
    ]
    assert portuguese["atoms_dialog#facts"] == [
        "Átomos de Al",
        "0 de 1 marcados",
        "Marque ao menos um átomo",
    ]
    grid = english["grid_dialog#facts"]
    assert grid[:5] == [
        "Could not open the grid “inexistente”.",
        "There is no saved grid named “1”.",
        "Cells 1 and 2 are at the same position (1, 1).",
        "Grid “1” saved.",
        "Grid “1” opened.",
    ]
    assert "Cell 1: position (1, 2) is outside the 1 × 1 grid." in grid
    assert "Rows and columns range from 1 to 6." in grid
    assert "Grade “1” salva." in portuguese["grid_dialog#facts"]


# -- spec 56: "Criar cálculo", the k-path editor and the report of the generation -------------------
def fact(facts: list[str], prefix: str) -> str:
    """The first fact that starts with ``prefix``."""
    return next(text for text in facts if text.startswith(prefix))


def test_the_report_title_follows_the_language_and_its_rows_do_not(english, portuguese):
    """``report_text`` writes the title in the language of the interface and every row as it was
    given (the labels of a type's rows are spec 57's): R2.2."""
    rows = ["", "- **rótulo**: valor", "- **Número**: 3.14", "name: geracao.md", "key: report"]
    assert english["report_text#facts"] == ["# Generation report", *rows]
    assert portuguese["report_text#facts"] == ["# Relatório da geração", *rows]


def test_the_report_tab_shows_what_is_written(english, portuguese):
    """The "Relatório" tab, the planned file and ``geracao.md`` on disk are the same text, in each
    language; the file keeps its name and only the prose follows the interface (R2.1, R2.3)."""
    for facts, title in (
        (english["calc_create_files#facts"], "# Generation report\n"),
        (portuguese["calc_create_files#facts"], "# Relatório da geração\n"),
    ):
        texts = [
            fact(facts, f"{kind}:\n").partition("\n")[2]
            for kind in ("preview", "planned", "written")
        ]
        assert texts[0] == texts[1] == texts[2] != ""
        assert texts[0].startswith(title)
        assert "name: geracao.md" in facts
        assert fact(facts, "files: ").split()[1] == "geracao.md"
    assert fact(english["calc_create_files#facts"], "files: ") == fact(
        portuguese["calc_create_files#facts"], "files: "
    )


def test_the_files_tab_names_the_kind_of_each_file(english, portuguese):
    assert [f for f in english["calc_create_files#facts"] if f.startswith("row: ")] == [
        "row: slab.qsub | SGE script",
        "row: vc-relax_kaolinite.in | pw.x input",
        "row: geracao.md | Report",
    ]
    assert [f for f in portuguese["calc_create_files#facts"] if f.startswith("row: ")] == [
        "row: slab.qsub | Script SGE",
        "row: vc-relax_kaolinite.in | Input do pw.x",
        "row: geracao.md | Relatório",
    ]
    assert any(
        f.startswith("note: Set jobs.pseudo_dir in config.yaml")
        for f in english["calc_create_files#facts"]
    )


def test_combo_data_is_the_value(english, portuguese):
    """A combo shows the label of the language and keeps the Portuguese token as its data, for every
    choice field of every type: ``currentData()`` is what ``plan`` reads (R2, R3.2)."""

    def data(facts: list[str]) -> list[str]:
        return [text for text in facts if text.startswith("data ")]

    assert data(english["combo_data#facts"]) == data(portuguese["combo_data#facts"])
    assert len(data(english["combo_data#facts"])) > 10  # the types have choices to compare
    shown = english["combo_data#facts"]
    assert (
        "data slab.fix_rule: ['camada inferior', 'espécies e vizinhos', 'nenhum'] now camada inferior"
        in shown
    )
    assert "text slab.fix_rule: ['bottom layer', 'species and neighbors', 'none']" in shown
    assert (
        "text adsorption.fix_rule: ['bottom layer', 'species and neighbors', 'from the SCF', 'none']"
        in shown
    )
    assert "text supercell.fix_rule: ['camada inferior'" in "\n".join(
        portuguese["combo_data#facts"]
    )
    # A code of pp.x and its label are one token (spec 57 R3.1): the data is the same text.
    assert (
        "data charge.iflag: ['0 — média esférica (1D)', '1 — gráfico 1D', '2 — gráfico 2D', "
        "'3 — grade 3D', '4 — gráfico 2D polar numa esfera'] now 3 — grade 3D"
    ) in shown
    assert (
        "text charge.iflag: ['0 — spherical average (1D)', '1 — 1D plot', '2 — 2D plot', "
        "'3 — 3D grid', '4 — 2D polar plot on a sphere']"
    ) in shown


def test_the_window_of_calc_create_follows_the_language(english, portuguese):
    """Step 1 and the switch of modes (R3.1): the title of the step, the switch and the rebuild notes."""
    en, pt = english["calc_create_setup#facts"], portuguese["calc_create_setup#facts"]
    assert en[0].startswith("Will be created: ") and pt[0].startswith("Será criada: ")
    assert en[1:3] == ["2 · Files", "Standard"] and pt[1:3] == ["2 · Arquivos", "Padrão"]
    assert en[3] == "This change redoes the next step: the fields go back to their defaults"
    assert en[4] == f"{en[3]} and the file edits are lost"
    assert pt[4] == f"{pt[3]} e as edições dos arquivos se perdem"
    shown = english["calc_create_setup"]
    for text in (
        "Only the type's standard fields; the rest follows the SCF and config.yaml",
        "Number",
    ):
        assert text in shown
    assert "Padrão" not in shown and "Avançado" not in shown


def test_the_errors_of_the_window_and_the_core_follow_the_language(english, portuguese):
    """What "Continuar" says it needs, what the folder name and the SCF are refused for, and what the
    core reports (R3.1, R1.2): the same errors, each in its language."""
    en, pt = english["calc_create_errors#facts"], portuguese["calc_create_errors#facts"]
    for facts, expected in (
        (
            en,
            [
                "no scf: Choose the SCF input",
                "name: Use only unaccented letters, digits, dot, hyphen and underscore in the name",
                "not an input: bands.dat.gnu does not look like a Quantum ESPRESSO input",
                "not an scf: The file is not an SCF (calculation = 'relax')",
                "taken: Will be created: Bands_Al_1 — Bands_Al already exists",
                "writer name: Invalid file name: 'a/b'",
                "writer place: The folder <dir>/nao_existe does not exist",
                "scf head: The file is not a pw.x input (no &SYSTEM)",
                "kmesh: the k-point mesh needs n1, n2, n3 ≥ 1",
                "kmesh: the mesh shifts are 0 or 1",
                "fixing: No atom was fixed by the rule 'from the SCF'",
            ],
        ),
        (
            pt,
            [
                "no scf: Escolha o input de SCF",
                "name: Use só letras sem acento, números, ponto, hífen e sublinhado no nome",
                "not an input: bands.dat.gnu não parece um input do Quantum ESPRESSO",
                "not an scf: O arquivo não é um SCF (calculation = 'relax')",
                "taken: Será criada: Bands_Al_1 — já existe Bands_Al",
                "writer name: Nome de arquivo inválido: 'a/b'",
                "writer place: A pasta <dir>/nao_existe não existe",
                "scf head: O arquivo não é um input do pw.x (sem &SYSTEM)",
                "kmesh: a rede de k-points precisa de n1, n2, n3 ≥ 1",
                "kmesh: os deslocamentos da rede são 0 ou 1",
                "fixing: Nenhum átomo ficou fixo pela regra 'do SCF'",
            ],
        ),
    ):
        assert [text for text in expected if text not in facts] == []
    assert fact(en, "bulk: ").startswith("bulk: scf-kaolinite.in looks like the SCF of a bulk: ")
    assert fact(en, "bulk: ").endswith("Choose the SCF of a relaxed surface (Slab or Supercell).")
    # A number is written with the point in both languages (QE reads it so; CLAUDE.md, "Numbers").
    assert "1.85 Å" in fact(en, "bulk: ") and "1.85 Å" in fact(pt, "bulk: ")
    assert fact(en, "writer write: ").startswith("writer write: Could not write <name>: ")
    assert fact(pt, "writer write: ").startswith("writer write: Não foi possível gravar <name>: ")
    # The token of the rule is shown by its label: the data ("do SCF") never leaks into the sentence.
    assert "'camada inferior'" not in "\n".join(en) and "'do SCF'" not in "\n".join(en)


def test_the_notices_and_the_counts_of_the_preview(english, portuguese):
    assert english["calc_create_notices#facts"] == [
        "Empty: keeps the K_POINTS of the SCF",
        "1×1×1 = 1 k-point in the mesh (pw.x reduces it by symmetry)",
        "4×4×2 = 32 k-points in the mesh (pw.x reduces them by symmetry)",
        "notice: Folder Bands_Al created with 1 file",
        "details:   bands.in",
        "notice: Folder Bands_Al created with 2 files. Use ‘Upload to cluster’ to take the folder to the cluster",
        "details: Bands already existed: created as Bands_Al",
        "place: Outside the root folder: detection and sync only see folders inside it",
        "place: The folder will be created outside a project and will show up as a new project.",
    ]
    assert portuguese["calc_create_notices#facts"] == [
        "Vazio: mantém o K_POINTS do SCF",
        "1×1×1 = 1 k-point na rede (o pw.x reduz pela simetria)",
        "4×4×2 = 32 k-points na rede (o pw.x reduz pela simetria)",
        "notice: Pasta Bands_Al criada com 1 arquivo",
        "details:   bands.in",
        "notice: Pasta Bands_Al criada com 2 arquivos. Use ‘Enviar ao cluster’ para levar a pasta ao cluster",
        "details: Bands já existia: criada como Bands_Al",
        "place: Fora da pasta raiz: a detecção e a sincronização só enxergam pastas dentro dela",
        "place: A pasta será criada fora de um projeto e aparecerá como um projeto novo.",
    ]


def test_the_cluster_reminder_names_the_action_as_the_menu_does(po):
    """The notice quotes the "Enviar ao cluster" item: its English text is the menu's, word for word."""
    items = {
        tool.sources(m)[0]: tool.forms(m)[0]
        for m in tool.messages(po)
        if tool.is_translated(m) and len(tool.sources(m)) == 1
    }
    quoted = items["Use ‘Enviar ao cluster’ para levar a pasta ao cluster"]
    assert f"‘{items['Enviar ao cluster']}’" in quoted


def test_the_k_path_editor_follows_the_language(english, portuguese):
    en, pt = english["kpath_editor#facts"], portuguese["kpath_editor#facts"]
    assert len(en) == len(pt)  # the same cells carry a note
    assert "cell 3,4: 'break' The path jumps from this point to the next one (weight 1)" in en
    assert "cell 3,4: 'quebra' O caminho salta deste ponto para o próximo (peso 1)" in pt
    assert any("Segment A→L collapses on the x axis of bands.x" in text for text in en)
    assert all("‘Distribute by length’" in text for text in en if "Segment" in text)
    assert all("‘Distribuir pelo comprimento’" in text for text in pt if "Segmento" in text)
    assert [text for text in en if text.startswith("typed")] == [
        "typed 'abc': Invalid value: abc",
        "typed '': Invalid value: empty",
    ]
    assert [text for text in pt if text.startswith("typed")] == [
        "typed 'abc': Valor inválido: abc",
        "typed '': Valor inválido: vazio",
    ]
    assert "no cell: SCF structure not readable" in en
    assert "no cell: Estrutura do SCF não legível" in pt
    shown = english["kpath_editor"]
    for text in ("Label", "Points", "Move up", "Mark segment break", "Points per Å⁻¹"):
        assert text in shown


def test_the_converged_scf_speaks_english(english, portuguese):
    en, pt = english["derive#facts"], portuguese["derive#facts"]
    assert en[0] == "toast: scf_convergido_silicon.in created"
    assert pt[0] == "toast: scf_convergido_silicon.in criado"
    assert "The SCF uses the same prefix (silicon) and outdir as the relax" in en[1]
    assert "O SCF usa o mesmo prefix (silicon) e outdir do relax" in pt[1]
    assert en[2] == "warning: Generate converged SCF | Relax input not found in the folder"
    assert pt[2] == "warning: Gerar SCF convergido | Input do relax não encontrado na pasta"
    assert "Generate converged SCF" in english["derive"]


# -- spec 57: the calculation types of "Criar cálculo" ---------------------------------------------
TYPES_EN = (
    "types: SCF | Relax | VC-Relax | Bands | PDOS | Charge | Charge difference | Slab | Supercell"
    " | Molecule on surface"
)
TYPES_PT = (
    "types: SCF | Relax | VC-Relax | Bandas | PDOS | Carga | Diferença de carga | Slab"
    " | Supercélula | Molécula na superfície"
)
QSUB_HEADER = "########       Configuração do pw.x         ########"
# Choice fields whose values are QE's own tokens: the combo shows them as written, in both
# languages, so they are no message (R3.1).
QE_CHOICES = {
    "axis": "the stacked axis and its Miller index, c (001)",
    "cell_dofree": "&CELL cell_dofree",
    "cell_dynamics": "&CELL cell_dynamics",
    "ion_dynamics": "&IONS ion_dynamics",
    "occupations": "&SYSTEM occupations",
}


def keyed(facts: list[str], prefix: str) -> dict[str, str]:
    """The facts ``<prefix> <key>: <text>`` as ``{key: text}``, in order."""
    found = {}
    for text in facts:
        if text.startswith(f"{prefix} "):
            key, _sep, rest = text.removeprefix(f"{prefix} ").partition(": ")
            found[key] = rest
    return found


def lost_code(pairs: dict[str, tuple[str, str]]) -> list[str]:
    """The pieces of code (``CODE_TOKENS``) of a Portuguese text that its English one lacks: what the
    window composes (a tooltip with its namelist, a message with its label) checked as shown."""
    return [
        f"{key}: lost {token!r}"
        for key, (portuguese, english) in pairs.items()
        for pattern in CODE_TOKENS
        for token in sorted(set(pattern.findall(portuguese)) - set(pattern.findall(english)))
    ]


def no_portuguese(facts: list[str], po) -> list[str]:
    """An accented letter or a short message of the area left in Portuguese inside an English text."""
    return [text for text in facts if ACCENTED.search(text)] + fragment_leaks(facts, po, {56, 57})


def test_the_probe_knows_every_type():
    from qe_studio.core.calc_create.types import REGISTRY

    assert tuple(calc_type.id for calc_type in REGISTRY) == TYPE_IDS


def test_the_fields_of_every_type_follow_the_language(english, portuguese, po):
    """Step 2 of each type in the avancado mode (R3.2): the same fields in both languages, each label
    and tooltip in English, with the keywords, namelists and units of QE as written (R1.2)."""
    for type_id in TYPE_IDS:
        en, pt = english[f"calc_create_{type_id}#facts"], portuguese[f"calc_create_{type_id}#facts"]
        en_fields, pt_fields = keyed(en, "field"), keyed(pt, "field")
        assert list(en_fields) == list(pt_fields) != [], type_id
        assert no_portuguese(en, po) == [], type_id
        assert lost_code({key: (pt_fields[key], en_fields[key]) for key in pt_fields}) == []
        assert (en[0], pt[0]) == (TYPES_EN, TYPES_PT)
    slab = english["calc_create_slab#facts"]
    assert "scf: Bulk SCF *" in slab and "tab: Surface" in slab
    assert keyed(slab, "field")["fix_rule"] == (
        "Fixed atoms (if_pos 0 0 0) | 'bottom layer': the atoms below the fraction of the thickness;"
        " 'species and neighbors': the fixed species and the neighbors bonded to them; 'none': all"
        " free"
    )
    assert "tab: Superfície" in portuguese["calc_create_slab#facts"]
    assert {"tab: Molecule", "tab: Site"} <= set(english["calc_create_adsorption#facts"])
    assert "tab: Atoms" in english["calc_create_charge_diff#facts"]
    assert "tab: Supercell" in english["calc_create_supercell#facts"]
    relax = keyed(english["calc_create_relax#facts"], "field")
    assert relax["nstep"] == (
        "Maximum steps (nstep) | &CONTROL nstep: maximum number of optimization steps"
    )
    assert relax["ion_dynamics"] == "Ion dynamics (ion_dynamics) | &IONS ion_dynamics"  # data
    pdos = keyed(english["calc_create_pdos#facts"], "field")
    assert pdos["ngauss"] == "Smearing type (ngauss) | &PROJWFC ngauss: ignored with tetrahedra"


def test_the_checks_of_every_type_follow_the_language(english, portuguese, po):
    """What each type says of an empty required field and of the values it refuses (R1.4, R3.2):
    the same problems on the same fields, each message read whole in English."""
    for type_id in TYPE_IDS:
        scenario = f"calc_create_validation_{type_id}#facts"
        en, pt = english[scenario], portuguese[scenario]
        assert len(en) == len(pt), type_id
        for state in ("empty", "typed"):
            assert list(keyed(en, f"{state} problem")) == list(keyed(pt, f"{state} problem"))
        assert any(text.startswith("typed error: ") for text in en), type_id  # something refused
        assert no_portuguese(en, po) == [], type_id
        assert lost_code({str(n): pair for n, pair in enumerate(zip(pt, en, strict=True))}) == []
    for type_id, expected in {
        "scf": ["typed note: Job name adjusted to job_de_teste (up to 15 characters: letters, digits, . _ -)"],
        "relax": [
            "typed error: Invalid value in Maximum steps (nstep): abc",
            "typed note: NP = 64 is not a multiple of nk = 7: pw.x stops with an error (mp_start_pools)",
        ],
        "charge": ["typed error: output_format = 5 does not apply to iflag = 2 (2D plot): use 2, 3, 7"],
        "slab": [
            "typed error: The adsorption distance must be greater than or equal to zero",
            "typed error: The bond tolerance must be greater than zero",
            "typed error: Edge metals: Xx is not in the ATOMIC_SPECIES of the SCF",
            "typed error: Fill in Fixed species",
            "typed note: No atom was fixed by the rule 'species and neighbors'",
        ],
        "supercell": [
            "typed error: The minimum vacuum must be greater than zero",
            "typed error: The fixed fraction of the thickness goes from 0 (exclusive) to 1",
        ],
        "adsorption": [
            "empty error: Fill in Molecule SCF",
            "typed legend site: The surface window must be greater than zero",
            "typed tip h_clearance: The minimum clearance must be greater than or equal to zero",
        ],
    }.items():  # fmt: skip
        shown = english[f"calc_create_validation_{type_id}#facts"]
        assert [text for text in expected if text not in shown] == [], type_id
    charge = portuguese["calc_create_validation_charge#facts"]
    assert (
        "typed error: output_format = 5 não vale para iflag = 2 (gráfico 2D): use 2, 3, 7" in charge
    )


def files_of(facts: list[str]) -> dict[str, str]:
    """``{name: text}`` of the files a scenario wrote (its ``file <name>:`` facts)."""
    found = {}
    for text in facts:
        head, _sep, body = text.partition("\n")
        if head.startswith("file "):
            found[head.removeprefix("file ").removesuffix(":")] = body
    return found


def test_a_slab_writes_the_same_inputs_in_both_languages(english, portuguese, po):
    """The same Slab (with the molecule) made in pt_BR and in en (R2.2): the input and the script
    byte for byte, the script's header in Portuguese in both (R2.3), no message in the input."""
    en_files = files_of(english["slab_files#facts"])
    pt_files = files_of(portuguese["slab_files#facts"])
    assert (
        sorted(en_files) == sorted(pt_files) == ["geracao.md", "slab.qsub", "vc-relax_kaolinite.in"]
    )
    assert en_files["vc-relax_kaolinite.in"] == pt_files["vc-relax_kaolinite.in"]
    assert en_files["slab.qsub"] == pt_files["slab.qsub"]
    assert QSUB_HEADER in en_files["slab.qsub"]
    texts = {
        text
        for message in tool.messages(po)
        if tool.is_translated(message)
        and any(area_of(filename) in {56, 57} for filename, _line in message.locations)
        for text in (*tool.sources(message), *tool.forms(message))
        if " " in text
    }
    assert sorted(text for text in texts if text in en_files["vc-relax_kaolinite.in"]) == []


def test_the_report_of_a_slab_follows_the_language(english, portuguese, po):
    """``geracao.md`` of that Slab (R2.1, R2.2): the same lines with the same numbers, each label the
    translation of the Portuguese one, nothing left in Portuguese; the tab, the plan and the file are
    the same text in each language (R2.4)."""
    en_facts, pt_facts = english["slab_files#facts"], portuguese["slab_files#facts"]
    en_report = files_of(en_facts)["geracao.md"]
    pt_report = files_of(pt_facts)["geracao.md"]
    for facts, report in ((en_facts, en_report), (pt_facts, pt_report)):
        shown = [fact(facts, f"{kind}:\n").partition("\n")[2] for kind in ("preview", "planned")]
        assert shown == [report, report]
    en, pt = en_report.splitlines(), pt_report.splitlines()
    assert len(en) == len(pt) > 10
    number = re.compile(r"\d+(?:\.\d+)?")
    assert [number.findall(line) for line in en] == [number.findall(line) for line in pt]
    row = re.compile(r"- \*\*(.+?)\*\*: ")
    en_labels = [found.group(1) for line in en if (found := row.match(line))]
    pt_labels = [found.group(1) for line in pt if (found := row.match(line))]
    translated = {
        tool.sources(m)[0]: tool.forms(m)[0]
        for m in tool.messages(po)
        if tool.is_translated(m) and len(tool.sources(m)) == 1
    }
    assert en_labels == [translated.get(label, label) for label in pt_labels] != pt_labels
    assert no_portuguese(en, po) == []
    assert (en[0], pt[0]) == ("# Generation report", "# Relatório da geração")
    for line in (
        "- **Requested vacuum**: 15.10 Å = 10.50 + molecule 2.60 + adsorption 2.00",
        "- **Surface**: axis c stacked (001), not flipped",
        "- **Fixed atoms**: 18/34 (Si 4, O 12, H 2), rule 'bottom layer'",
        "- **k-points**: 6 4 1 0 0 0 (from the SCF 6 4 4 0 0 0; vacuum 1)",
    ):
        assert line in en
    assert "- **Átomos fixos**: 18/34 (Si 4, O 12, H 2), regra 'camada inferior'" in pt


def test_choice_values_are_marked(po):
    """Every value of a choice of every type is a message of the catalog, translated (marked with N_
    where it is defined): the combo shows ``_(value)`` and keeps the value (R3.1). QE's own tokens
    are the exception, and a code of pp.x keeps its code in English."""
    from qe_studio.core.calc_create.types import REGISTRY
    from qe_studio.core.calc_create.types.charge import CODE_SEPARATOR, IFLAGS, OUTPUT_FORMATS

    from calc_helpers import JOBS, al
    from surface_helpers import BULK, SLAB_001, read

    translated = {
        tool.sources(m)[0]: tool.forms(m)[0]
        for m in tool.messages(po)
        if tool.is_translated(m) and len(tool.sources(m)) == 1
    }
    scf_of = {"slab": read(BULK), "supercell": read(SLAB_001), "adsorption": read(SLAB_001)}
    unmarked, tokens = [], []
    for calc_type in REGISTRY:
        fields = calc_type.fields(scf_of.get(calc_type.id) or al(), JOBS, "x")
        for form_field in (f for f in fields if f.kind == "choice"):
            for value in form_field.choices:
                if form_field.id in QE_CHOICES:
                    tokens.append(value)
                elif value not in translated:
                    unmarked.append(f"{calc_type.id}.{form_field.id}: {value!r}")
    assert unmarked == []
    assert len(tokens) > 20 and [t for t in tokens if t in translated or not t.isascii()] == []
    for value in (*IFLAGS.values(), *OUTPUT_FORMATS.values()):
        code = value.partition(CODE_SEPARATOR)[0]
        assert translated[value].startswith(f"{code}{CODE_SEPARATOR}"), value


def test_a_lost_qe_keyword_is_found():
    """A keyword a field names is kept like a namelist (R1.2): a catalog that swaps ``nstep`` for
    ``steps`` fails ``test_code_tokens_are_kept``."""
    where = "core/calc_create/types/relax.py"
    swapped = catalog(
        (
            "&CONTROL nstep: número máximo de passos da otimização",
            "&CONTROL steps: maximum number of optimization steps",
            where,
        ),
        ("Passos máximos (nstep)", "Maximum steps (steps)", where),
        ("Convergência das forças (forc_conv_thr)", "Force convergence (force threshold)", where),
    )
    assert sorted(lost_code_tokens(swapped, {57})) == [
        "'&CONTROL nstep: número máximo de passos da otimização': lost '&CONTROL nstep'",
        "'&CONTROL nstep: número máximo de passos da otimização': lost 'nstep'",
        "'Convergência das forças (forc_conv_thr)': lost 'forc_conv_thr'",
        "'Passos máximos (nstep)': lost 'nstep'",
    ]
    assert lost_code_tokens(swapped, {56}) == []


def test_a_fragment_left_in_portuguese_is_found():
    """The token of a choice formatted without ``_()`` inside an English sentence (R2.1)."""
    source = catalog(
        ("camada inferior", "bottom layer", "core/calc_create/surface/fixing.py"),
        ("{label} deve ser {limit}", "{label} must be {limit}", "core/calc_create/types/base.py"),
    )
    shown = ["18/34, rule 'camada inferior'", "18/34, rule 'bottom layer'", "camadas inferiores"]
    assert fragment_leaks(shown, source, {56, 57}) == [
        "'camada inferior' in \"18/34, rule 'camada inferior'\""
    ]
    assert fragment_leaks(shown, source, {55}) == []


# -- spec 58: the cluster and the sync -------------------------------------------------------------
def sync_facts(facts: list[str], prefix: str) -> list[str]:
    """The lines of a sync scenario that start with ``prefix``, without it."""
    return [text.removeprefix(prefix) for text in facts if text.startswith(prefix)]


def test_the_values_of_the_actions_are_data():
    """The preview shows ``ACTION_TITLES``, never the value of an action (R1.4)."""
    from qe_studio.core.sync.planner import Action
    from qe_studio.core.sync.push_plan import PushAction

    assert [action.value for action in Action] == ["novo", "atualizar", "local mais recente"]
    assert [action.value for action in PushAction] == ["enviar", "já existe"]


def test_the_sync_facts_have_the_same_shape_in_both_languages(english, portuguese):
    """The same lines, with the same numbers (counts, sizes, dates, exit codes), in both languages."""
    for scenario in AREA_58:
        en, pt = english[f"{scenario}#facts"], portuguese[f"{scenario}#facts"]
        assert len(en) == len(pt) > 10, scenario
        differ = [
            f"{a!r} / {b!r}"
            for a, b in zip(en, pt, strict=True)
            if re.findall(r"\d+", a) != re.findall(r"\d+", b)
        ]
        assert differ == [], scenario


def test_the_sync_speaks_english_without_leaving_portuguese_in_it(english, po):
    for scenario in AREA_58:
        facts = english[f"{scenario}#facts"]
        assert [text for text in facts if ACCENTED.search(text)] == [], scenario
        assert fragment_leaks(facts, po, {58}) == [], scenario


def test_the_preview_of_a_download_follows_the_language(english, portuguese):
    en, pt = english["sync_preview_pull#facts"], portuguese["sync_preview_pull#facts"]
    assert sync_facts(en, "pull summary: ") == [
        "3 new files (105.0 MB) · 1 to update (2.0 MB) · 2 newer on this computer (will not be changed)"
    ]
    assert sync_facts(pt, "pull summary: ") == [
        "3 arquivos novos (105.0 MB) · 1 a atualizar (2.0 MB) · 2 mais recentes no computador (não serão alterados)"
    ]
    # The sections, their notes and the label of the folder being synced.
    rows = sync_facts(en, "pull row ")
    assert rows[0].startswith("New (3) | 105.0 MB")
    assert "To update (1) | 2.0 MB |  | will ask for confirmation" in rows
    assert "Newer on this computer (2) | 9.8 KB |  | will not be changed" in rows
    assert "  (synced folder) | 10.0 KB |  | " in rows
    assert rows[-1].startswith("    p1.png | 4.9 KB | ") and rows[-1].endswith(
        "| will not be changed"
    )
    assert sync_facts(en, "pull header: ") == ["File | Size | Date on the cluster | Note"]
    assert sync_facts(pt, "pull header: ") == ["Arquivo | Tamanho | Data no cluster | Nota"]
    # Singular and plural, the large files, the window and the buttons.
    assert sync_facts(en, "pull count 1: ") == [
        "1 new file (10.0 KB) · 1 to update (2.0 MB) · 1 newer on this computer (will not be changed)"
    ]
    assert sync_facts(pt, "pull count 1: ") == [
        "1 arquivo novo (10.0 KB) · 1 a atualizar (2.0 MB) · 1 mais recente no computador (não será alterado)"
    ]
    assert sync_facts(en, "pull large ") == [
        "1: 1 large file adds up to 101.0 MB",
        "2: 2 large files add up to 202.0 MB",
    ]
    assert sync_facts(en, "pull title: ") == ["Syncing with the cluster"]
    assert sync_facts(en, "pull confirm: ") == ["Download"]
    assert sync_facts(pt, "pull confirm: ") == ["Baixar"]
    assert sync_facts(en, "pull transfer ") == [
        "1: Transferring 1 file… | 1/1 file",
        "2: Transferring 2 files… | 1/2 files",
    ]
    assert sync_facts(en, "pull waiting: ") == ["Waiting for your decision…"]
    assert sync_facts(pt, "pull waiting: ") == ["Aguardando sua decisão…"]
    shown = english["sync_preview_pull"]
    for text in ("Keep local", "Overwrite this one", "Overwrite all in this folder", "Cancel sync"):
        assert text in shown
    assert "The local file would be overwritten" in shown


def test_the_preview_of_an_upload_says_what_is_not_changed(english, portuguese):
    """The sentences that promise something stay as promises: the subject and the negation (R1.2)."""
    en, pt = english["sync_preview_push#facts"], portuguese["sync_preview_push#facts"]
    assert sync_facts(en, "push summary: ") == [
        "2 files to upload (101.0 MB) · 1 already on the cluster (will not be changed)"
    ]
    assert sync_facts(pt, "push summary: ") == [
        "2 arquivos a enviar (101.0 MB) · 1 já existe no cluster (não será alterado)"
    ]
    rows = sync_facts(en, "push row ")
    assert rows[0].startswith("To upload (2 · 101.0 MB) | 101.0 MB")
    assert any(
        row.startswith("Already on the cluster, will not be changed (1) | 7.0 MB") for row in rows
    )
    assert rows[-1].endswith("| will not be changed")  # the file the cluster has
    assert sync_facts(pt, "push row ")[-1].endswith("| não será alterado")
    assert sync_facts(en, "push count ") == [
        "1: 1 file to upload (900 B) · 1 already on the cluster (will not be changed)",
        "2: 2 files to upload (101.0 MB) · 2 already on the cluster (will not be changed)",
    ]
    assert sync_facts(en, "push header: ") == ["File | Size | Local date | Note"]
    assert sync_facts(en, "push title: ") == ["Uploading to the cluster"]
    assert sync_facts(en, "push scope: ")[0].startswith("Upload to the cluster: ")
    assert sync_facts(en, "push confirm: ") == ["Upload"]
    assert sync_facts(pt, "push confirm: ") == ["Enviar"]
    assert sync_facts(en, "push transfer ") == [
        "1: Uploading 1 file… | 1/1 file",
        "2: Uploading 2 files… | 1/2 files",
    ]


def test_the_report_of_a_run_follows_the_language(english, portuguese):
    en, pt = english["sync_report#facts"], portuguese["sync_report#facts"]
    assert "pull done 1 message: 1 file downloaded." in en
    assert "pull done 2 message: 2 files downloaded." in en
    assert "pull done 1 message: 1 conflict kept in the local version." in en
    assert "pull done 2 message: 2 conflicts kept in the local version." in en
    assert "pull done 2 message: 2 newer local files kept." in en
    assert (
        "pull done 1 message: 1 file changed locally during the preview and was not downloaded."
        in en
    )
    assert (
        "pull done 2 message: 2 files changed locally during the preview and were not downloaded."
        in en
    )
    assert "pull done 2 details: Changed locally (not downloaded) (2):" in en
    assert "pull done 2 details: Newer on this computer (2):" in en
    assert "pull done 2 details: Local folder: <root>/03_bands" in en
    assert "pull done 2 details: Pasta local: <root>/03_bands" in pt
    assert "push done 1 message: 1 already existed on the cluster and was not changed." in en
    assert "push done 2 message: 2 already existed on the cluster and were not changed." in en
    assert "push done 2 details: Already on the cluster (not changed) (2):" in en
    assert "push done 2 details: Uploaded (2):" in en
    assert "push up-to-date message: Nothing to upload." in en
    assert "pull up-to-date message: Folder already in sync: nothing to transfer." in en
    assert "pull cancelled message: Sync cancelled." in en
    assert "push cancelled message: Upload cancelled." in en
    assert "push done 2 message: 2 arquivos enviados." in pt
    assert "push done 2 message: 2 já existiam no cluster e não foram alterados." in pt
    # A refused password is told by the flag, not by the text: both languages set it.
    assert "auth: True" in en and "auth: True" in pt
    assert (
        "pull denied message: Sync failed: Authentication refused by the cluster (check the user, key or password)."
        in en
    )
    assert "Details" in english["sync_report"]  # the toast


def test_the_menu_and_the_scope_follow_the_language(english, portuguese):
    en, pt = english["sync_menu#facts"], portuguese["sync_menu#facts"]
    for fact in (
        "pull folder menu_text: Sync 04_pdos_orbitals/orbitals",
        "pull project menu_text: Sync project 01_relax",
        "pull root menu_text: Sync all",
        "push folder menu_text: Upload 04_pdos_orbitals/orbitals to cluster…",
        "push root menu_text: Upload folder to cluster…",
        "pull root tooltip: Download from the cluster: everything",
        "action _project_action: Sync all",
        "titles: Sync | Upload to cluster",
        "off cluster: cluster not configured (offline)",
    ):
        assert fact in en, fact
    for fact in (  # the same, in the language of the source
        "pull folder menu_text: Sincronizar 04_pdos_orbitals/orbitals",
        "pull root tooltip: Baixar do cluster: tudo",
        "push root menu_text: Enviar pasta ao cluster…",
        "titles: Sincronização | Envio ao cluster",
    ):
        assert fact in pt, fact
    assert "push root: Choose a calculation folder; the whole root folder is not uploaded." in en
    assert "push project: Choose a calculation folder; the whole project is not uploaded." in en
    assert "push root: Escolha uma pasta de cálculo; a pasta raiz inteira não é enviada." in pt
    assert (
        "refusal pull outside: /elsewhere is not inside the configured local folder (<root>)" in en
    )
    assert (
        "action _project_action: Sync project 01_relax | Download from the cluster: project 01_relax"
        in en
    )
    shown = english["sync_menu"]
    for text in (
        "Sync all",
        "Sync 04_pdos_orbitals/orbitals",
        "Upload 04_pdos_orbitals/orbitals to cluster…",
    ):
        assert text in shown, text


def test_failure_hints_follow_stderr(english, portuguese, po):
    """The needle is matched in the English stderr of ssh and rsync; the hint is the only thing that
    follows the language (R2.1): each needle picks its own hint, in the same order, and only the
    refusal of the credentials is ``auth_failed``."""
    from qe_studio.core.sync.rsync import AUTH_DENIED, FAILURE_HINTS

    translated = {
        tool.sources(m)[0]: tool.forms(m)[0] for m in tool.messages(po) if tool.is_translated(m)
    }

    def hints(facts: list[str]) -> list[tuple[str, str, str]]:
        found = []
        for index, (needle, _hint) in enumerate(FAILURE_HINTS):
            [line] = [text for text in facts if text.startswith(f"hint {index} ")]
            head, _sep, rest = line.removeprefix(f"hint {index} ").partition(": ")
            assert head == needle
            shown, _sep, flags = rest.partition(" | ")
            found.append((needle, shown, flags))
        return found

    pt = hints(portuguese["sync_failures#facts"])
    en = hints(english["sync_failures#facts"])
    assert len({shown for _needle, shown, _flags in pt}) == len(FAILURE_HINTS)  # one hint each
    for (needle, shown_pt, flags_pt), (_n, shown_en, flags_en) in zip(pt, en, strict=True):
        assert shown_en == translated[shown_pt], needle
        assert flags_en == flags_pt, needle  # which failure it is does not depend on the language
        assert ("auth=True" in flags_en) == (needle == AUTH_DENIED), needle
    # What is not a needle: precedence, the interrupted stream and rsync's own exit code.
    other_pt = sync_facts(portuguese["sync_failures#facts"], "other ")
    other_en = sync_facts(english["sync_failures#facts"], "other ")
    assert [text.split(" | ")[1:] for text in other_en] == [
        text.split(" | ")[1:] for text in other_pt
    ]
    assert other_en[0].startswith("0: Unknown host key.") and "auth=False" in other_en[0]
    assert other_en[1].startswith("1: Authentication refused by the cluster")
    assert other_en[2].startswith("2: Connection interrupted (the cluster closed the connection")
    assert other_en[3].startswith("3: rsync exited with code 23: something no one foresaw")
    assert other_en[4].startswith("4: rsync exited with code 23. ")
    assert sync_facts(english["sync_failures#facts"], "run ") == [
        "no rsync: rsync not found (sync.rsync_binary).",
        "no program: could not run /nonexistent/ssh",
        "unexpected: unexpected error (ValueError: boom)",
    ]


def test_the_sync_catalog_keeps_every_negation(po):
    """A translation of "não será alterado" that dropped the "not" would promise the opposite."""
    assert lost_negations(po, {58}) == []


def test_a_dropped_negation_is_found():
    source = catalog(
        ("não será alterado", "will be changed", "core/sync/preview.py"),
        ("não serão alterados", "will not be changed", "core/sync/preview.py"),
        ("Pasta não encontrada", "Folder missing", "ui/app.py"),
    )
    assert lost_negations(source, {58}) == [
        "'não será alterado': 'will be changed' has no negation"
    ]
    assert len(lost_negations(source, {53})) == 1
