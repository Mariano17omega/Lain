"""Rendering the packaged Jinja2 templates of "Criar cálculo" (spec 25 R2).

Templates live in ``qe_studio/resources/templates/`` (``qsub/`` for the cluster scripts, ``qe/<type>/``
for the inputs pw.x does not derive) and are read with ``importlib.resources``, like the
``config.yaml`` template. Undefined variables raise (``StrictUndefined``): a script never goes out
with a gap. ``jinja2`` is imported on first use, never with the window (spec 14).
"""

from __future__ import annotations

import functools
from collections.abc import Iterator, Mapping
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jinja2 import Environment

__all__ = ["TemplateFailure", "fortran_number", "fortran_string", "render", "template_names"]

TEMPLATES = "templates"


class TemplateFailure(Exception):
    """A template that is missing or needs a variable nobody gave (Portuguese, with the name)."""


def _root() -> Traversable:
    return files("qe_studio.resources").joinpath(TEMPLATES)


def _resource(name: str) -> Traversable:
    resource = _root()
    for part in name.split("/"):
        resource = resource.joinpath(part)
    return resource


def template_names() -> list[str]:
    """Every packaged template, as ``render`` names it (``qsub/scf.qsub.j2``)."""

    def walk(node: Traversable, prefix: str) -> Iterator[str]:
        for child in node.iterdir():
            if child.is_dir():
                yield from walk(child, f"{prefix}{child.name}/")
            elif child.name.endswith(".j2"):
                yield f"{prefix}{child.name}"

    return sorted(walk(_root(), ""))


def fortran_string(value: object) -> str:
    """A Fortran string literal: between ``'``, an inner ``'`` doubled."""
    return "'" + str(value).replace("'", "''") + "'"


def fortran_number(value: object) -> str:
    """A number as a namelist reads it: ints as they are, floats with a ``.`` (``-25.0``)."""
    if isinstance(value, bool):
        return ".true." if value else ".false."
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _load(name: str) -> str | None:
    resource = _resource(name)
    return resource.read_text(encoding="utf-8") if resource.is_file() else None


@functools.cache
def _environment() -> Environment:
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FunctionLoader(_load),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fstr"] = fortran_string
    env.filters["fnum"] = fortran_number
    return env


def render(template: str, values: Mapping[str, Any]) -> str:
    """The text of ``template`` (a name from ``template_names``) with ``values``. Raises
    ``TemplateFailure`` naming the template and what is missing."""
    import jinja2

    try:
        return _environment().get_template(template).render(**values)
    except jinja2.TemplateNotFound as exc:
        raise TemplateFailure(f"Template não encontrado: {exc.name}") from exc
    except jinja2.UndefinedError as exc:
        raise TemplateFailure(f"Template {template}: {exc.message}") from exc
