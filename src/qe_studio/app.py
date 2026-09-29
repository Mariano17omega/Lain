"""Application bootstrap: arguments, logging, config, theme and main window."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import QSettings, QThreadPool
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .config import ConfigError, load_config
from .core.appdirs import cache_dir
from .core.plotting.style import register_fonts
from .ui.theme.manager import THEMES, ThemeManager


def setup_logging(verbose: bool = False) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_dir = cache_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(log_dir / "qe_studio.log", maxBytes=1_000_000, backupCount=2)
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def install_excepthook() -> None:
    """Report unexpected errors instead of letting PyQt6 abort the whole app."""
    log = logging.getLogger("qe_studio")

    def hook(kind, value, tb) -> None:
        log.error("erro inesperado", exc_info=(kind, value, tb))
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                "Erro inesperado",
                f"{kind.__name__}: {value}\n\nDetalhes no log ({cache_dir() / 'qe_studio.log'}).",
            )

    sys.excepthook = hook


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="qe-studio", description="QE Studio")
    parser.add_argument("--config", help="caminho do config.yaml")
    parser.add_argument("--verbose", action="store_true", help="log detalhado")
    parser.add_argument("--version", action="version", version=f"QE Studio {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    install_excepthook()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("QE Studio")
    app.setOrganizationName("qe-studio")
    app.setApplicationVersion(__version__)
    register_fonts()

    settings = QSettings()
    try:
        loaded = load_config(args.config)
    except ConfigError as exc:
        ThemeManager("dark").apply(app)
        QMessageBox.critical(None, "config.yaml inválido", str(exc))
        return 2

    theme_name = str(settings.value("ui/theme", loaded.config.ui.theme))
    theme = ThemeManager(theme_name if theme_name in THEMES else loaded.config.ui.theme)
    theme.apply(app)

    from .ui.main_window import MainWindow

    window = MainWindow(loaded, theme, settings)
    window.show()
    code = app.exec()
    QThreadPool.globalInstance().waitForDone(5000)  # no worker may outlive the interpreter
    return code
