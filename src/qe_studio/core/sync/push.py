"""Push of one calculation folder to the cluster (spec 27): only files the cluster does not have
go up, and nothing there is ever changed or deleted (PRD §7 data integrity).

Stages: rsync version → dry run from the local folder → plan (``push_plan.build_push_plan``, in a
worker) → ``plan_ready`` **always**, whatever ``sync.confirm_plan`` says (a push writes on the
cluster) → transfer of the new files with ``--ignore-existing`` → ``PushReport``. A file the cluster
already has is only listed; there are no conflicts to resolve. Nothing local is created, changed
or cleaned up.
"""

from __future__ import annotations

from pathlib import Path

from ._process import RsyncRun
from .push_plan import PushPlan, build_push_plan
from .report import PushReport, SyncStatus
from .rsync import parse_dry_run, push_dry_run_command, push_transfer_command


def _push_plan(stdout: str, local_dir: Path) -> PushPlan:
    return build_push_plan(parse_dry_run(stdout), local_dir)


class PushController(RsyncRun):
    LISTING = "Comparando com o cluster…"
    PLANNING = "Conferindo arquivos locais…"
    SENDING = "Enviando {count} arquivo(s)…"

    _plan: PushPlan

    @property
    def plan(self) -> PushPlan:
        return self._plan

    def _reset(self) -> None:
        self._plan = PushPlan()

    def _dry_run_command(self) -> list[str]:
        return push_dry_run_command(
            self.config, self._remote, self._local_dir, self._version, self.extra_args
        )

    _build_plan = staticmethod(_push_plan)

    def _use_plan(self, plan: PushPlan) -> None:
        self._plan = plan
        if plan.new:
            self._ask_plan(plan)
        else:
            self._finish(SyncStatus.UP_TO_DATE)

    def _accepted(self) -> None:
        argv = push_transfer_command(
            self.config, self._remote, self._local_dir, self._version, self.extra_args
        )
        self._send([item.path for item in self._plan.new], argv)

    def _report(self, status: SyncStatus, error: str | None, connection_failed: bool) -> PushReport:
        return PushReport(
            status,
            self._local_dir,
            self._remote,
            transferred=list(self._transfer) if status is SyncStatus.DONE else [],
            existing=[item.path for item in self._plan.exists],
            error=error,
            connection_failed=connection_failed,
        )
