import threading
from pathlib import Path

from qe_studio.core import sniff as sniff_module
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


def _count_reads(monkeypatch) -> list:
    reads = []
    real = sniff_module._sniff_uncached

    def counting(path, size):
        reads.append(path)
        return real(path, size)

    monkeypatch.setattr(sniff_module, "_sniff_uncached", counting)
    return reads


def test_refresh_keeps_sniffs_of_unchanged_files(qtbot, demo_project, monkeypatch):
    """Spec 14 R4: F5 redoes detection without reading unchanged files again."""
    reads = _count_reads(monkeypatch)
    service = services.DetectionService()
    folders = [demo_project / name for name in ("01_relax", "02_scf", "03_bands", "04_pdos")]
    for folder in folders:
        service.detect_now(folder)
    assert reads
    reads.clear()
    service.invalidate()
    assert all(service.results(folder) is None for folder in folders)
    for folder in folders:
        service.detect_now(folder)
    assert reads == []
    assert service.wait()


def test_refresh_drops_sniffs_of_deleted_files(qtbot, demo_project):
    service = services.DetectionService()
    service.detect_now(demo_project / "03_bands")
    deleted = demo_project / "03_bands" / "bands.dat.gnu"
    assert service.file_sniff(deleted) is not None
    deleted.unlink()
    service.invalidate()
    assert service.file_sniff(deleted) is None
    assert service.file_sniff(demo_project / "03_bands" / "scf.out") is not None
    assert service.wait()


def test_paranoid_refresh_rereads_everything(qtbot, demo_project, monkeypatch):
    reads = _count_reads(monkeypatch)
    service = services.DetectionService()
    service.paranoid_refresh = True
    folder = demo_project / "03_bands"
    service.detect_now(folder)
    first = sorted(reads)
    reads.clear()
    service.invalidate()
    service.detect_now(folder)
    assert sorted(reads) == first
    assert service.wait()


# -- invalidation follows what the detection reads (spec 27-8 R4) ------------------------------------


def _detected(service, tmp_path, names) -> dict[str, Path]:
    """Folders ``names`` of a project, all detected (an empty folder is a result too)."""
    root = tmp_path / "proj"
    folders = {name: root / name for name in names}
    for folder in folders.values():
        folder.mkdir(parents=True)
    for folder in [root, *folders.values()]:
        service.detect_now(folder)
    return folders


def _cleared(service, folders) -> set[str]:
    return {name for name, folder in folders.items() if service.peek_results(folder) is None}


def test_invalidating_a_folder_clears_it_and_the_folders_that_read_it(qapp, tmp_path):
    service = services.DetectionService()
    names = ["scf_a", "bands_a", "pdos_a", "relax_a", "nested/pdos_b"]
    folders = _detected(service, tmp_path, names)
    root = tmp_path / "proj"

    service.invalidate(folders["bands_a"])  # nothing reads a bands folder
    assert _cleared(service, folders) == {"bands_a"} and service.peek_results(root) is not None
    assert all(service.peek_results(f) is not None for n, f in folders.items() if n != "bands_a")

    folders = _detected(service, tmp_path / "again", names)
    # Bands and PDOS read the SCF folder next to them; which of its siblings are those is not known
    # before their detection, so every sibling goes. A folder elsewhere keeps its result.
    service.invalidate(folders["scf_a"])
    assert _cleared(service, folders) == {"scf_a", "bands_a", "pdos_a", "relax_a"}


def test_invalidating_a_pdos_subfolder_clears_the_folder_that_reads_it(qapp, tmp_path):
    service = services.DetectionService()
    folders = _detected(service, tmp_path, ["calc", "other"])
    orbitals, plain = folders["calc"] / "orbitals", folders["calc"] / "plain"
    orbitals.mkdir()
    plain.mkdir()
    (orbitals / "pdos.dat.pdos_tot").write_text("")  # read by the detection of calc
    service.invalidate(plain)
    assert _cleared(service, folders) == set()  # nothing of it feeds calc
    service.invalidate(orbitals)
    assert _cleared(service, folders) == {"calc"}


