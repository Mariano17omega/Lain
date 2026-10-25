"""The cards and rows of the cluster's files (spec 65): what ``FileCardDelegate`` paints for the local
ones, with what a listing gives (name, size, date). No folder badges nor file states: those need the
content."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QModelIndex

from ...core.file_kinds import human_size
from ...core.remote.listing import RemoteEntry
from ...core.sync.preview import format_mtime
from ...i18n import _
from ..file_types import file_visual
from .file_card import CardDelegate, CardItem, CardPanel
from .remote_model import UP, RemoteFileModel


def remote_meta(entry: RemoteEntry, grid: bool) -> str:
    """The line under a card's name: "pasta" or the size. At the end of a row: the date, and the
    size of a file before it."""
    if grid:
        return _("pasta") if entry.is_dir else human_size(entry.size)
    when = format_mtime(entry.mtime)
    return when if entry.is_dir else f"{human_size(entry.size)} · {when}"


class RemoteCardDelegate(CardDelegate):
    def __init__(self, panel: CardPanel, model: RemoteFileModel):
        super().__init__(panel)
        self.model = model

    def describe(self, index: QModelIndex) -> CardItem:
        entry = self.model.entry(index)
        if entry is None:  # the folder above
            return CardItem(
                UP, "drive_folder_upload", "icon_folder", _("pasta acima"), "text_meta", True
            )
        icon, token = file_visual(Path(entry.name), entry.is_dir)
        meta = remote_meta(entry, self.panel.grid_mode)
        return CardItem(entry.name, icon, token, meta, "text_meta", entry.is_dir)
