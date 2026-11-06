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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_FILE = ROOT / "packaging" / "lain.desktop"
ICON_DIR = ROOT / "src" / "qe_studio" / "ui" / "resources" / "app"
ICON_NAME = re.compile(r"lain-(\d+)\.png")
# Desktop environments cache parsed .desktop files (KDE's ksycoca; the GNOME/XDG one that
# update-desktop-database maintains). Without a refresh the menu can keep running the launcher's
# previous version for a long time, so a reinstall looks like it changed nothing.
CACHE_REFRESH_COMMANDS = (
    ("update-desktop-database",),
    ("kbuildsycoca6", "--noincremental"),
    ("kbuildsycoca5", "--noincremental"),
)


def default_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def launcher_text() -> str:
    """The packaged launcher, with its working directory set to this checkout: a menu entry starts
    in $HOME, so without it the app would not find the ``config.yaml`` kept here (as ``lain`` does
    from a terminal in this folder)."""
    return DESKTOP_FILE.read_text(encoding="utf-8").rstrip("\n") + f"\nPath={ROOT}\n"


def install(data_home: Path) -> list[Path]:
    """Write the launcher and copy the icons under ``data_home``; return what was written."""
    written = []
    target = data_home / "applications" / DESKTOP_FILE.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(launcher_text(), encoding="utf-8")
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


def refresh_caches() -> list[str]:
    """Best effort: run whichever desktop-menu cache rebuilders are installed, so the new launcher
    is picked up right away instead of after a stale ``.desktop`` cache expires (or a logout).
    Returns the commands actually run; failures (tool missing, no session, ...) are swallowed."""
    ran = []
    for command in CACHE_REFRESH_COMMANDS:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, capture_output=True, check=False, timeout=30)
        except OSError:
            continue
        ran.append(" ".join(command))
    return ran


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
    # Only touch the menu's cache when installing into the real, default location: --prefix is
    # also used for tests and alternate installs, whose files the running desktop never serves.
    if args.prefix is None:
        if refresh_caches():
            print("refreshed the desktop menu's cache")
        else:
            print(
                "could not refresh the desktop menu's cache (no known tool found); "
                "if the icon or menu entry does not show up, log out and in"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
