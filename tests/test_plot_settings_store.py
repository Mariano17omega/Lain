"""``PlotSettingsStore`` writes: in the order they were asked for, even when ``flush_now`` gives up
waiting for a slow disk (spec 27-3 R3.2)."""

import contextlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from qe_studio.core.plotting.plot_file import WriteOrder, read_plot_file
from qe_studio.core.tasks import run_task
from qe_studio.ui import plot_settings
from qe_studio.ui.plot_settings import PlotSettingsStore


@dataclass
class Params:
    emin: float = -5.0


def session(folder: Path, emin: float):
    """What the store reads of a ``PlotSession``."""
    return SimpleNamespace(
        module=SimpleNamespace(plot_file=True),
        key="plot:bands:x",
        folder=folder,
        plot_target=folder,
        kind="bands",
        params=Params(emin),
    )


def stored_emin(folder: Path):
    params, _warnings = read_plot_file(folder, "bands")
    return params["emin"]


def test_write_order_skips_an_older_ticket(tmp_path):
    order, path = WriteOrder(), tmp_path / "bands.plot"
    older, newer = order.ticket(), order.ticket()
    ran = []
    assert order.run(path, newer, lambda: ran.append("newer"))
    assert not order.run(path, older, lambda: ran.append("older"))
    assert ran == ["newer"]


def test_write_order_is_per_file(tmp_path):
    order = WriteOrder()
    older, newer = order.ticket(), order.ticket()
    ran = []
    order.run(tmp_path / "a.plot", newer, lambda: ran.append("a"))
    assert order.run(tmp_path / "b.plot", older, lambda: ran.append("b"))  # another file
    assert ran == ["a", "b"]


def test_a_failed_write_does_not_hold_back_the_next(tmp_path):
    order, path = WriteOrder(), tmp_path / "x.plot"

    def fail():
        raise OSError("disk")

    first, second = order.ticket(), order.ticket()
    with contextlib.suppress(OSError):
        order.run(path, second, fail)
    assert order.run(path, first, lambda: None)  # nothing was written under the newer ticket


def test_write_order_serializes_the_writes(tmp_path):
    order, path = WriteOrder(), tmp_path / "x.plot"
    inside, overlap = [], []

    def slow():
        inside.append(1)
        overlap.append(len(inside) > 1)
        threading.Event().wait(0.02)
        inside.pop()

    threads = [
        threading.Thread(target=order.run, args=(path, order.ticket(), slow)) for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not any(overlap)


def test_a_write_still_queued_never_overwrites_the_newer_one_flush_now_made(
    qtbot, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(plot_settings, "DRAIN_MS", 50)
    store = PlotSettingsStore()
    gate = threading.Event()
    run_task(gate.wait, 10, pool=store._pool)  # the slow disk: the one worker is busy
    edited = session(tmp_path, emin=-1.0)
    store.mark(edited)
    store.flush()  # v1: queued behind the busy worker
    edited.params.emin = -2.0
    store.mark(edited)
    with caplog.at_level(logging.WARNING, logger=plot_settings.log.name):
        store.flush_now()  # gives up after 50 ms and writes v2 here
    assert "still queued" in caplog.text
    assert stored_emin(tmp_path) == -2.0
    gate.set()
    assert store._pool.waitForDone(10_000)
    qtbot.wait(50)
    assert stored_emin(tmp_path) == -2.0  # the older write was dropped by its ticket
    assert store.shutdown()


def test_without_a_delay_the_queue_is_drained_first(qtbot, tmp_path):
    store = PlotSettingsStore()
    edited = session(tmp_path, emin=-1.0)
    store.mark(edited)
    store.flush()
    edited.params.emin = -3.0
    store.mark(edited)
    store.flush_now()
    assert stored_emin(tmp_path) == -3.0 and not store.is_dirty(edited.key)
    assert store.shutdown()


def test_close_writes_what_is_pending_and_stops_the_queues(qtbot, tmp_path):
    store = PlotSettingsStore()
    edited = session(tmp_path, emin=-1.0)
    store.mark(edited)
    store.flush()
    edited.params.emin = -4.0
    store.mark(edited)
    assert store.close(5000)
    assert stored_emin(tmp_path) == -4.0 and not store.is_dirty(edited.key)


def test_close_gives_up_on_a_slow_disk_but_still_writes(qtbot, tmp_path):
    store = PlotSettingsStore()
    gate = threading.Event()
    run_task(gate.wait, 10, pool=store._pool)  # the one worker is busy
    edited = session(tmp_path, emin=-1.0)
    store.mark(edited)
    assert not store.close(50)  # the drain timed out: say so
    assert stored_emin(tmp_path) == -1.0  # and it was written anyway, here
    gate.set()
    assert store._pool.waitForDone(10_000)