def test_the_whole_project_is_still_cleared_without_a_folder(qapp, tmp_path):
    service = services.DetectionService()
    folders = _detected(service, tmp_path, ["scf_a", "bands_a"])
    service.invalidate()
    assert _cleared(service, folders) == {"scf_a", "bands_a"}


def test_unaffected_siblings_are_not_detected_again(qtbot, tmp_path, monkeypatch):
    """A running detection of a folder that does not read the invalidated one is left alone."""
    gate = threading.Event()
    calls = []

    def detect(folder, **kwargs):
        calls.append(folder.name)
        if folder.name == "pdos_a":
            gate.wait(5)
        return []

    monkeypatch.setattr(services, "detect_folder", detect)
    service = services.DetectionService()
    folders = _detected_empty(tmp_path, ["pdos_a", "bands_a"])
    service.request(folders["pdos_a"])
    qtbot.waitUntil(lambda: calls == ["pdos_a"], timeout=5000)
    service.invalidate(folders["bands_a"])  # pdos_a does not read it
    gate.set()
    qtbot.waitUntil(lambda: service.peek_results(folders["pdos_a"]) is not None, timeout=5000)
    assert service.wait() and calls == ["pdos_a"]


def _detected_empty(tmp_path, names) -> dict[str, Path]:
    folders = {name: tmp_path / "proj" / name for name in names}
    for folder in folders.values():
        folder.mkdir(parents=True)
    return folders


# -- a failing detection is not an empty folder (spec 27-8 R5) ---------------------------------------


def _raise(*args, **kwargs):
    raise ValueError("arquivo estranho")


def test_a_failed_detection_ends_says_so_once_and_f5_tries_again(
    qtbot, tmp_path, monkeypatch, caplog
):
    folder = _detected_empty(tmp_path, ["calc"])["calc"]
    real = services.detect_folder
    monkeypatch.setattr(services, "detect_folder", _raise)
    service = services.DetectionService()
    emitted, messages = [], []
    service.detected.connect(emitted.append)
    service.message.connect(lambda text, level, ms: messages.append((text, level)))

    with qtbot.waitSignal(service.detected, timeout=5000):
        assert service.results(folder) is None
    assert service.results(folder) == [] and emitted == [str(folder)]  # not scheduled again
    assert messages == [("Falha ao detectar calc (veja o log)", "warning")]
    assert "detecção falhou" in caplog.text

    with qtbot.waitSignal(service.detected, timeout=5000):
        service.request(folder, fresh=True)
    assert len(emitted) == 2 and len(messages) == 1  # said once

    monkeypatch.setattr(services, "detect_folder", real)
    service.invalidate()  # F5
    assert service.peek_results(folder) is None
    with qtbot.waitSignal(service.detected, timeout=5000):
        assert service.results(folder) is None
    assert service.results(folder) == [] and len(messages) == 1  # real detection: no calculation

    monkeypatch.setattr(services, "detect_folder", _raise)
    service.invalidate()
    with qtbot.waitSignal(service.detected, timeout=5000):
        service.request(folder)
    assert len(messages) == 2  # F5 cleared the mark: a new failure is told again
    assert service.wait()


def test_a_failed_detection_ends_the_busy_state_of_the_plot(qtbot, tmp_path, monkeypatch):
    from test_plot_workflow_unit import Rig

    asked = []
    monkeypatch.setattr(
        "qe_studio.ui.plot_workflow.ask_mapping", lambda *args: asked.append(args) or None
    )
    monkeypatch.setattr(services, "detect_folder", _raise)
    rig = Rig(qtbot, _detected_empty(tmp_path, ["calc"])["calc"].parent, tmp_path)
    try:
        folder = tmp_path / "proj" / "calc"
        with qtbot.waitSignal(rig.service.detected, timeout=5000):
            rig.workflow.generate(folder, auto_export=False)
            assert rig.workflow.busy.labels == ["Detectando cálculo…"]
        qtbot.waitUntil(lambda: bool(asked), timeout=5000)  # the usual "map it by hand" fallback
        assert rig.workflow.busy.labels == []
    finally:
        rig.close()
