"""The latency budget of a plot (NFR §7, < 500 ms for loading the curves and updating the view)."""

from __future__ import annotations

import time
from collections.abc import Callable


def warm_seconds(name: str, action: Callable[[], object]) -> float:
    """Seconds of ``action`` once its first run has paid what happens once per process: matplotlib
    builds its mathtext parser and looks up its fonts in the first plot of a session (0.5 to 1 s). A
    test that timed the first run measured that, or not, depending on the tests that ran before it.
    ``-s`` prints both numbers, so the cost of that first plot stays visible."""
    start = time.perf_counter()
    action()
    first = time.perf_counter() - start
    start = time.perf_counter()
    action()
    seconds = time.perf_counter() - start
    print(f"\nperf {name}: first {first * 1000:.0f} ms, then {seconds * 1000:.0f} ms")
    return seconds
