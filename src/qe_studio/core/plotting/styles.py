"""Plot styles (spec 82): the look a new plot starts with, one YAML file per style in
``resources/templates/plot_styles/`` (``padrao.yaml`` is the default one). Not ``style.py``, the
figure colors that follow a background.

A style gives values by parameter name (the names a ``.plot`` uses), only of the fields a style may
give (``style_fields``): the look of ``CommonParams`` and every color parameter of the plot modules.
``load_config`` reads the folder and installs it (``set_styles``); ``default_params`` and the panel's
"Estilo do gráfico" take it from ``styles()``. Lain never writes there: what the user changes in a
plot goes to its ``.plot``.
"""

from __future__ import annotations

import copy
import functools
import logging
import threading
import typing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from matplotlib.colors import is_color_like

from ...i18n import _

log = logging.getLogger(__name__)

DEFAULT_STYLE = "padrao"  # its file name: what a .plot keeps, the same in every language
FORMAT_VERSION = 1  # the ``lain_style:`` of a style file
SUFFIX = ".yaml"
STYLES_DIR = Path(str(files("qe_studio.resources").joinpath("templates").joinpath("plot_styles")))

# The look of every plot (``CommonParams``) a style may give; its other fields are colors.
APPEARANCE = (
    "figure_width",
    "figure_height",
    "font_size",
    "background",
    "line_width",
    "show_legend",
    "legend_loc",
    "legend_dx",
    "legend_dy",
    "legend_frame",
    "legend_size",
    "legend_transparency",
    "tick_size",
    "label_size",
)


@dataclass(frozen=True)
class Rule:
    """How a style's value of one field is checked: its kind (``float``, ``bool``, ``choice``,
    ``color`` or ``colors``) and the bounds and choices of its panel field."""

    kind: str
    optional: bool = False  # a float that may be None (= automatic)
    bounds: tuple[float, float] | None = None
    choices: tuple[object, ...] = ()
    blank: bool = False  # a color that may be "" (the theme's text color, as ``total_color``)
    keys: tuple[str, ...] = ()  # the only keys a map of colors may have; () any label

    def accepts(self, value: Any) -> bool:
        if self.kind == "float":
            if value is None:
                return self.optional
            if isinstance(value, bool) or not isinstance(value, int | float):
                return False
            return self.bounds is None or self.bounds[0] <= value <= self.bounds[1]
        if self.kind == "bool":
            return isinstance(value, bool)
        if self.kind == "choice":
            return value in self.choices
        if self.kind == "color":
            return isinstance(value, str) and (is_color_like(value) or (self.blank and not value))
        if self.kind == "colors":
            return isinstance(value, dict) and all(
                self._key(key) and isinstance(color, str) and is_color_like(color)
                for key, color in value.items()
            )
        return False

    def _key(self, key: object) -> bool:
        """A key of a map of colors: a label as the output writes it (no space, which would never
        match one), and one of ``keys`` when the map has them."""
        if not isinstance(key, str) or not key or any(c.isspace() for c in key):
            return False
        return not self.keys or key in self.keys


@functools.cache
def style_fields() -> dict[str, Rule]:
    """``STYLE_FIELDS`` (spec 82 R1.2): what a style may give, and how each value is checked. The
    look of ``CommonParams``, bounded as its panel fields are, and every parameter of a plot module
    that declares ``metadata={"kind": "color" | "colors"}``.

    Built on first use: the modules import this one (``apply_common_config``), so neither their
    registry nor ``calculations.params`` can be imported at the top.
    """
    from ..calculations import REGISTRY
    from ..calculations.params import COMMON_FIELDS

    panel = {f.name: f for f in COMMON_FIELDS}
    rules: dict[str, Rule] = {}
    for name in APPEARANCE:
        f = panel[name]
        bounds = None if f.minimum is None or f.maximum is None else (f.minimum, f.maximum)
        choices = tuple(value for value, _label in f.choices)
        rules[name] = Rule(f.kind, f.optional, bounds, choices)
    for cls in _params_classes(REGISTRY):
        for f in fields(cls):
            kind = f.metadata.get("kind")
            if kind in ("color", "colors") and f.name not in rules:
                keys = tuple(f.metadata.get("keys", ()))
                rules[f.name] = Rule(kind, blank=f.default == "", keys=keys)
    return rules


def _params_classes(modules: Iterable[object]) -> list[type]:
    """The parameter class of each module: the ``P`` of its ``CalculationModule[D, P]`` base."""
    classes: list[type] = []
    for module in modules:
        for base in getattr(type(module), "__orig_bases__", ()):
            args = typing.get_args(base)
            cls = args[1] if len(args) == 2 else None
            if isinstance(cls, type) and is_dataclass(cls) and cls not in classes:
                classes.append(cls)
    return classes


@dataclass(frozen=True)
class Style:
    name: str  # the file name without ``.yaml``: what a ``.plot`` keeps
    label: str  # its ``name:``, shown in the combo (the file name without one)
    params: Mapping[str, Any]  # the valid values it gives, by parameter name


