"""Helpers shared by the sync tests that run the real rsync."""

import os
from pathlib import Path

from PyQt6.QtCore import QTimer

from qe_studio.core.sync.controller import SyncController
from qe_studio.core.sync.planner import Decision
from qe_studio.core.sync.rsync import Endpoint

T0 = 1_700_000_000


def write(root: Path, rel: str, content: str, mtime: float = T0) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def run_sync(
    qtbot,
    controller: SyncController,
    local: Path,
    endpoint: Endpoint,
    decisions: dict[str, Decision] | None = None,
    on_stage=None,
    timeout: int = 30_000,
):
    """Run one sync to its end. Conflicts are answered from ``decisions`` (default: skip)."""
    prompts = []

    def answer(item):
        prompts.append(item.path)
        decision = (decisions or {}).get(item.path, Decision.SKIP)
        QTimer.singleShot(0, lambda: controller.resolve(decision))

    controller.conflict_needed.connect(answer)
    if on_stage:
        controller.stage_changed.connect(on_stage)
    with qtbot.waitSignal(controller.finished, timeout=timeout) as blocker:
        controller.start(local, endpoint)
    return blocker.args[0], prompts
