"""Who the app says it is to the desktop: names, window icon and ``.desktop`` association.

Qt ties the window to ``lain.desktop`` through the desktop file name (Wayland app id), and to
the taskbar icon through ``setWindowIcon``. The identifiers keep the old product name on
purpose, so existing QSettings and config directories keep working (see CLAUDE.md).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PyQt6.QtGui import QGuiApplication, QIcon

from .. import __version__

APPLICATION_NAME = "QE Studio"
ORGANIZATION_NAME = "qe-studio"
DESKTOP_FILE_NAME = "lain"  # packaging/lain.desktop (without the extension)


def icon_dir() -> Path:
    return Path(str(files("qe_studio.ui.resources").joinpath("app")))


def app_icon() -> QIcon:
    """The Lain icon: the vector file plus every ``lain-<size>.png`` next to it."""
    folder = icon_dir()
    icon = QIcon()
    for png in sorted(folder.glob("lain-*.png")):
        icon.addFile(str(png))
    icon.addFile(str(folder / "lain.svg"))
    return icon


def configure_application(app: QGuiApplication) -> None:
    app.setApplicationName(APPLICATION_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationVersion(__version__)
    QGuiApplication.setDesktopFileName(DESKTOP_FILE_NAME)
    app.setWindowIcon(app_icon())
