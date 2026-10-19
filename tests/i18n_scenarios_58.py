"""Probe scenarios of spec 58: the cluster and the sync (``tests/i18n_probe.py`` adds ``SCENARIOS`` to
its own).

None of them opens a connection: the plans come from ``tests/sync_helpers.py``
(``sample_pull_plan``, ``sample_push_plan``), the dialogs are laid on controllers that are never
started, and the failures are synthetic ``stderr`` texts.

- ``sync_preview_pull`` / ``sync_preview_push``: the sync window of a download / an upload, from the
  search page to the progress, its preview tree (as facts: the cells of a ``QTreeWidget`` are items,
  not widgets), the summaries with 1 and with 2 files, and the conflict prompt of the pull.
- ``sync_report``: how a pull and a push end (message, headline and the full report), with one and with
  two files, as facts and in the toast.
- ``sync_menu``: the menu actions and the scope in words (folder, project, everything; download and
  upload), why a folder cannot be synced, and what an unconfigured cluster says.
- ``sync_failures``: the hint of each ``FAILURE_HINTS`` needle, the ones rsync and ssh give by other
  means and the errors of a run that cannot start.

Facts are ``<kind> <detail>: <text>`` lines for the tests to compare between the languages. The paths
of the temporary project are written ``<root>``. Modules with texts are imported inside the functions:
the language is installed before them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

CLUSTER_DIR = "/scratch/usuario/MoS2/03_bands"
STDERR_FOR = "ssh: connect to host cluster.example.org port 22: {needle}"
PRECEDENCE = (  # (stderr, what it checks): the first known cause in the text wins
    "Host key verification failed.\nPermission denied (publickey).",
    "Permission denied (publickey).\nrsync: connection unexpectedly closed (0 bytes received)",
    "rsync error: unexplained error (code 255)\nrsync: connection unexpectedly closed (0 bytes)",
    "something no one foresaw\n",
    "",
)


def anonymous(text: str, project: Path) -> str:
    return text.replace(str(project), "<root>")


def tree_lines(tree) -> list[str]:
    """The header and every row of a ``QTreeWidget``, the depth as indentation."""
    columns = tree.columnCount()
    header = tree.headerItem()
    lines = ["header: " + " | ".join(header.text(column) for column in range(columns))]

    def walk(item, depth: int) -> None:
        cells = " | ".join(item.text(column) for column in range(columns))
        lines.append("row " + "  " * depth + cells)
        for index in range(item.childCount()):
            walk(item.child(index), depth + 1)

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index), 0)
    return lines


def window_facts(dialog, controller) -> list[str]:
    """The window as the preview left it, and the texts it takes while the run goes on."""
    return [
        f"title: {dialog.windowTitle()}",
        f"scope: {dialog.scope_label.text()}",
        f"confirm: {dialog.download_button.text()}",
        f"cancel: {dialog.cancel_button.text()}",
        f"search: {dialog.search.stage.text()}",
        f"stage listing: {controller.LISTING}",
        f"stage planning: {controller.PLANNING}",
    ]


def preview_facts(dialog) -> list[str]:
    page = dialog.preview
    return [
        f"summary: {page.summary.text()}",
        f"large: {page.large.text()}",
        *tree_lines(page.tree),
    ]


def transfer_facts(dialog, controller) -> list[str]:
    """The confirmed plan on the transfer page: the stage, the progress and the cancel."""
    dialog.download()
    facts = [f"transfer: {dialog.transfer.stage.text()}"]
    for count in (1, 2):
        controller.stage_changed.emit(controller._sending(count))
        controller.progress_changed.emit(50, controller._files_done(1, count))
        facts.append(
            f"transfer {count}: {dialog.transfer.stage.text()} | {dialog.transfer.detail.text()}"
        )
    dialog.request_cancel()
    facts.append(f"cancel: {dialog.transfer.stage.text()}")
    return facts


def sync_preview_pull(window, project: Path) -> list[str]:
    from qe_studio.core.sync.controller import SyncController
    from qe_studio.core.sync.planner import Action, PlanItem
    from qe_studio.core.sync.preview import large_summary, plan_summary
    from qe_studio.core.sync.request import sync_scope
    from qe_studio.ui.dialogs.sync_dialog import ConflictDialog, SyncDialog

    from sync_helpers import T0, sample_pull_plan

    scope = sync_scope(window.config, project / "04_pdos_orbitals" / "orbitals")
    controller = SyncController(window.config, window)
    dialog = SyncDialog(window.theme, controller, scope, window)
    dialog.show()
    facts = [f"pull {text}" for text in window_facts(dialog, controller)]
    facts.append(f"pull stage checking: {SyncController.CHECKING}")
    dialog.show_plan(sample_pull_plan())
    facts += [f"pull {text}" for text in preview_facts(dialog)]
    for count in (1, 2):  # the singular and the plural of every count
        plan = sample_pull_plan(new=count, update=count, newer=count)
        facts.append(f"pull count {count}: {plan_summary(plan)}")
        facts.append(f"pull large {count}: {large_summary(sample_pull_plan(new=3 * count))}")
    facts += [f"pull {text}" for text in transfer_facts(dialog, controller)]
    item = PlanItem("relax.out", Action.UPDATE, 2 * 1024**2, T0, T0 - 60, 1)
    conflict = ConflictDialog(item, dialog)
    conflict.show()
    dialog.await_decision(item)
    facts.append(f"pull waiting: {dialog.transfer.stage.text()}")
    return facts


def sync_preview_push(window, project: Path) -> list[str]:
    from qe_studio.core.sync.preview import large_summary, push_summary
    from qe_studio.core.sync.push import PushController
    from qe_studio.core.sync.request import Direction, sync_scope
    from qe_studio.ui.dialogs.sync_dialog import SyncDialog

    from sync_helpers import sample_push_plan

    scope = sync_scope(
        window.config, project / "04_pdos_orbitals" / "orbitals", direction=Direction.PUSH
    )
    controller = PushController(window.config, window)
    dialog = SyncDialog(window.theme, controller, scope, window)
    dialog.show()
    facts = [f"push {text}" for text in window_facts(dialog, controller)]
    dialog.show_plan(sample_push_plan())
    facts += [f"push {text}" for text in preview_facts(dialog)]
    for count in (1, 2):
        facts.append(
            f"push count {count}: {push_summary(sample_push_plan(new=count, exists=count))}"
        )
        facts.append(f"push large {count}: {large_summary(sample_push_plan(new=2 * count))}")
    facts += [f"push {text}" for text in transfer_facts(dialog, controller)]
    return facts


def report_facts(name: str, report, project: Path) -> list[str]:
    facts = []
    for part in ("message", "headline", "details"):
        for line in getattr(report, part).splitlines():
            facts.append(anonymous(f"{name} {part}: {line}", project))
    return facts


def sync_report(window, project: Path) -> list[str]:
    from qe_studio.core.sync.report import PushReport, SyncReport, SyncStatus
    from qe_studio.core.sync.rsync import Endpoint, explain_failure, is_auth_failure

    local = project / "03_bands"
    remote = Endpoint(CLUSTER_DIR, "cluster.example.org", "usuario")

    def pull(status, count=1, **fields):
        names = lambda prefix: [f"{prefix}{n}.out" for n in range(count)]  # noqa: E731
        return SyncReport(
            status,
            local,
            remote,
            transferred=names("down") if status is SyncStatus.DONE else [],
            skipped=names("kept"),
            local_newer=names("newer"),
            changed_locally=tuple(names("edited")),
            **fields,
        )

    def push(status, count=1, **fields):
        names = [f"up{n}.in" for n in range(count)]
        existing = [f"there{n}.in" for n in range(count)]
        return PushReport(
            status,
            local,
            remote,
            transferred=names if status is SyncStatus.DONE else [],
            existing=existing,
            **fields,
        )

    stderr = "Permission denied (publickey)."
    denied = pull(
        SyncStatus.FAILED,
        error=explain_failure(255, stderr),
        auth_failed=is_auth_failure(stderr),
    )
    reports = {
        "pull done 1": pull(SyncStatus.DONE, 1),
        "pull done 2": pull(SyncStatus.DONE, 2),
        "pull up-to-date": pull(SyncStatus.UP_TO_DATE),
        "pull local-newer": pull(SyncStatus.LOCAL_NEWER),
        "pull cancelled": pull(SyncStatus.CANCELLED),
        "pull denied": denied,
        "push done 1": push(SyncStatus.DONE, 1),
        "push done 2": push(SyncStatus.DONE, 2),
        "push up-to-date": push(SyncStatus.UP_TO_DATE),
        "push cancelled": push(SyncStatus.CANCELLED),
        "push failed": push(SyncStatus.FAILED, error=explain_failure(255, "Connection refused")),
    }
    facts = [f"auth: {denied.auth_failed}"]
    for name, report in reports.items():
        facts += report_facts(name, report, project)
    done = reports["pull done 2"]
    window.toast.show_message(done.headline, "warning", details=done.details)
    return facts


def sync_menu(window, project: Path) -> list[str]:
    from qe_studio.core.config import parse_config
    from qe_studio.core.sync.request import (
        Direction,
        prepare_push,
        prepare_sync,
        push_availability,
        sync_scope,
    )
    from qe_studio.ui.sync_coordinator import SyncCoordinator

    config = window.config
    orbitals = project / "04_pdos_orbitals" / "orbitals"
    scopes = {
        "folder": (orbitals, ""),
        "project": (project / "01_relax", "01_relax"),
        "root": (project, ""),
    }
    facts = []
    for direction in (Direction.PULL, Direction.PUSH):
        for name, (folder, project_name) in scopes.items():
            scope = sync_scope(config, folder, direction=direction, project=project_name)
            for part in ("menu_text", "tooltip", "title", "window_title", "confirm_text", "label"):
                facts.append(
                    anonymous(f"{direction} {name} {part}: {getattr(scope, part)}", project)
                )
    # The real menu items, as the window keeps them up to date.
    window.sync.set_project(project / "01_relax")
    window.sync.show_scope(orbitals)
    for name in ("_folder_action", "_project_action", "_push_action"):
        action = getattr(window.sync, name)
        facts.append(anonymous(f"action {name}: {action.text()} | {action.toolTip()}", project))
    window.sync.set_project(None)
    window.sync.show_scope(orbitals)
    facts.append(f"action _project_action: {window.sync._project_action.text()}")
    # Why a folder cannot be sent or synced.
    elsewhere = Path("/elsewhere")
    for name, folder in (
        ("root", project),
        ("project", project / "01_relax"),
        ("none", project / "none"),
    ):
        facts.append(anonymous(f"push {name}: {push_availability(config, folder)}", project))
    for name, request in (
        ("push missing", prepare_push(config, project / "none")),
        ("push outside", prepare_push(config, elsewhere)),
        ("pull outside", prepare_sync(config, elsewhere)),
    ):
        facts.append(
            anonymous(f"refusal {name}: {getattr(request, 'message', 'accepted')}", project)
        )
    # A window with no cluster: the label of the monitor and the scope's tooltip.
    off = parse_config({"paths": {"local_root": str(project)}})
    coordinator = SyncCoordinator(off, window.theme, window)
    states: list[str] = []
    tips: list[str] = []
    coordinator.cluster_changed.connect(lambda label, state: states.append(f"{label} ({state})"))
    coordinator.scope_changed.connect(tips.append)
    coordinator._on_state("offline")
    coordinator.show_scope(orbitals)
    facts += [f"off cluster: {text}" for text in states]
    facts += [anonymous(f"off scope: {text}", project) for text in tips]
    facts.append(f"off push: {push_availability(off, orbitals)}")
    facts.append(f"off refusal: {prepare_sync(off, orbitals).message}")  # type: ignore[union-attr]
    coordinator.shutdown()
    coordinator.deleteLater()
    facts.append(f"titles: {coordinator_titles()}")
    return facts


def coordinator_titles() -> str:
    from qe_studio.ui import sync_coordinator

    return f"{sync_coordinator.TITLE} | {sync_coordinator.PUSH_TITLE}"


def finish_of(controller, start: Callable[[], None]) -> object:
    """The report of a run that ends by itself (it cannot start), after ``start()``."""
    from PyQt6.QtCore import QEventLoop, QTimer

    reports: list[object] = []
    loop = QEventLoop()

    def done(report: object) -> None:
        reports.append(report)
        loop.quit()

    controller.finished.connect(done)
    QTimer.singleShot(5000, loop.quit)
    start()
    loop.exec()
    if not reports:
        raise RuntimeError("the run did not end")
    return reports[0]


def sync_failures(window, project: Path) -> list[str]:
    from qe_studio.core.config import parse_config
    from qe_studio.core.sync._process import RSYNC_MISSING
    from qe_studio.core.sync.controller import SyncController
    from qe_studio.core.sync.rsync import (
        FAILURE_HINTS,
        Endpoint,
        explain_failure,
        is_auth_failure,
        is_connection_failure,
    )

    def line(stderr: str, exit_code: int = 255) -> str:
        message = explain_failure(exit_code, stderr).replace("\n", " ")
        auth, connection = is_auth_failure(stderr), is_connection_failure(exit_code, stderr)
        return f"{message} | auth={auth} | connection={connection}"

    facts = [
        f"hint {index} {needle}: {line(STDERR_FOR.format(needle=needle))}"
        for index, (needle, _hint) in enumerate(FAILURE_HINTS)
    ]
    facts += [f"other {index}: {line(text, 23)}" for index, text in enumerate(PRECEDENCE)]
    facts.append(f"missing: {RSYNC_MISSING}")
    # The errors of a run that cannot go on (no process: a binary that does not exist).
    broken = parse_config({"sync": {"rsync_binary": "/nonexistent/rsync"}})
    remote = Endpoint(CLUSTER_DIR, "cluster.example.org", "usuario")
    controller = SyncController(broken, window)
    report = finish_of(controller, lambda: controller.start(project / "x", remote))
    facts.append(f"run no rsync: {report.error}")  # type: ignore[attr-defined]
    controller = SyncController(broken, window)
    controller._running = True
    report = finish_of(
        controller, lambda: controller._launch(["/nonexistent/ssh"], lambda *a: None)
    )
    facts.append(f"run no program: {report.error}")  # type: ignore[attr-defined]
    controller = SyncController(broken, window)
    controller._running = True
    logger = logging.getLogger("qe_studio.core.sync._process")
    logger.disabled = True  # the traceback of the error is for the log, not for this probe
    try:
        report = finish_of(controller, lambda: controller._unexpected(ValueError("boom")))
    finally:
        logger.disabled = False
    facts.append(f"run unexpected: {report.error}")  # type: ignore[attr-defined]
    window.toast.show_message(str(report.error), "error")  # type: ignore[attr-defined]
    return facts


SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    "sync_preview_pull": sync_preview_pull,
    "sync_preview_push": sync_preview_push,
    "sync_report": sync_report,
    "sync_menu": sync_menu,
    "sync_failures": sync_failures,
}
