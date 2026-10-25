"""The state of the cluster mode, without Qt (spec 65 R2): which folder of the cluster stands for
which local one, how far up the view goes, and what was listed in this session.

The window's paths are built on ``paths.local_root`` as the config gives it, never resolved, so the
mapping is path arithmetic: nothing here touches the disk. The cache lives in memory, for the
session only; a listing older than ``STALE_SECONDS`` is still shown, and listed again.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..config import AppConfig
from ..sync.rsync import remote_dir_of
from .listing import RemoteEntry

STALE_SECONDS = 60


@dataclass(frozen=True)
class _Listing:
    entries: tuple[RemoteEntry, ...]
    at: float  # the caller's clock at ``put``


class RemoteBrowser:
    def __init__(self, config: AppConfig, view_root: Path):
        self.local_root = Path(config.paths.local_root)
        self.remote_root = config.paths.remote_root
        cluster = config.cluster
        self.account = f"{cluster.user}@{cluster.host}"
        self._cache: dict[str, _Listing] = {}
        self.top = ""
        self.set_view_root(view_root)

    def set_view_root(self, view_root: Path) -> None:
        """The folder the window shows as its top (spec 31: the selected project, else the root):
        ``top`` is its cluster side, the highest folder the mode shows."""
        self.top = self.remote_of(view_root)

    # -- local ↔ cluster ---------------------------------------------------------------------------
    def remote_of(self, local_folder: Path) -> str:
        """The cluster side of ``local_folder``, which lies inside ``paths.local_root`` (else
        ``ValueError``)."""
        return remote_dir_of(Path(local_folder), self.local_root, self.remote_root)

    def mirror_of(self, remote_dir: str) -> Path:
        """The local folder at the same path relative to the roots (it may not exist)."""
        relative = PurePosixPath(remote_dir).relative_to(self.remote_root)
        return self.local_root.joinpath(*relative.parts)

    def inside(self, remote_dir: str) -> bool:
        """``remote_dir`` is ``top`` or below it."""
        return PurePosixPath(remote_dir).is_relative_to(self.top)

    def parent(self, remote_dir: str) -> str | None:
        """The folder above ``remote_dir``; None at ``top`` (never above it) and outside it."""
        if remote_dir == self.top or not self.inside(remote_dir):
            return None
        return str(PurePosixPath(remote_dir).parent)

    @staticmethod
    def child(remote_dir: str, name: str) -> str:
        return str(PurePosixPath(remote_dir) / name)

    def label(self, remote_dir: str) -> str:
        """``usuario@host:/caminho``: what the footer shows."""
        return f"{self.account}:{remote_dir}"

    # -- the cache of the session -----------------------------------------------------------------
    def put(self, remote_dir: str, entries: Iterable[RemoteEntry], now: float) -> None:
        self._cache[remote_dir] = _Listing(tuple(entries), now)

    def get(self, remote_dir: str) -> list[RemoteEntry] | None:
        listing = self._cache.get(remote_dir)
        return list(listing.entries) if listing is not None else None

    def needs_refresh(self, remote_dir: str, now: float) -> bool:
        """Never listed, or listed more than ``STALE_SECONDS`` before ``now``."""
        listing = self._cache.get(remote_dir)
        return listing is None or now - listing.at > STALE_SECONDS

    def invalidate(self, remote_dir: str | None = None) -> None:
        """Forget the listing of ``remote_dir``, or every one (None)."""
        if remote_dir is None:
            self._cache.clear()
        else:
            self._cache.pop(remote_dir, None)
