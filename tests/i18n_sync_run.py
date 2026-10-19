"""One real pull or push in a language, as JSON, from a new process (spec 58 R3.3).

    python tests/i18n_sync_run.py --language en --config cfg.json --step pull --folder DIR

The language is chosen once, before the modules with texts are imported (spec end R1), so each language
needs a process of its own, like ``tests/i18n_probe.py``. This one runs the *controllers* of
``core/sync`` (no window) against the SSH server of ``tests/ssh_server.py``, which lives in the test's
process: ``cfg.json`` is ``server.config_data()`` with the ``paths`` of the test. The preview is
confirmed, a conflict is skipped. The last line of stdout is the JSON: the status, the files copied
and left alone, what the preview and the report say, and everything the root logger heard, at DEBUG.

``--step``: ``pull`` (``--folder`` is the local folder to bring down), ``push`` (the local folder to
send up). ``--password`` goes to the controller as the window passes it (never to argv of ssh).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from qe_studio import i18n  # no texts: the language is installed before the modules that have them

RUN_TIMEOUT_MS = 60_000


class Heard(logging.Handler):
    """Every record of the run, formatted, traceback included."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def preview_lines(plan) -> list[str]:
    from qe_studio.core.sync.preview import describe_plan

    preview = describe_plan(plan)
    lines = [f"summary: {preview.summary}"]
    if preview.large:
        lines.append(f"large: {preview.large}")
    for section in preview.sections:
        lines.append(f"section: {section.title} | {section.note}")
        for group in section.groups:
            lines += [f"row: {row.path} | {row.note}" for row in group.rows]
    return lines


def run(args: argparse.Namespace) -> dict:
    from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

    from qe_studio.core.config import parse_config
    from qe_studio.core.sync.controller import SyncController
    from qe_studio.core.sync.planner import Decision
    from qe_studio.core.sync.push import PushController
    from qe_studio.core.sync.request import SyncRefusal, prepare_push, prepare_sync

    app = QCoreApplication(sys.argv[:1])
    config = parse_config(json.loads(args.config.read_text(encoding="utf-8")))
    folder = args.folder
    push = args.step == "push"
    request = (prepare_push if push else prepare_sync)(config, folder)
    if isinstance(request, SyncRefusal):
        return {"refused": request.message}
    controller = (PushController if push else SyncController)(config, password=args.password)
    previews: list[list[str]] = []
    reports: list[object] = []
    loop = QEventLoop()

    def plan_ready(plan: object) -> None:
        previews.append(preview_lines(plan))
        QTimer.singleShot(0, lambda: controller.confirm_plan(True))

    def finished(report: object) -> None:
        reports.append(report)
        loop.quit()

    controller.plan_ready.connect(plan_ready)
    controller.finished.connect(finished)
    if isinstance(controller, SyncController):  # a conflict keeps the local file
        controller.conflict_needed.connect(
            lambda _item: QTimer.singleShot(0, lambda: controller.resolve(Decision.SKIP))
        )
    QTimer.singleShot(RUN_TIMEOUT_MS, loop.quit)
    controller.start(request.folder, request.endpoint)
    loop.exec()
    if not reports:
        raise RuntimeError("the run did not end")
    report = reports[0]
    del app
    return {
        "status": str(report.status),  # type: ignore[attr-defined]
        "transferred": sorted(report.transferred),  # type: ignore[attr-defined]
        "existing": sorted(getattr(report, "existing", [])),
        "error": report.error,  # type: ignore[attr-defined]
        "auth_failed": report.auth_failed,  # type: ignore[attr-defined]
        "message": report.message,  # type: ignore[attr-defined]
        "headline": report.headline,  # type: ignore[attr-defined]
        "details": report.details,  # type: ignore[attr-defined]
        "preview": previews[0] if previews else [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--language", required=True, choices=i18n.LANGUAGES)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--step", required=True, choices=["pull", "push"])
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--password", default=None)
    args = parser.parse_args(argv)

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    i18n.install(args.language)  # before the modules with texts are imported
    heard = Heard()
    logging.getLogger().addHandler(heard)
    logging.getLogger().setLevel(logging.DEBUG)
    result = run(args)
    result["log"] = heard.lines
    print(json.dumps(result, ensure_ascii=False), flush=True)
    sys.stderr.flush()
    os._exit(0)  # no interpreter teardown with Qt threads alive (as the probe)


if __name__ == "__main__":
    sys.exit(main())
