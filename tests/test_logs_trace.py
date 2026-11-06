"""What the log tells (spec 90): the session, what the user asked for, what changed on disk and the
errors that would get lost.

``caplog`` hears the records, whatever the file does: the file itself is ``test_logs.py`` and
``test_logs_privacy.py``. A native crash, and whatever needs ``faulthandler`` free (pytest holds it
here), runs in a process of its own.
"""

import logging
import os
import subprocess
import sys
import textwrap
import threading
import warnings
from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QDialog, QMainWindow, QMenu

from qe_studio import __version__
from qe_studio.core.app import logs
from qe_studio.core.appdirs import atomic_write_text, set_data_dir
from qe_studio.core.config import ClusterConfig, LoadedConfig, parse_config
from qe_studio.core.sync.monitor import ConnectionMonitor
from qe_studio.ui.actions import build_menus
from qe_studio.ui.dialogs import cluster_action
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.files.detection_service import DetectionService
from qe_studio.ui.widgets.shell.workspace_tabs import add_action

from calc_dialog_helpers import to_files
from remote_helpers import REMOTE, FakeListing, entries, remote_window, turn_on

log = logging.getLogger("qe_studio.test")


@pytest.fixture
def info(caplog):
    """The level of a session with the default ``log.level``."""
    caplog.set_level(logging.INFO, logger="qe_studio")
    return caplog


@pytest.fixture
def debug(caplog):
    caplog.set_level(logging.DEBUG, logger="qe_studio")
    return caplog


# -- the start and the end of a session (R2) ------------------------------------------------------
def test_the_session_lines_say_what_a_bug_report_needs(tmp_path):
    set_data_dir(tmp_path)
    config = parse_config(
        {
            "paths": {"local_root": "/runs", "remote_root": "/scratch/ana"},
            "cluster": {"host": "hpc.test", "port": 2222, "user": "ana", "multiplex": False},
            "log": {"level": "debug", "max_size_mb": 7},
        }
    )
    lines = logs.session_lines(LoadedConfig(config, Path("/etc/c.yaml")), "/x/settings.ini")
    assert all(line.startswith("session: ") for line in lines)
    text = "\n".join(lines)
    assert f"session: Lain {__version__} pid={os.getpid()} platform=" in text
    assert "language=" in text
    assert f"session: config=/etc/c.yaml data={tmp_path} settings=/x/settings.ini" in text
    assert "session: local_root=/runs remote_root=/scratch/ana" in text
    assert "session: cluster=ana@hpc.test:2222 auth=key multiplex=False" in text
    assert f"session: log={tmp_path / 'lain.log'} level=debug limit=7 MB" in text


def test_the_session_lines_with_no_cluster_and_no_config(tmp_path):
    set_data_dir(tmp_path)
    text = "\n".join(logs.session_lines(LoadedConfig(parse_config({}), None), "s.ini"))
    assert "session: config=none " in text and "session: cluster=not configured" in text


def test_a_reload_logs_the_config_and_its_warnings(main_window, tmp_path, info):
    root = main_window.config.paths.local_root
    config = tmp_path / "c.yaml"
    config.write_text(f"paths:\n  local_root: {root}\n", encoding="utf-8")
    main_window.load_config_file(config)
    assert f"session: config reloaded from {config}" in info.text
    assert f"session: config={config} " in info.text
    assert f"session: local_root={root} " in info.text
    warned = [r.getMessage() for r in info.records if r.levelno == logging.WARNING]
    assert any("Cluster não configurado" in message for message in warned)


