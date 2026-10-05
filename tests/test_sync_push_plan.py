"""What a push plans, previews, reports and refuses, without Qt (spec 27 R2, R3.4, R4.1, R4.3)."""

import os
from pathlib import Path

from qe_studio.core.config import parse_config
from qe_studio.core.sync.planner import Action, PlanItem, SyncPlan
from qe_studio.core.sync.preview import (
    LARGE_TIP,
    PUSH_LARGE_TIP,
    describe_plan,
    large_summary,
    push_summary,
)
from qe_studio.core.sync.push_plan import PushAction, PushItem, PushPlan, build_push_plan
from qe_studio.core.sync.report import PushReport, SyncReport, SyncStatus
from qe_studio.core.sync.request import (
    NOT_CONFIGURED,
    PUSH_PROJECT,
    PUSH_ROOT,
    SYNC_OFF,
    Direction,
    PushRequest,
    SyncRefusal,
    prepare_push,
    push_availability,
    sync_scope,
)
from qe_studio.core.sync.rsync import DryRunItem, Endpoint, parse_dry_run

T0 = 1_700_000_000.0
MB = 1024**2


def local_file(root: Path, rel: str, size: int, mtime: float = T0) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


def test_new_files_go_up_and_the_rest_only_exists(tmp_path):
    local_file(tmp_path, "scf.in", 3)
    local_file(tmp_path, "sub/job.qsub", 5, T0 + 60)
    local_file(tmp_path, "scf.out", 7)
    records = [
        DryRunItem("<f+++++++++", 99, 0.0, "scf.in"),  # sizes and dates come from the disk
        DryRunItem("<f+++++++++", 5, T0, "sub/job.qsub"),
        DryRunItem("<f.st......", 7, T0, "scf.out"),
        DryRunItem("cd+++++++++", 0, T0, "sub"),  # a folder: never an item
        DryRunItem("<f+++++++++", 1, T0, "gone.in"),  # removed since the dry run
    ]
    plan = build_push_plan(records, tmp_path)
    assert [(i.path, i.action) for i in plan.items] == [
        ("scf.in", PushAction.NEW),
        ("sub/job.qsub", PushAction.NEW),
        ("scf.out", PushAction.EXISTS),
    ]
    assert plan.items[0].size == 3 and plan.items[1].mtime == T0 + 60
    assert [i.path for i in plan.new] == ["scf.in", "sub/job.qsub"]
    assert [i.path for i in plan.exists] == ["scf.out"]
    assert plan.total_bytes == 8 and plan.large == []


def test_the_plan_reads_rsyncs_push_listing(tmp_path):
    local_file(tmp_path, "a b.in", 1)
    output = "created directory /x\n<f+++++++++|1|2023/11/14-22:13:20|a b.in\n"
    plan = build_push_plan(parse_dry_run(output), tmp_path)
    assert [(i.path, i.action) for i in plan.items] == [("a b.in", PushAction.NEW)]


def test_a_plan_with_nothing_new_has_nothing_to_send(tmp_path):
    local_file(tmp_path, "scf.in", 3)
    plan = build_push_plan([DryRunItem("<f..t......", 3, T0, "scf.in")], tmp_path)
    assert plan.new == [] and len(plan.exists) == 1
    assert push_summary(plan) == "1 já existe no cluster (não será alterado)"
    assert push_summary(PushPlan()) == "Nada a enviar."


def item(path, action=PushAction.NEW, size=1024):
    return PushItem(path, action, size, T0)


def test_push_preview_has_two_sections_the_second_closed_and_dimmed():
    plan = PushPlan(
        [
            item("scf.in", size=MB),
            item("sub/big.dat", size=150 * MB),
            item("scf.out", PushAction.EXISTS, 10),
            item("old/x.in", PushAction.EXISTS, 20),
        ]
    )
    preview = describe_plan(plan)
    assert preview.date_header == "Data local" and preview.large_tip == PUSH_LARGE_TIP
    assert preview.summary == (
        "2 arquivos a enviar (151.0 MB) · 2 já existem no cluster (não serão alterados)"
    )
    assert preview.large == "1 arquivo grande soma 150.0 MB" == large_summary(plan)
    send, exists = preview.sections
    assert send.title == "Serão enviados (2 · 151.0 MB)" and send.expanded and not send.dimmed
    assert exists.title == "Já existem no cluster, não serão alterados (2)"
    assert not exists.expanded and exists.dimmed
    assert [g.label for g in send.groups] == ["(pasta sincronizada)", "sub/"]
    assert send.groups[1].has_large and send.groups[1].rows[0].large
    assert [g.label for g in exists.groups] == ["(pasta sincronizada)", "old/"]
    assert exists.groups[0].rows[0].note == "não será alterado"


