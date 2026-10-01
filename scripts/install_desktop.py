"""Install the Lain launcher and icons for the current user.

Nothing is installed by ``uv sync`` or by running the app: run this once if you want Lain in the
application menu with its icon (and a matching taskbar icon).

    uv run python scripts/install_desktop.py [--prefix DIR]

Files go under ``DIR`` (default ``$XDG_DATA_HOME``, i.e. ``~/.local/share``):

    DIR/applications/lain.desktop
    DIR/icons/hicolor/<N>x<N>/apps/lain.png

The launcher runs ``lain``, so install it first (``uv tool install --editable .``, see README).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_FILE = ROOT / "packaging" / "lain.desktop"
ICON_DIR = ROOT / "src" / "qe_studio" / "ui" / "resources" / "app"
ICON_NAME = re.compile(r"lain-(\d+)\.png")


def default_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def install(data_home: Path) -> list[Path]:
    """Copy the launcher and the icons under ``data_home``; return what was written."""
    written = []
    target = data_home / "applications" / DESKTOP_FILE.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DESKTOP_FILE, target)
    written.append(target)
    for png in sorted(ICON_DIR.glob("lain-*.png")):
        match = ICON_NAME.fullmatch(png.name)
        if match is None:
            continue
        size = match.group(1)
        icon = data_home / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "lain.png"
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(png, icon)
        written.append(icon)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the Lain launcher and icons.")
    parser.add_argument(
        "--prefix",
        type=Path,
        help="data directory to install into (default: $XDG_DATA_HOME or ~/.local/share)",
    )
    args = parser.parse_args(argv)
    if not DESKTOP_FILE.is_file():
        print(f"missing {DESKTOP_FILE}: run this from a source checkout", file=sys.stderr)
        return 1
    for path in install(args.prefix or default_data_home()):
        print(f"installed {path}")
    print(
        "If the icon or menu entry does not show up, log out and in, or run update-desktop-database."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
