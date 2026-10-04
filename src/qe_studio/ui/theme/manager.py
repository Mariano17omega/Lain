"""Theme tokens, QSS assembly, palette and tinted icons (PRD §2.2).

Styles live in ``resources/styles/<domain>/<component>.qss`` and reference colors as
``${token}``; tokens come from ``resources/themes/<theme>.yaml``. Custom-painted widgets read
colors with :meth:`ThemeManager.color` and refresh on ``theme_changed``.
"""

from __future__ import annotations

from importlib.resources import as_file, files
from string import Template

import yaml
from PyQt6.QtCore import QObject, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from ...core.appdirs import cache_dir
from ...core.colors import RGBA
from ...core.fontscale import clamp_scale, scale_qss, size_tokens
from . import scale as font_scale_state

THEMES = ("dark", "light")  # the concrete themes: a token file each
MODES = (*THEMES, "system")  # what the user picks; "system" follows the OS color scheme
# Icons referenced from QSS as url(${token}): (token, icon, color token, size px)
QSS_ICONS = (
    ("icon_close", "close", "text_muted", 14),
    ("icon_close_hover", "close", "text", 14),
    ("icon_branch_closed", "chevron_right", "text_muted", 14),
    ("icon_branch_open", "expand_more", "text_muted", 14),
    ("icon_combo_arrow", "expand_more", "text_muted", 14),
)
STYLE_DOMAINS = ("base", "layout", "navigation", "workspace", "controls", "dialogs")

_fonts_loaded = False


def load_fonts() -> None:
    """Register the vendored Inter / JetBrains Mono with Qt (idempotent)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    for resource in files("qe_studio.ui.resources").joinpath("fonts").iterdir():
        if resource.name.endswith(".ttf"):
            with as_file(resource) as path:
                QFontDatabase.addApplicationFont(str(path))
    _fonts_loaded = True


def load_tokens(theme: str) -> dict[str, str]:
    text = files("qe_studio.ui.resources").joinpath("themes", f"{theme}.yaml").read_text("utf-8")
    return {str(k): str(v) for k, v in yaml.safe_load(text).items()}


def style_files() -> list[tuple[str, str]]:
    """``(relative path, text)`` of every QSS file, domains in cascade order."""
    root = files("qe_studio.ui.resources").joinpath("styles")
    out = []
    for domain in STYLE_DOMAINS:
        folder = root.joinpath(domain)
        for resource in sorted(folder.iterdir(), key=lambda r: r.name):
            if resource.name.endswith(".qss"):
                out.append((f"{domain}/{resource.name}", resource.read_text("utf-8")))
    return out


def build_stylesheet(tokens: dict[str, str], scale: float = 1.0) -> str:
    """Concatenate all QSS files with tokens substituted; unknown tokens raise KeyError.

    ``scale`` is ``ui.font_scale``: it scales every ``font-size`` and the heights of the
    ``size_tokens`` (spec 19 R2).
    """
    values = {**tokens, **size_tokens(scale)}
    parts = []
    for name, text in style_files():
        parts.append(f"/* ---- {name} ---- */\n{Template(text).substitute(values)}")
    return scale_qss("\n".join(parts), scale)


def system_theme() -> str:
    """The concrete theme the OS asks for: its color scheme, ``dark`` when it does not say."""
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme() if hints is not None else Qt.ColorScheme.Unknown
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def parse_color(value: str) -> QColor:
    match = RGBA.fullmatch(value.strip())
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
    """``mode`` is the user's pick (dark / light / system); ``name`` the concrete theme applied.

    ``theme_changed`` carries the concrete name, so painted widgets never see "system".
    """

    theme_changed = pyqtSignal(str)
    mode_changed = pyqtSignal(str)
    scale_changed = pyqtSignal(float)

    def __init__(self, theme: str = "dark", parent: QObject | None = None, font_scale: float = 1.0):
        super().__init__(parent)
        self._svgs: dict[str, bytes] = {}
        self._icons: dict[tuple, QIcon] = {}
        self.mode = theme if theme in MODES else "dark"
        self.name = self._resolve(self.mode)
        self.tokens = load_tokens(self.name)
        self.font_scale = clamp_scale(font_scale)
        font_scale_state.set_current(self.font_scale)
        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.connect(self._on_scheme_changed)

    @staticmethod
    def _resolve(mode: str) -> str:
        return system_theme() if mode == "system" else mode

    # -- applying ------------------------------------------------------------------------------
    def apply(self, app: QApplication | None = None) -> None:
        if app is None:
            instance = QApplication.instance()
            assert isinstance(instance, QApplication), "the theme styles a QApplication"
            app = instance
        load_fonts()
        app.setStyle("Fusion")
        app.setPalette(self.palette())
        app.setStyleSheet(self.stylesheet())

    def stylesheet(self) -> str:
        return build_stylesheet({**self.tokens, **self.asset_tokens()}, self.font_scale)

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

    def set_mode(self, mode: str, app: QApplication | None = None) -> None:
        if mode not in MODES:
            return
        changed = mode != self.mode
        self.mode = mode
        self._switch(self._resolve(mode), app)
        if changed:
            self.mode_changed.emit(mode)

    def _switch(self, theme: str, app: QApplication | None = None) -> None:
        """Apply the concrete ``theme`` (nothing when it is already the one in use)."""
        if theme == self.name:
            return
        self.name = theme
        self.tokens = load_tokens(theme)
        self._icons.clear()
        self.apply(app)
        self.theme_changed.emit(theme)

    def _on_scheme_changed(self, *_args) -> None:
        if self.mode == "system":
            self._switch(self._resolve("system"))

    def label(self) -> str:
        """The mode in words: ``Escuro``, ``Claro`` or ``Sistema (escuro agora)``."""
        if self.mode == "system":
            return f"Sistema ({'escuro' if self.name == 'dark' else 'claro'} agora)"
        return "Escuro" if self.mode == "dark" else "Claro"

    def toggle(self) -> str:
        """The next mode: dark → light → system → dark. Returns it."""
        self.set_mode(MODES[(MODES.index(self.mode) + 1) % len(MODES)])
        return self.mode

    def set_font_scale(self, scale: float, app: QApplication | None = None) -> None:
        scale = clamp_scale(scale)
        if scale == self.font_scale:
            return
        self.font_scale = scale
        font_scale_state.set_current(scale)
        self.apply(app)
        self.scale_changed.emit(scale)

    # -- lookups -------------------------------------------------------------------------------
    def color(self, token: str) -> QColor:
        return parse_color(self.tokens[token])

    def has_color(self, token: str) -> bool:
        return token in self.tokens

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
            resource = files("qe_studio.ui.resources").joinpath("icons", f"{name}.svg")
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
