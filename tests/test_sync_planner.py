import os

import pytest

from qe_studio.core.sync.planner import (
    LARGE_FILE_BYTES,
    Action,
    ConflictResolver,
    Decision,
    PlanItem,
    PlanStatus,
    SyncPlan,
    build_plan,
    total_size,
)
from qe_studio.core.sync.rsync import DryRunItem

T0 = 1_700_000_000.0


def local_file(root, rel, mtime, content="local"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    os.utime(path, (mtime, mtime))
    return path


def record(rel, mtime, size=5):
    return DryRunItem(">f.st......", size, mtime, rel)


def test_actions(tmp_path):
    local_file(tmp_path, "older.out", T0)
    local_file(tmp_path, "newer.out", T0 + 100)
    local_file(tmp_path, "same.out", T0, "12345")
    local_file(tmp_path, "resized.out", T0, "123")
    plan = build_plan(
        [
            record("missing.out", T0),
            record("older.out", T0 + 100),
            record("newer.out", T0),
            record("same.out", T0 + 1),
            record("resized.out", T0),
            DryRunItem("cd+++++++++", 0, T0, "dir/"),
        ],
        tmp_path,
    )
    actions = {item.path: item.action for item in plan.items}
    assert actions == {
        "missing.out": Action.NEW,
        "older.out": Action.UPDATE,
        "newer.out": Action.LOCAL_NEWER,
        "resized.out": Action.UPDATE,
    }
    assert plan.status is PlanStatus.PENDING
    assert [i.path for i in plan.conflicts] == ["older.out", "resized.out"]


def test_folder_local_newer_rule(tmp_path):
    local_file(tmp_path, "a/x.out", T0 + 100)
    local_file(tmp_path, "b/y.out", T0 + 100)
    plan = build_plan(
        [record("a/x.out", T0), record("b/y.out", T0), record("b/z.out", T0)], tmp_path
    )
    assert plan.local_newer_folders == ["a"]
    assert plan.status is PlanStatus.PENDING  # b/z.out is new

    only_local_newer = build_plan([record("a/x.out", T0)], tmp_path)
    assert only_local_newer.status is PlanStatus.LOCAL_NEWER
    assert build_plan([], tmp_path).status is PlanStatus.UP_TO_DATE


def test_local_only_files_do_not_count(tmp_path):
    # Generated figures exist only locally; rsync's dry run never lists them.
    local_file(tmp_path, "plots/bands.png", T0 + 10_000)
    plan = build_plan([record("bands.dat.gnu", T0)], tmp_path)
    assert plan.status is PlanStatus.PENDING
    assert [i.action for i in plan.items] == [Action.NEW]


def item(path):
    return PlanItem(path, Action.UPDATE, 1, T0, T0 - 10)


def test_resolver_decisions():
    resolver = ConflictResolver([item("a.out"), item("sub/x"), item("sub/y"), item("z.out")])
    assert resolver.next_conflict().path == "a.out"
    resolver.resolve(Decision.OVERWRITE)
    assert resolver.next_conflict().path == "sub/x"
    resolver.resolve(Decision.OVERWRITE_FOLDER)
    assert resolver.next_conflict().path == "z.out"  # sub/y approved automatically
    resolver.resolve(Decision.SKIP)
    assert resolver.done
    assert [i.path for i in resolver.approved] == ["a.out", "sub/x", "sub/y"]
    assert [i.path for i in resolver.skipped] == ["z.out"]


def test_resolver_cancel():
    resolver = ConflictResolver([item("a"), item("b")])
    resolver.resolve(Decision.CANCEL)
    assert resolver.cancelled and resolver.done and resolver.next_conflict() is None
    with pytest.raises(RuntimeError):
        ConflictResolver([]).resolve(Decision.SKIP)


def test_large_is_strictly_above_the_threshold():
    assert LARGE_FILE_BYTES == 100 * 1024**2
    assert not PlanItem("a", Action.NEW, LARGE_FILE_BYTES, T0).is_large
    assert PlanItem("a", Action.NEW, LARGE_FILE_BYTES + 1, T0).is_large


def test_plan_large_lists_big_items_of_any_action():
    big = LARGE_FILE_BYTES + 1
    items = [
        PlanItem("new.wfc", Action.NEW, big, T0),
        PlanItem("small.out", Action.NEW, 1024, T0),
        PlanItem("charge.dat", Action.UPDATE, big, T0, T0 - 10),
        PlanItem("mine.dat", Action.LOCAL_NEWER, big, T0, T0 + 10),
    ]
    plan = SyncPlan(items)
    assert [item.path for item in plan.large] == ["new.wfc", "charge.dat", "mine.dat"]
    assert total_size(plan.new) == big + 1024 and total_size([]) == 0
