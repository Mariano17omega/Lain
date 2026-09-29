"""Pull synchronization state machine driving rsync through QProcess (PRD §5).

Stages: dry run → plan → conflict prompts → transfer. The controller never blocks the GUI
thread and never opens dialogs: it emits ``conflict_needed`` and waits for ``resolve()``, so
the UI (or a test) decides how to ask.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from ..config import AppConfig
from .planner import ConflictResolver, Decision, PlanItem, PlanStatus, SyncPlan, build_plan
from .rsync import (
    Endpoint,
    child_env,
    dry_run_command,
    explain_failure,
    is_connection_failure,
    parse_dry_run,
    parse_progress,
    rsync_version,
    transfer_command,
)

log = logging.getLogger(__name__)

KILL_GRACE_MS = 3000


class SyncStatus(StrEnum):
    DONE = "done"
    UP_TO_DATE = "up_to_date"
    LOCAL_NEWER = "local_newer"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class SyncReport:
    status: SyncStatus
    local_dir: Path
    remote: Endpoint
    transferred: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    local_newer: list[str] = field(default_factory=list)
    local_newer_folders: list[str] = field(default_factory=list)
    error: str | None = None
    connection_failed: bool = False

    @property
    def message(self) -> str:
        if self.status is SyncStatus.FAILED:
            return f"Falha na sincronização: {self.error}"
        if self.status is SyncStatus.CANCELLED:
            return "Sincronização cancelada."
        if self.status is SyncStatus.UP_TO_DATE:
            return "Pasta já sincronizada: nada a transferir."
        lines = []
        if self.status is SyncStatus.LOCAL_NEWER:
            lines.append(
                "A cópia local é mais recente que a do cluster: nenhuma transferência realizada."
            )
        else:
            lines.append(f"{len(self.transferred)} arquivo(s) baixado(s).")
        if self.skipped:
            lines.append(f"{len(self.skipped)} conflito(s) mantido(s) na versão local.")
        if self.local_newer and self.status is not SyncStatus.LOCAL_NEWER:
            lines.append(
                f"{len(self.local_newer)} arquivo(s) local(is) mais recente(s) mantido(s)."
            )
        return "\n".join(lines)


class SyncController(QObject):
    stage_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, str)  # percent (-1 = indeterminate), detail
    conflict_needed = pyqtSignal(object)  # PlanItem
    finished = pyqtSignal(object)  # SyncReport

    def __init__(
        self,
        config: AppConfig,
        parent: QObject | None = None,
        extra_args: list[str] | None = None,
        password: str | None = None,
    ):
        super().__init__(parent)
        self.config = config
        self.extra_args = extra_args or []
        self.password = password  # typed by the user for this session; never persisted
        self._process: QProcess | None = None
        self._cancelled = False
        self._local_dir = Path()
        self._remote = Endpoint("")
        self._plan = SyncPlan()
        self._resolver: ConflictResolver | None = None
        self._transfer: list[str] = []
        self._stderr = ""
        self._version: tuple[int, ...] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def plan(self) -> SyncPlan:
        return self._plan

    # -- public API -------------------------------------------------------------------------------
    def start(self, local_dir: Path, remote: Endpoint) -> None:
        if self._running:
            raise RuntimeError("sincronização já em andamento")
        self._running = True
        self._cancelled = False
        self._local_dir = Path(local_dir)
        self._remote = remote
        self._plan = SyncPlan()
        self._resolver = None
        self._transfer = []
        self._version = rsync_version(self.config.sync.rsync_binary)
        if self._version is None:
            self._finish(SyncStatus.FAILED, error="rsync não encontrado (sync.rsync_binary).")
            return
        self.stage_changed.emit("Listando arquivos no cluster…")
        self.progress_changed.emit(-1, remote.spec())
        argv = dry_run_command(self.config, remote, self._local_dir, self._version, self.extra_args)
        self._launch(argv, self._on_dry_run_finished)

    def resolve(self, decision: Decision) -> None:
        if self._resolver is None or not self._running:
            return
        self._resolver.resolve(Decision(decision))
        if self._resolver.cancelled:
            self._finish(SyncStatus.CANCELLED)
        else:
            QTimer.singleShot(0, self._next_conflict)

    def cancel(self) -> None:
        if not self._running:
            return
        self._cancelled = True
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            self.stage_changed.emit("Cancelando…")
            process.terminate()
            QTimer.singleShot(KILL_GRACE_MS, self._kill_if_running)
        else:
            self._finish(SyncStatus.CANCELLED)

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """Cancel and wait for rsync to exit (window close)."""
        process = self._process
        self.cancel()
        running = process is not None and process.state() != QProcess.ProcessState.NotRunning
        if running and not process.waitForFinished(timeout_ms):
            process.kill()
            process.waitForFinished(1000)

    # -- stages -----------------------------------------------------------------------------------
    def _on_dry_run_finished(self, code: int, stdout: str) -> None:
        if self._cancelled:
            self._finish(SyncStatus.CANCELLED)
            return
        if code != 0:
            self._fail(code)
            return
        self.stage_changed.emit("Comparando datas de modificação…")
        self._plan = build_plan(parse_dry_run(stdout), self._local_dir)
        if self._plan.status is PlanStatus.UP_TO_DATE:
            self._finish(SyncStatus.UP_TO_DATE)
        elif self._plan.status is PlanStatus.LOCAL_NEWER:
            self._finish(SyncStatus.LOCAL_NEWER)
        else:
            self._resolver = ConflictResolver(self._plan.conflicts)
            self._next_conflict()

    def _next_conflict(self) -> None:
        if not self._running or self._resolver is None:
            return
        item = self._resolver.next_conflict()
        if item is not None:
            self.stage_changed.emit("Conflito: aguardando decisão…")
            self.conflict_needed.emit(item)
            return
        self._start_transfer()

    def _start_transfer(self) -> None:
        approved = self._resolver.approved if self._resolver else []
        self._transfer = [item.path for item in self._plan.new + approved]
        if not self._transfer:
            self._finish(SyncStatus.DONE)
            return
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self.stage_changed.emit(f"Transferindo {len(self._transfer)} arquivo(s)…")
        self.progress_changed.emit(0, f"0/{len(self._transfer)} arquivos")
        argv = transfer_command(
            self.config, self._remote, self._local_dir, self._version, self.extra_args
        )
        stdin = ("\0".join(self._transfer) + "\0").encode("utf-8")
        self._launch(argv, self._on_transfer_finished, stdin=stdin, progress=True)

    def _on_transfer_finished(self, code: int, _stdout: str) -> None:
        if self._cancelled:
            self._remove_temp_files()
            self._finish(SyncStatus.CANCELLED)
        elif code != 0:
            self._remove_temp_files()
            self._fail(code)
        else:
            self.progress_changed.emit(100, f"{len(self._transfer)}/{len(self._transfer)} arquivos")
            self._finish(SyncStatus.DONE)

    # -- helpers ----------------------------------------------------------------------------------
    def _launch(self, argv, on_finished, stdin: bytes | None = None, progress: bool = False):
        process = QProcess(self)
        env = QProcessEnvironment()
        for key, value in child_env(self.config.cluster, password=self.password).items():
            env.insert(key, value)
        process.setProcessEnvironment(env)
        chunks: list[bytes] = []
        self._stderr = ""

        def read_stdout() -> None:
            data = bytes(process.readAllStandardOutput())
            chunks.append(data)
            if progress:
                self._report_progress(data.decode("utf-8", "replace"))

        def read_stderr() -> None:
            self._stderr += bytes(process.readAllStandardError()).decode("utf-8", "replace")

        def done(code: int, _status) -> None:
            read_stdout()
            read_stderr()
            if self._process is process:
                self._process = None
            process.deleteLater()
            on_finished(code, b"".join(chunks).decode("utf-8", "surrogateescape"))

        def failed(error) -> None:
            if error == QProcess.ProcessError.FailedToStart:
                if self._process is process:
                    self._process = None
                self._finish(SyncStatus.FAILED, error=f"não foi possível executar {argv[0]}")

        process.readyReadStandardOutput.connect(read_stdout)
        process.readyReadStandardError.connect(read_stderr)
        process.finished.connect(done)
        process.errorOccurred.connect(failed)
        self._process = process
        log.debug("sync: %s", " ".join(argv))
        process.start(argv[0], argv[1:])
        if stdin is not None:
            process.write(stdin)
            process.closeWriteChannel()

    def _report_progress(self, chunk: str) -> None:
        update = parse_progress(chunk)
        if update is None:
            return
        total = update.files_total or len(self._transfer)
        done = update.files_done if update.files_done is not None else 0
        self.progress_changed.emit(update.percent, f"{min(done, total)}/{total} arquivos")

    def _kill_if_running(self) -> None:
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _remove_temp_files(self) -> None:
        """rsync writes ``.name.XXXXXX`` temps; SIGKILL can leave them behind."""
        for relative in self._transfer:
            target = self._local_dir / relative
            pattern = re.compile(rf"^\.{re.escape(target.name)}\.[A-Za-z0-9]{{6}}$")
            try:
                for entry in os.scandir(target.parent):
                    if pattern.match(entry.name):
                        os.remove(entry.path)
            except OSError:
                continue

    def _fail(self, code: int) -> None:
        connection = is_connection_failure(code, self._stderr)
        self._finish(SyncStatus.FAILED, explain_failure(code, self._stderr), connection)

    def _finish(
        self, status: SyncStatus, error: str | None = None, connection_failed: bool = False
    ) -> None:
        if not self._running:
            return
        self._running = False
        resolver = self._resolver
        report = SyncReport(
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
        self.finished.emit(report)


__all__ = ["Decision", "PlanItem", "SyncController", "SyncReport", "SyncStatus"]
