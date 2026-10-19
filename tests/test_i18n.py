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
    first_lines,
    leaks,
    lost_code_tokens,
    probe_texts,
    script,
    untranslated_in_done,
)
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
# form.py, the rule of the fixed atoms; 57: adsorption.py). A new one
# goes here, with that test.
DYNAMIC = [
    ("core/calc_create/surface/fixing.py", "rule"),
    ("core/calc_create/types/adsorption.py", "FROM_COORDS"),
    ("core/calc_create/types/adsorption.py", "FROM_LIST"),
    ("core/calculations/base.py", "self.value"),
    ("core/calculations/relax_panels.py", "QE_DEFAULT"),
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
# The scenarios with texts to check for leaks: spec 52's two, spec 53's eleven (the window, its
# menus and the general dialogs), spec 54's six, spec 55's nine, spec 56's five. The next specs of
# the series add theirs.
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
    "first_run",
]
# What no widget shows (the probe's "facts"). They run before ``first_run``, whose overlay stays on.
FACT_SCENARIOS = ["menus", "cli", "config", "restart", "type_filter", "lint"]


@pytest.fixture(scope="module")
def english():
    order = [*LEAK_SCENARIOS[:-1], *FACT_SCENARIOS, *FACTS_55, *FACTS_56, LEAK_SCENARIOS[-1]]
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
