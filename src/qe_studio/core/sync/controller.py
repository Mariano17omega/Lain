"""Pull synchronization state machine driving rsync through QProcess (PRD §5).

Stages: rsync version → dry run → plan → plan preview → conflict prompts → transfer. The
controller never blocks the GUI thread (processes run in ``QProcess``, the plan's local stats in a
worker) and never opens dialogs: it emits ``plan_ready`` and waits for ``confirm_plan()`` (spec 17
R2), then ``conflict_needed`` and waits for ``resolve()``, so the UI (or a test) decides how to ask.
The process handling it shares with the push is ``_process.RsyncRun``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSignal

from ._process import RsyncRun
from .planner import ConflictResolver, Decision, PlanItem, PlanStatus, SyncPlan, build_plan
from .report import SyncReport, SyncStatus
from .rsync import dry_run_command, parse_dry_run, transfer_command

TEMP_NAME = re.compile(r"^\.(.+)\.[A-Za-z0-9]{6}$")  # rsync's partial file for ``name``


def _pull_plan(stdout: str, local_dir: Path) -> SyncPlan:
    """Compares the dry-run listing with the local files: one stat per file, network homes."""
    return build_plan(parse_dry_run(stdout), local_dir)


class SyncController(RsyncRun):
    conflict_needed = pyqtSignal(object)  # PlanItem

    _plan: SyncPlan
    _resolver: ConflictResolver | None

    @property
    def plan(self) -> SyncPlan:
        return self._plan

    def resolve(self, decision: Decision) -> None:
        if self._resolver is None or not self._running:
            return
        self._resolver.resolve(Decision(decision))
        if self._resolver.cancelled:
            self._finish(SyncStatus.CANCELLED)
        else:
            # Next loop turn, not a worker: the conflict dialog that called us closes first.
            QTimer.singleShot(0, self._next_conflict)

    # -- stages -----------------------------------------------------------------------------------
    def _reset(self) -> None:
        self._plan = SyncPlan()
        self._resolver = None

    def _dry_run_command(self) -> list[str]:
        return dry_run_command(
            self.config, self._remote, self._local_dir, self._version, self.extra_args
        )

    _build_plan = staticmethod(_pull_plan)

    def _use_plan(self, plan: SyncPlan) -> None:
        self._plan = plan
        if self._plan.status is PlanStatus.UP_TO_DATE:
            self._finish(SyncStatus.UP_TO_DATE)
        elif self._plan.status is PlanStatus.LOCAL_NEWER:
            self._finish(SyncStatus.LOCAL_NEWER)
        elif self.config.sync.confirm_plan:
            self._ask_plan(self._plan)
        else:
            self._begin_conflicts()

    def _accepted(self) -> None:
        self._begin_conflicts()

    def _begin_conflicts(self) -> None:
        self._resolver = ConflictResolver(self._plan.conflicts)
        self._next_conflict()

    def _next_conflict(self) -> None:
        if not self._running or self._resolver is None:
            return
        item = self._resolver.next_conflict()
        if item is not None:
            self.stage_changed.emit("Aguardando sua decisão…")
            self.conflict_needed.emit(item)
            return
        self._step(self._start_transfer)

    def _start_transfer(self) -> None:
        approved = self._resolver.approved if self._resolver else []
        files = [item.path for item in self._plan.new + approved]
        if not files:
            self._finish(SyncStatus.DONE)
            return
        self._local_dir.mkdir(parents=True, exist_ok=True)
        argv = transfer_command(
            self.config, self._remote, self._local_dir, self._version, self.extra_args
        )
        self._send(files, argv)

    # -- helpers ----------------------------------------------------------------------------------
    def _discard_partial(self) -> None:
        self._remove_temp_files()

    def _remove_temp_files(self) -> None:
        """rsync writes ``.name.XXXXXX`` temps; SIGKILL can leave them behind."""
        names: dict[Path, set[str]] = {}
        for relative in self._transfer:
            target = self._local_dir / relative
            names.setdefault(target.parent, set()).add(target.name)
        for folder, expected in names.items():  # one listing per folder, not one per file
            try:
                with os.scandir(folder) as entries:
                    temps = [e.path for e in entries if _temp_of(e.name) in expected]
            except OSError:
                continue
            for path in temps:
                try:
                    os.remove(path)
                except OSError:
                    continue

    def _report(self, status: SyncStatus, error: str | None, connection_failed: bool) -> SyncReport:
        resolver = self._resolver
        return SyncReport(
            status,
            self._local_dir,
            self._remote,
            transferred=list(self._transfer) if status is SyncStatus.DONE else [],
            skipped=[item.path for item in resolver.skipped] if resolver else [],
            local_newer=[item.path for item in self._plan.local_newer],
            local_newer_folders=self._plan.local_newer_folders,
            error=error,
            connection_failed=connection_failed,
        )


def _temp_of(name: str) -> str | None:
    match = TEMP_NAME.match(name)
    return match.group(1) if match else None


__all__ = ["Decision", "PlanItem", "SyncController", "SyncReport", "SyncStatus"]
