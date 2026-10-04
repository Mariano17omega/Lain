"""``SyncCoordinator`` without the main window (spec 15 R4.7): refusals, the session password, the
final report and the cluster label. Real pulls are in ``test_sync_ui.py``."""

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QWidget

from qe_studio.core.config import parse_config
from qe_studio.core.sync.controller import SyncReport, SyncStatus
from qe_studio.core.sync.request import NOT_CONFIGURED
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui.sync_coordinator import SyncCoordinator
from qe_studio.ui.theme.manager import ThemeManager


@pytest.fixture
def boxes(monkeypatch):
    shown = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, kind, staticmethod(lambda *a, k=kind, **kw: shown.append((k, a[2])))
        )
    return shown


def make(qtbot, tmp_path, **cluster):
    data = {"paths": {"local_root": str(tmp_path)}}
    if cluster:
        data["paths"]["remote_root"] = "/scratch/me"
        data["cluster"] = {"host": "hpc.example", "user": "me", **cluster}
    parent = QWidget()
    qtbot.addWidget(parent)
    coordinator = SyncCoordinator(parse_config(data), ThemeManager("dark"), parent, parent)
    return coordinator


def test_not_configured_explains_and_starts_nothing(qtbot, tmp_path, boxes):
    coordinator = make(qtbot, tmp_path)
    labels = []
    coordinator.cluster_changed.connect(lambda label, state: labels.append((label, state)))
    coordinator.start_monitor()
    assert labels == [("cluster não configurado", "disabled")]
    coordinator.start(tmp_path)
    assert boxes == [("information", NOT_CONFIGURED)] and coordinator.controller is None


def test_a_folder_outside_the_project_is_a_warning(qtbot, tmp_path, boxes):
    coordinator = make(qtbot, tmp_path / "proj", auth="key")
    coordinator.start(tmp_path / "elsewhere")
    assert boxes and boxes[0][0] == "warning" and coordinator.controller is None


def test_the_password_is_asked_once_per_session(qtbot, tmp_path, boxes, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    coordinator = make(qtbot, tmp_path, auth="password", password_env="LAIN_NO_PW")
    asked, runs = [], []
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: asked.append(1) or ("pw", True))
    )
    monkeypatch.setattr(
        coordinator, "run", lambda folder, endpoint, password=None: runs.append(password)
    )
    coordinator.start(tmp_path)
    coordinator.start(tmp_path)
    assert runs == ["pw", "pw"] and len(asked) == 1


def test_a_cancelled_password_prompt_starts_nothing(qtbot, tmp_path, boxes, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    coordinator = make(qtbot, tmp_path, auth="password", password_env="LAIN_NO_PW")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    monkeypatch.setattr(coordinator, "run", lambda *a, **k: pytest.fail("started"))
    coordinator.start(tmp_path)


def report(status: SyncStatus, local: Path, **fields) -> SyncReport:
    return SyncReport(status, local, Endpoint("/scratch/me", "hpc.example", "me"), **fields)


@pytest.mark.parametrize(
    ("status", "box", "message"),
    [
        (SyncStatus.DONE, "information", ("0 arquivo(s) baixado(s).", "info")),
        (SyncStatus.LOCAL_NEWER, "warning", None),
        (SyncStatus.CANCELLED, None, ("Sincronização cancelada.", "warning")),
        (SyncStatus.FAILED, "critical", None),
    ],
)
def test_the_report_is_shown_after_the_folder_is_refreshed(
    qtbot, tmp_path, boxes, status, box, message
):
    coordinator = make(qtbot, tmp_path, auth="key")
    events = []
    coordinator.synced.connect(lambda folder: events.append(("synced", folder, len(boxes))))
    coordinator.message.connect(lambda text, level, _ms: events.append(("message", text, level)))
    with qtbot.waitSignal(coordinator.finished) as blocker:
        coordinator._on_finished(report(status, tmp_path, error="boom"))
    assert blocker.args[0].status is status
    assert events[0] == ("synced", tmp_path, 0)  # refreshed before any message box
    assert [b[0] for b in boxes] == ([box] if box else [])
    assert [e[1:] for e in events[1:]] == ([message] if message else [])


def test_an_authentication_failure_forgets_the_password(qtbot, tmp_path, boxes):
    coordinator = make(qtbot, tmp_path, auth="password", password_env="LAIN_NO_PW")
    coordinator._session_password = "wrong"
    coordinator._on_finished(report(SyncStatus.FAILED, tmp_path, error="Autenticação recusada"))
    assert coordinator._session_password is None


def test_a_new_config_replaces_the_monitor(qtbot, tmp_path, boxes):
    coordinator = make(qtbot, tmp_path)
    old = coordinator.monitor
    labels = []
    coordinator.cluster_changed.connect(lambda label, state: labels.append(label))
    data = {
        "paths": {"local_root": str(tmp_path), "remote_root": "/r"},
        "cluster": {"host": "127.0.0.1", "port": 9, "user": "u"},  # a probe is refused at once
    }
    coordinator.set_config(parse_config(data))
    assert coordinator.monitor is not old and labels[0] == "u@127.0.0.1"
    coordinator.shutdown()
