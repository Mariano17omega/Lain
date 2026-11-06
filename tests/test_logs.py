"""The log file (spec 89): where it lives, its limit, and turning it on and off.

The tests call ``logs.start`` through the ``log_session`` fixture, which puts the process's logging
back. What needs the real start-up order, or two writers, runs in a process of its own.
"""

import logging
import os
import subprocess
import sys
import textwrap
from logging.handlers import RotatingFileHandler
from pathlib import Path

from qe_studio.core.appdirs import cache_dir, default_data_dir, log_path, set_data_dir
from qe_studio.core.config import LogConfig

log = logging.getLogger("qe_studio.test")


def _file_handlers():
    return [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]


def _on_disk(folder: Path) -> dict[str, int]:
    return {p.name: p.stat().st_size for p in folder.iterdir() if p.name.startswith("lain.log")}


# -- where it lives (R2) ------------------------------------------------------------------------
def test_the_log_goes_to_the_data_folder(log_session, tmp_path):
    assert set_data_dir(tmp_path) is None
    log_session.start()
    assert log_session.apply_config(LogConfig()) is None
    log.info("aqui")
    assert "aqui" in (tmp_path / "lain.log").read_text(encoding="utf-8")
    assert not list(cache_dir().glob("*.log*"))


def test_without_paths_data_it_goes_to_the_default_data_folder(log_session):
    log_session.start()
    log_session.apply_config(LogConfig())
    log.info("aqui")
    assert log_path() == default_data_dir() / "lain.log"
    assert "aqui" in log_path().read_text(encoding="utf-8")


def test_an_unusable_data_folder_takes_the_log_to_the_default(log_session, tmp_path):
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("x", encoding="utf-8")
    assert set_data_dir(not_a_folder) is not None
    log_session.start()
    assert log_session.apply_config(LogConfig()) is None
    assert (default_data_dir() / "lain.log").is_file()


