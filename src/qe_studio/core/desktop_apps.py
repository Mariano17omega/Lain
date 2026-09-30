"""Installed programs that open a MIME type, from freedesktop ``.desktop`` files ("Abrir com").

Follows the Desktop Entry and MIME Applications Associations specs, reduced to what the context
menu needs: the programs registered for a type (``MimeType`` plus the user's added
associations in ``mimeapps.list``), the default one, and the argument list to start a program
with one file. Programs are always started with an argument list, never through a shell.
"""

from __future__ import annotations

import functools
import os
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

GROUP = "Desktop Entry"
_ESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
_FILE_CODES = {"%f", "%F", "%u", "%U"}
_DEPRECATED_CODES = {"%d", "%D", "%n", "%N", "%v", "%m"}


@dataclass(frozen=True)
class DesktopApp:
    id: str  # desktop file ID, e.g. "org.kde.kate.desktop"
    name: str
    exec: str
    icon: str
    mime_types: frozenset[str]
    path: Path


def _env_dirs(var: str, default: str) -> list[Path]:
    return [Path(d) for d in (os.environ.get(var) or default).split(":") if d]


def _home_dir(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def _unescape(value: str) -> str:
    out, chars = [], iter(value)
    for char in chars:
        if char == "\\":
            nxt = next(chars, "")
            out.append(_ESCAPES.get(nxt, "\\" + nxt))
        else:
            out.append(char)
    return "".join(out)


def read_ini(path: Path) -> dict[str, dict[str, str]]:
    """Groups of a freedesktop key file (``.desktop``, ``mimeapps.list``); unreadable → {}."""
    groups: dict[str, dict[str, str]] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return groups
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = groups.setdefault(line[1:-1], {})
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            current.setdefault(key.strip(), value.strip())  # first occurrence wins
    return groups


def _split_list(value: str) -> list[str]:
    return [item for item in _unescape(value).split(";") if item]


def _executable(program: str) -> bool:
    if os.path.isabs(program):
        return os.access(program, os.X_OK)
    return shutil.which(program) is not None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _localized(entry: dict[str, str], key: str) -> str:
    for candidate in (f"{key}[pt_BR]", f"{key}[pt]", key):
        if entry.get(candidate):
            return _unescape(entry[candidate])
    return ""


def parse_desktop_file(path: Path, app_id: str) -> DesktopApp | None:
    """The application in ``path``, or None when it must not be offered."""
    entry = read_ini(path).get(GROUP)
    if not entry or entry.get("Type", "Application") != "Application":
        return None
    if _truthy(entry.get("NoDisplay")) or _truthy(entry.get("Hidden")):
        return None
    exec_line = entry.get("Exec", "")
    try_exec = _unescape(entry.get("TryExec", ""))
    if not exec_line or (try_exec and not _executable(try_exec)):
        return None
    return DesktopApp(
        id=app_id,
        name=_localized(entry, "Name") or app_id.removesuffix(".desktop"),
        exec=exec_line,
        icon=_unescape(entry.get("Icon", "")),
        mime_types=frozenset(_split_list(entry.get("MimeType", ""))),
        path=path,
    )


class AppCatalog:
    """Applications and ``mimeapps.list`` associations found in the XDG directories."""

    def __init__(
        self,
        data_dirs: Sequence[Path] | None = None,
        config_dirs: Sequence[Path] | None = None,
        desktops: Sequence[str] | None = None,
    ):
        if data_dirs is None:
            data_dirs = [
                _home_dir("XDG_DATA_HOME", ".local/share"),
                *_env_dirs("XDG_DATA_DIRS", "/usr/local/share:/usr/share"),
            ]
        if config_dirs is None:
            config_dirs = [
                _home_dir("XDG_CONFIG_HOME", ".config"),
                *_env_dirs("XDG_CONFIG_DIRS", "/etc/xdg"),
            ]
        if desktops is None:
            desktops = [d.lower() for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")]
        self.apps: dict[str, DesktopApp] = {}
        seen: set[str] = set()  # IDs shadowed by an earlier directory, even if not offered
        for data_dir in data_dirs:
            applications = Path(data_dir) / "applications"
            for path in sorted(applications.rglob("*.desktop")) if applications.is_dir() else []:
                app_id = path.relative_to(applications).as_posix().replace("/", "-")
                if app_id in seen:
                    continue
                seen.add(app_id)
                if (app := parse_desktop_file(path, app_id)) is not None:
                    self.apps[app_id] = app
        self.defaults: dict[str, list[str]] = {}
        self.added: dict[str, list[str]] = {}
        self.removed: dict[str, set[str]] = {}
        lists = [Path(d) for d in config_dirs] + [Path(d) / "applications" for d in data_dirs]
        for folder in lists:
            for name in [f"{d}-mimeapps.list" for d in desktops if d] + ["mimeapps.list"]:
                groups = read_ini(folder / name)
                for mime, value in groups.get("Default Applications", {}).items():
                    self.defaults.setdefault(mime, []).extend(_split_list(value))
                for mime, value in groups.get("Added Associations", {}).items():
                    self.added.setdefault(mime, []).extend(_split_list(value))
                for mime, value in groups.get("Removed Associations", {}).items():
                    self.removed.setdefault(mime, set()).update(_split_list(value))

    def apps_for(self, mime_types: Iterable[str]) -> list[DesktopApp]:
        """Programs registered for any of ``mime_types``, by name."""
        found: dict[str, DesktopApp] = {}
        for mime in mime_types:
            removed = self.removed.get(mime, set())
            added = [self.apps[i] for i in self.added.get(mime, []) if i in self.apps]
            listed = [app for app in self.apps.values() if mime in app.mime_types]
            for app in added + listed:
                if app.id not in removed:
                    found.setdefault(app.id, app)
        return sorted(found.values(), key=lambda app: (app.name.casefold(), app.id))

    def default_app(self, mime_types: Iterable[str]) -> DesktopApp | None:
        """``mimeapps.list`` default (most specific type first), else the preferred program."""
        mime_types = list(mime_types)
        for table in (self.defaults, self.added):
            for mime in mime_types:
                for app_id in table.get(mime, []):
                    if app_id in self.apps and app_id not in self.removed.get(mime, set()):
                        return self.apps[app_id]
        apps = self.apps_for(mime_types)
        return apps[0] if apps else None


@functools.cache
def catalog() -> AppCatalog:
    """The session's catalog, built on first use."""
    return AppCatalog()


def split_exec(line: str) -> list[str]:
    """Arguments of an ``Exec`` value: general escapes, then double quotes with ``\\`` escapes."""
    line = _unescape(line)
    args: list[str] = []
    current: list[str] = []
    quoted = in_arg = False
    chars = iter(line)
    for char in chars:
        if quoted:
            if char == "\\":
                current.append(next(chars, ""))
            elif char == '"':
                quoted = False
            else:
                current.append(char)
        elif char == '"':
            quoted = in_arg = True
        elif char in " \t":
            if in_arg:
                args.append("".join(current))
                current, in_arg = [], False
        else:
            current.append(char)
            in_arg = True
    if in_arg:
        args.append("".join(current))
    return args


def expand_exec(app: DesktopApp, path: Path) -> list[str]:
    """argv that opens ``path`` with ``app``; the path is always an argument of its own."""
    path = Path(path)
    values = {
        "%f": [str(path)],
        "%F": [str(path)],
        "%u": [path.as_uri()],
        "%U": [path.as_uri()],
        "%i": ["--icon", app.icon] if app.icon else [],
        "%c": [app.name],
        "%k": [str(app.path)],
    }
    argv: list[str] = []
    has_file = False
    for arg in split_exec(app.exec):
        if arg in values:
            argv.extend(values[arg])
            has_file |= arg in _FILE_CODES
        elif arg in _DEPRECATED_CODES:
            continue
        else:  # codes inside an argument (e.g. --file=%f) expand in place
            out, chars = [], iter(arg)
            for char in chars:
                if char != "%":
                    out.append(char)
                    continue
                code = "%" + next(chars, "")
                if code == "%%":
                    out.append("%")
                elif code in values and len(values[code]) == 1:
                    out.append(values[code][0])
                    has_file |= code in _FILE_CODES
            argv.append("".join(out))
    if not has_file:
        argv.append(str(path))
    return argv