# -- what the user asked for (R3) -----------------------------------------------------------------
class _AnySlot:
    """Whatever slot ``ACTIONS`` names: ``window.a.b`` is this too, and calling it logs a line."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __call__(self, *_args):
        log.info("the slot ran")


class _Window(QMainWindow):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _AnySlot()


def test_a_menu_action_is_traced_before_its_slot(qtbot, main_window, info):
    window = _Window()
    qtbot.addWidget(window)
    build_menus(window)["files.refresh"].trigger()
    assert [r.getMessage() for r in info.records] == ["action: files.refresh", "the slot ran"]
    info.clear()
    main_window._actions["files.refresh"].trigger()
    assert "action: files.refresh" in info.text


def test_a_context_menu_item_is_traced(qtbot, info):
    menu = QMenu()
    qtbot.addWidget(menu)
    chosen = []
    add_action(menu, "Renomear", lambda: chosen.append(True))
    menu.actions()[0].trigger()
    assert chosen == [True] and "menu: Renomear" in info.text


def _dialog_answering(code):
    class Answered:
        def __init__(self, *_args):
            pass

        def exec(self):
            return code

        def deleteLater(self):
            pass

    return Answered


@pytest.mark.parametrize(
    ("code", "accepted"),
    [(QDialog.DialogCode.Accepted, True), (QDialog.DialogCode.Rejected, False)],
)
def test_the_cluster_confirmations_are_traced(monkeypatch, info, code, accepted):
    for name in ("SubmitDialog", "SameNameDialog", "CancelDialog", "TrashDialog"):
        monkeypatch.setattr(cluster_action, name, _dialog_answering(code))
    assert cluster_action.ask_submit(None, None, "") is accepted
    assert cluster_action.ask_same_name(None, "", ()) is accepted
    assert cluster_action.ask_cancel(None, (), "", "", "") is accepted
    assert cluster_action.ask_trash(None, None, "") is accepted
    assert [r.getMessage() for r in info.records] == [
        f"confirm: {word} accepted={accepted}"
        for word in ("submit", "same_name", "cancel", "trash")
    ]


def test_turning_the_cluster_mode_on_that_is_refused_leaves_no_line(main_window, info):
    main_window.remote.toggle()  # no cluster in this config
    assert not main_window.remote.active and "cluster: mode" not in info.text


def test_the_cluster_mode_is_traced_when_it_changes(
    qtbot, window_factory, demo_project, monkeypatch, info
):
    fake = FakeListing({REMOTE: entries("01_relax")})
    window = remote_window(window_factory, demo_project, monkeypatch, fake)
    turn_on(qtbot, window)
    assert "cluster: mode on" in info.text and "cluster: mode off" not in info.text
    window.remote.set_active(False)
    assert "cluster: mode off" in info.text


# -- what changed on disk (R4) --------------------------------------------------------------------
def test_plot_and_export_leave_a_trace(qtbot, main_window, demo_project, info):
    folder = demo_project / "03_bands"
    signals = [main_window.plot_ready, main_window.export_finished]
    with qtbot.waitSignals(signals, timeout=20_000):
        main_window.generate_plot_for(folder, auto_export=True)
    assert f"plot: bands {folder} in " in info.text
    line = next(r.getMessage() for r in info.records if r.getMessage().startswith("export: "))
    assert str(folder / "plots") in line and "PosixPath" not in line


def test_a_rename_leaves_a_trace(main_window, demo_project, monkeypatch, info):
    monkeypatch.setattr(
        "qe_studio.ui.files.rename_controller.ask_rename", lambda parent, path: "04_dos"
    )
    main_window.rename_path(demo_project / "04_pdos")
    assert f"file: renamed {demo_project / '04_pdos'} -> {demo_project / '04_dos'}" in info.text


def test_a_created_calculation_leaves_a_trace(qtbot, main_window, demo_project, monkeypatch, info):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)
    main_window.activity.new_calc.click()
    dialog = main_window.calc_create.dialog
    assert dialog is not None
    to_files(qtbot, dialog, "pdos", location=demo_project)
    with qtbot.waitSignal(main_window.calc_create.created, timeout=10_000) as blocker:
        dialog.create_button.click()
    created = blocker.args[0]
    assert f"file: calculation created {created.folder}: " in info.text
    line = next(r.getMessage() for r in info.records if "calculation created" in r.getMessage())
    assert created.files[0].name in line
    if not sip.isdeleted(dialog):
        dialog.close()


def test_a_data_file_write_is_traced_at_debug(tmp_path, debug):
    target = tmp_path / "dados.json"
    atomic_write_text(target, "conteúdo que não vai ao log")
    assert f"file: wrote {target}" in debug.text and "conteúdo" not in debug.text
    assert [r.levelno for r in debug.records] == [logging.DEBUG]


# -- the cluster's state (R5.5) -------------------------------------------------------------------
def test_the_cluster_state_is_traced_only_when_it_changes(qtbot, info):
    monitor = ConnectionMonitor(ClusterConfig(host="hpc.test", user="ana"), enabled=True)
    monitor.report(True)
    monitor.report(True)
    monitor.report(False)
    assert [r.getMessage() for r in info.records] == [
        "cluster: state unknown -> online",
        "cluster: state online -> offline",
    ]


# -- what only DEBUG hears (R6) -------------------------------------------------------------------
def test_what_the_user_was_told_is_traced(main_window, caplog):
    caplog.set_level(logging.INFO, logger="qe_studio")
    main_window.toast.show_message("aviso no toast", "warning")
    main_window.status.set_message("erro na barra", "error")
    main_window.toast.show_message("toast comum")
    main_window.status.set_message("barra comum")
    told = [r for r in caplog.records if r.getMessage().startswith("told: ")]
    assert [r.getMessage() for r in told] == ["told: aviso no toast", "told: erro na barra"]
    assert {r.levelno for r in told} == {logging.INFO}  # the cause has a line of its own

    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="qe_studio")
    main_window.toast.show_message("toast em debug")
    main_window.status.set_message("barra em debug")
    assert "told: toast em debug" in caplog.text and "told: barra em debug" in caplog.text

    caplog.clear()
    main_window.status.set_message("")  # the timer clearing the bar
    assert "told: " not in caplog.text


def test_a_detection_is_traced_at_debug(qtbot, demo_project, debug):
    service = DetectionService()
    folder = demo_project / "03_bands"
    with qtbot.waitSignal(service.detected, timeout=10_000):
        assert service.results(folder) is None
    assert f"detection: {folder}: ['bands']" in debug.text
    assert service.shutdown()


def test_a_folder_and_a_tab_are_traced_at_debug(main_window, demo_project, debug):
    folder = demo_project / "02_scf"
    main_window.navigation.visited(folder)
    assert f"folder: {folder}" in debug.text
    main_window.workspace.open_file(folder / "scf.out", "text")
    assert f"tab: {folder / 'scf.out'} (text)" in debug.text


# -- the errors that get lost (R7) ----------------------------------------------------------------
def test_an_exception_in_a_thread_reaches_the_log(log_session, caplog):
    before = threading.excepthook
    log_session.start()

    def boom():
        raise RuntimeError("a thread died")

    thread = threading.Thread(target=boom, name="lain-test-thread")
    thread.start()
    thread.join()
    assert "thread lain-test-thread failed" in caplog.text and "a thread died" in caplog.text
    log_session.stop()
    assert threading.excepthook is before


def test_a_python_warning_reaches_the_log(log_session, caplog):
    before = warnings.showwarning
    log_session.start()
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn("a warning of a library", UserWarning, stacklevel=1)
    assert "a warning of a library" in caplog.text
    log_session.stop()
    assert warnings.showwarning is before


SESSION = """
    import faulthandler, sys
    from pathlib import Path
    from qe_studio.core.app import logs
    from qe_studio.core.appdirs import crash_path, set_data_dir
    from qe_studio.core.config import LogConfig

    set_data_dir(Path(sys.argv[1]))
