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
    assert desktop.read_bytes() == (ROOT / "packaging" / "lain.desktop").read_bytes()
    for size in SIZES:
        installed = tmp_path / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "lain.png"
        assert installed.read_bytes() == (icon_dir() / f"lain-{size}.png").read_bytes()
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1 + len(SIZES)
    assert str(desktop) in capsys.readouterr().out
    assert installer.main(["--prefix", str(tmp_path)]) == 0  # running it again just overwrites


def test_default_location_is_xdg_data_home(installer, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert installer.main([]) == 0
    assert (tmp_path / "data" / "applications" / "lain.desktop").is_file()
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    assert installer.default_data_home() == tmp_path / "home" / ".local" / "share"
