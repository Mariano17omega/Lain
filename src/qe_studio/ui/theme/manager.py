"""Theme tokens, QSS assembly, palette and tinted icons (PRD §2.2).

Styles live in ``resources/styles/<domain>/<component>.qss`` and reference colors as
``${token}``; tokens come from ``resources/themes/<theme>.yaml``. Custom-painted widgets read
colors with :meth:`ThemeManager.color` and refresh on ``theme_changed``.
"""

from __future__ import annotations

import re
from importlib.resources import as_file, files
from string import Template

import yaml
from PyQt6.QtCore import QObject, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from ...core.appdirs import cache_dir
from ...core.plotting.style import PlotStyle, style_for

THEMES = ("dark", "light")
# Icons referenced from QSS as url(${token}): (token, icon, color token, size px)
QSS_ICONS = (
    ("icon_close", "close", "text_muted", 14),
    ("icon_close_hover", "close", "text", 14),
    ("icon_branch_closed", "chevron_right", "text_muted", 14),
    ("icon_branch_open", "expand_more", "text_muted", 14),
    ("icon_combo_arrow", "expand_more", "text_muted", 14),
)
STYLE_DOMAINS = ("base", "layout", "navigation", "workspace", "controls", "dialogs")
_RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")

_fonts_loaded = False


def load_fonts() -> None:
    """Register the vendored Inter / JetBrains Mono with Qt (idempotent)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    for resource in files("qe_studio.resources").joinpath("fonts").iterdir():
        if resource.name.endswith(".ttf"):
            with as_file(resource) as path:
                QFontDatabase.addApplicationFont(str(path))
    _fonts_loaded = True


def load_tokens(theme: str) -> dict[str, str]:
    text = files("qe_studio.resources").joinpath("themes", f"{theme}.yaml").read_text("utf-8")
    return {str(k): str(v) for k, v in yaml.safe_load(text).items()}


def style_files() -> list[tuple[str, str]]:
    """``(relative path, text)`` of every QSS file, domains in cascade order."""
    root = files("qe_studio.resources").joinpath("styles")
    out = []
    for domain in STYLE_DOMAINS:
        folder = root.joinpath(domain)
        for resource in sorted(folder.iterdir(), key=lambda r: r.name):
            if resource.name.endswith(".qss"):
                out.append((f"{domain}/{resource.name}", resource.read_text("utf-8")))
    return out


def build_stylesheet(tokens: dict[str, str]) -> str:
    """Concatenate all QSS files with tokens substituted; unknown tokens raise KeyError."""
    parts = []
    for name, text in style_files():
        parts.append(f"/* ---- {name} ---- */\n{Template(text).substitute(tokens)}")
    return "\n".join(parts)


def parse_color(value: str) -> QColor:
    match = _RGBA.fullmatch(value.strip())
    if match:
        r, g, b, a = match.groups()
        return QColor(int(r), int(g), int(b), round(float(a) * 255))
    return QColor(value)


def tinted_pixmap(svg: bytes, color: QColor, size: int, ratio: float = 1.0) -> QPixmap:
    px = max(1, round(size * ratio))
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(svg).render(painter, QRectF(0, 0, px, px))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self, theme: str = "dark", parent: QObject | None = None):
        super().__init__(parent)
        self._svgs: dict[str, bytes] = {}
        self._icons: dict[tuple, QIcon] = {}
        self.name = theme if theme in THEMES else "dark"
        self.tokens = load_tokens(self.name)

    # -- applying ------------------------------------------------------------------------------
    def apply(self, app: QApplication | None = None) -> None:
        app = app or QApplication.instance()
        load_fonts()
        app.setStyle("Fusion")
        app.setPalette(self.palette())
        app.setStyleSheet(self.stylesheet())

    def stylesheet(self) -> str:
        return build_stylesheet({**self.tokens, **self.asset_tokens()})

    def asset_tokens(self) -> dict[str, str]:
        """Render the QSS icons as PNG (1x and @2x) into the cache dir; token → file path."""
        folder = cache_dir() / "qss" / self.name
        folder.mkdir(parents=True, exist_ok=True)
        out = {}
        for token, icon, color, size in QSS_ICONS:
            path = folder / f"{icon}-{color}.png"
            for ratio, target in ((1.0, path), (2.0, path.with_name(f"{path.stem}@2x.png"))):
                if not target.exists():
                    tinted_pixmap(self._svg(icon), self.color(color), size, ratio).save(str(target))
            out[token] = path.as_posix()
        return out

    def set_theme(self, theme: str, app: QApplication | None = None) -> None:
        if theme not in THEMES or theme == self.name:
            return
        self.name = theme
        self.tokens = load_tokens(theme)
        self._icons.clear()
        self.apply(app)
        self.theme_changed.emit(theme)

    def toggle(self) -> str:
        self.set_theme("light" if self.name == "dark" else "dark")
        return self.name

    # -- lookups -------------------------------------------------------------------------------
    def color(self, token: str) -> QColor:
        return parse_color(self.tokens[token])

    @property
    def plot_style(self) -> PlotStyle:
        return style_for(self.name)

    def palette(self) -> QPalette:
        c = self.color
        palette = QPalette()
        role = QPalette.ColorRole
        for r, token in (
            (role.Window, "window"),
            (role.WindowText, "text"),
            (role.Base, "input"),
            (role.AlternateBase, "panel_alt"),
            (role.Text, "text"),
            (role.Button, "card"),
            (role.ButtonText, "text"),
            (role.ToolTipBase, "popover"),
            (role.ToolTipText, "text"),
            (role.PlaceholderText, "text_dim"),
            (role.Highlight, "accent"),
            (role.HighlightedText, "primary_fg"),
            (role.Link, "accent"),
            (role.Mid, "border"),
            (role.Dark, "border_strong"),
        ):
            palette.setColor(r, c(token))
        palette.setColor(QPalette.ColorGroup.Disabled, role.Text, c("text_dim"))
        palette.setColor(QPalette.ColorGroup.Disabled, role.WindowText, c("text_dim"))
        palette.setColor(QPalette.ColorGroup.Disabled, role.ButtonText, c("text_dim"))
        return palette

    def _svg(self, name: str) -> bytes:
        if name not in self._svgs:
            resource = files("qe_studio.resources").joinpath("icons", f"{name}.svg")
            self._svgs[name] = resource.read_bytes()
        return self._svgs[name]

    def icon(
        self,
        name: str,
        token: str = "text_muted",
        active_token: str | None = None,
        size: int = 20,
    ) -> QIcon:
        """Material Symbol ``name`` tinted with theme colors (``active_token`` when checked)."""
        app = QGuiApplication.instance()
        ratio = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 1.0
        key = (name, token, active_token, size, ratio)
        if key not in self._icons:
            icon = QIcon()
            svg = self._svg(name)
            normal = tinted_pixmap(svg, self.color(token), size, ratio)
            icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
            active = tinted_pixmap(svg, self.color(active_token or token), size, ratio)
            icon.addPixmap(active, QIcon.Mode.Normal, QIcon.State.On)
            icon.addPixmap(active, QIcon.Mode.Active, QIcon.State.On)
            icon.addPixmap(
                tinted_pixmap(svg, self.color("text_dim"), size, ratio), QIcon.Mode.Disabled
            )
            self._icons[key] = icon
        return self._icons[key]

    def pixmap(self, name: str, token: str, size: int = 20) -> QPixmap:
        return self.icon(name, token, size=size).pixmap(QSize(size, size))