def test_what_was_logged_before_the_config_reaches_the_file(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log.info("cedo")
    assert not (tmp_path / "lain.log").exists()  # the folder is not known yet
    log_session.apply_config(LogConfig())
    log.info("depois")
    lines = (tmp_path / "lain.log").read_text(encoding="utf-8").splitlines()
    assert [line.rsplit(": ", 1)[1] for line in lines] == ["cedo", "depois"]


def test_what_was_logged_before_the_config_is_dropped_when_it_is_off(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log.info("cedo")
    log_session.apply_config(LogConfig(enabled=False))
    log_session.apply_config(LogConfig())
    log.info("depois")
    text = (tmp_path / "lain.log").read_text(encoding="utf-8")
    assert "depois" in text and "cedo" not in text


def test_a_folder_that_cannot_hold_the_log_warns(log_session, tmp_path):
    set_data_dir(tmp_path)
    (tmp_path / "lain.log").mkdir()
    log_session.start()
    warning = log_session.apply_config(LogConfig())
    assert warning is not None and str(tmp_path / "lain.log") in warning
    assert log_session.log_is_off()
    log.warning("sem arquivo, sem erro")
    assert logging.getLogger("qe_studio").level == logging.WARNING  # only the terminal listens


def test_each_line_says_which_process_and_thread(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    log.info("aqui")
    line = (tmp_path / "lain.log").read_text(encoding="utf-8")
    assert f" INFO [{os.getpid()} MainThread] qe_studio.test: aqui" in line


def test_third_party_debug_stays_out(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start(verbose=True)
    log_session.apply_config(LogConfig(level="debug"))
    library = logging.getLogger("matplotlib")
    library.debug("uma fonte")
    library.warning("um aviso")
    log.debug("do lain")
    text = (tmp_path / "lain.log").read_text(encoding="utf-8")
    assert "uma fonte" not in text
    assert "um aviso" in text and "do lain" in text


def test_apply_config_before_start_does_nothing(log_session, tmp_path):
    """A window built without ``main`` reloads its config: the process's logging stays as it was."""
    set_data_dir(tmp_path)
    before = list(logging.getLogger().handlers), logging.getLogger("qe_studio").level
    assert log_session.apply_config(LogConfig(enabled=False)) is None
    assert not log_session.log_is_off()
    assert (list(logging.getLogger().handlers), logging.getLogger("qe_studio").level) == before
    assert not (tmp_path / "lain.log").exists()


# -- the real start-up order (R2.3, R2.6) ---------------------------------------------------------
MAIN = textwrap.dedent(
    """
    import logging, os, sys
    from PyQt6.QtWidgets import QApplication, QMessageBox

    def run(*_args):
        logging.getLogger("qe_studio").info("the marker")
        return 0

    QApplication.exec = run
    QMessageBox.critical = staticmethod(lambda *_args: 0)
    from qe_studio.ui.app import main

    code = main(["--config", sys.argv[1]])
    logging.shutdown()
    sys.stdout.flush()
    os._exit(code)  # no teardown of a window nobody closed
    """
)


def _main(config: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", MAIN, str(config)], capture_output=True, text=True, timeout=55
    )


def test_main_writes_the_log_in_paths_data(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(f"paths:\n  local_root: {root}\n  data: data\n", encoding="utf-8")
    done = _main(config)
    assert done.returncode == 0, done.stderr
    assert "the marker" in (tmp_path / "data" / "lain.log").read_text(encoding="utf-8")
    assert not list(cache_dir().glob("*.log*"))


def test_main_writes_the_session_lines(tmp_path):
    """The wiring of spec 90 R2 in the real ``main``, from the first line to the last."""
    root = tmp_path / "root"
    root.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(f"paths:\n  local_root: {root}\n  data: data\n", encoding="utf-8")
    done = _main(config)
    assert done.returncode == 0, done.stderr
    text = (tmp_path / "data" / "lain.log").read_text(encoding="utf-8")
    words = ["session: Lain ", f"session: config={config} ", "session: qt=", "the marker"]
    positions = [text.index(word) for word in words]
    assert positions == sorted(positions)
    assert f"session: local_root={root} " in text and "session: cluster=not configured" in text
    assert "session: python=" in text and "ase=" in text  # from a worker, drained by ``finish``
    assert "session: end code=0 after " in text


def test_an_invalid_config_leaves_no_log_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("paths:\n  data: data\nlog:\n  level: nope\n", encoding="utf-8")
    done = _main(config)
    assert done.returncode == 2, done.stderr
    assert not (tmp_path / "data").exists()
    assert not (default_data_dir() / "lain.log").exists()
    assert not list(cache_dir().glob("*.log*"))


# -- the limit (R3) -------------------------------------------------------------------------------
def test_the_log_never_passes_its_limit(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig(max_size_mb=1))
    line = "x" * 200
    for _ in range(3_000_000 // len(line)):
        log.info(line)
    sizes = _on_disk(tmp_path)
    assert set(sizes) == {"lain.log", "lain.log.1"}
    assert sum(sizes.values()) <= 1_000_000


def test_one_huge_record_is_cut(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    log.info("COMEÇO" + "x" * 5_000_000 + "FIM")
    path = tmp_path / "lain.log"
    assert path.stat().st_size <= 17_000
    text = path.read_text(encoding="utf-8")
    assert "COMEÇO" in text and text.rstrip().endswith("FIM") and "characters cut] …" in text


def test_a_cut_record_keeps_the_traceback_end(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    try:
        raise ValueError("o fim do traceback")
    except ValueError:
        log.exception("a" * 100_000)
    assert "ValueError: o fim do traceback" in (tmp_path / "lain.log").read_text(encoding="utf-8")


def test_a_name_with_undecodable_bytes_is_written(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    log.info("copiado: %s", b"caf\xe9.in".decode("utf-8", "surrogateescape"))
    assert r"caf\udce9.in" in (tmp_path / "lain.log").read_text(encoding="utf-8")


# -- on, off and reload (R4) ----------------------------------------------------------------------
def test_off_writes_nothing_and_keeps_what_exists(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig(enabled=False))
    log.error("sem arquivo")
    assert log_session.log_is_off()
    assert not (tmp_path / "lain.log").exists()

    (tmp_path / "lain.log").write_text("de antes\n", encoding="utf-8")
    log.error("sem arquivo")
    assert (tmp_path / "lain.log").read_text(encoding="utf-8") == "de antes\n"
    assert logging.getLogger("qe_studio").level == logging.WARNING


def test_the_terminal_shows_only_warnings_without_verbose(log_session, capfd):
    log_session.start()
    log_session.apply_config(LogConfig(enabled=False))
    log.info("baixo")
    log.warning("alto")
    err = capfd.readouterr().err
    assert "alto" in err and "baixo" not in err


def test_reload_turns_it_off_and_on(main_window, log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    config = tmp_path / "c.yaml"
    root = main_window.config.paths.local_root
    base = f"paths:\n  local_root: {root}\n  data: {tmp_path}\n"

    log.info("primeiro")
    config.write_text(base + "log:\n  enabled: false\n", encoding="utf-8")
    main_window.load_config_file(config)
    assert log_session.log_is_off()
    log.info("do meio")

    config.write_text(base + "log:\n  enabled: true\n", encoding="utf-8")
    main_window.reload_config()
    assert not log_session.log_is_off()
    log.info("depois")

    text = (tmp_path / "lain.log").read_text(encoding="utf-8")
    assert "primeiro" in text and "depois" in text and "do meio" not in text


def test_a_reload_applies_the_level_and_the_limit(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    log.debug("ainda não")
    [handler] = _file_handlers()
    log_session.apply_config(LogConfig(level="debug", max_size_mb=2))
    log.debug("agora sim")
    assert _file_handlers() == [handler]
    assert handler.maxBytes == 1_000_000
    text = (tmp_path / "lain.log").read_text(encoding="utf-8")
    assert "agora sim" in text and "ainda não" not in text


def test_the_same_settings_keep_the_file_open(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start()
    log_session.apply_config(LogConfig())
    [handler] = _file_handlers()
    stream = handler.stream
    log_session.apply_config(LogConfig())
    assert _file_handlers() == [handler]
    assert handler.stream is stream


def test_a_reload_tries_a_failed_file_again(log_session, tmp_path):
    set_data_dir(tmp_path)
    blocker = tmp_path / "lain.log"
    blocker.mkdir()
    log_session.start()
    assert log_session.apply_config(LogConfig()) is not None
    blocker.rmdir()
    assert log_session.apply_config(LogConfig()) is None
    assert not log_session.log_is_off() and blocker.is_file()


def test_verbose_wins_over_the_level(log_session, tmp_path):
    set_data_dir(tmp_path)
    log_session.start(verbose=True)
    log_session.apply_config(LogConfig(level="info"))
    log.debug("detalhe")
    assert "detalhe" in (tmp_path / "lain.log").read_text(encoding="utf-8")
    log_session.apply_config(LogConfig(enabled=False))
    assert logging.getLogger("qe_studio").level == logging.DEBUG


def test_start_twice_leaves_one_terminal(log_session):
    root = logging.getLogger()
    before = len(root.handlers)
    log_session.start()
    log_session.start()
    assert len(root.handlers) == before + 2  # the terminal and the memory, once each
    log_session.stop()
    assert len(root.handlers) == before


WRITER = textwrap.dedent(
    """
    import logging, sys
    from pathlib import Path
    from qe_studio.core.app import logs
    from qe_studio.core.appdirs import set_data_dir
    from qe_studio.core.config import LogConfig

    set_data_dir(Path(sys.argv[1]))
    logs.start()
    assert logs.apply_config(LogConfig(max_size_mb=1)) is None
    log = logging.getLogger("qe_studio")
    for i in range(15_000):
        log.info("%06d %s", i, "x" * 200)
    """
)


def test_a_second_process_on_the_same_log_stays_within_the_limit(tmp_path):
    writers = [
        subprocess.Popen(
            [sys.executable, "-c", WRITER, str(tmp_path)], stderr=subprocess.PIPE, text=True
        )
        for _ in range(2)
    ]
    errors = [writer.communicate(timeout=50)[1] for writer in writers]
    assert [writer.returncode for writer in writers] == [0, 0], errors
    assert not any("Logging error" in error for error in errors), errors
    sizes = _on_disk(tmp_path)
    assert set(sizes) == {"lain.log", "lain.log.1"}
    assert sum(sizes.values()) <= 1_000_000
