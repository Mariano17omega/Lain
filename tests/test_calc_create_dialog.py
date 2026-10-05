"""Spec 26 R2–R4: the "Criar cálculo" window on its own (the controller writes; this never does).

Most run in the "avancado" mode (every field shown); the "Padrão / Avançado" switch of spec 28 R5
is tested at the end.
"""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QComboBox, QLineEdit

from qe_studio.core.calc_create.types import by_id
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.kmesh import KMeshEditor
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.kpath_editor import KPathEditor

from calc_dialog_helpers import fill_setup, pick_scf, to_files, tree
from calc_helpers import AL_PATH, AL_SCF, JOBS, al, hex_path, hex_scf_text


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    return folder


@pytest.fixture
def make_dialog(qtbot, place):
    """New windows on ``place`` (``mode`` set before step 2 is built; None: the remembered one);
    closed at teardown unless a test closed (deleted) them. Not ``qtbot.addWidget``: it would
    close a window its delete-on-close already deleted."""
    made = []

    def make(mode="avancado", settings=None) -> CalcCreateDialog:
        window = CalcCreateDialog(ThemeManager("dark"), place, place, JOBS, settings=settings)
        if mode is not None:
            window.set_mode(mode)
        window.show()
        made.append(window)
        return window

    yield make
    for window in made:
        if not sip.isdeleted(window):
            window.close()


@pytest.fixture
def dialog(make_dialog):
    return make_dialog()


@pytest.fixture(autouse=True)
def asked(monkeypatch):
    """The discard question, patched (a real one would block, even at teardown): its answer
    (``asked.answer``) and the calls (``asked.calls``)."""
    answers = []

    def ask(parent):
        answers.append(parent)
        return ask.answer

    ask.answer = True
    monkeypatch.setattr(dialog_module, "ask_discard", ask)
    ask.calls = answers
    return ask


def relax_input(tmp_path):
    path = tmp_path / "relax.in"
    path.write_text(AL_SCF.read_text().replace("'scf'", "'relax'"))
    return path


# -- step 1 ---------------------------------------------------------------------------------------
def test_continue_waits_for_everything(qtbot, dialog, place):
    setup = dialog.setup
    assert dialog.windowTitle() == "Criar cálculo"
    assert not dialog.continue_button.isEnabled()
    assert dialog.continue_button.toolTip() == "Escolha o tipo de cálculo"
    setup.set_type("bandas")
    assert dialog.continue_button.toolTip() == "Escolha o input de SCF"
    pick_scf(qtbot, dialog, AL_SCF)
    assert dialog.continue_button.isEnabled()  # the folder's name is optional (spec 28 R5.3)
    assert setup.name_preview.text() == "Será criada: Bands"
    assert setup.suffix_message.isHidden()
    setup.suffix_edit.setText("Al é")
    assert not dialog.continue_button.isEnabled()
    assert "letras sem acento" in setup.suffix_message.text()
    setup.suffix_edit.setText("Al")
    assert dialog.continue_button.isEnabled()
    assert setup.name_preview.text() == "Será criada: Bands_Al"
    setup.set_location(place / "nada")
    assert not dialog.continue_button.isEnabled()
    assert "não existe" in setup.location_message.text()


def test_an_input_that_is_not_an_scf_is_refused(qtbot, dialog, tmp_path):
    dialog.setup.set_type("pdos")
    assert pick_scf(qtbot, dialog, relax_input(tmp_path)) is None
    assert dialog.setup.scf_message.text() == "O arquivo não é um SCF (calculation = 'relax')"
    assert not dialog.continue_button.isEnabled()
    text = tmp_path / "notes.txt"
    text.write_text("só texto\n")
    assert pick_scf(qtbot, dialog, text) is None
    assert "não parece um input" in dialog.setup.scf_message.text()
    assert pick_scf(qtbot, dialog, AL_SCF) is not None
    assert dialog.setup.scf_message.isHidden()


def test_name_preview_says_when_the_name_is_taken(qtbot, dialog, place):
    (place / "Bands_Al").mkdir()
    fill_setup(qtbot, dialog, "bandas")
    assert dialog.setup.name_preview.text() == "Será criada: Bands_Al_1 — já existe Bands_Al"


def test_a_place_outside_the_project_warns(qtbot, dialog, tmp_path):
    fill_setup(qtbot, dialog, "scf", location=tmp_path)
    assert dialog.continue_button.isEnabled()  # a warning, not a block
    assert "Fora da pasta do projeto" in dialog.setup.location_message.text()