@dataclass(frozen=True)
class StyleSet:
    """The styles of a folder, by name. The default one is always there: empty without a valid
    ``padrao.yaml``, and then the parameters' own defaults (those of the code) hold."""

    styles: Mapping[str, Style]
    warnings: tuple[str, ...] = ()

    def choices(self) -> tuple[tuple[str, str], ...]:
        """(name, label) of the combo: the default first, translated; the others by their label."""
        others = sorted(
            (style for style in self.styles.values() if style.name != DEFAULT_STYLE),
            key=lambda style: (style.label.casefold(), style.name),
        )
        return ((DEFAULT_STYLE, _("Padrão")), *((style.name, style.label) for style in others))

    def own(self, name: str) -> Mapping[str, Any]:
        """The values the file of ``name`` gives itself (none for a style that does not exist)."""
        style = self.styles.get(name)
        return style.params if style is not None else {}

    def values(self, name: str) -> dict[str, Any]:
        """The default style's values, then those of ``name``: a map of colors is added to the
        default's, never replaces it whole."""
        values = dict(self.own(DEFAULT_STYLE))
        if name != DEFAULT_STYLE:
            for key, value in self.own(name).items():
                values[key] = _over(values.get(key), value)
        return values


def _over(base: Any, value: Any) -> Any:
    """``value`` over ``base``: a map is added to the base's map."""
    if isinstance(value, dict) and isinstance(base, dict):
        return {**base, **value}
    return value


def load_styles(folder: Path) -> StyleSet:
    """Every ``*.yaml`` of ``folder`` (spec 82 R1.3), checked as a ``.plot`` is: a file that cannot
    be read or has no ``lain_style: 1`` is left out, and a field a style may not give or an invalid
    value is dropped, each with a warning for the user. Never writes."""
    found: dict[str, Style] = {}
    warnings: list[str] = []
    for path in sorted(folder.glob(f"*{SUFFIX}")):
        if path.is_file() and (style := _read_style(path, warnings)) is not None:
            found[style.name] = style
    if DEFAULT_STYLE not in found:
        warnings.append(
            _("Estilo de gráfico {file} ausente ou inválido: usando os padrões do Lain.").format(
                file=DEFAULT_STYLE + SUFFIX
            )
        )
        found[DEFAULT_STYLE] = Style(DEFAULT_STYLE, DEFAULT_STYLE, {})
    return StyleSet(found, tuple(warnings))


def _read_style(path: Path, warnings: list[str]) -> Style | None:
    file = path.name
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("%s: %s", path, exc)
        error = getattr(exc, "strerror", None) or exc
        text = _("Estilo de gráfico {file} ignorado: não foi possível ler o arquivo ({error}).")
        warnings.append(text.format(file=file, error=error))
        return None
    except yaml.YAMLError as exc:
        log.warning("%s: %s", path, exc)
        warnings.append(_("Estilo de gráfico {file} ignorado: YAML inválido.").format(file=file))
        return None
    if not isinstance(data, dict) or data.get("lain_style") != FORMAT_VERSION:
        text = _("Estilo de gráfico {file} ignorado: falta “lain_style: {version}”.")
        warnings.append(text.format(file=file, version=FORMAT_VERSION))
        return None
    params = data.get("params") or {}
    if not isinstance(params, dict):
        text = _(
            "Estilo de gráfico {file} ignorado: “params” deve ser um mapeamento (chave: valor)."
        )
        warnings.append(text.format(file=file))
        return None
    label = data.get("name")
    name = path.name.removesuffix(SUFFIX)
    return Style(
        name,
        label.strip() if isinstance(label, str) and label.strip() else name,
        _checked(params, file, warnings),
    )


def _checked(params: dict, file: str, warnings: list[str]) -> dict[str, Any]:
    rules = style_fields()
    values: dict[str, Any] = {}
    for key, value in params.items():
        rule = rules.get(key) if isinstance(key, str) else None
        if rule is None:
            text = _("Estilo {file}: {key} não é um campo de estilo e é ignorado.")
            warnings.append(text.format(file=file, key=key))
        elif not rule.accepts(value):
            text = _("Estilo {file}: valor inválido em {key} ({value!r}), ignorado.")
            warnings.append(text.format(file=file, key=key, value=value))
        else:
            is_int = isinstance(value, int) and not isinstance(value, bool)
            values[key] = float(value) if rule.kind == "float" and is_int else value
    return values


_lock = threading.Lock()
_current: StyleSet | None = None


def set_styles(styles: StyleSet | None) -> None:
    """Install the styles read with the config (``load_config``, at startup and on "Recarregar
    config.yaml"); None: the next ``styles()`` reads the package folder again."""
    global _current
    with _lock:
        _current = styles


def styles() -> StyleSet:
    """The styles in use. Read from ``STYLES_DIR`` on the first call when nobody installed any
    (tests, scripts): the app installs them at startup, before any plot, so the GUI thread never
    reads the folder here."""
    global _current
    with _lock:
        if _current is None:
            _current = load_styles(STYLES_DIR)
        return _current


def apply_style(params: Any, name: str) -> list[str]:
    """Give ``params`` the look of style ``name`` (spec 82 R1.3): the default style's values, then
    the style's own, on the fields ``params`` has; a map of colors is added to the one it holds.
    Returns the style's fields ``params`` does not have (another module's colors)."""
    values = styles().values(name)
    for key, value in values.items():
        if hasattr(params, key):
            setattr(params, key, copy.deepcopy(_over(getattr(params, key), value)))
    return sorted(key for key in values if not hasattr(params, key))


def restyle(params: Any, defaults: Any) -> None:
    """After the user picks ``params.style`` in the panel (spec 82 R3.2): every field a style may
    give takes its value in ``defaults`` (the plot's defaults: the default style plus the module's
    own touches, like the taller figure of a relaxation), then the chosen style's own value, a map
    of colors added to the default's. The other parameters (energy window, atoms, labels…) stay; a
    style that no longer exists gives nothing of its own."""
    name = params.style
    own = {} if name == DEFAULT_STYLE else styles().own(name)
    for key in style_fields():
        if hasattr(params, key):
            base = getattr(defaults, key)
            setattr(params, key, copy.deepcopy(_over(base, own.get(key, base))))
