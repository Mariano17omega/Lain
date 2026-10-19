"""Probe scenario of spec 60: what the program persists does not depend on the language.

``persist`` does, in the probe's window, the same sequence of actions in every language and returns
what was written as facts: the files of ``.lain/``, every ``*.plot``, the names of what was exported
or created, the CSV and the keys of QSettings, with the temporary paths replaced. The test runs it
in ``pt_BR`` and in ``en`` and compares. Two outputs follow the language on purpose and come back
under their own prefix (``report:`` for the ``geracao.md`` of the Slab, spec 56 R2; ``copied:`` for
the text of the measures, spec 59 R2) for the test to name them.

``legacy`` opens files written before the series (``tests/fixtures/i18n_legacy``, spec 60 R2.3) and
returns them as they were and as they are after the window read them.

It goes last: the shutdown steps it runs and the dialogs it patches stay for the rest of the process.
Modules with texts are imported inside the functions: the language is installed before them.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from i18n_scenarios_55 import open_plot, wait_for, wait_plot
from i18n_scenarios_57 import MOLECULE, files_step, pick_molecule

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "tests" / "fixtures" / "i18n_legacy"
REPORT_PREFIX = "report:"  # the file that follows the language (geracao.md)
REPORT_NAME = "geracao.md"
TEXT = {".json", ".plot", ".csv", ".in", ".qsub", ".md"}
COPIED_PREFIX = "copied:"  # the text of the measures that follows the language
# Keys that hold the machine, not the user's choices: the window's size and the project's path.
VOLATILE_KEYS = ("window/geometry", "explorer/last_folder")


def copy_folder(project: Path, source: str, target: str) -> Path:
    folder = project / target
    shutil.copytree(project / source, folder)
    return folder


def pump(rounds: int = 20) -> None:
    from PyQt6.QtWidgets import QApplication

    for _round in range(rounds):
        QApplication.processEvents()


# -- the actions ---------------------------------------------------------------------------------
def map_files(window, project: Path) -> None:
    """Two files mapped to roles by hand (``Method.MANUAL``, remembered in ``folders.json``)."""
    for name in ("05_mapped", "06_to_rename"):
        folder = copy_folder(project, "03_bands", name)
        window.memory.set_mapping(
            folder, "bands", {"scf_out": [folder / "scf.out"], "gnu": [folder / "bands.dat.gnu"]}
        )
        window.service.invalidate(folder)
        window.service.detect_now(folder)


def rename_folder(window, project: Path) -> None:
    from qe_studio.ui import rename_controller

    folder = project / "06_to_rename"  # mapped by ``map_files``: its entry moves with it
    real = rename_controller.ask_rename
    rename_controller.ask_rename = lambda parent, path: "08_renamed"  # type: ignore[assignment]
    try:
        window.renamer.rename(folder)
    finally:
        rename_controller.ask_rename = real  # type: ignore[assignment]


def save_grid_and_compound(window, project: Path) -> None:
    from qe_studio.core.plotting.grid import GridCell, GridSpec, PlotRef

    store = window.plot_workflow.stores.grids
    store.save(
        GridSpec(
            "Comparison",
            1,
            2,
            [
                GridCell(0, 0, PlotRef(project / "03_bands", "bands"), "Bands"),
                GridCell(0, 1, PlotRef(project / "04_pdos_orbitals", "pdos")),
            ],
        )
    )
    store.save_params("Comparison", {"hspace": 0.3, "wspace": 0.2})
    window.compounds.set_root(window.root)
    window.compounds.save("Al", "Al", [1], [(0.0, 0.0, 0.0)])


def favorite_and_visit(window, project: Path) -> None:
    window.navigation.set_favorite(project / "03_bands", True)
    for name in ("02_scf", "04_pdos_orbitals", "03_bands"):
        window.explorer.select_path(project / name)
    window.navigation_store.flush()


def adjust_plots(window, project: Path) -> None:
    """Bands, PDOS, relax and SCF opened, one ``choice`` of each changed, the ``.plot`` written."""
    for kind in ("bands", "pdos", "relax", "scf"):
        open_plot(window, project, kind)
        session = window.current_plot().session
        for field in session.module.param_schema(session.dataset):
            if field.kind != "choice":
                continue
            current = getattr(session.params, field.name)
            other = next((value for value, _label in field.choices if value != current), None)
            if other is not None:
                window.params.set_param(field.name, other)
                break
        pump()
        window.plot_settings.flush_now()


def adjust_3d(window, project: Path) -> list[str]:
    """The 3D window of ``scf.in`` with the style, labels and background changed; closed, so its
    ``view3d.plot`` is written. Returns the text of a copied measure (follows the language)."""
    from qe_studio.core.structure3d.measurements import Measurement, to_tsv
    from qe_studio.core.structure3d.model import AtomRef

    opened: list[object] = []
    window.structure3d.opened.connect(opened.append)
    try:
        window.structure3d.open(project / "02_scf" / "scf.in")
        wait_for(window.structure3d.opened)
    finally:
        window.structure3d.opened.disconnect(opened.append)
    if not opened:
        raise RuntimeError("the 3D window did not open")
    view = opened[0]
    for combo, value in (
        (view.panel.style_choice, "vareta"),  # type: ignore[attr-defined]
        (view.panel.labels, "indice"),  # type: ignore[attr-defined]
        (view.panel.background, "claro"),  # type: ignore[attr-defined]
    ):
        index = combo.findData(value)
        if index < 0:
            raise RuntimeError(f"no choice {value!r} in the 3D panel")
        combo.setCurrentIndex(index)
    measure = Measurement("distancia", (AtomRef(0), AtomRef(0, (1, 0, 0))), 2.863)
    copied = to_tsv(view.structure, [measure])  # type: ignore[attr-defined]
    view.close()  # type: ignore[attr-defined]
    window.structure3d.wait_saves()
    return [f"{COPIED_PREFIX}\n{copied}"]


def export_bands(window, project: Path) -> None:
    open_plot(window, project, "bands")
    if not window.export_plot():
        raise RuntimeError("the export did not start")
    wait_for(window.export_finished)


def create_slab(window, project: Path) -> None:
    dialog, tabs = files_step(window, "slab", project)
    pick_molecule(tabs, MOLECULE)
    dialog.create_button.click()
    wait_for(window.calc_create.created)


# -- what was written ----------------------------------------------------------------------------
def readable(text: str, project: Path) -> str:
    return text.replace(str(project), "<project>")


def written_files(project: Path) -> list[str]:
    """The text of ``.lain/*.json``, the ``*.plot`` and ``*.csv`` files and the files of the Slab,
    and the name of every other file in a ``plots/`` folder. ``geracao.md`` apart: it follows the
    language."""
    facts: list[str] = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project).as_posix()
        data = relative.startswith(".lain/") or "/plots/" in relative or "Slab" in relative
        if not path.is_file() or not data:
            continue
        text = readable(path.read_text("utf-8"), project) if path.suffix in TEXT else ""
        if path.name == REPORT_NAME:
            facts.append(f"{REPORT_PREFIX} {relative}\n{text}")
        elif path.suffix in TEXT:
            facts.append(f"file {relative}:\n{text}")
        else:
            facts.append(f"name {relative}")
    return facts


def settings_dump(window, project: Path) -> list[str]:
    window.panel_layout.save()
    window.settings.sync()
    facts = []
    for key in sorted(window.settings.allKeys()):
        if key in VOLATILE_KEYS:
            continue
        facts.append(f"setting {key} = {readable(repr(window.settings.value(key)), project)}")
    return facts


def persist_scenario(window, project: Path) -> list[str]:
    """The same actions in every language, then everything they persisted."""
    map_files(window, project)
    rename_folder(window, project)
    save_grid_and_compound(window, project)
    favorite_and_visit(window, project)
    adjust_plots(window, project)
    copied = adjust_3d(window, project)
    export_bands(window, project)
    create_slab(window, project)
    pump()
    return [*written_files(project), *settings_dump(window, project), *copied]


# -- files written before the series ---------------------------------------------------------------
LEGACY_FILES = {
    "03_bands/plots/bands.plot": "bands.plot",
    "04_pdos_orbitals/plots/pdos.plot": "pdos.plot",
    "02_scf/plots/view3d.plot": "view3d.plot",
    ".lain/folders.json": "folders.json",
}


def legacy_scenario(window, project: Path) -> list[str]:
    """The files of ``tests/fixtures/i18n_legacy`` put into the project, then read by the window
    (the plots, the 3D view, the remembered mapping): each as it was and as it is afterwards, and
    the closed section of a QSettings key written with the Portuguese title."""
    from qe_studio.ui.widgets.param_widgets import Section

    window.settings.setValue("params/sections/bands/Estilo", False)  # the title, before the ids
    before: dict[str, str] = {}
    for target, name in LEGACY_FILES.items():
        path = project / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(LEGACY / name, path)
        before[target] = path.read_text("utf-8")
    window.memory.set_root(project)
    window.service.invalidate(project / "03_bands")
    window.service.detect_now(project / "03_bands")
    wait_plot(window, lambda: window.generate_plot_for(project / "03_bands", auto_export=False))
    section = next(s for s in window.params.body.findChildren(Section) if s.id == "style")
    facts = [f"style section open: {section.header.isChecked()}"]
    open_plot(window, project, "pdos")
    window.plot_settings.flush_now()
    opened: list[object] = []
    window.structure3d.opened.connect(opened.append)
    try:
        window.structure3d.open(project / "02_scf" / "scf.in")
        wait_for(window.structure3d.opened)
    finally:
        window.structure3d.opened.disconnect(opened.append)
    if not opened:
        raise RuntimeError("the 3D window did not open")
    opened[0].close()  # type: ignore[attr-defined]
    window.structure3d.wait_saves()
    for target in LEGACY_FILES:
        after = (project / target).read_text("utf-8")
        facts.append(f"{target} rewritten: {after != before[target]}")
    return facts


SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    "persist": persist_scenario,
    "legacy": legacy_scenario,
}
