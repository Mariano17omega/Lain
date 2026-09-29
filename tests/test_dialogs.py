from PyQt6.QtWidgets import QDialogButtonBox

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.detection import detect_folder
from qe_studio.ui.dialogs.mapping import ManualMappingDialog
from qe_studio.ui.dialogs.overwrite import OverwriteChoice, OverwriteDialog

from conftest import FIXTURES


def plottable():
    return [m for m in REGISTRY if m.plottable]


def test_mapping_dialog_prefills_and_validates(qtbot, tmp_path):
    folder = FIXTURES / "al_bands"
    dialog = ManualMappingDialog(folder, plottable(), detect_folder(folder))
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert dialog.module.kind == "bands"
    assert dialog.edits["scf_out"].text().endswith("al.scf.out")
    assert ok.isEnabled()
    dialog.edits["scf_out"].setText(str(tmp_path / "missing.out"))
    assert not ok.isEnabled()
    mapping = dialog.mapping()
    assert mapping["gnu"][0].name == "bands.dat.gnu"


def test_mapping_dialog_switches_kind(qtbot):
    dialog = ManualMappingDialog(FIXTURES / "al_bands", plottable(), [])
    qtbot.addWidget(dialog)
    dialog.kind.setCurrentIndex(dialog.kind.findData("pdos"))
    assert "pdos_atm" in dialog.edits
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    atm = sorted((FIXTURES / "al_pdos_flat").glob("*pdos_atm*"))
    dialog.edits["pdos_atm"].setText(";".join(map(str, atm)))
    assert dialog.mapping()["pdos_atm"] == atm


def test_overwrite_dialog_choices(qtbot, tmp_path):
    dialog = OverwriteDialog([tmp_path / "bands.png"], "bands_2")
    qtbot.addWidget(dialog)
    dialog._choose(OverwriteChoice.NEW_VERSION)
    assert dialog.choice is OverwriteChoice.NEW_VERSION and dialog.result() == 1
    dialog = OverwriteDialog([tmp_path / "bands.png"], "bands_2")
    qtbot.addWidget(dialog)
    dialog._choose(OverwriteChoice.CANCEL)
    assert dialog.result() == 0
