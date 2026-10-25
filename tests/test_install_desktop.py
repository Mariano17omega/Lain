import configparser
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

from qe_studio.ui.app_identity import DESKTOP_FILE_NAME, icon_dir

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 32, 48, 64, 128, 256)


@pytest.fixture(scope="module")
def installer():
    spec = importlib.util.spec_from_file_location(
        "install_desktop", ROOT / "scripts" / "install_desktop.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_entry(path: Path) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # keep the case of keys
    parser.read(path, encoding="utf-8")
    return dict(parser["Desktop Entry"])


def test_desktop_entry_matches_the_app():
    entry = read_entry(ROOT / "packaging" / "lain.desktop")
    assert (ROOT / "packaging" / f"{DESKTOP_FILE_NAME}.desktop").is_file()
    assert entry["Type"] == "Application"
    assert entry["Name"] == "Lain" and entry["GenericName"] == "QE Studio"
    assert entry["Icon"] == "lain"
    assert entry["StartupWMClass"] == DESKTOP_FILE_NAME
    assert entry["Exec"].split()[0] == "lain"
    assert entry["Categories"] == "Science;Physics;Education;"


@pytest.mark.skipif(shutil.which("desktop-file-validate") is None, reason="desktop-file-utils")
def test_desktop_entry_validates():
    result = subprocess.run(
        ["desktop-file-validate", str(ROOT / "packaging" / "lain.desktop")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_install_into_a_prefix(installer, tmp_path, capsys):
    assert installer.main(["--prefix", str(tmp_path)]) == 0

    desktop = tmp_path / "applications" / "lain.desktop"
    assert desktop.read_text(encoding="utf-8") == installer.launcher_text()
    assert read_entry(desktop)["Path"] == str(ROOT)  # the menu starts where config.yaml is
    for size in SIZES:
        installed = tmp_path / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "lain.png"
        assert installed.read_bytes() == (icon_dir() / f"lain-{size}.png").read_bytes()
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1 + len(SIZES)
    assert str(desktop) in capsys.readouterr().out
    assert installer.main(["--prefix", str(tmp_path)]) == 0  # running it again just overwrites


def test_default_location_is_xdg_data_home(installer, tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "refresh_caches", lambda: [])  # never touch the real menu cache
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert installer.main([]) == 0
    assert (tmp_path / "data" / "applications" / "lain.desktop").is_file()
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    assert installer.default_data_home() == tmp_path / "home" / ".local" / "share"


def test_refresh_caches_only_for_the_real_default_location(installer, tmp_path, monkeypatch):
    """A ``--prefix`` install (tests, an alternate location) never rebuilds the menu's cache: the
    running desktop does not serve that prefix's files anyway."""
    calls = []
    monkeypatch.setattr(installer, "refresh_caches", lambda: calls.append(1) or [])

    assert installer.main(["--prefix", str(tmp_path)]) == 0
    assert calls == []

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert installer.main([]) == 0
    assert calls == [1]


def test_refresh_caches_runs_known_tools_and_ignores_missing_ones(installer, monkeypatch):
    ran = []
    monkeypatch.setattr(
        installer.shutil,
        "which",
        lambda name: "/usr/bin/" + name if name != "kbuildsycoca5" else None,
    )
    monkeypatch.setattr(
        installer.subprocess, "run", lambda command, **kwargs: ran.append(command) or None
    )

    assert installer.refresh_caches() == [
        "update-desktop-database",
        "kbuildsycoca6 --noincremental",
    ]
    assert [c[0] for c in ran] == ["update-desktop-database", "kbuildsycoca6"]
