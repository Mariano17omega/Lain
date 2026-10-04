"""Whether a pull can start, without Qt (spec 15 R5: ``core/sync/request``)."""

from qe_studio.core.config import parse_config
from qe_studio.core.sync.request import NOT_CONFIGURED, SyncRefusal, SyncRequest, prepare_sync
from qe_studio.core.sync.rsync import Endpoint


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
