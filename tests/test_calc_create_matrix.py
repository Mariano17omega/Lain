"""Spec 39 R1: "Continuar" of "Criar cálculo" is never silent.

Every calculation type with every SCF input of the fixtures reaches step 2 with the files of its type
(the net the "Diferença de carga" report showed missing); a step 2 that cannot be built is said and
logged with the window left usable; and while "Continuar" is disabled, step 1 says why on the page.
"""

import logging

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QMessageBox

from fragment_helpers import SMALL, slab_scf
from qe_studio.core.calc_create.scf_info import ScfInputError, scf_info
from qe_studio.core.calc_create.surface.report import REPORT_KEY
from qe_studio.core.calc_create.types import REGISTRY, CalcType, by_id
from qe_studio.core.calc_create.writer import validate_suffix
from qe_studio.core.sniff import looks_like_input
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.setup_page import CHOOSE_SCF, CHOOSE_TYPE, READING
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import fill_setup, pick_scf, to_files
from calc_helpers import AL_SCF, JOBS
from conftest import FIXTURES

NAME = "teste"


def _is_scf(path) -> bool:
    if not looks_like_input(path):
        return False
    try:
        scf_info(path.read_text(errors="replace"), path)
    except ScfInputError:
        return False
    return True


FIXTURE_SCFS = sorted(
    path for path in FIXTURES.rglob("*") if path.suffix in (".in", ".pwi") and _is_scf(path)
)
TEXTS = {"SMALL": SMALL, "slab": slab_scf()}  # SMALL holds the HUBBARD card and spin
SOURCES = [str(path.relative_to(FIXTURES)) for path in FIXTURE_SCFS] + list(TEXTS)


def test_the_fixtures_hold_the_scfs():
    """The filter above must not quietly leave the matrix empty."""
    assert len(FIXTURE_SCFS) >= 6


@pytest.fixture
def make_dialog(qtbot, tmp_path):
    place = tmp_path / "proj"
    place.mkdir()
    made = []

    def make(mode="avancado") -> CalcCreateDialog:
        window = CalcCreateDialog(ThemeManager("dark"), place, place, JOBS)
        window.set_mode(mode)
        window.show()
        made.append(window)
        return window

    yield make
    for window in made:
        if not sip.isdeleted(window):
            window.close()


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


@pytest.fixture
def failures(monkeypatch):
    """``ask_failed``, patched: the exceptions it was shown."""
    shown = []
    monkeypatch.setattr(dialog_module, "ask_failed", lambda parent, exc: shown.append(exc))
    return shown


def scf_path(source: str, tmp_path):
    if source in TEXTS:
        path = tmp_path / "scf.in"
        path.write_text(TEXTS[source])
        return path
    return FIXTURES / source


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("type_id", [calc_type.id for calc_type in REGISTRY])
def test_every_type_reaches_step_2_with_every_scf(qtbot, make_dialog, tmp_path, type_id, source):
    dialog = make_dialog()
    tabs = to_files(qtbot, dialog, type_id, scf=scf_path(source, tmp_path), suffix=NAME)
    scf = dialog.setup.scf
    assert scf is not None
    calc_type = by_id(type_id)
    keys = ["script", *(f.key for f in calc_type.input_files(scf, NAME))]
    keys += [REPORT_KEY] if calc_type.writes_report else []  # geracao.md (spec 40)
    assert [planned.key for planned in tabs.plan.files] == keys
    assert tabs.tab_labels()[-2:] == ["Arquivos", "Descrição"]
    dialog.set_mode("padrao")  # the other mode plans the same files
    assert [planned.key for planned in tabs.plan.files] == keys


def broken_plan(self, *args, **kwargs):
    raise RuntimeError("quebrou")


def test_a_step_2_that_cannot_be_built_is_said_and_logged(
    qtbot, make_dialog, tmp_path, monkeypatch, failures, caplog
):
    dialog = make_dialog()
    dialog.debounce_ms = 0
    fill_setup(qtbot, dialog, "charge_diff", scf=scf_path("SMALL", tmp_path))
    working = CalcType.plan
    monkeypatch.setattr(CalcType, "plan", broken_plan)
    with caplog.at_level(logging.ERROR, logger=dialog_module.__name__):
        dialog.continue_button.click()
    assert [str(exc) for exc in failures] == ["quebrou"]
    assert any(record.exc_info for record in caplog.records)  # the traceback is in the log
    assert not dialog.on_files_step() and dialog.tabs is None
    assert dialog.isVisible() and dialog.continue_button.isEnabled()  # still usable
    monkeypatch.setattr(CalcType, "plan", working)
    dialog.continue_button.click()
    assert dialog.on_files_step() and len(dialog.tabs.plan.files) == 8


def test_a_failed_rebuild_drops_the_old_step_2(qtbot, make_dialog, monkeypatch, failures):
    dialog = make_dialog()
    to_files(qtbot, dialog, "pdos")
    dialog.back_button.click()
    dialog.setup.set_type("scf")
    assert not dialog.setup.rebuild_note.isHidden()
    monkeypatch.setattr(CalcType, "plan", broken_plan)
    dialog.continue_button.click()
    assert len(failures) == 1 and dialog.tabs is None and not dialog.on_files_step()
    assert dialog.setup.rebuild_note.isHidden()  # nothing built: nothing to redo
    assert not dialog.create_button.isEnabled()


def test_the_failure_message(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: shown.append(args[2]))
    dialog_module.ask_failed(None, RuntimeError("quebrou"))
    dialog_module.ask_failed(None, AssertionError())
    assert shown[0] == (
        "Não foi possível montar os arquivos deste cálculo: quebrou. "
        "O log tem o detalhe (Ajuda ▸ Abrir log)."
    )
    assert "cálculo: AssertionError." in shown[1]  # an exception without a message


def test_step_1_says_why_continue_is_disabled(qtbot, make_dialog, tmp_path):
    dialog = make_dialog()
    setup = dialog.setup

    def reason() -> str:
        return "" if setup.reason.isHidden() else setup.reason.text()

    assert reason() == CHOOSE_TYPE
    setup.set_type("charge_diff")
    assert reason() == CHOOSE_SCF
    with qtbot.waitSignal(setup.scf_ready, timeout=10_000):
        setup.set_scf(AL_SCF)
        assert reason() == READING
    assert reason() == "" and dialog.continue_button.isEnabled()
    text = tmp_path / "notes.txt"
    text.write_text("só texto\n")
    pick_scf(qtbot, dialog, text)
    assert reason() == "notes.txt não parece um input do Quantum ESPRESSO"
    relax = tmp_path / "relax.in"
    relax.write_text(AL_SCF.read_text().replace("'scf'", "'relax'"))
    pick_scf(qtbot, dialog, relax)
    assert reason() == "O arquivo não é um SCF (calculation = 'relax')"
    pick_scf(qtbot, dialog, AL_SCF)
    setup.suffix_edit.setText("Al é")
    assert reason() == validate_suffix("Al é")[0]
    setup.suffix_edit.setText("Al")
    assert reason() == ""
    setup.set_location(tmp_path / "nada")
    assert reason() == f"A pasta {tmp_path / 'nada'} não existe"
    assert not dialog.continue_button.isEnabled()
    dialog.continue_()  # a click that cannot go on says why, and stays
    assert not dialog.on_files_step() and reason().endswith("não existe")
