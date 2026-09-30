"""Plot settings saved next to the simulation as ``<kind>.plot`` (YAML), one file per plot kind.

The file holds every field of the module's parameter dataclass. It is read in the load worker and
applied over ``default_params`` field by field, so a hand-edited or outdated file can only drop
the values it gets wrong, never break the plot.
"""

from __future__ import annotations

import logging
import types
import typing
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import yaml
from matplotlib.colors import is_color_like

from ..appdirs import atomic_write_text

log = logging.getLogger(__name__)

FORMAT_VERSION = 1
SUFFIX = ".plot"
HEADER = "# Lain: ajustes do gráfico. Gerado automaticamente; apague para voltar aos padrões.\n"


def plot_file_path(folder: Path, kind: str) -> Path:
    return Path(folder) / f"{kind}{SUFFIX}"


def read_plot_file(folder: Path, kind: str) -> tuple[dict[str, Any] | None, list[str]]:
    """(stored parameters or None, warnings for the user). A missing file is not a warning."""
    path = plot_file_path(folder, kind)
    invalid = f"{path.name} inválido; usando ajustes padrão."
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, []
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        log.warning("%s: %s", path, exc)
        return None, [invalid]
    if not isinstance(data, dict) or not isinstance(data.get("params"), dict):
        return None, [invalid]
    if data.get("lain_plot") != FORMAT_VERSION:
        version = data.get("lain_plot")
        return None, [f"{path.name} ignorado: versão de formato desconhecida ({version!r})."]
    if data.get("kind") != kind:
        return None, [
            f"{path.name} ignorado: pertence a outro tipo de gráfico ({data.get('kind')!r})."
        ]
    return data["params"], []


def write_plot_file(folder: Path, kind: str, params: Any) -> Path:
    path = plot_file_path(folder, kind)
    data = {"lain_plot": FORMAT_VERSION, "kind": kind, "params": stored_params(params)}
    atomic_write_text(path, HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


def stored_params(params: Any) -> dict[str, Any]:
    """``params`` as the file stores them (what ``read_plot_file`` returns)."""
    return _plain(asdict(params))


def _plain(value: Any) -> Any:
    """Numpy scalars (e.g. from axis limits) as Python numbers, which ``safe_dump`` accepts."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value.item() if hasattr(value, "item") and not isinstance(value, str) else value


def delete_plot_file(folder: Path, kind: str) -> None:
    plot_file_path(folder, kind).unlink(missing_ok=True)


def apply_stored(params: Any, stored: dict[str, Any], schema: typing.Iterable = ()) -> list[str]:
    """Set the valid stored values on ``params``; returns the names of the ignored fields.

    ``schema`` (the module's ``ParamField`` list) restricts ``choice`` fields to their choices.
    """
    hints = typing.get_type_hints(type(params))
    choices = {f.name: [c[0] for c in f.choices] for f in schema if f.kind == "choice"}
    names = {f.name for f in fields(params)}
    ignored = []
    for name, value in stored.items():
        if name not in names:
            log.debug("plot file: unknown field %r ignored", name)
            continue
        default = getattr(params, name)
        valid = _fits(hints[name], value) and _valid_value(name, value, default, choices)
        if not valid:
            log.warning("plot file: %s = %r ignored (default %r)", name, value, default)
            ignored.append(name)
            continue
        if isinstance(value, int) and not isinstance(value, bool) and _accepts(hints[name], float):
            value = float(value)
        setattr(params, name, value)
    return ignored


def _options(hint: Any) -> tuple[Any, ...]:
    if typing.get_origin(hint) in (typing.Union, types.UnionType):
        return typing.get_args(hint)
    return (hint,)


def _accepts(hint: Any, kind: type) -> bool:
    return kind in _options(hint)


def _fits(hint: Any, value: Any) -> bool:
    """Does ``value`` (from YAML) match the field annotation? ``int`` is fine for ``float``."""
    for option in _options(hint):
        origin, args = typing.get_origin(option), typing.get_args(option)
        if option is type(None):
            ok = value is None
        elif option is float:
            ok = isinstance(value, int | float) and not isinstance(value, bool)
        elif option in (int, str, bool):
            ok = type(value) is option
        elif origin is list:
            ok = isinstance(value, list) and all(_fits(args[0], item) for item in value)
        elif origin is dict:
            ok = isinstance(value, dict) and all(
                _fits(args[0], k) and _fits(args[1], v) for k, v in value.items()
            )
        else:
            ok = False
        if ok:
            return True
    return False


def _valid_value(name: str, value: Any, default: Any, choices: dict[str, list]) -> bool:
    """Values that would make ``render`` fail: unknown choices and invalid colours."""
    if name in choices:
        return value in choices[name]
    if name == "background" or name.endswith("color"):
        return (value == "" and default == "") or is_color_like(value)
    if name.endswith("_colors"):
        return all(is_color_like(color) for color in value.values())
    return True
