"""Spec 61 R2: ``paths.data``, the folder of Lain's own data (QSettings, lock, fallback of roots)."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from qe_studio.core.appdirs import (
    data_dir,
    data_dir_differs,
    default_data_dir,
    lock_path,
    set_data_dir,
    settings_file,
)
from qe_studio.core.config import load_config, parse_config
from qe_studio.core.project_data import FALLBACK_DIR, GRIDS_FILE, StoreFile, fallback_folder
from qe_studio.ui.app import open_settings
from qe_studio.ui.restart_notice import restart_notices

AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
RESTART = "A pasta de dados muda ao reiniciar o Lain."


def ini(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_set_data_dir_moves_lock_and_fallback(tmp_path):
    default = default_data_dir()
    assert data_dir() == default and settings_file() is None
    folder = tmp_path / "portable" / "data"
    assert set_data_dir(folder) is None
    assert folder.is_dir()  # made at startup, so the lock and the QSettings can be written
    assert data_dir() == folder
    assert lock_path() == folder / "lain.lock"
    assert settings_file() == folder / "settings.ini"
    root = tmp_path / "root"
    assert fallback_folder(root).parent == folder / FALLBACK_DIR
    store = StoreFile(GRIDS_FILE, None)
    assert store.path == folder / GRIDS_FILE  # before there is a root
    root.mkdir()
    assert store.follow(root)
    assert store.legacy == default / GRIDS_FILE  # the files from before spec 48 stay there

    assert set_data_dir(None) is None
    assert data_dir() == default and settings_file() is None
    assert lock_path() == default / "lain.lock"


def _a_file(tmp_path: Path) -> tuple[Path, Path | None]:
    path = tmp_path / "a-file"
    path.write_text("not a folder", encoding="utf-8")
    return path, None


def _read_only(tmp_path: Path) -> tuple[Path, Path | None]:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    return locked, locked


def _inside_read_only(tmp_path: Path) -> tuple[Path, Path | None]:
    locked, _ = _read_only(tmp_path)
    return locked / "data", locked


@pytest.mark.parametrize(
    ("make", "error"),
    [
        (_a_file, "não é uma pasta"),
        pytest.param(
            _read_only, "não é gravável", marks=pytest.mark.skipif(AS_ROOT, reason="root writes")
        ),
        # The system's message (its language follows the locale Qt set): only the form is checked.
        pytest.param(
            _inside_read_only, None, marks=pytest.mark.skipif(AS_ROOT, reason="root writes")
        ),
    ],
)
def test_unusable_data_dir_falls_back_with_a_warning(tmp_path, make, error):
    folder, locked = make(tmp_path)
    try:
        warning = set_data_dir(folder)
    finally:
        if locked is not None:
            locked.chmod(0o755)
    assert warning is not None
    start = f"A pasta de dados {folder} não pode ser usada ("
    end = f"); usando {default_data_dir()}."
    assert warning.startswith(start) and warning.endswith(end)
    if error is not None:
        assert warning == f"{start}{error}{end}"
    assert data_dir() == default_data_dir() and settings_file() is None
    assert not data_dir_differs(folder)  # what was asked for: reloading it does not nag


def test_settings_are_copied_once(tmp_path, caplog):
    legacy = ini(tmp_path / "QE Studio.conf")
    legacy.setValue("ui/theme", "light")
    legacy.setValue("files/last_folder", "/somewhere")
    legacy.sync()
    target = tmp_path / "data" / "settings.ini"
    with caplog.at_level(logging.INFO, logger="qe_studio"):
        settings = open_settings(target, legacy)
    assert settings.value("ui/theme") == "light"
    assert settings.value("files/last_folder") == "/somewhere"
    assert f"copied from {legacy.fileName()} to {target}" in caplog.text
    settings.setValue("ui/theme", "dark")
    settings.sync()

    again = open_settings(target, legacy)
    assert again.value("ui/theme") == "dark"  # a key changed afterwards is not overwritten
    assert legacy.value("ui/theme") == "light"  # the old file is left as it is
    assert sorted(legacy.allKeys()) == ["files/last_folder", "ui/theme"]


def test_nothing_to_copy_leaves_the_new_settings_empty(tmp_path):
    settings = open_settings(tmp_path / "settings.ini", ini(tmp_path / "empty.conf"))
    assert settings.allKeys() == []


def test_copying_the_folder_takes_the_settings(tmp_path):
    original = tmp_path / "lain"
    original.mkdir()
    (original / "config.yaml").write_text("paths:\n  data: data\n", encoding="utf-8")
    nothing = ini(tmp_path / "system.conf")  # the system's QSettings: empty here

    def start(folder: Path) -> QSettings:
        loaded = load_config(folder / "config.yaml", environ={}, cwd=tmp_path)
        assert set_data_dir(loaded.config.paths.data) is None
        return open_settings(settings_file(), nothing)

    first = start(original)
    assert Path(first.fileName()) == original / "data" / "settings.ini"
    first.setValue("ui/theme", "light")
    first.sync()
    copy = tmp_path / "elsewhere" / "lain"
    shutil.copytree(original, copy)
    first.setValue("ui/theme", "dark")  # the original changes after the copy
    first.sync()

    moved = start(copy)
    assert Path(moved.fileName()) == copy / "data" / "settings.ini"
    assert moved.value("ui/theme") == "light"
    assert lock_path() == copy / "data" / "lain.lock"


def test_reload_with_another_data_dir_tells_to_restart(tmp_path):
    here = tmp_path / "here"
    assert set_data_dir(here) is None
    assert restart_notices(parse_config({"paths": {"data": str(here)}})) == ""
    assert restart_notices(parse_config({"paths": {"data": str(tmp_path / "there")}})) == RESTART
    assert restart_notices(parse_config({})) == RESTART  # back to the system's folder
    assert data_dir() == here  # the session keeps the folder in use


def test_a_reload_keeps_the_data_dir_of_the_session(main_window, tmp_path, monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        main_window.toast, "show_message", lambda text, *rest, **kw: shown.append(text)
    )
    path = tmp_path / "c.yaml"
    root = main_window.config.paths.local_root
    path.write_text(f"paths:\n  local_root: {root}\n  data: portable\n", encoding="utf-8")
    main_window.load_config_file(path)
    assert shown == [RESTART]
    assert main_window.config.paths.data == tmp_path / "portable"
    assert data_dir() == default_data_dir() and not (tmp_path / "portable").exists()

    shown.clear()
    path.write_text(f"paths:\n  local_root: {root}\n", encoding="utf-8")
    main_window.load_config_file(path)
    assert shown == []
