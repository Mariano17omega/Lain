"""The dataset cache (spec 27-4 R2): a byte budget, one load per key, emptying by folder."""

import threading
from pathlib import Path

import numpy as np
import pytest

from qe_studio.core import cancel
from qe_studio.core.calculations import CLOSE_DROP_MIN_BYTES, drop_cached
from qe_studio.core.calculations.load_cache import (
    CACHE,
    LOAD_CACHE_BYTES,
    LOAD_CACHE_SIZE,
    LoadCache,
)
from qe_studio.core.detection import detect_folder
from qe_studio.core.sniff import SniffCache
from qe_studio.ui.services import DetectionService

from conftest import FIXTURES, copy_fixture

KB = 1024


def blob(kb: int) -> np.ndarray:
    return np.zeros(kb * KB, dtype=np.uint8)


def test_the_budgets_are_the_ones_of_the_spec():
    assert LOAD_CACHE_BYTES == 256 * 1024 * 1024
    assert LOAD_CACHE_SIZE == 8
    assert CLOSE_DROP_MIN_BYTES == 4 * 1024 * 1024


def test_a_hit_returns_the_same_dataset_without_loading():
    cache, calls = LoadCache(), []
    first = cache.get_or_load("k", [], lambda: calls.append(1) or blob(1))
    assert cache.get_or_load("k", [], lambda: calls.append(1) or blob(1)) is first
    assert calls == [1]


def test_the_oldest_go_when_the_bytes_do_not_fit():
    cache = LoadCache(max_bytes=250 * KB)  # the spec's 256 MB, scaled down: three of 100 fit never
    for name in "abc":
        cache.get_or_load(name, [], lambda: blob(100))
    assert len(cache) == 2 and cache.total_bytes == 200 * KB
    calls = []
    cache.get_or_load("a", [], lambda: calls.append("a") or blob(100))  # was evicted
    cache.get_or_load("c", [], lambda: calls.append("c") or blob(100))  # still here
    assert calls == ["a"]


def test_a_hit_makes_the_entry_the_newest():
    cache = LoadCache(max_bytes=250 * KB)
    cache.get_or_load("a", [], lambda: blob(100))
    cache.get_or_load("b", [], lambda: blob(100))
    cache.get_or_load("a", [], lambda: blob(100))  # a is the newest now
    cache.get_or_load("c", [], lambda: blob(100))  # evicts b
    calls = []
    cache.get_or_load("a", [], lambda: calls.append("a") or blob(100))
    cache.get_or_load("b", [], lambda: calls.append("b") or blob(100))
    assert calls == ["b"]


def test_the_entry_count_is_a_second_limit():
    cache = LoadCache(max_entries=3)
    for n in range(5):
        cache.get_or_load(n, [], lambda: blob(1))
    assert len(cache) == 3


def test_a_dataset_over_the_whole_budget_is_returned_but_not_kept():
    cache, calls = LoadCache(max_bytes=250 * KB), []
    big = cache.get_or_load("big", [], lambda: calls.append(1) or blob(300))
    assert big.nbytes == 300 * KB
    assert len(cache) == 0 and cache.total_bytes == 0
    cache.get_or_load("big", [], lambda: calls.append(1) or blob(300))
    assert calls == [1, 1]


def test_two_threads_asking_for_one_key_load_it_once():
    cache, calls = LoadCache(), []
    gate, started = threading.Event(), threading.Event()

    def slow():
        calls.append(threading.current_thread().name)
        started.set()
        gate.wait(5)
        return blob(1)

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(cache.get_or_load("k", [], slow)))
        for _ in range(2)
    ]
    threads[0].start()
    assert started.wait(5)
    threads[1].start()  # asks while the first loads
    gate.set()
    for thread in threads:
        thread.join(5)
    assert len(calls) == 1 and results[0] is results[1]


def test_a_failed_load_is_retried_by_the_waiter():
    cache = LoadCache()
    gate, started = threading.Event(), threading.Event()
    outcome: dict[str, object] = {}

    def failing():
        started.set()
        gate.wait(5)
        raise OSError("gone")

    def first():
        try:
            cache.get_or_load("k", [], failing)
        except OSError as exc:
            outcome["first"] = exc

    loader = threading.Thread(target=first)
    loader.start()
    assert started.wait(5)
    waiter = threading.Thread(
        target=lambda: outcome.update(second=cache.get_or_load("k", [], lambda: "loaded"))
    )
    waiter.start()
    gate.set()
    loader.join(5)
    waiter.join(5)
    assert isinstance(outcome["first"], OSError) and outcome["second"] == "loaded"


