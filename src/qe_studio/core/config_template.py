"""The config.yaml template shipped with the package, and creating a first config from it
(spec 18 R5).

Lain only ever *creates* a config; an existing one belongs to the user (PRD §6) and is never
touched. No Qt.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path

LOCAL_ROOT_LINE = re.compile(r"^(?P<indent>[ \t]*)local_root:.*$", re.MULTILINE)


def template_text() -> str:
    """The packaged ``config.example.yaml`` (the repository root keeps a copy as documentation)."""
    resource = files("qe_studio.resources").joinpath("config.example.yaml")
    return resource.read_text(encoding="utf-8")


def with_local_root(text: str, folder: Path | str) -> str:
    """``text`` with its ``paths.local_root`` line pointing at ``folder``.

    The value is written as a JSON string, which is a valid YAML double-quoted scalar, so spaces,
    ``:`` and ``#`` in the path survive. Only the first ``local_root:`` line changes.
    """
    value = json.dumps(str(folder), ensure_ascii=False)
    return LOCAL_ROOT_LINE.sub(
        lambda match: f"{match.group('indent')}local_root: {value}", text, count=1
    )


def create_config(path: Path, local_root: Path | str | None = None) -> Path:
    """Write the template to ``path`` (with ``local_root`` when given) and return it.

    Raises FileExistsError when ``path`` exists: an existing config is never overwritten.
    """
    text = template_text()
    if local_root is not None:
        text = with_local_root(text, local_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(text)
    return path