def test_the_pull_preview_is_what_it_was():
    plan = SyncPlan(
        [
            PlanItem("a.out", Action.NEW, 10, T0),
            PlanItem("scf.out", Action.UPDATE, 20, T0, T0 - 60),
        ]
    )
    preview = describe_plan(plan)
    assert preview.date_header == "Data no cluster" and preview.large_tip == LARGE_TIP
    assert [(s.title, s.note, s.expanded, s.dimmed) for s in preview.sections] == [
        ("Novos (1)", "", True, False),
        ("A atualizar (1)", "pedirá confirmação", True, False),
    ]
    row = preview.sections[1].groups[0].rows[0]
    assert (row.name, row.size, row.note) == ("scf.out", 20, "pedirá confirmação")


def report(status, **fields) -> PushReport:
    return PushReport(status, Path("/p/run"), Endpoint("/scratch/run", "hpc", "me"), **fields)


def test_push_report_says_what_went_up_and_what_was_left_alone():
    done = report(SyncStatus.DONE, transferred=["a.in", "b.qsub"], existing=["scf.out"])
    assert done.message == (
        "2 arquivo(s) enviado(s).\n1 já existiam no cluster e não foram alterados."
    )
    assert "Enviados (2):\n  a.in\n  b.qsub" in done.details
    assert "Já existiam no cluster (não alterados) (1):\n  scf.out" in done.details
    assert "Cluster: me@hpc:/scratch/run/" in done.details
    assert (
        not done.changes_local and SyncReport(SyncStatus.DONE, Path(), Endpoint("")).changes_local
    )
    assert report(SyncStatus.UP_TO_DATE).message == "Nada a enviar."
    assert report(SyncStatus.CANCELLED).message == "Envio cancelado."
    assert report(SyncStatus.FAILED, error="x").message == "Falha no envio: x"


def config(root, **cluster):
    return parse_config(
        {
            "paths": {"local_root": str(root), "remote_root": "/scratch/me/proj"},
            "cluster": {"host": "hpc", "user": "me", **cluster},
        }
    )


def test_prepare_push(tmp_path):
    (tmp_path / "ilita" / "bandas_1").mkdir(parents=True)
    run = tmp_path / "ilita" / "bandas_1"
    request = prepare_push(config(tmp_path), run)
    assert request == PushRequest(
        run, Endpoint("/scratch/me/proj/ilita/bandas_1", "hpc", "me"), False
    )
    assert prepare_push(config(tmp_path), tmp_path) == SyncRefusal("warning", PUSH_ROOT)
    # A project (a first-level folder) is not a calculation folder (spec 31 R5.2).
    assert prepare_push(config(tmp_path), tmp_path / "ilita") == SyncRefusal(
        "warning", PUSH_PROJECT
    )
    outside = prepare_push(config(tmp_path / "proj"), tmp_path / "elsewhere")
    assert isinstance(outside, SyncRefusal) and outside.level == "warning"
    missing = prepare_push(config(tmp_path), tmp_path / "nope")
    assert isinstance(missing, SyncRefusal) and "Pasta não encontrada" in missing.message
    bare = parse_config({"paths": {"local_root": str(tmp_path)}})
    assert prepare_push(bare, run) == SyncRefusal("info", NOT_CONFIGURED)


def test_push_availability_is_the_disabled_items_reason(tmp_path):
    (tmp_path / "ilita" / "run").mkdir(parents=True)
    run = tmp_path / "ilita" / "run"
    assert push_availability(config(tmp_path), run) == ""
    assert push_availability(config(tmp_path), tmp_path) == PUSH_ROOT
    assert push_availability(config(tmp_path), tmp_path / "ilita") == PUSH_PROJECT
    bare = parse_config({"paths": {"local_root": str(tmp_path)}})
    assert push_availability(bare, run) == SYNC_OFF


def test_push_scope_wording(tmp_path):
    cfg = config(tmp_path)
    scope = sync_scope(cfg, tmp_path / "a" / "b", direction=Direction.PUSH)
    assert scope.title == "Enviar para o cluster: a/b (e subpastas)"
    assert scope.menu_text == "Enviar a/b ao cluster…" and scope.available
    assert scope.window_title == "Enviando para o cluster" and scope.confirm_text == "Enviar"
    assert scope.remote == "me@hpc:/scratch/me/proj/a/b/"
    root = sync_scope(cfg, tmp_path, direction=Direction.PUSH)
    assert root.menu_text == "Enviar pasta ao cluster…" and not root.available
    assert root.tooltip == PUSH_ROOT
    project = sync_scope(cfg, tmp_path / "a", direction=Direction.PUSH)
    assert project.menu_text == "Enviar pasta ao cluster…" and not project.available
    assert project.tooltip == PUSH_PROJECT
    pull = sync_scope(cfg, tmp_path / "a")
    assert pull.window_title == "Sincronizando com o cluster" and pull.confirm_text == "Baixar"
    assert pull.title == "Baixar do cluster: a (e subpastas)" and pull.available
    off = sync_scope(parse_config({}), tmp_path, direction=Direction.PUSH)
    assert off.tooltip == SYNC_OFF and not off.available
