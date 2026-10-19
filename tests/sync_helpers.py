"""Helpers shared by the sync tests that run the real rsync."""

import os
from pathlib import Path

from PyQt6.QtCore import QTimer

from qe_studio.core.sync.controller import SyncController
from qe_studio.core.sync.planner import LARGE_FILE_BYTES, Action, Decision, PlanItem, SyncPlan
from qe_studio.core.sync.push import PushController
from qe_studio.core.sync.push_plan import PushAction, PushItem, PushPlan
from qe_studio.core.sync.rsync import Endpoint

T0 = 1_700_000_000
MB = 1024**2


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
    confirm: bool | None = True,
    plans: list[SyncPlan] | None = None,
    before_confirm=None,
):
    """Run one sync to its end. The plan preview is answered with ``confirm`` (None: the test
    answers it) after ``before_confirm(plan)``, if given (the files the user changes while the
    preview is open), and collected in ``plans``; conflicts are answered from ``decisions``
    (default: skip)."""
    prompts = []

    def answer(item):
        prompts.append(item.path)
        decision = (decisions or {}).get(item.path, Decision.SKIP)
        QTimer.singleShot(0, lambda: controller.resolve(decision))

    def preview(plan):
        if plans is not None:
            plans.append(plan)
        if before_confirm is not None:
            before_confirm(plan)
        if confirm is not None:
            QTimer.singleShot(0, lambda: controller.confirm_plan(confirm))

    controller.plan_ready.connect(preview)
    controller.conflict_needed.connect(answer)
    if on_stage:
        controller.stage_changed.connect(on_stage)
    with qtbot.waitSignal(controller.finished, timeout=timeout) as blocker:
        controller.start(local, endpoint)
    return blocker.args[0], prompts


def run_push(
    qtbot,
    controller: PushController,
    local: Path,
    endpoint: Endpoint,
    confirm: bool | None = True,
    plans: list[PushPlan] | None = None,
    before_confirm=None,
    timeout: int = 30_000,
):
    """Run one push to its end. The preview is answered with ``confirm`` (None: the test answers
    it) after ``before_confirm(plan)``, if given, and collected in ``plans``."""

    def preview(plan):
        if plans is not None:
            plans.append(plan)
        if before_confirm is not None:
            before_confirm(plan)
        if confirm is not None:
            QTimer.singleShot(0, lambda: controller.confirm_plan(confirm))

    controller.plan_ready.connect(preview)
    with qtbot.waitSignal(controller.finished, timeout=timeout) as blocker:
        controller.start(local, endpoint)
    return blocker.args[0]


def sample_pull_plan(**counts: int) -> SyncPlan:
    """A plan with the three groups of the pull preview, no connection: ``new`` files (two of them in
    ``bands/``, one large), ``update`` and ``newer`` (local newer), 1 each by default."""
    new, update, newer = counts.get("new", 3), counts.get("update", 1), counts.get("newer", 2)
    names = ["scf.out", "bands/bands.dat.gnu", "bands/big.wfc1"]
    sizes = [10 * 1024, 4 * MB, LARGE_FILE_BYTES + MB]
    items = [
        PlanItem(names[i % 3] if i < 3 else f"new{i}.out", Action.NEW, sizes[i % 3], T0)
        for i in range(new)
    ]
    items += [
        PlanItem(f"relax{i}.out", Action.UPDATE, 2 * MB, T0, T0 - 60, 1) for i in range(update)
    ]
    items += [
        PlanItem(f"plots/p{i}.png", Action.LOCAL_NEWER, 5000, T0, T0 + 60, 1) for i in range(newer)
    ]
    return SyncPlan(items)


def sample_push_plan(**counts: int) -> PushPlan:
    """A plan with the two groups of the push preview, no connection: ``new`` files to send (the
    second, in ``job/``, is large) and ``exists`` ones the cluster has, 2 and 1 by default."""
    new, exists = counts.get("new", 2), counts.get("exists", 1)
    names = ["scf.in", "job/wfc.dat"]
    sizes = [900, LARGE_FILE_BYTES + MB]
    items = [
        PushItem(
            names[i] if i < 2 else f"new{i}.in", PushAction.NEW, sizes[i] if i < 2 else 900, T0
        )
        for i in range(new)
    ]
    items += [PushItem(f"scf{i}.out", PushAction.EXISTS, 7 * MB, T0 + 30) for i in range(exists)]
    return PushPlan(items)
