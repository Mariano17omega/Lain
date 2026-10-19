"""Spec 60: what holds across the whole i18n series.

- R2: nothing the program persists depends on the language (and files from before the series load);
- R3: the real entry point chooses the language, Qt's own texts follow it, a reload that asks for
  another language only says so;
- R4.5: the header of the catalog has no placeholder left.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMessageBox

from i18n_helpers import probe_texts, script
from i18n_scenarios_60 import COPIED_PREFIX, REPORT_PREFIX
from qe_studio import i18n
from qe_studio.core.language import ENV_LANGUAGE, ENV_LANGUAGE_ALIAS
from qe_studio.ui.language import install_qt_translator

tool = script()

# The two outputs that follow the language of the interface on purpose, by the prefix the scenario
# gives their facts: the report of "Criar cálculo" (spec 56 R2) and the copied measures (spec 59 R2).
FOLLOW_THE_LANGUAGE = (REPORT_PREFIX, COPIED_PREFIX)


# -- R2: persisted data -----------------------------------------------------------------------
@pytest.fixture(scope="module")
def persisted():
    return {
        language: probe_texts(language, "persist")["persist#facts"] for language in ("pt_BR", "en")
    }


def stable(facts: list[str]) -> list[str]:
    return [fact for fact in facts if not fact.startswith(FOLLOW_THE_LANGUAGE)]


def test_persisted_data_is_language_independent(persisted):
    """The same actions give the same ``.lain/*.json``, ``*.plot``, CSV, export and file names, Slab
    ``.in`` and ``.qsub`` and QSettings keys, except the two named outputs."""
    pt, en = persisted["pt_BR"], persisted["en"]
    assert stable(en) == stable(pt)
    kinds = ("file .lain/compounds.json", "file .lain/folders.json", "file .lain/grids.json")
    kinds += ("file .lain/navigation.json", "file 03_bands/plots/bands.plot")
    kinds += ("file 02_scf/plots/view3d.plot", "file 03_bands/plots/03_bands-bands.csv")
    kinds += ("file Slab_I18n/slab.qsub", "file Slab_I18n/vc-relax_kaolinite.in")
    kinds += ("name 03_bands/plots/03_bands-bands.png", "setting calc_create/mode")
    for kind in kinds:  # the probe really did the actions: each output is among the facts
        assert any(fact.startswith(kind) for fact in en), kind
    assert any("08_renamed" in fact for fact in en if fact.startswith("file .lain/folders.json"))


def test_the_outputs_that_follow_the_language_are_the_two_named_ones(persisted):
    pt, en = persisted["pt_BR"], persisted["en"]
    differing = [(a, b) for a, b in zip(en, pt, strict=True) if a != b]
    assert len(en) == len(pt)
    assert len(differing) == 2
    assert all(a.startswith(FOLLOW_THE_LANGUAGE) for a, _b in differing)
    report_en, report_pt = (
        next(f for f in facts if f.startswith(REPORT_PREFIX)) for facts in (en, pt)
    )
    assert "# Generation report" in report_en and "# Relatório da geração" in report_pt
    copied_en, copied_pt = (
        next(f for f in facts if f.startswith(COPIED_PREFIX)) for facts in (en, pt)
    )
    assert "Measure\tAtoms\tValue" in copied_en and "Medida\tÁtomos\tValor" in copied_pt


def test_the_excluded_outputs_are_only_text_and_not_data(persisted):
    """The exclusion hides no data: ``geracao.md`` is a report, its facts carry no ``.in``."""
    for facts in persisted.values():
        names = [fact.split("\n")[0] for fact in facts if fact.startswith(FOLLOW_THE_LANGUAGE)]
        assert names == [f"{REPORT_PREFIX} Slab_I18n/geracao.md", COPIED_PREFIX]


@pytest.fixture(scope="module")
def legacy():
    return {
        language: probe_texts(language, "legacy")["legacy#facts"] for language in ("pt_BR", "en")
    }


def test_files_from_before_the_series_load_and_are_not_rewritten(legacy):
    for language, facts in legacy.items():
        assert len(facts) == 5, language
        assert all(fact.endswith("rewritten: False") for fact in facts[1:]), (language, facts)
    assert legacy["pt_BR"] == legacy["en"]


def test_a_section_saved_with_its_portuguese_title_is_still_read(legacy):
    """``params/sections/bands/Estilo`` closed the "style" section before the sections had ids."""
    for facts in legacy.values():
        assert facts[0] == "style section open: False"


# -- R3: the real entry point -----------------------------------------------------------------
HELP = {"pt_BR": "caminho do config.yaml", "en": "path to config.yaml"}
SYSTEM = {"pt_BR": "pt_BR.UTF-8", "en": "en_US.UTF-8"}


def other(language: str) -> str:
    return "en" if language == "pt_BR" else "pt_BR"


def run_help(tmp_path: Path, *, config: str | None = None, **environ: str) -> str:
    """``python -m qe_studio --help`` in a process of its own, the environment as given (the
    inherited language variables removed), and what it prints."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {ENV_LANGUAGE, ENV_LANGUAGE_ALIAS, "QE_STUDIO_CONFIG", "LANG", "LANGUAGE", "LC_ALL"}
    }
    env |= {
        "QT_QPA_PLATFORM": "offscreen",
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }
    env |= {"LC_ALL": "C", **environ}
    command = [sys.executable, "-m", "qe_studio"]
    if config is not None:
        path = tmp_path / "config.yaml"
        path.write_text(f"ui:\n  language: {config}\n", encoding="utf-8")
        command += ["--config", str(path)]
    # cwd is a temporary folder: a ./config.yaml of the user's own would answer instead
    done = subprocess.run(
        [*command, "--help"], capture_output=True, text=True, cwd=tmp_path, env=env, timeout=60
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout


def spoken(text: str) -> str:
    found = [language for language, phrase in HELP.items() if phrase in text]
    assert len(found) == 1, text
    return found[0]


@pytest.mark.parametrize("language", ["pt_BR", "en"])
def test_entry_point_language(tmp_path, language):
    """Each way to choose the language reaches ``--help``, against a system that says the other."""
    against = {"LC_ALL": SYSTEM[other(language)]}
    assert spoken(run_help(tmp_path, **{ENV_LANGUAGE: language}, **against)) == language
    assert spoken(run_help(tmp_path, **{ENV_LANGUAGE_ALIAS: language}, **against)) == language
    assert spoken(run_help(tmp_path, config=language, **against)) == language


@pytest.mark.parametrize("language", ["pt_BR", "en"])
def test_entry_point_language_auto_follows_the_system(tmp_path, language):
    system = {"LC_ALL": SYSTEM[language]}
    assert spoken(run_help(tmp_path, **system)) == language
    assert spoken(run_help(tmp_path, config="auto", **system)) == language
    assert spoken(run_help(tmp_path, **{ENV_LANGUAGE: "auto"}, **system)) == language


def test_entry_point_language_order(tmp_path):
    """The environment variable beats its alias, which beats the config, which beats the system."""
    system = {"LC_ALL": SYSTEM["pt_BR"]}
    both = {ENV_LANGUAGE: "en", ENV_LANGUAGE_ALIAS: "pt_BR"}
    assert spoken(run_help(tmp_path, config="pt_BR", **both, **system)) == "en"
    both = {ENV_LANGUAGE: "pt_BR", ENV_LANGUAGE_ALIAS: "en"}
    assert spoken(run_help(tmp_path, config="en", **both, **system)) == "pt_BR"
    assert (
        spoken(run_help(tmp_path, config="en", **{ENV_LANGUAGE_ALIAS: "pt_BR"}, **system))
        == "pt_BR"
    )
    assert spoken(run_help(tmp_path, config="en", **system)) == "en"


BUTTONS = {
    "pt_BR": ["Sim", "Não", "Cancelar"],
    "en": ["Yes", "No", "Cancel"],
}


@pytest.mark.parametrize("language", ["pt_BR", "en"])
def test_qt_translator(qapp, language):
    """The standard buttons of Qt follow the language; skipped where Qt has no catalog for it."""
    from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator

    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not QTranslator().load(QLocale(language), "qtbase", "_", path):
        pytest.skip(f"no qtbase for {language} in {path}")
    try:
        assert install_qt_translator(qapp, language)
        box = QMessageBox()
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
        assert sorted(b.text().replace("&", "") for b in box.buttons()) == sorted(BUTTONS[language])
        box.deleteLater()
    finally:
        install_qt_translator(qapp, i18n.current_language())


def test_a_reload_with_another_language_only_says_so(main_window, tmp_path, monkeypatch):
    """ "Recarregar config.yaml" with a different ``ui.language`` shows the restart notice and
    changes nothing of the session."""
    monkeypatch.delenv(ENV_LANGUAGE, raising=False)
    monkeypatch.delenv(ENV_LANGUAGE_ALIAS, raising=False)
    current = i18n.current_language()
    wanted = other(current)
    path = tmp_path / "config.yaml"
    path.write_text(
        f"paths:\n  local_root: {main_window.config.paths.local_root}\nui:\n  language: {wanted}\n",
        encoding="utf-8",
    )
    shown: list[str] = []
    monkeypatch.setattr(
        main_window.toast, "show_message", lambda text, *rest, **kw: shown.append(text)
    )
    before = main_window.menuBar().actions()[0].text()
    main_window.load_config_file(path)
    assert shown == [i18n._("O idioma muda ao reiniciar o Lain.")]
    assert i18n.current_language() == current
    assert main_window.menuBar().actions()[0].text() == before


# -- R4.5: the header of the catalog ---------------------------------------------------------
PLACEHOLDERS = (
    "EMAIL@ADDRESS",
    "FULL NAME",
    "FIRST AUTHOR",
    "YEAR-MO-DA",
    "LL@li.org",
    "ORGANIZATION",
    "Lain: QE Studio VERSION",
)


def test_the_catalog_header_has_no_placeholder():
    text = tool.po_path("en").read_text(encoding="utf-8")
    assert [mark for mark in PLACEHOLDERS if mark in text] == []


def test_the_catalog_header_carries_the_project_version():
    po = tool.read_catalog(tool.po_path("en"), "en")
    assert po.version == tool.project_version()
    assert f"Project-Id-Version: Lain: QE Studio {tool.project_version()}" in tool.po_path(
        "en"
    ).read_text(encoding="utf-8")
    assert po.last_translator and "@" in po.last_translator and po.language_team


def test_update_keeps_the_header_filled():
    """``update`` over the committed catalog leaves no placeholder behind."""
    updated = tool.update(tool.extract(), "en")
    assert updated.version == tool.project_version()
    assert "FULL NAME" not in updated.last_translator
    assert "LL@li.org" not in updated.language_team
