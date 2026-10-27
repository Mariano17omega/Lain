import os
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import settings

from cluster_guard import Guard
from ssh_server import LocalSSHServer, ServerKeys

# Must be set before any PyQt6 import so tests run headless. Forced, not defaulted: a shell with
# QT_QPA_PLATFORM=xcb would run the tests on the real display, with other screen sizes than CI.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("MPLBACKEND", "Agg")
# The texts the tests compare are the Portuguese source ones, whatever the machine's language is
# (the modules are imported with no language installed, which is the source language too).
os.environ["QE_STUDIO_LANGUAGE"] = "pt_BR"
# The config lookup never finds the checkout's own config.yaml (spec 61 R1.5): a developer's file
# would answer the tests that expect none.
os.environ["QE_STUDIO_NO_CHECKOUT_CONFIG"] = "1"

FIXTURES = Path(__file__).parent / "fixtures"

# Runner time varies, so Hypothesis never fails a test on its deadline. CI sets
# HYPOTHESIS_PROFILE=ci for fewer examples and no example database.
settings.register_profile("dev", deadline=None)
settings.register_profile("ci", max_examples=25, deadline=None, database=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_collection_modifyitems(items):
    # Last, so the fixtures check also sees what this run's tests wrote.
    items.sort(key=lambda item: item.name == "test_fixtures_are_untouched")


@pytest.fixture(autouse=True)
def _source_language():
    """A test may install another language (spec end R4); the next one starts in Portuguese."""
    from qe_studio import i18n

    yield
    if i18n.current_language() != i18n.SOURCE_LANGUAGE:
        i18n.install(i18n.SOURCE_LANGUAGE)


@pytest.fixture(autouse=True)
def _empty_dataset_cache():
    """The loaded datasets are process-wide (spec 27-4): no test starts with another's."""
    from qe_studio.core.calculations import drop_cached

    drop_cached()
    yield
    drop_cached()


@pytest.fixture(autouse=True)
def _default_data_dir():
    """A ``paths.data`` fixed by a test (spec 61) is not the next test's data folder."""
    from qe_studio.core import appdirs

    yield
    appdirs.set_data_dir(None)


@pytest.fixture(autouse=True)
def _isolated_user_dirs(tmp_path_factory, monkeypatch):
    """Keep app data/config/cache writes out of the real home directory, and the ssh sockets out
    of the real ``/run/user``: a short runtime folder in ``/tmp`` (``tmp_path`` is too long for a
    socket path, spec 72 R4.9)."""
    base = tmp_path_factory.mktemp("userdirs")
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(var, str(base / var.lower()))
    runtime = tempfile.mkdtemp(prefix="lm", dir="/tmp" if os.path.isdir("/tmp") else None)
    monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)
    yield
    shutil.rmtree(runtime, ignore_errors=True)


@pytest.fixture(autouse=True)
def _cluster_guard(tmp_path_factory, monkeypatch):
    """The cluster is production (spec 69 R7): a test that reads the real config.yaml or contacts
    a host that is not a test one fails (``tests/cluster_guard.py``). A test asks for this fixture
    by name to see the guard."""
    monkeypatch.delenv("QE_STUDIO_CONFIG", raising=False)
    guard = Guard([tmp_path_factory.getbasetemp(), Path(__file__).parent])
    guard.install(monkeypatch)
    yield guard
    if guard.violations:
        pytest.fail("\n".join(guard.violations))


