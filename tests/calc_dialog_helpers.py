"""Shared steps of the "Criar cálculo" window tests (spec 26): fill step 1, go to step 2."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QTextCursor

from qe_studio.core.calc_create.types import by_id
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create.tabs_page import TabsPage

from calc_helpers import AL_SCF, SI_SCF


def pick_scf(qtbot, dialog: CalcCreateDialog, path: Path):
    """Choose ``path`` as the SCF and wait for the worker; the ``ScfInfo`` (None: refused)."""
    with qtbot.waitSignal(dialog.setup.scf_ready, timeout=10_000) as blocker:
        dialog.setup.set_scf(path)
    return blocker.args[0]


def add_scfs(qtbot, dialog: CalcCreateDialog, paths: list[Path]) -> None:
    """Add ``paths`` to step 1's list of SCFs (a ``multi_scf`` type, spec 79) and wait for them."""
    scf_list = dialog.setup.scf_list
    scf_list.add_paths(paths)
    qtbot.waitUntil(lambda: not scf_list.reading, timeout=10_000)


def second_scf(path: Path) -> Path:
    """Another SCF to go with ``path`` in a list (spec 79)."""
    return SI_SCF if path == AL_SCF else AL_SCF


def fill_setup(
    qtbot,
    dialog: CalcCreateDialog,
    type_id: str = "bandas",
    scf: Path = AL_SCF,
    suffix: str = "Al",
    location: Path | None = None,
) -> None:
    dialog.setup.set_type(type_id)
    if by_id(type_id).multi_scf:
        add_scfs(qtbot, dialog, [scf, second_scf(scf)])
    else:
        pick_scf(qtbot, dialog, scf)
    dialog.setup.suffix_edit.setText(suffix)
    if location is not None:
        dialog.setup.set_location(location)


def to_files(qtbot, dialog: CalcCreateDialog, type_id: str = "bandas", **setup) -> TabsPage:
    """Step 1 filled, then "Continuar": the step 2 page (plans at once: no debounce)."""
    dialog.debounce_ms = 0
    fill_setup(qtbot, dialog, type_id, **setup)
    assert dialog.continue_button.isEnabled(), dialog.continue_button.toolTip()
    dialog.continue_button.click()
    assert dialog.tabs is not None and dialog.on_files_step()
    return dialog.tabs


def type_in_preview(qtbot, tabs: TabsPage, key: str, text: str) -> None:
    """Type ``text`` at the end of the preview of file ``key``, its tab shown (spec 39 R2)."""
    tabs.tabs.setCurrentWidget(tabs._tab_of[key])
    preview = tabs.previews[key]
    preview.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClicks(preview, text)


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))
