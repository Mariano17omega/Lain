"""One running app per data dir (spec 27-3 R4.3): ``acquire_instance_lock``."""

import os
import subprocess
import sys
import textwrap
import time

import pytest
from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QMessageBox

from qe_studio.ui import app as app_module
from qe_studio.ui.app import acquire_instance_lock, ask_open_anyway, claim_instance


@pytest.fixture
def lock_file(tmp_path):
    return tmp_path / "data" / "lain.lock"


def test_the_first_instance_gets_the_lock_and_the_second_does_not(lock_file):
    first = acquire_instance_lock(lock_file)
    assert first is not None and first.isLocked()
    assert acquire_instance_lock(lock_file) is None
    first.unlock()
    again = acquire_instance_lock(lock_file)
    assert again is not None and again.isLocked()
    again.unlock()


def test_a_lock_of_a_live_owner_is_not_taken_over_because_it_is_old(lock_file):
    """QLockFile calls a lock "stale" after 30 s by default, owner alive or not."""
    first = acquire_instance_lock(lock_file)
    assert first is not None
    hour_ago = time.time() - 3600
    os.utime(lock_file, (hour_ago, hour_ago))
    assert acquire_instance_lock(lock_file) is None
    first.unlock()


def test_a_lock_left_by_a_dead_process_is_recovered(lock_file):
    lock_file.parent.mkdir(parents=True)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                import os
                from PyQt6.QtCore import QLockFile
                lock = QLockFile({str(lock_file)!r})
                lock.setStaleLockTime(0)
                assert lock.tryLock(0)
                os._exit(0)  # a crash: the lock file stays, nobody unlocks it
                """
            ),
        ],
        capture_output=True,
        timeout=60,
    )
    assert child.returncode == 0, child.stderr
    assert lock_file.exists()
    recovered = acquire_instance_lock(lock_file)
    assert recovered is not None and recovered.isLocked()
    recovered.unlock()


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a folder one cannot write")
def test_an_unwritable_data_dir_does_not_bother_the_user(tmp_path, monkeypatch):
    locked = tmp_path / "ro"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        lock = acquire_instance_lock(locked / "data" / "lain.lock")
    finally:
        locked.chmod(0o700)
    assert isinstance(lock, QLockFile) and not lock.isLocked()  # not None: nobody else has it


@pytest.mark.parametrize(
    ("button", "expected"),
    [(QMessageBox.StandardButton.Yes, True), (QMessageBox.StandardButton.No, False)],
)
def test_the_question_of_a_second_instance(monkeypatch, button, expected):
    asked = []

    def question(parent, title, text, buttons, default):
        asked.append((text, default))
        return button

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    assert ask_open_anyway() is expected
    assert asked == [
        (
            "O Lain já está aberto com esta configuração. Abrir mesmo assim?",
            QMessageBox.StandardButton.No,
        )
    ]


@pytest.mark.parametrize(("answer", "proceeds"), [(True, True), (False, False)])
def test_a_second_instance_goes_on_without_a_lock_or_leaves(
    monkeypatch, lock_file, answer, proceeds, caplog
):
    holder = acquire_instance_lock(lock_file)
    assert holder is not None
    monkeypatch.setattr(app_module, "ask_open_anyway", lambda: answer)
    proceed, lock = claim_instance(lock_file)
    assert proceed is proceeds and lock is None  # the holder keeps the lock either way
    assert ("sem trava" in caplog.text) is answer
    assert holder.isLocked()
    holder.unlock()


def test_the_first_instance_is_not_asked_anything(monkeypatch, lock_file):
    monkeypatch.setattr(app_module, "ask_open_anyway", lambda: pytest.fail("asked"))
    proceed, lock = claim_instance(lock_file)
    assert proceed and lock is not None and lock.isLocked()
    lock.unlock()
