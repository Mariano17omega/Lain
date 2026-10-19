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
# Spec 54: the viewers (text, input, diff, Markdown, .qsub) and the Resumo.
AREA_54 = ["text_viewer", "input_viewer", "diff", "summary", "markdown", "qsub"]
# The scenarios with texts to check for leaks: spec 52's two, spec 53's eleven (the window, its
# menus and the general dialogs), spec 54's six. The next specs of the series add theirs.
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
    "first_run",
]
# What no widget shows (the probe's "facts"). They run before ``first_run``, whose overlay stays on.
FACT_SCENARIOS = ["menus", "cli", "config", "restart", "type_filter", "lint"]


@pytest.fixture(scope="module")
def english():
    order = [*LEAK_SCENARIOS[:-1], *FACT_SCENARIOS, LEAK_SCENARIOS[-1]]
    return probe_texts("en", *order)


@pytest.fixture(scope="module")
def portuguese():
    return probe_texts("pt_BR", "main", "shortcuts", "tree", *AREA_54, *FACT_SCENARIOS)


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
