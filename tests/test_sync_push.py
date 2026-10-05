"""Pushes through the real rsync binary (spec 27): only new files go up, a file the cluster
already has is never changed, nothing there is deleted and nothing local is touched.

Remote side: a local folder (host-less ``Endpoint``) or, for the remote ``mkdir -p`` and the two
authentications, the ``ssh_server`` fixture (see ``ssh_server.py``).
"""

import shlex
import shutil
from pathlib import Path

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.sync.push import PushController
from qe_studio.core.sync.report import SyncStatus
from qe_studio.core.sync.rsync import Endpoint

from ssh_server import HOST_ALIAS, PASSWORD, USER
from sync_helpers import T0, run_push, write

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")


def make_config(**sync):
    return parse_config({"sync": sync} if sync else {})  # the cluster is a local path here


def snapshot(root: Path) -> dict[str, tuple[bytes, float]]:
    """Every file under ``root``: content and mtime."""
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def dirs(tmp_path):
    """(local, remote): the same calculation folder on both sides, accents and spaces in the path."""
    local = tmp_path / "local" / "Simulações" / "scf Al"
    remote = tmp_path / "cluster" / "Simulações" / "scf Al"
    local.mkdir(parents=True)
    remote.mkdir(parents=True)
    return local, remote


def push(qtbot, local, remote, config=None, **kwargs):
    controller = PushController(config or make_config())
    return run_push(qtbot, controller, local, Endpoint(str(remote)), **kwargs)


def test_the_preview_comes_first_and_only_new_files_go_up(qtbot, dirs):
    local, remote = dirs
    write(local, "scf.in", "input")
    write(local, "job/scf.qsub", "qsub", T0 + 60)
    write(local, "scf.out", "local copy", T0 + 100)
    write(remote, "scf.out", "cluster copy")
    before = snapshot(remote)
    untouched, plans = [], []
    report = push(
        qtbot,
        local,
        remote,
        plans=plans,
        before_confirm=lambda plan: untouched.append(snapshot(remote) == before),
    )
    assert untouched == [True]  # nothing went up while the preview was open
    (plan,) = plans
    assert sorted(i.path for i in plan.new) == ["job/scf.qsub", "scf.in"]
    assert [i.path for i in plan.exists] == ["scf.out"]
    assert report.status is SyncStatus.DONE, report.error
    assert sorted(report.transferred) == ["job/scf.qsub", "scf.in"]
    assert report.existing == ["scf.out"] and "2 arquivo(s) enviado(s)." in report.message
    assert (remote / "scf.in").read_text() == "input"
    assert abs((remote / "job/scf.qsub").stat().st_mtime - (T0 + 60)) < 1  # dates kept
    assert (remote / "scf.out").read_text() == "cluster copy"


def test_declining_the_preview_sends_nothing(qtbot, dirs):
    local, remote = dirs
    write(local, "scf.in", "input")
    write(remote, "old.out", "keep")
    before = snapshot(remote)
    report = push(qtbot, local, remote, confirm=False)
    assert report.status is SyncStatus.CANCELLED and report.transferred == []
    assert snapshot(remote) == before


@pytest.mark.parametrize("remote_mtime", [T0 - 3600, T0 + 3600], ids=["older", "newer"])
def test_a_file_on_the_cluster_is_never_changed(qtbot, dirs, remote_mtime):
    local, remote = dirs
    write(local, "scf.in", "new local version, longer", T0)
    write(local, "extra.in", "extra")
    write(remote, "scf.in", "on the cluster", remote_mtime)
    write(remote, "only_there.out", "keep")
    local_before = snapshot(local)
    report = push(qtbot, local, remote)
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == ["extra.in"] and report.existing == ["scf.in"]
    assert (remote / "scf.in").read_text() == "on the cluster"
    assert abs((remote / "scf.in").stat().st_mtime - remote_mtime) < 1
    assert (remote / "only_there.out").read_text() == "keep"  # nothing deleted
    assert snapshot(local) == local_before  # nothing local touched


def test_nothing_new_is_nothing_to_send(qtbot, dirs):
    local, remote = dirs
    write(local, "same.in", "same")
    write(remote, "same.in", "same")  # identical: rsync -i does not even list it
    write(local, "scf.in", "local")
    write(remote, "scf.in", "on the cluster")  # differs (size): listed, never sent
    plans = []
    report = push(qtbot, local, remote, plans=plans)
    assert plans == [] and report.status is SyncStatus.UP_TO_DATE
    assert report.existing == ["scf.in"]
    assert report.message.splitlines()[0] == "Nada a enviar."


