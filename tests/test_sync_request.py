"""Whether a pull can start, without Qt (spec 15 R5: ``core/sync/request``)."""

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.sync.request import (
    NOT_CONFIGURED,
    Direction,
    SyncRefusal,
    SyncRequest,
    prepare_push,
    prepare_sync,
    push_availability,
    sync_scope,
)
from qe_studio.core.sync.rsync import Endpoint, remote_dir_for


def config(tmp_path, **cluster):
    return parse_config(
        {
            "paths": {"local_root": str(tmp_path), "remote_root": "/scratch/me/proj"},
            "cluster": {"host": "hpc", "user": "me", **cluster},
        }
    )


def test_not_configured_is_refused_with_a_hint(tmp_path):
    bare = parse_config({"paths": {"local_root": str(tmp_path)}})
    assert prepare_sync(bare, tmp_path) == SyncRefusal("info", NOT_CONFIGURED)


def test_a_folder_outside_the_project_is_refused(tmp_path):
    refusal = prepare_sync(config(tmp_path / "proj"), tmp_path / "elsewhere")
    assert isinstance(refusal, SyncRefusal) and refusal.level == "warning"
    assert "não está dentro da pasta local configurada" in refusal.message


def test_the_remote_folder_mirrors_the_local_one(tmp_path):
    (tmp_path / "03_bands").mkdir()
    request = prepare_sync(config(tmp_path), tmp_path / "03_bands")
    assert request == SyncRequest(
        tmp_path / "03_bands", Endpoint("/scratch/me/proj/03_bands", "hpc", "me"), False
    )
    whole = prepare_sync(config(tmp_path), tmp_path)
    assert isinstance(whole, SyncRequest) and whole.endpoint.path == "/scratch/me/proj"


def test_password_auth_without_a_password_asks_for_one(tmp_path, monkeypatch):
    monkeypatch.delenv("LAIN_TEST_PW", raising=False)
    asking = prepare_sync(config(tmp_path, auth="password", password_env="LAIN_TEST_PW"), tmp_path)
    assert isinstance(asking, SyncRequest) and asking.needs_password
    monkeypatch.setenv("LAIN_TEST_PW", "s3cret")
    known = prepare_sync(config(tmp_path, auth="password", password_env="LAIN_TEST_PW"), tmp_path)
    assert isinstance(known, SyncRequest) and not known.needs_password


@pytest.mark.parametrize("cluster", [True, False])
@pytest.mark.parametrize("where", ["root", "inside", "deep", "missing", "outside"])
@pytest.mark.parametrize("linked", [False, True])
def test_a_resolved_root_changes_nothing_but_the_resolves(tmp_path, cluster, where, linked):
    """``resolved_root=`` (spec 27-8 R3) is the root the call would have resolved itself."""
    real = tmp_path / "real"
    (real / "a" / "b").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    root = real
    if linked:
        root = tmp_path / "link"
        root.symlink_to(real, target_is_directory=True)
    cfg = config(root) if cluster else parse_config({"paths": {"local_root": str(root)}})
    folder = {
        "root": root,
        "inside": root / "a",
        "deep": root / "a" / "b",
        "missing": root / "nope",
        "outside": tmp_path / "elsewhere",
    }[where]
    resolved = root.resolve()
    for direction in Direction:
        assert sync_scope(cfg, folder, direction=direction) == sync_scope(
            cfg, folder, direction=direction, resolved_root=resolved
        )
    assert prepare_sync(cfg, folder) == prepare_sync(cfg, folder, resolved_root=resolved)
    assert prepare_push(cfg, folder) == prepare_push(cfg, folder, resolved_root=resolved)
    assert push_availability(cfg, folder) == push_availability(cfg, folder, resolved_root=resolved)
    if cluster and where != "outside":
        assert remote_dir_for(folder, cfg) == remote_dir_for(folder, cfg, resolved_root=resolved)


def test_the_scope_says_the_cluster_side_of_its_folder(tmp_path):
    (tmp_path / "a").mkdir()
    scope = sync_scope(config(tmp_path), tmp_path / "a")
    assert (scope.relative, scope.remote) == ("a", "me@hpc:/scratch/me/proj/a/")
    assert sync_scope(config(tmp_path), tmp_path / "..").remote == ""  # outside: no cluster side
