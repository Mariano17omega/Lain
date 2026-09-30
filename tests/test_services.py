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


def test_superseded_queued_tasks_skip_detection(qtbot, demo_project, monkeypatch):
    """Repeated invalidate() (F5, syncs) must not leave old queued tasks redoing the work."""
    real = services.detect_folder
    gate = threading.Event()
    calls = []

    def detect(folder, **kwargs):
        calls.append(folder)
        if len(calls) == 1:
            gate.wait(5)
        return real(folder, **kwargs)

    monkeypatch.setattr(services, "detect_folder", detect)
    service = services.DetectionService()
    service._pool.setMaxThreadCount(1)  # the first task holds the only thread
    running, queued = demo_project / "01_relax", demo_project / "04_pdos"
    service.request(running)
    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    service.request(queued)
    for _ in range(3):
        service.invalidate(demo_project)
    gate.set()
    assert service.wait()
    qtbot.wait(50)
    assert calls.count(queued) == 1 and calls.count(running) == 2
    assert [r.badge for r in service.results(queued)] == ["PDOS"]


def test_invalidate_covers_sibling_folders_only(qtbot, demo_project):
    service = services.DetectionService()
    for folder in (demo_project, demo_project / "02_scf", demo_project / "03_bands"):
        service.detect_now(folder)
    service.invalidate(demo_project / "02_scf")
    assert service.results(demo_project) is not None  # the parent does not read it
    assert service.results(demo_project / "03_bands") is None  # may take its SCF from it
    assert service.file_sniff(demo_project / "03_bands" / "scf.out") is not None
    assert service.wait()


def test_shutdown_skips_queued_tasks(qtbot, demo_project, monkeypatch):
    gate = threading.Event()
    calls = []

    def detect(folder, **kwargs):
        calls.append(folder)
        gate.wait(5)
        return []

    monkeypatch.setattr(services, "detect_folder", detect)
    service = services.DetectionService()
    service._pool.setMaxThreadCount(1)
    for name in ("01_relax", "02_scf", "03_bands", "04_pdos"):
        service.request(demo_project / name)
    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    gate.set()
    assert service.shutdown()
    assert calls == [demo_project / "01_relax"]
