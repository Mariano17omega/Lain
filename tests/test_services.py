import threading

from qe_studio.ui import services


def test_invalidate_drops_results_of_running_tasks(qtbot, demo_project, monkeypatch):
    """A detection that started before invalidate() must not refill the cache with old data."""
    real = services.detect_folder
    gate = threading.Event()
    calls = []

    def detect(folder, **kwargs):
        calls.append(folder)
        if len(calls) == 1:  # the pre-invalidation run: blocks, then reports stale data
            gate.wait(5)
            return []
        return real(folder, **kwargs)

    monkeypatch.setattr(services, "detect_folder", detect)
    service = services.DetectionService()
    emitted = []
    service.detected.connect(emitted.append)
    folder = demo_project / "03_bands"
    assert service.results(folder) is None
    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    service.invalidate(demo_project)  # parent folder: covers its subfolders
    gate.set()
    qtbot.waitUntil(lambda: bool(emitted), timeout=5000)
    assert service.wait()
    qtbot.wait(50)  # let the stale task's queued signal arrive too
    assert [r.badge for r in service.results(folder)] == ["BANDS"]
    assert emitted == [str(folder)] and len(calls) == 2


def test_fresh_request_supersedes_running_task(qtbot, demo_project, monkeypatch):
    real = services.detect_folder
    gate = threading.Event()
    calls = []

    def detect(folder, **kwargs):
        calls.append(folder)
        if len(calls) == 1:
            gate.wait(5)
            return []
        return real(folder, **kwargs)

    monkeypatch.setattr(services, "detect_folder", detect)
    service = services.DetectionService()
    folder = demo_project / "04_pdos"
    service.request(folder)
    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    with qtbot.waitSignal(service.detected, timeout=5000):
        service.request(folder, fresh=True)
    gate.set()
    assert service.wait()
    qtbot.wait(50)
    assert [r.badge for r in service.results(folder)] == ["PDOS"]