# -- step 2 ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "type_id, labels",
    [
        ("pdos", ["Script (pdos.qsub)", "SCF (scf_al.in)", "NSCF (nscf_al.in)", "projwfc.in"]),
        ("bandas", ["Script (bands.qsub)", "SCF (scf_al.in)", "Bandas (bands.in)", "bands_pp.in"]),
        ("scf", ["Script (scf.qsub)", "SCF (scf_al.in)"]),
        ("relax", ["Script (relax.qsub)", "Relax (relax_al.in)"]),
        ("vc-relax", ["Script (vc-relax.qsub)", "VC-Relax (vc-relax_al.in)"]),
    ],
)
def test_a_tab_per_file(qtbot, dialog, type_id, labels):
    tabs = to_files(qtbot, dialog, type_id)
    assert tabs.tab_labels() == [*labels, "Arquivos", "Descrição"]
    assert tabs.tabs.objectName() == "calcTabs"
    assert not dialog.continue_button.isVisible() and dialog.create_button.isVisible()


def test_fields_open_with_the_scf_values(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    scf = al()
    nbnd = tabs.widget_of("nbnd")
    assert isinstance(nbnd, QLineEdit)
    expected = by_id("pdos").fields(scf, JOBS)
    default = next(f.default for f in expected if f.id == "nbnd")
    assert nbnd.text() == str(default) and nbnd.placeholderText() == f"vazio = {default}"
    assert tabs.widget_of("filpdos").text() == "al.dat"  # from the prefix
    occupations = tabs.widget_of("occupations")
    assert isinstance(occupations, QComboBox) and occupations.currentText() == "smearing"
    mesh = tabs.widget_of("kmesh")
    assert isinstance(mesh, KMeshEditor) and [c.value() for c in mesh.counts] == [10, 10, 10]
    assert "1000 k-points" in mesh.summary.text()


def test_editing_a_field_plans_again(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    nscf = tabs.previews["nscf"]
    assert nscf.isReadOnly()
    tabs.widget_of("nbnd").setText("")
    qtbot.keyClicks(tabs.widget_of("nbnd"), "42")
    assert "nbnd = 42" in nscf.toPlainText()
    assert tabs.dirty
    tabs.widget_of("nbnd").setText("")
    tabs.flush()
    default = next(f.default for f in tabs.fields if f.id == "nbnd")
    assert f"nbnd = {default}" in nscf.toPlainText()  # empty: back to the default


def test_the_preview_is_debounced(qtbot, make_dialog):
    window = make_dialog()
    fill_setup(qtbot, window, "pdos")
    window.debounce_ms = 50
    window.continue_button.click()
    tabs = window.tabs
    nscf = tabs.previews["nscf"]
    nbnd = tabs.widget_of("nbnd")
    qtbot.keyClicks(nbnd, "7")
    typed = f"nbnd = {nbnd.text()}"
    assert typed not in nscf.toPlainText()  # not yet: 50 ms later
    qtbot.waitUntil(lambda: typed in nscf.toPlainText(), timeout=2000)


def test_lines_changed_from_the_scf_are_painted(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    nscf = tabs.previews["nscf"]
    lines = nscf.toPlainText().splitlines()
    painted = [lines[row] for row in nscf.changed_rows()]
    assert any("'nscf'" in line for line in painted)
    assert not any("ecutwfc" in line for line in painted)
    scf = tabs.previews["scf"]  # the SCF itself, but in the folder's ./tmp/ (spec 28 R2.1)
    assert [scf.toPlainText().splitlines()[row] for row in scf.changed_rows()] == [
        "    outdir='./tmp/' "
    ]
    assert tabs.previews["projwfc"].changed_rows() == []  # a template, not an edit


def test_invalid_and_missing_values_block_create(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    assert dialog.create_button.isEnabled()
    np_ = tabs.widget_of("np")
    qtbot.keyClicks(np_, "x")
    assert not dialog.create_button.isEnabled()
    assert dialog.create_button.toolTip().startswith("Valor inválido em Núcleos (NP)")
    assert np_.property("invalid") is True
    np_.setText("10")
    tabs.widget_of("nk").setText("4")
    tabs.flush()
    assert dialog.create_button.isEnabled()  # NP not a multiple of nk: a warning only
    assert np_.property("invalid") is False
    assert "NP = 10 não é múltiplo de nk = 4" in tabs.files_view.warnings.text()


def test_band_path_tab(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "bandas")
    editor = tabs.widget_of("kpath")
    assert isinstance(editor, KPathEditor)
    tabs.tabs.setCurrentIndex(tabs.tab_labels().index("Bandas (bands.in)"))  # nothing is suggested
    assert editor.table.rowCount() == 0
    assert not dialog.create_button.isEnabled()
    assert dialog.create_button.toolTip() == "Defina ao menos 2 pontos do caminho"
    editor.set_path(AL_PATH)
    assert dialog.create_button.isEnabled()
    assert "K_POINTS crystal_b" in tabs.previews["bands"].toPlainText()
    assert not tabs.dirty  # a path shown by the program is not an edit
    for _ in range(4):
        editor.table.setCurrentCell(0, 0)
        editor.remove_point()
    assert len(editor.value().points) == 1
    assert dialog.create_button.toolTip() == "Defina ao menos 2 pontos do caminho"
    assert tabs.dirty


def test_band_path_that_collapses_is_noted_and_marked_but_never_blocks(qtbot, dialog, tmp_path):
    scf = tmp_path / "hex.scf.in"
    scf.write_text(hex_scf_text())
    tabs = to_files(qtbot, dialog, "bandas", scf=scf)
    editor = tabs.widget_of("kpath")
    tabs.widget_of("nbnd").setText("8")  # no output next to this SCF to read it from
    editor.set_path(hex_path())
    tabs.flush()
    assert dialog.create_button.isEnabled()
    warnings = tabs.files_view.warnings.text()
    assert "Segmento A→L colapsa no eixo x do bands.x" in warnings
    assert editor.table.item(4, 0).toolTip().startswith("Segmento A→L colapsa")
    editor.distribute_button.click()
    tabs.flush()
    assert "colapsa" not in tabs.files_view.warnings.text()
    assert editor.table.item(4, 0).toolTip() == ""
    assert tabs.dirty  # a click on "Distribuir pelo comprimento" is the user's edit
    assert dialog.create_button.isEnabled()


def test_band_path_without_a_readable_structure(qtbot, dialog, tmp_path):
    scf = tmp_path / "scf.in"
    scf.write_text(AL_SCF.read_text().replace("    celldm(1)=  7.630781648,\n", ""))
    tabs = to_files(qtbot, dialog, "bandas", scf=scf)
    editor = tabs.widget_of("kpath")
    editor.set_path(hex_path())
    tabs.flush()
    assert not editor.distribute_button.isEnabled()
    assert editor.distribute_button.toolTip() == "Estrutura do SCF não legível"
    warnings = tabs.files_view.warnings.text()
    assert "checagem do eixo x das bandas não feita" in warnings
    assert "colapsa" not in warnings
    assert all(editor.table.item(row, 0).toolTip() == "" for row in range(editor.table.rowCount()))


def test_files_tab_lists_what_will_be_written(qtbot, dialog, place):
    tabs = to_files(qtbot, dialog, "pdos")
    view = tabs.files_view
    assert view.names() == ["pdos.qsub", "scf_al.in", "nscf_al.in", "projwfc.in"]
    assert view.target.text() == f"Pasta: {place / 'PDOS_Al'}"
    assert "PDOS_Al_1" in view.note.text()
    tabs.notes.setPlainText("Teste de convergência")
    assert view.names()[-1] == "descricao.md"
    assert tabs.dirty
    tabs.notes.setPlainText("  ")
    assert "descricao.md" not in view.names()


def test_back_keeps_both_steps(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    tabs.widget_of("nbnd").setText("33")
    dialog.back_button.click()
    assert not dialog.on_files_step()
    assert dialog.setup.suffix == "Al" and dialog.setup.calc_type.id == "pdos"
    dialog.setup.suffix_edit.setText("Al2")
    dialog.continue_button.click()
    assert dialog.tabs is tabs and tabs.widget_of("nbnd").text() == "33"
    assert tabs.files_view.target.text().endswith("PDOS_Al2")


def test_changing_the_type_rebuilds_step_2(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    dialog.back_button.click()
    assert dialog.setup.rebuild_note.isHidden()
    dialog.setup.set_type("scf")
    assert not dialog.setup.rebuild_note.isHidden()
    dialog.continue_button.click()
    assert dialog.tabs is not tabs
    assert dialog.tabs.tab_labels()[0] == "Script (scf.qsub)"
    dialog.back_button.click()
    assert dialog.setup.rebuild_note.isHidden()
    pick_scf(qtbot, dialog, AL_SCF)  # the SCF chosen again: rebuilt too
    assert not dialog.setup.rebuild_note.isHidden()


def test_the_charge_type_names_its_input_after_the_folder(qtbot, dialog):
    """Spec 29: ``pp_<nome>_charge.in`` takes the name typed in step 1, so changing it rebuilds
    step 2 (the other types keep their fields: ``test_back_keeps_both_steps``)."""
    assert dialog.setup.type_combo.findText("Carga") >= 0
    tabs = to_files(qtbot, dialog, "charge", suffix="Al")
    assert tabs.tab_labels()[:3] == ["Script (charge.qsub)", "SCF (scf_al.in)", "pp_Al_charge.in"]
    assert tabs.widget_of("name:pp_charge").text() == "pp_Al_charge.in"
    assert "pp_Al_charge.out" in tabs.previews["script"].toPlainText()
    tabs.widget_of("fileout").setText("x/y.xsf")
    dialog.back_button.click()
    assert dialog.setup.rebuild_note.isHidden()
    dialog.setup.suffix_edit.setText("Fe")
    assert not dialog.setup.rebuild_note.isHidden()
    dialog.continue_button.click()
    assert dialog.tabs is not tabs and dialog.setup.rebuild_note.isHidden()
    assert dialog.tabs.widget_of("name:pp_charge").text() == "pp_Fe_charge.in"
    assert dialog.tabs.widget_of("fileout").text() == "cdd_xsf/al_charge.xsf"  # back to the default
    dialog.back_button.click()
    dialog.setup.suffix_edit.setText("")
    dialog.continue_button.click()
    assert dialog.tabs.tab_labels()[2] == "pp_charge.in"
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert [f.name for f in blocker.args[0].plan.files] == [
        "charge.qsub",
        "scf_al.in",
        "pp_charge.in",
    ]


def test_the_charge_standard_mode_shows_no_field(qtbot, make_dialog):
    dialog = make_dialog(mode="padrao")
    tabs = to_files(qtbot, dialog, "charge")
    assert [tabs.form_shown(key) for key in tabs.previews] == [False, False, False]
    assert dialog.create_button.isEnabled()
    dialog.set_mode("avancado")
    assert tabs.form_shown("pp_charge") and tabs.widget_of("iflag").currentText().startswith("3")
    tabs.widget_of("fileout").setText("../x.xsf")
    tabs.flush()
    assert tabs.widget_of("fileout").property("invalid") is True
    assert (
        not dialog.create_button.isEnabled() and "dentro da pasta" in dialog.create_button.toolTip()
    )


# -- closing --------------------------------------------------------------------------------------
@pytest.mark.parametrize("how", ["cancel", "escape", "close"])
def test_closing_creates_nothing(qtbot, dialog, place, asked, how):
    before = tree(place)
    tabs = to_files(qtbot, dialog, "bandas")
    qtbot.keyClicks(tabs.widget_of("nbnd"), "2")
    assert tabs.dirty
    with qtbot.waitSignal(dialog.destroyed, timeout=2000):
        if how == "cancel":
            dialog.cancel_button.click()
        elif how == "escape":
            qtbot.keyClick(dialog, Qt.Key.Key_Escape)
        else:
            dialog.close()
    assert len(asked.calls) == 1
    assert tree(place) == before


def test_closing_unedited_does_not_ask(qtbot, dialog, asked):
    to_files(qtbot, dialog, "scf")
    with qtbot.waitSignal(dialog.destroyed, timeout=2000):
        dialog.cancel_button.click()
    assert asked.calls == []


def test_saying_no_keeps_the_window(qtbot, dialog, asked):
    tabs = to_files(qtbot, dialog, "scf")
    tabs.notes.setPlainText("anotação")
    asked.answer = False
    dialog.close()
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.isVisible() and len(asked.calls) == 2


def test_create_asks_the_controller(qtbot, dialog, place):
    tabs = to_files(qtbot, dialog, "scf")
    tabs.notes.setPlainText("nota")
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    request = blocker.args[0]
    assert (request.parent, request.calc_type.id, request.suffix) == (place, "scf", "Al")
    assert request.plan == tabs.plan and request.notes == "nota"
    assert tree(place) == []  # the window never writes
    dialog.set_busy(True)
    assert not dialog.create_button.isEnabled() and not dialog.pages.isEnabled()
    dialog.close()
    assert dialog.isVisible()  # not while the folder is written


# -- modes (spec 28 R5) ---------------------------------------------------------------------------
def test_the_standard_mode_shows_only_its_fields(qtbot, make_dialog):
    dialog = make_dialog(mode="padrao")
    assert dialog.mode_switch.isHidden()  # a switch of step 2
    tabs = to_files(qtbot, dialog, "pdos")
    assert not dialog.mode_switch.isHidden() and dialog.mode == "padrao"
    form = tabs.form_of("e_min")
    assert form.shown("e_min") and form.shown("e_max")
    assert not form.shown("delta_e") and not form.shown("name:projwfc")
    assert not tabs.form_of("nbnd").shown("nbnd")
    # Tabs with nothing to fill are their preview alone.
    assert [tabs.form_shown(key) for key in ("script", "scf", "nscf", "projwfc")] == [
        False,
        False,
        False,
        True,
    ]
    assert dialog.create_button.isEnabled()
    assert "degauss = 0.000735" in tabs.previews["projwfc"].toPlainText()


def test_switching_modes_keeps_the_tabs_and_the_edits(qtbot, make_dialog):
    dialog = make_dialog(mode="padrao")
    tabs = to_files(qtbot, dialog, "pdos")
    nscf = tabs.previews["nscf"]
    standard = nscf.toPlainText()
    dialog.mode_switch.buttons["avancado"].click()
    assert dialog.tabs is tabs and dialog.mode == "avancado"
    assert tabs.form_of("nbnd").shown("nbnd") and tabs.form_shown("script")
    nbnd = tabs.widget_of("nbnd")
    nbnd.setText("")
    qtbot.keyClicks(nbnd, "42")
    assert "nbnd = 42" in nscf.toPlainText()
    dialog.mode_switch.buttons["padrao"].click()
    assert nscf.toPlainText() == standard  # hidden: its default counts
    assert nbnd.text() == "42" and tabs.dirty  # kept, and still asked about on close
    dialog.mode_switch.buttons["avancado"].click()
    assert "nbnd = 42" in nscf.toPlainText()


def test_the_mode_is_remembered(qtbot, make_dialog, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    first = make_dialog(mode=None, settings=settings)
    assert first.mode == "padrao"  # the first time
    to_files(qtbot, first, "scf")
    first.mode_switch.buttons["avancado"].click()
    assert settings.value("calc_create/mode") == "avancado"
    first.close()
    again = make_dialog(mode=None, settings=settings)
    assert again.mode == "avancado"
    tabs = to_files(qtbot, again, "scf")
    assert tabs.mode == "avancado" and tabs.form_shown("script")
    settings.setValue("calc_create/mode", "outro")
    assert make_dialog(mode=None, settings=settings).mode == "padrao"


def test_a_file_renamed_in_the_advanced_mode(qtbot, dialog, place):
    tabs = to_files(qtbot, dialog, "pdos", suffix="")
    name = tabs.widget_of("name:scf")
    assert isinstance(name, QLineEdit) and name.text() == "scf_al.in"
    name.setText("")
    qtbot.keyClicks(name, "scf_teste.in")
    assert "SCF (scf_teste.in)" in tabs.tab_labels()
    assert tabs.files_view.names()[1] == "scf_teste.in"
    assert '-i "scf_teste.in" > "scf_teste.out"' in tabs.previews["script"].toPlainText()
    assert tabs.files_view.target.text() == f"Pasta: {place / 'PDOS'}"  # no name: the prefix
    name.setText("")
    qtbot.keyClicks(name, "nscf_al.in")
    assert not dialog.create_button.isEnabled()
    assert dialog.create_button.toolTip() == "Nome de arquivo repetido: nscf_al.in"
    assert name.property("invalid") is True
    assert tabs.widget_of("name:nscf").property("invalid") is True
    name.setText("")
    qtbot.keyClicks(name, "a/b.in")
    assert "só letras sem acento" in dialog.create_button.toolTip()
    name.setText("")
    tabs.flush()
    assert dialog.create_button.isEnabled() and name.property("invalid") is False
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert blocker.args[0].suffix == ""
