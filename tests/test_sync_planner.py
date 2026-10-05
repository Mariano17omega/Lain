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
    recheck_local,
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


# -- recheck_local (spec 27-3 R3.1) ----------------------------------------------------------------
def planned(tmp_path, rel, mtime, content="local"):
    """The plan item of a file that is there, as ``build_plan`` records it."""
    local_file(tmp_path, rel, mtime, content)
    (item,) = build_plan([record(rel, mtime + 100, size=1)], tmp_path).items
    assert item.action is Action.UPDATE and item.local_size == len(content)
    return item


def test_build_plan_records_the_size_of_the_local_file(tmp_path):
    local_file(tmp_path, "a.out", T0, "12345")
    plan = build_plan([record("a.out", T0 + 100), record("new.out", T0)], tmp_path)
    old, new = plan.items
    assert (old.local_mtime, old.local_size) == (T0, 5)
    assert (new.local_mtime, new.local_size) == (None, None)


def test_recheck_keeps_what_is_as_planned(tmp_path):
    item = planned(tmp_path, "a.out", T0)
    new = PlanItem("new.out", Action.NEW, 3, T0)
    result = recheck_local([item, new], tmp_path)
    assert result.keep == [item, new] and result.changed == []


def test_recheck_finds_an_edit_by_date_or_by_size(tmp_path):
    by_date = planned(tmp_path, "a.out", T0)
    by_size = planned(tmp_path, "b.out", T0)
    os.utime(tmp_path / "a.out", (T0 + 5, T0 + 5))
    local_file(tmp_path, "b.out", T0, "longer content")  # same mtime, other size
    result = recheck_local([by_date, by_size], tmp_path)
    assert result.keep == [] and result.changed == [by_date, by_size]


def test_recheck_finds_a_new_file_that_appeared_and_one_that_vanished(tmp_path):
    gone = planned(tmp_path, "gone.out", T0)
    (tmp_path / "gone.out").unlink()
    appeared = PlanItem("late.out", Action.NEW, 3, T0)
    local_file(tmp_path, "late.out", T0)
    result = recheck_local([gone, appeared], tmp_path)
    assert result.changed == [gone, appeared] and result.keep == []


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs a folder the user cannot search (not on Windows, not as root)",
)
def test_recheck_does_not_trust_a_file_it_cannot_stat(tmp_path):
    item = planned(tmp_path, "a.out", T0)
    (tmp_path / "a.out").unlink()
    (tmp_path / "a.out").mkdir()
    (tmp_path / "a.out" / "x").write_text("x")
    os.chmod(
        tmp_path / "a.out", 0
    )  # not searchable: stat of a.out itself works, of its content not
    try:
        assert recheck_local([PlanItem("a.out/x", Action.NEW, 1, T0), item], tmp_path).keep == []
    finally:
        os.chmod(tmp_path / "a.out", 0o755)