def copy_fixture(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(FIXTURES / name, target)
    return target


@pytest.fixture
def al_pdos_orbitals(tmp_path) -> Path:
    """Al PDOS files rearranged into the PRD layout (scf/nscf/projwfc names + orbitals/)."""
    src = FIXTURES / "al_pdos_flat"
    folder = tmp_path / "04_pdos"
    (folder / "orbitals").mkdir(parents=True)
    shutil.copy(src / "al.scf.out", folder / "scf.out")
    shutil.copy(src / "al.nscf.out", folder / "nscf.out")
    shutil.copy(src / "al.projwfc.out", folder / "projwfc.out")
    shutil.copy(src / "pdos.dat.pdos_tot", folder / "pdos.dat.pdos_tot")
    for path in src.glob("*pdos_atm*"):
        shutil.copy(path, folder / "orbitals" / path.name)
    return folder


@pytest.fixture
def raiz(tmp_path) -> Path:
    """A root of projects (spec 31): ``ilita`` and ``outro`` with nested analyses, a ``plots``
    folder (a grid export: never a project), a hidden folder and a loose file."""
    root = tmp_path / "raiz"
    for folder in (
        "ilita/Analise_1/Bandas",
        "ilita/Analise_2/PDOS",
        "outro/Analise_1/Relax",
        "plots",
        ".oculta",
    ):
        (root / folder).mkdir(parents=True)
    (root / "solto.txt").write_text("a loose file")
    return root


@pytest.fixture
def demo_project(tmp_path) -> Path:
    """Project tree like the mockup: 01_relax, 02_scf, 03_bands (PRD names), 04_pdos."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "si_relax", project / "01_relax")
    (project / "02_scf").mkdir()
    shutil.copy(FIXTURES / "al_bands/al.scf.out", project / "02_scf/scf.out")
    bands = project / "03_bands"
    bands.mkdir()
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.band.in", "bands.in"),
        ("al.band.out", "bands.out"),
        ("bands.out", "bands_pp.out"),
        ("bands.dat.gnu", "bands.dat.gnu"),
    ]:
        shutil.copy(FIXTURES / "al_bands" / old, bands / new)
    pdos = project / "04_pdos"
    (pdos / "orbitals").mkdir(parents=True)
    src = FIXTURES / "al_pdos_flat"
    for old, new in [
        ("al.scf.out", "scf.out"),
        ("al.nscf.out", "nscf.out"),
        ("al.projwfc.out", "projwfc.out"),
        ("pdos.dat.pdos_tot", "pdos.dat.pdos_tot"),
    ]:
        shutil.copy(src / old, pdos / new)
    for path in src.glob("*pdos_atm*"):
        shutil.copy(path, pdos / "orbitals" / path.name)
    (project / "03_bands" / "tmp").mkdir()
    return project


@pytest.fixture
def window_factory(qtbot, demo_project, tmp_path, monkeypatch):
    """``make(**stores)`` builds a ``MainWindow`` on ``demo_project`` with isolated QSettings and
    stores. Called again with the same ``tmp_path`` files it is a restart of the app: whatever the
    first window saved is read back. Every window made is closed at teardown. The stores get fixed
    ``tmp_path`` files, so no test makes a ``.lain`` folder in its root by accident (spec 48), except
    the window's ``GridStore``, which the window builds itself and follows the root."""
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QMenu

    def blocking_menu(menu, *args):
        # A real popup would wait for a click forever (pytest-timeout cannot interrupt it).
        raise AssertionError("QMenu.exec would block the test; patch it")

    monkeypatch.setattr(QMenu, "exec", blocking_menu)

    from qe_studio.core.cluster_jobs import JobsFailure
    from qe_studio.ui import jobs_controller

    def no_cluster(_config, _password=None):
        # A window with a cluster in its config never logs in for its jobs (spec 64): an answer
        # that leaves the LED alone. ``jobs_helpers.cluster_window`` gives a test its own.
        return JobsFailure("no cluster in the tests", local=True)

    monkeypatch.setattr(jobs_controller, "fetch_jobs", no_cluster)

    from qe_studio.core.compounds import CompoundStore
    from qe_studio.core.config import LoadedConfig, parse_config
    from qe_studio.core.folder_memory import FolderMemory
    from qe_studio.core.nav_store import NavigationStore
    from qe_studio.ui.main_window import MainWindow
    from qe_studio.ui.theme.manager import ThemeManager

    windows = []

    def make(loaded=None, ui=None, follow_root=False, **kwargs):
        """``loaded``: a ``LoadedConfig`` of its own (first run, missing root…) instead of one
        whose ``local_root`` is ``demo_project``; ``ui``: keys of its ``ui:`` section;
        ``follow_root``: the window builds its own stores, kept in the root's settings folder
        (spec 48), as the app does."""
        if not follow_root:
            kwargs.setdefault("navigation", NavigationStore(tmp_path / "navigation.json"))
            kwargs.setdefault("compounds", CompoundStore(tmp_path / "compounds.json"))
        config = parse_config({"paths": {"local_root": str(demo_project)}, "ui": ui or {}})
        theme = ThemeManager("dark")
        theme.apply()
        settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
        window = MainWindow(
            loaded or LoadedConfig(config, None),
            theme,
            settings,
            None if follow_root else FolderMemory(tmp_path / "memory.json"),
            **kwargs,
        )
        qtbot.addWidget(window)
        window.show()
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.close()


@pytest.fixture
def main_window(window_factory):
    return window_factory()


@pytest.fixture
def tree_files_window(window_factory):
    """A window whose folder tree lists the files too (``ui.tree_show_files``, spec 37)."""
    return window_factory(ui={"tree_show_files": True})


@pytest.fixture
def fake_apps(tmp_path, monkeypatch):
    """Two programs for text files; "Other" is the mimeapps.list default and opens folders."""
    from qe_studio.core.desktop_apps import AppCatalog
    from qe_studio.ui.widgets import context_menu

    data, config = tmp_path / "apps-data", tmp_path / "apps-config"
    (data / "applications").mkdir(parents=True)
    (data / "applications" / "fake.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Fake\nExec=fake-editor %f\nMimeType=text/plain;\n"
    )
    (data / "applications" / "other.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Other\nExec=other --open %U\n"
        "MimeType=text/plain;inode/directory;\n"
    )
    config.mkdir()
    (config / "mimeapps.list").write_text("[Default Applications]\ntext/plain=other.desktop\n")
    monkeypatch.setattr(context_menu, "catalog", lambda: AppCatalog([data], [config], []))


@pytest.fixture
def launched(monkeypatch):
    """QProcess.startDetached calls; nothing is started."""
    from PyQt6.QtCore import QProcess

    calls = []

    def start(program, args=(), cwd=""):
        calls.append((program, list(args), cwd))
        return calls[-1][0] != "broken", 4242

    monkeypatch.setattr(QProcess, "startDetached", staticmethod(start))
    return calls


@pytest.fixture(scope="session")
def ssh_keys(tmp_path_factory) -> ServerKeys:
    """Host and client keys of the test SSH server, generated once per session."""
    return ServerKeys.generate(tmp_path_factory.mktemp("ssh_keys"))


@pytest.fixture
def ssh_server(ssh_keys, tmp_path):
    """``(server, remote_root)``: a local SSH server whose "cluster" is the folder ``remote_root``.

    Needs the real ``rsync`` and ``ssh`` binaries (tests skip without them). The server is shut
    down at teardown and no thread of it may outlive the test.
    """
    if shutil.which("rsync") is None or shutil.which("ssh") is None:
        pytest.skip("rsync and ssh are required")
    remote_root = tmp_path / "cluster"
    remote_root.mkdir()
    workdir = tmp_path / "ssh"
    workdir.mkdir()
    server = LocalSSHServer(remote_root, ssh_keys, workdir)
    yield server, remote_root
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"
