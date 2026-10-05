"""What the sync window says, without Qt (spec 17): the plan preview's groups and summary, the
scope of the Rsync button and the menu, and the full report behind the toast's "Detalhes"."""

from pathlib import Path

from qe_studio.core.config import parse_config
from qe_studio.core.sync.planner import LARGE_FILE_BYTES, Action, PlanItem, SyncPlan
from qe_studio.core.sync.preview import (
    SYNCED_FOLDER,
    format_mtime,
    large_summary,
    plan_groups,
    plan_summary,
)
from qe_studio.core.sync.report import DETAILS_MAX_FILES, SyncReport, SyncStatus
from qe_studio.core.sync.request import SYNC_OFF, sync_scope
from qe_studio.core.sync.rsync import Endpoint

T0 = 1_700_000_000.0
MB = 1024**2


def item(path, action=Action.NEW, size=1024):
    return PlanItem(path, action, size, T0, None if action is Action.NEW else T0 - 60)


def test_groups_by_action_then_folder_largest_first():
    plan = SyncPlan(
        [
            item("b/small.out", size=10),
            item("scf.out", Action.UPDATE),
            item("b/big.wfc1", size=150 * MB),
            item("a/x.out"),
            item("top.out"),
            item("b/mid.dat", size=5 * MB),
            item("mine.dat", Action.LOCAL_NEWER),
        ]
    )
    groups = plan_groups(plan)
    assert [(g.action, g.folder) for g in groups] == [
        (Action.NEW, "."),
        (Action.NEW, "a"),
        (Action.NEW, "b"),
        (Action.UPDATE, "."),
        (Action.LOCAL_NEWER, "."),
    ]
    b = groups[2]
    assert [i.name for i in b.items] == ["big.wfc1", "mid.dat", "small.out"]
    assert b.has_large and not groups[1].has_large
    assert b.size == 155 * MB + 10 and b.label == "b/" and groups[0].label == SYNCED_FOLDER


def test_summary_counts_sizes_and_leaves_out_empty_parts():
    plan = SyncPlan(
        [item(f"n{i}", size=MB) for i in range(12)]
        + [item(f"u{i}", Action.UPDATE, MB // 2) for i in range(3)]
        + [item(f"l{i}", Action.LOCAL_NEWER) for i in range(2)]
    )
    assert plan_summary(plan) == (
        "12 arquivos novos (12.0 MB) · 3 a atualizar (1.5 MB) · "
        "2 mais recentes no computador (não serão alterados)"
    )
    assert plan_summary(SyncPlan([item("one")])) == "1 arquivo novo (1.0 KB)"
    assert plan_summary(SyncPlan([item("u", Action.UPDATE)])) == "1 a atualizar (1.0 KB)"


def test_large_summary_only_when_something_is_large():
    assert large_summary(SyncPlan([item("a", size=LARGE_FILE_BYTES)])) is None
    one = SyncPlan([item("a", size=150 * MB), item("b")])
    assert large_summary(one) == "1 arquivo grande soma 150.0 MB"
    two = SyncPlan([item("a", size=7 * 1024 * MB), item("b", Action.UPDATE, 7 * 1024 * MB)])
    assert large_summary(two) == "2 arquivos grandes somam 14.0 GB"


def test_format_mtime():
    assert format_mtime(None) == "—"
    assert format_mtime(T0).count("/") == 2


def config(tmp_path, cluster=True):
    data = {"paths": {"local_root": str(tmp_path)}}
    if cluster:
        data["paths"]["remote_root"] = "/scratch/me"
        data["cluster"] = {"host": "hpc.example", "user": "me"}
    return parse_config(data)


def test_scope_of_a_subfolder(tmp_path):
    scope = sync_scope(config(tmp_path), tmp_path / "a" / "b")
    assert "a/b (e subpastas)" in scope.tooltip and scope.tooltip.startswith("Baixar do cluster")
    assert scope.menu_text == "Sincronizar a/b" and scope.local_text == "a/b"
    assert scope.remote == "me@hpc.example:/scratch/me/a/b/"


def test_scope_of_the_root(tmp_path):
    scope = sync_scope(config(tmp_path), tmp_path)
    assert scope.whole_project and scope.tooltip == "Baixar do cluster: tudo"
    assert scope.menu_text == "Sincronizar tudo" and scope.local_text == "."


def test_scope_of_a_project(tmp_path):
    cfg = config(tmp_path)
    scope = sync_scope(cfg, tmp_path / "ilita", project="ilita")  # what "Sincronizar projeto" says
    assert scope.tooltip == "Baixar do cluster: projeto ilita"
    assert scope.menu_text == "Sincronizar projeto ilita" and scope.local_text == "ilita"
    assert scope.remote == "me@hpc.example:/scratch/me/ilita/"
    plain = sync_scope(cfg, tmp_path / "ilita")  # the same folder as a plain pull: as before
    assert plain.menu_text == "Sincronizar ilita" and "ilita (e subpastas)" in plain.tooltip


def test_scope_with_sync_off(tmp_path):
    scope = sync_scope(config(tmp_path, cluster=False), tmp_path / "a")
    assert scope.tooltip == SYNC_OFF and not scope.enabled and scope.remote == ""


def test_scope_keeps_the_end_of_a_long_path_in_the_menu(tmp_path):
    deep = "/".join(["pasta_longa"] * 6)
    scope = sync_scope(config(tmp_path), tmp_path / deep)
    assert scope.menu_text.startswith("Sincronizar …") and scope.menu_text.endswith("pasta_longa")
    assert deep in scope.tooltip  # the tooltip has it all


def test_scope_takes_the_endpoint_of_a_prepared_run(tmp_path):
    scope = sync_scope(config(tmp_path, cluster=False), tmp_path / "a", Endpoint("/remote/a"))
    assert scope.remote == "/remote/a/"


def test_report_details_list_every_file():
    many = [f"f{i:04}.out" for i in range(DETAILS_MAX_FILES + 5)]
    report = SyncReport(
        SyncStatus.DONE,
        Path("/home/me/proj/a"),
        Endpoint("/scratch/me/a", "hpc", "me"),
        transferred=many,
        skipped=["scf.out"],
    )
    details = report.details
    assert details.startswith(report.message)
    assert "Pasta local: /home/me/proj/a" in details and "Cluster: me@hpc:/scratch/me/a/" in details
    assert f"Baixados ({len(many)}):" in details and "… e mais 5" in details
    assert "Mantidos na versão local (1):\n  scf.out" in details
    assert "Mais recentes no computador" not in details
