"""Shared pieces of the cluster mode tests (spec 65): a fake ``list_remote``, a window with a
cluster, and a local folder that the copies of a remote plot (spec 66) come from."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path, PurePosixPath

from PyQt6.QtWidgets import QMenu

from qe_studio.core import cancel
from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.remote.listing import NOT_FOUND, RemoteEntry, RemoteFailure
from qe_studio.core.sync import monitor
from qe_studio.core.sync.request import SyncRefusal, prepare_scratch
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui import remote_controller, sync_coordinator

REMOTE = "/scratch/usuario"
ACCOUNT = "usuario@hpc.example"
T0 = 1_761_400_000.0


def entries(*folders: str, files: tuple[str, ...] = ()) -> list[RemoteEntry]:
    """A listing: ``folders`` then ``files`` (100 bytes each)."""
    return [RemoteEntry(name, True, 4096, T0) for name in folders] + [
        RemoteEntry(name, False, 100, T0) for name in files
    ]


class FakeListing:
    """``list_remote`` of the tests: answers from ``folders`` (a folder → its entries or a
    ``RemoteFailure``; a folder not in it is missing on the "cluster") and keeps every folder asked.
    ``hold()`` makes the next calls wait for ``release()``, or for their task to be cancelled, which
    ``cancelled`` records."""

    def __init__(self, folders: dict | None = None):
        self.folders = dict(folders or {})
        self.calls: list[str] = []
        self.passwords: list[str | None] = []
        self.cancelled: list[str] = []
        self._gate = threading.Event()
        self._gate.set()
        self.exited = threading.Event()  # a held call is over (released or cancelled)

    def hold(self) -> None:
        self._gate.clear()
        self.exited.clear()

    def release(self) -> None:
        self._gate.set()

    def __call__(self, config, remote_dir, password=None):
        self.calls.append(remote_dir)
        self.passwords.append(password)
        try:
            while not self._gate.wait(0.02):
                if cancel.is_cancelled():
                    self.cancelled.append(remote_dir)
                    raise cancel.Cancelled
        finally:
            self.exited.set()
        return self.folders.get(remote_dir, RemoteFailure(NOT_FOUND, missing=True))


def remote_window(window_factory, demo_project, monkeypatch, fake, reachable=True, **cluster):
    """A window whose config has a cluster (``cluster`` overrides its keys) and ``remote_root``
    ``REMOTE``; ``fake`` stands in for ``list_remote`` and the reachability probe answers
    ``reachable`` without the network."""
    monkeypatch.setattr(remote_controller, "list_remote", fake)
    monkeypatch.setattr(monitor, "probe", lambda *_args, **_kwargs: reachable)
    settings = {"host": "hpc.example", "user": "usuario", **cluster}
    paths = {"local_root": str(demo_project), "remote_root": REMOTE}
    config = parse_config({"paths": paths, "cluster": settings})
    return window_factory(loaded=LoadedConfig(config, None))


def turn_on(qtbot, window, folder: str = REMOTE, timeout: int = 5000) -> None:
    """Click "Cluster" and wait until the grid's folder ``folder`` is listed."""
    with qtbot.waitSignal(
        window.remote.listed, timeout=timeout, check_params_cb=lambda d, _r: d == folder
    ):
        window.activity.remote.click()


def menu_spy(monkeypatch, choose: str | None = None) -> list[list[tuple[str, bool, str]]]:
    """``QMenu.exec`` patched: every menu shown as (text, enabled, tooltip) of its items; the item
    named ``choose`` is triggered."""
    menus: list[list[tuple[str, bool, str]]] = []

    def exec_(menu, *_args):
        actions = [a for a in menu.actions() if not a.isSeparator()]
        menus.append([(a.text(), a.isEnabled(), a.toolTip()) for a in actions])
        for action in actions:
            if action.text() == choose and action.isEnabled():
                action.trigger()
        return None

    monkeypatch.setattr(QMenu, "exec", exec_)
    return menus


def serve_locally(monkeypatch, cluster: Path, remote_root: str = REMOTE) -> None:
    """The copies of a remote plot (spec 66) come from ``cluster``, a local folder that stands for
    ``remote_root``: ``prepare_scratch`` as always, then a host-less endpoint under ``cluster``
    (the real rsync, no ssh). Patched where the coordinator imports it."""

    def prepare(config, mirror, *, resolved_root=None):
        request = prepare_scratch(config, mirror, resolved_root=resolved_root)
        if isinstance(request, SyncRefusal):
            return request
        relative = PurePosixPath(request.endpoint.path).relative_to(remote_root)
        return replace(request, endpoint=Endpoint(str(cluster.joinpath(*relative.parts))))

    monkeypatch.setattr(sync_coordinator, "prepare_scratch", prepare)
