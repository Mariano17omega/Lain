"""``SyncCoordinator`` without the main window (spec 15 R4.7): refusals, the session password, the
final report and the cluster label. Real pulls are in ``test_sync_ui.py``."""

from pathlib import Path

import pytest
from PyQt6.QtGui import QAction
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
    ("status", "box", "message", "notice"),
    [
        (SyncStatus.DONE, None, ("0 arquivo(s) baixado(s).", "info"), "success"),
        (
            SyncStatus.UP_TO_DATE,
            None,
            ("Pasta já sincronizada: nada a transferir.", "info"),
            "info",
        ),
        (SyncStatus.LOCAL_NEWER, "warning", None, None),
        (SyncStatus.CANCELLED, None, ("Sincronização cancelada.", "warning"), None),
        (SyncStatus.FAILED, "critical", None, None),
    ],
)
def test_the_report_is_shown_after_the_folder_is_refreshed(
    qtbot, tmp_path, boxes, status, box, message, notice
):
    """A pull that went well ends with a toast and the footer, never a message box (spec 17 R3)."""
    coordinator = make(qtbot, tmp_path, auth="key")
    events, notices = [], []
    coordinator.synced.connect(lambda folder: events.append(("synced", folder, len(boxes))))
    coordinator.message.connect(lambda text, level, _ms: events.append(("message", text, level)))
    coordinator.notice.connect(lambda text, level, details: notices.append((text, level, details)))
    with qtbot.waitSignal(coordinator.finished) as blocker:
        coordinator._on_finished(report(status, tmp_path, error="boom"))
    assert blocker.args[0].status is status
    assert events[0] == ("synced", tmp_path, 0)  # refreshed before any message box
    assert [b[0] for b in boxes] == ([box] if box else [])
    assert [e[1:] for e in events[1:]] == ([message] if message else [])
    assert [n[1] for n in notices] == ([notice] if notice else [])
    if notices:
        text, _level, details = notices[0]
        assert text == message[0] and details.startswith(text) and "hpc.example" in details


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


def test_the_entry_points_pull_the_selection_or_the_whole_project(qtbot, tmp_path, boxes):
    selected, started = tmp_path / "03_bands", []
    data = {"paths": {"local_root": str(tmp_path)}}
    parent = QWidget()
    qtbot.addWidget(parent)
    coordinator = SyncCoordinator(
        parse_config(data), ThemeManager("dark"), parent, parent, current_folder=lambda: selected
    )
    coordinator.start = started.append  # type: ignore[method-assign]
    coordinator.start_selected()
    coordinator.start_project()
    assert started == [selected, tmp_path]  # the root, whatever is selected


def test_a_pull_refreshes_what_changed(qtbot, tmp_path, boxes):
    refreshed = []
    parent = QWidget()
    qtbot.addWidget(parent)
    coordinator = SyncCoordinator(
        parse_config({"paths": {"local_root": str(tmp_path)}}),
        ThemeManager("dark"),
        parent,
        parent,
        refresh=refreshed.append,
    )
    coordinator.synced.emit(tmp_path / "03_bands")
    assert refreshed == [tmp_path / "03_bands"]
    SyncCoordinator(
        parse_config({"paths": {"local_root": str(tmp_path)}}), ThemeManager("dark"), parent
    ).synced.emit(tmp_path)  # no refresh given: nothing to do, nothing raised


def test_shutdown_without_a_run_is_in_time(qtbot, tmp_path, boxes):
    assert make(qtbot, tmp_path).shutdown(100) is True


def test_a_folder_change_resolves_one_path(qtbot, tmp_path, monkeypatch):
    """Spec 27-8 R3.1: the root and the scope of the whole project are kept; only the folder is
    resolved, for the three actions at once."""
    (tmp_path / "ilita" / "03_bands").mkdir(parents=True)
    coordinator = make(qtbot, tmp_path, auth="key")
    actions = {
        key: QAction(key, coordinator) for key in ("sync.start", "sync.project", "sync.push")
    }
    coordinator.bind_actions(actions)

    resolves = []
    original = Path.resolve
    monkeypatch.setattr(
        Path, "resolve", lambda self, *a, **k: resolves.append(self) or original(self, *a, **k)
    )
    coordinator.show_scope(tmp_path / "ilita" / "03_bands")
    assert len(resolves) == 1
    assert actions["sync.start"].text() == "Sincronizar ilita/03_bands"
    assert actions["sync.push"].text() == "Enviar ilita/03_bands ao cluster…"
    assert actions["sync.push"].isEnabled()
    assert "tudo" in actions["sync.project"].toolTip()

    resolves.clear()
    coordinator.show_scope(tmp_path)
    assert len(resolves) == 1
    assert actions["sync.start"].text() == "Sincronizar tudo"
    assert not actions["sync.push"].isEnabled()  # the root is never pushed
    resolves.clear()
    coordinator.show_scope(tmp_path / "ilita")
    assert len(resolves) == 1
    assert not actions["sync.push"].isEnabled()  # nor a project (spec 31 R5.2)
    resolves.clear()
    assert coordinator.push_state(tmp_path / "ilita" / "03_bands") == ""
    assert len(resolves) == 2  # prepare_sync's and prepare_push's own; the root is not resolved