class Token:
    cancelled = False


def test_the_result_of_a_cancelled_task_is_not_kept():
    cache, token = LoadCache(), Token()

    def load():
        token.cancelled = True  # cancelled while loading
        return blob(1)

    with cancel.bind(token), pytest.raises(cancel.Cancelled):
        cache.get_or_load("k", [], load)
    assert len(cache) == 0
    assert cache.get_or_load("k", [], lambda: "again") == "again"  # and the key is free again


def test_a_cancelled_task_does_not_start_a_load():
    token, calls = Token(), []
    token.cancelled = True
    with cancel.bind(token), pytest.raises(cancel.Cancelled):
        LoadCache().get_or_load("k", [], lambda: calls.append(1))
    assert calls == []


def test_a_cancelled_waiter_leaves_without_waiting_for_the_load():
    cache = LoadCache()
    gate, started = threading.Event(), threading.Event()

    def slow():
        started.set()
        gate.wait(5)
        return blob(1)

    loader = threading.Thread(target=lambda: cache.get_or_load("k", [], slow))
    loader.start()
    assert started.wait(5)
    token, raised = Token(), []

    def wait():
        try:
            with cancel.bind(token):
                cache.get_or_load("k", [], lambda: "never")
        except cancel.Cancelled:
            raised.append(1)

    waiter = threading.Thread(target=wait)
    waiter.start()
    token.cancelled = True
    waiter.join(2)  # well before the load ends
    assert raised == [1] and not waiter.is_alive()
    gate.set()
    loader.join(5)


def test_drop_removes_only_the_entries_under_the_folder(tmp_path):
    cache = LoadCache()
    cache.get_or_load("a", [tmp_path / "a" / "x.gnu"], lambda: blob(1))
    cache.get_or_load("b", [tmp_path / "b" / "x.gnu"], lambda: blob(1))
    cache.get_or_load("ab", [tmp_path / "a" / "x", tmp_path / "b" / "y"], lambda: blob(1))
    assert cache.drop(tmp_path / "a") == 2  # a, and the entry that has one file there
    assert len(cache) == 1 and cache.total_bytes == KB
    assert cache.drop() == 1 and len(cache) == 0 and cache.total_bytes == 0


def test_drop_with_a_minimum_spares_the_small_ones(tmp_path):
    cache = LoadCache()
    cache.get_or_load("small", [tmp_path / "s"], lambda: blob(1))
    cache.get_or_load("big", [tmp_path / "b"], lambda: blob(100))
    assert cache.drop(tmp_path, min_bytes=10 * KB) == 1
    assert len(cache) == 1 and cache.total_bytes == KB


def test_a_sibling_folder_with_the_same_prefix_is_not_under_it(tmp_path):
    cache = LoadCache()
    cache.get_or_load("k", [tmp_path / "bands_2" / "x"], lambda: blob(1))
    assert cache.drop(tmp_path / "bands") == 0


def test_load_cached_of_a_module_goes_through_the_shared_cache():
    from qe_studio.core.calculations import module_for

    sniff = SniffCache().sniff
    (result,) = detect_folder(FIXTURES / "al_bands", sniff=sniff)
    module = module_for("bands")
    dataset = module.load_cached(result, sniff)
    assert len(CACHE) == 1 and CACHE.total_bytes > 0
    assert module.load_cached(result, sniff) is dataset
    assert drop_cached(FIXTURES / "al_bands") == 1 and len(CACHE) == 0


def test_invalidate_empties_the_cache(qtbot, tmp_path):
    from qe_studio.core.calculations import module_for
    from qe_studio.core.folder_memory import FolderMemory

    service = DetectionService(FolderMemory(tmp_path / "folders.json"))
    folder = copy_fixture("al_bands", tmp_path)
    other = copy_fixture("al_pdos_flat", tmp_path)
    for path, kind in ((folder, "bands"), (other, "pdos")):
        results = service.detect_now(path)
        result = next(r for r in results if r.kind == kind)
        module_for(kind).load_cached(result, service.sniff_cache.sniff)
    assert len(CACHE) == 2
    service.invalidate(folder)  # only that folder's datasets go
    assert len(CACHE) == 1
    service.invalidate()  # F5: all of them
    assert len(CACHE) == 0
    assert Path(folder).exists()
