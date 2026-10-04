"""Pull synchronization state machine driving rsync through QProcess (PRD §5).

Stages: rsync version → dry run → plan → conflict prompts → transfer. The controller never
blocks the GUI thread (processes run in ``QProcess``, the plan's local stats in a worker) and
never opens dialogs: it emits ``conflict_needed`` and waits for ``resolve()``, so the UI (or a
test) decides how to ask.
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
from ..tasks import TaskHandle, run_task
from .planner import ConflictResolver, Decision, PlanItem, PlanStatus, SyncPlan, build_plan
from .rsync import (
    Endpoint,
    child_env,
    dry_run_command,
    explain_failure,
    is_connection_failure,
    parse_dry_run,
    parse_progress,
    parse_version,
    transfer_command,
    version_command,
)

log = logging.getLogger(__name__)

KILL_GRACE_MS = 3000
RSYNC_MISSING = "rsync não encontrado (sync.rsync_binary)."
TEMP_NAME = re.compile(r"^\.(.+)\.[A-Za-z0-9]{6}$")  # rsync's partial file for ``name``


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


def _plan(stdout: str, local_dir: Path) -> SyncPlan:
    """Compares the dry-run listing with the local files: one stat per file, network homes."""
    return build_plan(parse_dry_run(stdout), local_dir)


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
        self._plan_task: TaskHandle | None = None  # cancelled with the run: its plan is dropped

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
        self._version = None
        self.stage_changed.emit("Listando arquivos no cluster…")
        self.progress_changed.emit(-1, remote.spec())
        self._step(self._check_version)

    def resolve(self, decision: Decision) -> None:
        if self._resolver is None or not self._running:
            return
        self._resolver.resolve(Decision(decision))
        if self._resolver.cancelled:
            self._finish(SyncStatus.CANCELLED)
        else:
            # Next loop turn, not a worker: the conflict dialog that called us closes first.
            QTimer.singleShot(0, self._next_conflict)

    def cancel(self) -> None:
        if not self._running:
            return
        self._cancelled = True
        if self._plan_task is not None:
            self._plan_task.cancel()
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
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        if not process.waitForFinished(timeout_ms):
            process.kill()
            process.waitForFinished(1000)

    # -- stages -----------------------------------------------------------------------------------
    def _step(self, stage, *args) -> None:
        """Run a stage; an unexpected error (e.g. the local folder cannot be created) ends the
        sync as FAILED instead of leaving it, and its dialog, running forever."""
        try:
            stage(*args)
        except Exception as exc:
            self._unexpected(exc)

    def _unexpected(self, exc: BaseException) -> None:
        log.error("sync stage failed", exc_info=exc)
        self._kill_if_running()
        self._finish(SyncStatus.FAILED, error=f"erro inesperado ({type(exc).__name__}: {exc})")

    def _check_version(self) -> None:
        argv = version_command(self.config.sync.rsync_binary)
        self._launch(argv, self._on_version, start_error=RSYNC_MISSING)

    def _on_version(self, _code: int, stdout: str) -> None:
        if self._cancelled:
            self._finish(SyncStatus.CANCELLED)
            return
        self._version = parse_version(stdout)
        if self._version is None:
            self._finish(SyncStatus.FAILED, error=RSYNC_MISSING)
            return
        argv = dry_run_command(
            self.config, self._remote, self._local_dir, self._version, self.extra_args
        )
        self._launch(argv, self._on_dry_run_finished)

    def _on_dry_run_finished(self, code: int, stdout: str) -> None:
        if self._cancelled:
            self._finish(SyncStatus.CANCELLED)
            return
        if code != 0:
            self._fail(code)
            return
        self.stage_changed.emit("Comparando datas de modificação…")
        self._plan_task = run_task(
            _plan, stdout, self._local_dir, on_done=self._on_plan, on_error=self._on_plan_failed
        )

    def _on_plan(self, plan: SyncPlan) -> None:
        if self._running:  # a cancelled run's plan never arrives: cancel() dropped it
            self._step(self._use_plan, plan)

    def _on_plan_failed(self, error: Exception) -> None:
        if self._running:  # reported as a failed sync, never lost in the worker
            self._unexpected(error)

    def _use_plan(self, plan: SyncPlan) -> None:
        self._plan = plan
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
        self._step(self._start_transfer)

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
    def _launch(
        self,
        argv,
        on_finished,
        stdin: bytes | None = None,
        progress: bool = False,
        start_error: str | None = None,
    ):
        process = QProcess(self)
        env = QProcessEnvironment()
        for key, value in child_env(self.config.cluster, password=self.password).items():
            env.insert(key, value)
        process.setProcessEnvironment(env)
        chunks: list[bytes] = []
        self._stderr = ""

        def read_stdout() -> None:
            data = process.readAllStandardOutput().data()
            chunks.append(data)
            if progress:
                self._report_progress(data.decode("utf-8", "replace"))

        def read_stderr() -> None:
            self._stderr += process.readAllStandardError().data().decode("utf-8", "replace")

        def done(code: int, _status) -> None:
            read_stdout()
            read_stderr()
            if self._process is process:
                self._process = None
            process.deleteLater()
            self._step(on_finished, code, b"".join(chunks).decode("utf-8", "surrogateescape"))

        def failed(error) -> None:
            if error == QProcess.ProcessError.FailedToStart:
                if self._process is process:
                    self._process = None
                self._finish(
                    SyncStatus.FAILED, error=start_error or f"não foi possível executar {argv[0]}"
                )

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


def _temp_of(name: str) -> str | None:
    match = TEMP_NAME.match(name)
    return match.group(1) if match else None


__all__ = ["Decision", "PlanItem", "SyncController", "SyncReport", "SyncStatus"]