"""
CRASHES = """
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # a crash on purpose leaves no core file
    logs.start()
    logs.apply_config(LogConfig())
    faulthandler._sigsegv()
"""
STARTS = """
    logs.start()
    logs.apply_config(LogConfig())
    logs.stop()
"""
FOLLOWS_THE_LOG = """
    logs.start()
    states = [faulthandler.is_enabled()]
    logs.apply_config(LogConfig(enabled=False))
    states.append(faulthandler.is_enabled())
    missing = not crash_path().exists()
    logs.apply_config(LogConfig())
    states.append(faulthandler.is_enabled())
    logs.apply_config(LogConfig(enabled=False))
    states.append(faulthandler.is_enabled())
    logs.apply_config(LogConfig())
    logs.stop()
    states.append(faulthandler.is_enabled())
    print(states, missing)
"""
ALREADY_ON = """
    logs.start()
    logs.apply_config(LogConfig())
    logs.stop()
    print(faulthandler.is_enabled())
"""


def _session(folder: Path, body: str, *python: str) -> subprocess.CompletedProcess:
    code = textwrap.dedent(SESSION) + textwrap.dedent(body)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONFAULTHANDLER"}
    command = [sys.executable, *python, "-c", code, str(folder)]
    return subprocess.run(command, capture_output=True, text=True, timeout=55, env=env)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="needs SIGSEGV and resource")
def test_a_native_crash_appears_in_the_next_session(tmp_path):
    done = _session(tmp_path, CRASHES)
    assert done.returncode < 0, done.stderr  # killed by the signal, after the dump
    assert "Segmentation fault" in _read(tmp_path / "lain.crash")
    assert "Segmentation fault" not in _read(tmp_path / "lain.log")

    done = _session(tmp_path, STARTS)
    assert done.returncode == 0, done.stderr
    assert "session: the previous session crashed:" in _read(tmp_path / "lain.log")
    assert "Segmentation fault" in _read(tmp_path / "lain.log")
    assert (tmp_path / "lain.crash").stat().st_size == 0

    done = _session(tmp_path, STARTS)  # told once
    assert done.returncode == 0, done.stderr
    assert _read(tmp_path / "lain.log").count("the previous session crashed") == 1


def test_with_the_log_off_there_is_no_crash_file(tmp_path):
    done = _session(tmp_path, FOLLOWS_THE_LOG)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[False, False, True, False, False] True"


def test_a_crash_file_that_cannot_be_opened_does_not_stop_the_session(tmp_path):
    (tmp_path / "lain.crash").mkdir()
    done = _session(tmp_path, STARTS)
    assert done.returncode == 0, done.stderr
    assert "session: no crash file" in _read(tmp_path / "lain.log")


def test_a_faulthandler_someone_else_turned_on_stays_theirs(tmp_path):
    (tmp_path / "lain.crash").write_text("Fatal Python error: an old one\n", encoding="utf-8")
    done = _session(tmp_path, ALREADY_ON, "-X", "faulthandler")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "True"  # neither moved nor turned off by ``stop``
    assert "an old one" in _read(tmp_path / "lain.log")  # the last crash is told all the same
    assert (tmp_path / "lain.crash").stat().st_size == 0
