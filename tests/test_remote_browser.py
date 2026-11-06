"""The state of the cluster mode (spec 65 R2): local ↔ cluster folders, the top of the view and the
cache of the session."""

from pathlib import Path

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote.browser import STALE_SECONDS, RemoteBrowser
from qe_studio.core.remote.download import only_file_rules
from qe_studio.core.remote.listing import RemoteEntry
from qe_studio.core.sync.request import SyncScope

ROOT = Path("/home/u/simulacoes")


def browser(view_root: Path = ROOT, remote_root: str = "/scratch/u/sims") -> RemoteBrowser:
    config = parse_config(
        {
            "paths": {"local_root": str(ROOT), "remote_root": remote_root},
            "cluster": {"host": "hpc", "user": "u"},
        }
    )
    return RemoteBrowser(config, view_root)


def test_the_root_and_its_cluster_side():
    b = browser()
    assert b.top == "/scratch/u/sims"
    assert b.remote_of(ROOT / "ilita" / "Bandas") == "/scratch/u/sims/ilita/Bandas"
    assert b.mirror_of("/scratch/u/sims/ilita/Bandas") == ROOT / "ilita" / "Bandas"
    assert b.mirror_of(b.top) == ROOT
    assert b.label("/scratch/u/sims/x") == "u@hpc:/scratch/u/sims/x"
    with pytest.raises(ValueError):
        b.remote_of(Path("/elsewhere"))


def test_a_project_is_the_top():
    b = browser(ROOT / "ilita")
    assert b.top == "/scratch/u/sims/ilita"
    assert b.parent("/scratch/u/sims/ilita/A/B") == "/scratch/u/sims/ilita/A"
    assert b.parent("/scratch/u/sims/ilita/A") == "/scratch/u/sims/ilita"
    assert b.parent(b.top) is None  # never above the top
    assert b.parent("/scratch/u/sims/outro") is None and not b.inside("/scratch/u/sims/outro")
    b.set_view_root(ROOT)
    assert b.parent("/scratch/u/sims/ilita") == "/scratch/u/sims"


def test_a_relative_remote_root():
    b = browser(remote_root="sims")
    assert b.top == "sims" and b.remote_of(ROOT / "a") == "sims/a"
    assert b.mirror_of("sims/a") == ROOT / "a" and b.child("sims", "a b") == "sims/a b"


def test_the_cache_and_its_age():
    b, folder = browser(), "/scratch/u/sims/a"
    entries = [RemoteEntry("scf.out", False, 10, 0.0)]
    assert b.get(folder) is None and b.needs_refresh(folder, 100.0)
    b.put(folder, entries, 100.0)
    assert b.get(folder) == entries
    assert not b.needs_refresh(folder, 100.0 + STALE_SECONDS)
    assert b.needs_refresh(folder, 100.0 + STALE_SECONDS + 1)
    b.put("/scratch/u/sims", [], 100.0)
    b.invalidate(folder)
    assert b.get(folder) is None and b.get("/scratch/u/sims") == []
    b.invalidate()
    assert b.get("/scratch/u/sims") is None


@pytest.mark.parametrize(
    ("name", "include"),
    [
        ("a[1].in", "/a\\[1].in"),
        ("x*y.out", "/x\\*y.out"),
        ("q?.in", "/q\\?.in"),
        ("w\\[1]", "/w\\\\\\[1]"),  # a backslash is escaped in a wildcard pattern
        ("plain\\name", "/plain\\name"),  # and compared as is in a literal one
        ("com espaço.out", "/com espaço.out"),
    ],
)
def test_only_file_rules(name, include):
    assert only_file_rules(name) == [f"--include={include}", "--exclude=*"]


def test_the_scope_of_one_file():
    scope = SyncScope(
        "ilita/Bandas", "u@hpc:/scratch/u/sims/ilita/Bandas/bands.out", file="bands.out"
    )
    assert scope.title == "Baixar do cluster: ilita/Bandas/bands.out"
    assert scope.local_text == "ilita/Bandas/bands.out"
    at_root = SyncScope("", file="scf.out")
    assert at_root.title == "Baixar do cluster: scf.out" and at_root.local_text == "scf.out"