def test_a_new_remote_folder_is_created(qtbot, tmp_path):
    local = tmp_path / "local" / "bandas_Al_1"
    remote = tmp_path / "cluster" / "bandas_Al_1"
    remote.parent.mkdir()
    write(local, "bands.in", "bands")
    report = push(qtbot, local, remote)
    assert report.status is SyncStatus.DONE, report.error
    assert (remote / "bands.in").read_text() == "bands"


def test_a_file_created_on_the_cluster_after_the_preview_is_kept(qtbot, dirs):
    """--ignore-existing: the race between the preview and "Enviar" never overwrites."""
    local, remote = dirs
    write(local, "scf.in", "local")
    write(local, "other.in", "other")
    report = push(
        qtbot,
        local,
        remote,
        before_confirm=lambda plan: write(remote, "scf.in", "arrived meanwhile", T0 - 60),
    )
    assert report.status is SyncStatus.DONE, report.error
    assert (remote / "scf.in").read_text() == "arrived meanwhile"
    assert (remote / "other.in").read_text() == "other"


def test_excluded_files_never_go_up(qtbot, dirs):
    local, remote = dirs
    write(local, "scf.in", "input")
    write(local, "plots/bands.png", "figure")
    write(local, "bands.plot", "settings")
    write(local, "tmp/al.save/data-file.xml", "heavy")
    write(local, "al.wfc1", "heavy")
    report = push(qtbot, local, remote)
    assert report.status is SyncStatus.DONE, report.error
    assert report.transferred == ["scf.in"]
    assert sorted(snapshot(remote)) == ["scf.in"]


def test_confirm_plan_off_still_shows_the_preview(qtbot, dirs):
    local, remote = dirs
    write(local, "scf.in", "input")
    plans = []
    report = push(qtbot, local, remote, make_config(confirm_plan=False), confirm=False, plans=plans)
    assert len(plans) == 1 and report.status is SyncStatus.CANCELLED
    assert not (remote / "scf.in").exists()


# -- over ssh --------------------------------------------------------------------------------------
def ssh_push(qtbot, tmp_path, ssh_server, password=None, **options):
    """Push ``tmp_path/local/proj/bandas Al_1`` to the same path under the served folder, where
    neither level exists yet."""
    server, root = ssh_server
    local = tmp_path / "local" / "proj" / "bandas Al_1"
    write(local, "bands.in", "bands")
    write(local, "job/bandas.qsub", "qsub")
    write(local, "plots/bands.png", "figure")
    remote = root / "proj" / "bandas Al_1"
    config = parse_config(server.config_data(**options))
    controller = PushController(config, password=password)
    plans = []
    endpoint = Endpoint(str(remote), HOST_ALIAS, USER)
    report = run_push(qtbot, controller, local, endpoint, plans=plans)
    return report, remote, plans


def test_key_auth_push_makes_the_nested_remote_folder(qtbot, tmp_path, ssh_server):
    server, _root = ssh_server
    report, remote, plans = ssh_push(qtbot, tmp_path, ssh_server)
    assert report.status is SyncStatus.DONE, report.error
    assert sorted(i.path for i in plans[0].new) == ["bands.in", "job/bandas.qsub"]
    assert (remote / "bands.in").read_text() == "bands"
    assert (remote / "job/bandas.qsub").read_text() == "qsub"
    assert not (remote / "plots").exists()
    dry_run, transfer = server.commands()
    assert dry_run.startswith("rsync --server")  # nothing made before "Enviar"
    assert transfer.startswith(f"mkdir -p {shlex.quote(str(remote))} && rsync --server")
    assert not any("--sender" in command for command in server.commands())  # a push, not a pull
    assert {r.method for r in server.log} == {"publickey"}


def test_password_push_through_askpass(qtbot, tmp_path, ssh_server):
    server, _root = ssh_server
    report, remote, _plans = ssh_push(
        qtbot, tmp_path, ssh_server, password=PASSWORD, auth="password"
    )
    assert report.status is SyncStatus.DONE, report.error
    assert (remote / "bands.in").read_text() == "bands"
    assert {r.method for r in server.log} == {"password"}


@pytest.mark.parametrize("auth", ["key", "password"])
@pytest.mark.parametrize("strict", ["no", "accept-new"])
def test_a_permissive_ssh_config_cannot_accept_an_unknown_host_on_push(
    qtbot, tmp_path, ssh_server, auth, strict
):
    server, root = ssh_server
    report, remote, plans = ssh_push(
        qtbot,
        tmp_path,
        ssh_server,
        password=PASSWORD,
        auth=auth,
        strict=strict,
        known_hosts="empty",
    )
    assert report.status is SyncStatus.FAILED
    assert "Chave do host" in report.error
    assert plans == []  # refused before the dry run listed anything
    assert server.attempts == [] and server.log == []
    assert (server.workdir / "known_hosts").read_text() == ""
    assert not (root / "proj").exists()
