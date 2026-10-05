"""One rsync run driven through QProcess, shared by the pull (``controller.SyncController``) and the
push (``push.PushController``, spec 27).

Stages: rsync version → dry run → plan (local stats in a worker) → ``plan_ready`` and
``confirm_plan()`` → transfer → report. The run never blocks the GUI thread and never opens
dialogs; subclasses say which commands run, how a plan is built and used, and what the report says.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from ..config import AppConfig
from ..tasks import TaskHandle, run_task
from .report import SyncReport, SyncStatus
from .rsync import (
    Endpoint,
    child_env,
    explain_failure,
    is_connection_failure,
    parse_progress,
    parse_version,
    version_command,
)

log = logging.getLogger(__name__)

KILL_GRACE_MS = 3000
RSYNC_MISSING = "rsync não encontrado (sync.rsync_binary)."


class RsyncRun(QObject):
    stage_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, str)  # percent (-1 = indeterminate), detail
    plan_ready = pyqtSignal(object)  # the plan, with something to transfer: confirm_plan() answers
    transfer_started = pyqtSignal(int)  # files to transfer, before its stage and progress
    finished = pyqtSignal(object)  # SyncReport (or a subclass)

    LISTING: ClassVar[str] = "Listando arquivos no cluster…"
    PLANNING: ClassVar[str] = "Comparando datas de modificação…"
    SENDING: ClassVar[str] = "Transferindo {count} arquivo(s)…"

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
        self._transfer: list[str] = []
        self._stderr = ""
        self._version: tuple[int, ...] | None = None
        self._running = False
        self._awaiting_plan = False  # plan_ready emitted, confirm_plan() not called yet
        self._plan_task: TaskHandle | None = None  # cancelled with the run: its plan is dropped
        self._reset()

    @property
    def running(self) -> bool:
        return self._running

    # -- public API -------------------------------------------------------------------------------
    def start(self, local_dir: Path, remote: Endpoint) -> None:
        if self._running:
            raise RuntimeError("sincronização já em andamento")
        self._running = True
        self._cancelled = False
        self._local_dir = Path(local_dir)
        self._remote = remote
        self._transfer = []
        self._version = None
        self._awaiting_plan = False
        self._reset()
        self.stage_changed.emit(self.LISTING)
        self.progress_changed.emit(-1, remote.spec())
        self._step(self._check_version)

    def confirm_plan(self, accepted: bool) -> None:
        """Answer to ``plan_ready``: go on with the plan, or end the run as CANCELLED."""
        if not self._running or not self._awaiting_plan:
            return
        self._awaiting_plan = False
        if accepted:
            self._step(self._accepted)
        else:
            self._finish(SyncStatus.CANCELLED)

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

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Cancel and wait for rsync to exit (window close); False when it had to be killed."""
        process = self._process
        self.cancel()
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return True
        if process.waitForFinished(timeout_ms):
            return True
        process.kill()
        process.waitForFinished(1000)
        return False

    # -- what a subclass says ---------------------------------------------------------------------
    def _reset(self) -> None:
        """Set the subclass's own state, fresh (``__init__`` and every ``start``)."""

    def _dry_run_command(self) -> list[str]:
        raise NotImplementedError

    # Runs in a worker: (dry-run stdout, local folder) → plan. A plain function (staticmethod).
    _build_plan: Callable[[str, Path], Any]

    def _use_plan(self, plan: Any) -> None:
        """Keep the plan, then finish, emit ``plan_ready`` (``_awaiting_plan``) or go on."""
        raise NotImplementedError

    def _accepted(self) -> None:
        """The plan was confirmed."""
        raise NotImplementedError

    def _discard_partial(self) -> None:
        """A transfer failed or was cancelled: clean what it may have left behind."""

    def _report(self, status: SyncStatus, error: str | None, connection_failed: bool) -> SyncReport:
        raise NotImplementedError

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
        self._launch(self._dry_run_command(), self._on_dry_run_finished)

    def _on_dry_run_finished(self, code: int, stdout: str) -> None:
        if self._cancelled:
            self._finish(SyncStatus.CANCELLED)
            return
        if code != 0:
            self._fail(code)
            return
        self.stage_changed.emit(self.PLANNING)
        self._plan_task = run_task(
            self._build_plan,
            stdout,
            self._local_dir,
            on_done=self._on_plan,
            on_error=self._on_plan_failed,
        )

    def _on_plan(self, plan: Any) -> None:
        if self._running:  # a cancelled run's plan never arrives: cancel() dropped it
            self._step(self._use_plan, plan)

    def _on_plan_failed(self, error: Exception) -> None:
        if self._running:  # reported as a failed sync, never lost in the worker
            self._unexpected(error)

    def _ask_plan(self, plan: Any) -> None:
        self._awaiting_plan = True
        self.stage_changed.emit("Aguardando confirmação…")
        self.plan_ready.emit(plan)

    def _send(self, files: list[str], argv: list[str]) -> None:
        """Transfer ``files`` (relative to the synced folder, on rsync's stdin) with ``argv``."""
        self._transfer = files
        self.transfer_started.emit(len(files))
        self.stage_changed.emit(self.SENDING.format(count=len(files)))
        self.progress_changed.emit(0, f"0/{len(files)} arquivos")
        stdin = ("\0".join(files) + "\0").encode("utf-8")
        self._launch(argv, self._on_transfer_finished, stdin=stdin, progress=True)

    def _on_transfer_finished(self, code: int, _stdout: str) -> None:
        if self._cancelled:
            self._discard_partial()
            self._finish(SyncStatus.CANCELLED)
        elif code != 0:
            self._discard_partial()
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

    def _fail(self, code: int) -> None:
        connection = is_connection_failure(code, self._stderr)
        self._finish(SyncStatus.FAILED, explain_failure(code, self._stderr), connection)

    def _finish(
        self, status: SyncStatus, error: str | None = None, connection_failed: bool = False
    ) -> None:
        if not self._running:
            return
        self._running = False
        self._awaiting_plan = False
        self.finished.emit(self._report(status, error, connection_failed))
