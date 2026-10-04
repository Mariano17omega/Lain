"""Tooltips of the folder badges and the file state labels (spec 18 R3).

Paint-path rules: only caches are read (``peek_results``, ``file_sniff``), so a tooltip never
schedules detection or touches the disk. The wording lives in ``core`` (the module's
``badge_tooltip``, ``file_kinds.status_tooltip``): the UI keeps no table of its own.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QHelpEvent

from ...core.file_kinds import status_label, status_tooltip
from ..services import DetectionService


def folder_tooltip(service: DetectionService, path: Path) -> str:
    """What each badge of a folder means, one block per badge; empty when none is cached."""
    results = service.peek_results(path) or []
    return "\n\n".join(result.module.badge_tooltip() for result in results)


def state_tooltip(service: DetectionService, path: Path, size: int) -> str:
    """The meaning of a file's state label (OK, INCOMPLETO…); empty when it has none."""
    sniff = service.file_sniff(path)
    label = status_label(path, size, sniff)
    return status_tooltip(label[0], sniff) if label else ""


def is_tooltip(event: QHelpEvent) -> bool:
    """Whether a delegate's ``helpEvent`` is a tooltip request (the other kind is "What's this")."""
    return event.type() == QEvent.Type.ToolTip
