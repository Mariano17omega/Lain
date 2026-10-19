"""Probe scenarios of spec 55: the plots (panel of adjustments and figures), the atoms, the Grids and
the export (``tests/i18n_probe.py`` adds ``SCENARIOS`` to its own).

- ``params_<kind>``: the plot of each module opened in the window, every section of its panel open
  (the widgets are the probe's usual texts).
- ``figures``: what no widget shows, the text drawn *inside* each figure, as facts.
- ``csv``, ``export``, ``plot_files``: what is written to disk must not follow the language (spec 55
  R2, R3). They come back as facts for the test to compare between the languages.
- ``atoms_dialog``, ``grid_dialog``, ``files_roles``: the dialogs and the roles of the detected files.

Modules with texts are imported inside the functions: the language is installed before them
(``tests/i18n_probe.py``). Files are written into the probe's temporary project and ``--plot-dir``;
nothing is written into ``tests/fixtures``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
PLOT_WAIT_MS = 20_000

# Where ``plot_files`` keeps its ``.plot`` files: the first language to run writes them, the next
# one reads them (``--plot-dir`` of the probe; None = a folder of its own).
PLOT_DIR: Path | None = None

# The plots of the demo project (``screenshot.build_project``), by module.
FOLDERS = {"bands": "03_bands", "pdos": "04_pdos_orbitals", "relax": "01_relax"}


# -- plots in the window -------------------------------------------------------------------------
def start_plot(window, project: Path, kind: str) -> None:
    if kind in FOLDERS:
        window.generate_plot_for(project / FOLDERS[kind], auto_export=False)
    elif kind == "scf":
        window.plot_file(project / "02_scf" / "scf.out", "scf")
    elif kind == "bands_dos":
        window.plot_workflow.plot_pair(project / "03_bands", project / "04_pdos_orbitals")
    else:
        raise ValueError(kind)


def wait_plot(window, start: Callable[[], None]) -> None:
    """Run ``start`` and wait for the plot it asks for: ``RuntimeError`` when it fails or is late."""
    from PyQt6.QtCore import QEventLoop, QTimer

    outcome: list[str | None] = []
    loop = QEventLoop()

    def ready(session: object) -> None:
        outcome.append(None)
        loop.quit()

    def failed(message: str) -> None:
        outcome.append(message or "the plot failed")
        loop.quit()

    window.plot_ready.connect(ready)
    window.plot_failed.connect(failed)
    QTimer.singleShot(PLOT_WAIT_MS, loop.quit)
    try:
        start()
        if not outcome:
            loop.exec()
    finally:
        window.plot_ready.disconnect(ready)
        window.plot_failed.disconnect(failed)
    if not outcome or outcome[0] is not None:
        raise RuntimeError(f"no plot: {outcome[0] if outcome else 'timeout'}")


def wait_for(signal, timeout_ms: int = PLOT_WAIT_MS) -> None:
    from PyQt6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    signal.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    signal.disconnect(loop.quit)


def open_plot(window, project: Path, kind: str) -> None:
    wait_plot(window, lambda: start_plot(window, project, kind))


def ensure_plot(window, project: Path, kind: str) -> None:
    """The plot of ``kind``, unless one is open already."""
    from qe_studio.ui.grids_controller import open_sessions

    if not any(session.kind == kind for session in open_sessions(window.workspace)):
        open_plot(window, project, kind)


def open_sections(window) -> None:
    """Every section of the panel of the current plot open."""
    from qe_studio.ui.widgets.param_widgets import Section

    for section in window.params.body.findChildren(Section):
        section.header.setChecked(True)


def params_scenario(kind: str) -> Callable[..., None]:
    def scenario(window, project: Path) -> None:
        open_plot(window, project, kind)
        open_sections(window)

    scenario.__doc__ = f"The {kind} plot and its panel of adjustments, every section open."
    return scenario


# -- sessions without a window ---------------------------------------------------------------------
# (path, kind, partner) of each figure: the fixtures the module tests use.
CASES = {
    "bands": (FIXTURES / "al_bands", "bands", None),
    "bands_spin": (FIXTURES / "qe731_ni_spin_bands", "bands", None),
    "pdos": (FIXTURES / "al_pdos_flat", "pdos", None),
    "pdos_spin": (FIXTURES / "qe731_ni_spin_pdos", "pdos", None),
    "relax": (FIXTURES / "si_relax", "relax", None),
    "relax_vc": (FIXTURES / "kao_vc_relax", "relax", None),  # thresholds the run did not state
    "scf": (FIXTURES / "al_bands" / "al.scf.out", "scf", None),
    "bands_dos": (FIXTURES / "al_bands", "bands_dos", FIXTURES / "al_pdos_flat"),
}


def build(case: str, scratch: Path, stored: tuple = (None, [])):
    """The session of ``case`` (its ``.plot`` content given as ``read_plot_file`` answers)."""
    from qe_studio.core.config import AppConfig
    from qe_studio.core.detection import ref_target
    from qe_studio.core.folder_memory import FolderMemory
    from qe_studio.core.plotting.grid import PlotRef
    from qe_studio.core.plotting.session import build_session, load_plot
    from qe_studio.core.sniff import SniffCache

    path, kind, partner = CASES[case]
    sniff = SniffCache().sniff
    result, dataset = load_plot(ref_target(PlotRef(path, kind, partner), sniff), sniff)
    memory = FolderMemory(scratch / f"{case}.folders.json")
    session, _warnings = build_session(result, dataset, AppConfig(), stored, memory)
    return session


def figure_texts(session, **changes) -> list[str]:
    """The text of every ``matplotlib.text.Text`` the figure holds: axes, ticks, legend, title,
    annotations and the "no data" message."""
    import matplotlib
    import matplotlib.text
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from qe_studio.core.plotting.style import figure_style

    params = dataclasses.replace(session.params, **changes)
    style = figure_style(params.background)
    figure = Figure(figsize=params.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context(style.rc(params.font_size)):
        info = session.module.render(figure, session.dataset, params, style)
    figure.canvas.draw()
    texts = {t.get_text() for t in figure.findobj(matplotlib.text.Text) if t.get_text().strip()}
    return sorted(texts | {line for line in info.summary.split(" · ") if line})


def figures_scenario(window, project: Path) -> list[str]:
    """The text of the five modules' figures (the legend on, so its entries exist), the bands of a
    spin run coloured by occupation, a PDOS of two atoms' sum, an SCF with no panel left, and a
    grid with a cell that cannot be drawn."""
    with tempfile.TemporaryDirectory(prefix="lain-i18n-figures-") as where:
        scratch = Path(where)
        texts = figure_texts(build("bands", scratch), show_legend=True)
        spin = build("bands_spin", scratch)
        texts += figure_texts(spin, show_legend=True, spin_coloring="occupation")
        pdos = build("pdos", scratch)
        texts += figure_texts(pdos, atoms=[1])
        texts += figure_texts(build("pdos_spin", scratch), spin_mode="overlay")
        texts += figure_texts(build("relax", scratch), panels="all")
        texts += figure_texts(relax_with_default_thresholds(scratch), panels="all")
        scf = build("scf", scratch)
        texts += figure_texts(scf)
        texts += figure_texts(scf, show_accuracy=False, show_energy=False, show_magnetization=False)
        texts += figure_texts(build("bands_dos", scratch), show_legend=True)
        texts += figure_texts(grid_session(scratch))
    return sorted(set(texts))


def relax_with_default_thresholds(scratch: Path):
    """The vc-relax whose energy and pressure thresholds are the QE defaults (the legend says so)."""
    from qe_studio.core.qe.relax import QE_DEFAULT

    session = build("relax_vc", scratch)
    data = session.dataset.data
    data.energy_threshold_source = data.pressure_threshold_source = QE_DEFAULT
    return session


def grid_session(scratch: Path):
    """A grid of the bands, the PDOS and a plot whose folder is gone."""
    from qe_studio.core.calculations.grid import GridCellData
    from qe_studio.core.config import AppConfig
    from qe_studio.core.folder_memory import FolderMemory
    from qe_studio.core.plotting.grid import GridCell, GridSpec, PlotRef
    from qe_studio.core.plotting.grid_session import build_grid_session

    gone = PlotRef(scratch / "gone", "bands")
    cells = [
        GridCellData(GridCell(0, 0, PlotRef(*CASES["bands"][:2]), "A"), build("bands", scratch)),
        GridCellData(GridCell(0, 1, PlotRef(*CASES["pdos"][:2])), build("pdos", scratch)),
        GridCellData(GridCell(1, 0, gone), None, f"{gone.path}"),
    ]
    spec = GridSpec("g", 2, 2, [c.cell for c in cells])
    memory = FolderMemory(scratch / "grid.folders.json")
    return build_grid_session(spec, cells, scratch, AppConfig(), memory, None)


# -- what is written must not follow the language ------------------------------------------------------
CSV_CASES = (
    ("bands", {}),
    ("bands_spin", {}),
    ("pdos", {}),
    ("pdos", {"atoms": [1]}),
    ("pdos_spin", {}),  # mirrored: the ↓ column carries "espelhado"
    ("bands_dos", {}),
)


def csv_scenario(window, project: Path) -> list[str]:
    """The CSV of each figure that has one (its header and a digest of the whole text) and the files
    ``plan_export`` would write for it."""
    from qe_studio.core.plotting.export import plan_export
    from qe_studio.core.plotting.table import to_csv

    facts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lain-i18n-csv-") as where:
        scratch = Path(where)
        for case, changes in CSV_CASES:
            session = build(case, scratch)
            params = dataclasses.replace(session.params, **changes)
            text = to_csv(session.module.table(session.dataset, params))
            label = f"{case} {sorted(changes)}"
            facts.append(f"{label} header: {text.splitlines()[0]}")
            facts.append(f"{label} digest: {hashlib.sha256(text.encode()).hexdigest()[:16]}")
            plan = plan_export(session, FIXTURES)
            facts.append(f"{label} plan: {plan.stem} {plan.formats} table={plan.table}")
    return facts


def alter_choices(session) -> None:
    """Every ``choice`` of the panel to another of its values."""
    for field in session.module.param_schema(session.dataset):
        if field.kind != "choice":
            continue
        current = getattr(session.params, field.name)
        other = next((value for value, _label in field.choices if value != current), None)
        if other is not None:
            setattr(session.params, field.name, other)


def changed_fields(session) -> list[str]:
    return sorted(
        name
        for name in vars(session.params)
        if getattr(session.params, name) != getattr(session.defaults, name)
    )


PLOT_CASES = ("bands", "bands_spin", "pdos", "pdos_spin", "relax", "scf", "bands_dos")


def plot_files_scenario(window, project: Path) -> list[str]:
    """A ``<kind>.plot`` per module with every choice changed, then read and written again.

    The first language to run writes the files into ``PLOT_DIR``; the next one finds them and
    reads what the other wrote. Per case the facts are: the fields that differ from the defaults,
    the file as it was, and as this language writes it back. Then ``bands`` again through the
    window: the real way, ``PlotSettingsStore.flush_now``."""
    from qe_studio.core.plotting.plot_file import (
        plot_file_path,
        read_plot_file,
        write_plot_file,
    )

    keep = PLOT_DIR or Path(tempfile.mkdtemp(prefix="lain-i18n-plots-"))
    facts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lain-i18n-again-") as where:
        scratch = Path(where)
        for case in PLOT_CASES:
            folder = keep / case
            kind = CASES[case][1]
            if not plot_file_path(folder, kind).exists():  # the first language writes it
                fresh = build(case, scratch)
                alter_choices(fresh)
                write_plot_file(folder, kind, fresh.params)
            original = plot_file_path(folder, kind).read_text(encoding="utf-8")
            session = build(case, scratch, read_plot_file(folder, kind))
            again = write_plot_file(scratch / case, kind, session.params)
            facts += [
                f"{case} changed: {changed_fields(session)}",
                f"{case} original:\n{original}",
                f"{case} again:\n{again.read_text(encoding='utf-8')}",
            ]
        facts.append("window bands:\n" + window_round_trip(window, project, keep / "bands"))
    return facts


def window_round_trip(window, project: Path, stored: Path) -> str:
    """``03_bands`` copied, the ``bands.plot`` of ``stored`` put into it, plotted, marked as edited
    and written by ``flush_now``: the text of the file after."""
    from qe_studio.core.plotting.plot_file import plot_file_path

    folder = project / "07_bands_plot_file"
    shutil.copytree(project / "03_bands", folder)
    target = plot_file_path(folder, "bands")
    target.parent.mkdir(exist_ok=True)
    shutil.copy(plot_file_path(stored, "bands"), target)
    window.service.detect_now(folder)
    wait_plot(window, lambda: window.generate_plot_for(folder, auto_export=False))
    session = window.current_plot().session
    window.plot_settings.mark(session)
    window.plot_settings.flush_now()
    return target.read_text(encoding="utf-8")


# -- dialogs --------------------------------------------------------------------------------------------
def atoms_dialog_scenario(window, project: Path) -> list[str]:
    """The atoms of the PDOS compound with nothing marked, so the warning shows."""
    from qe_studio.ui.dialogs.atoms import AtomsDialog

    open_plot(window, project, "pdos")
    session = window.current_plot().session
    choices = session.module.atoms_of(session.dataset)
    dialog = AtomsDialog(choices, [1], window)
    dialog.show()
    dialog.unmark_all.click()
    dialog.save_button.click()
    return [dialog.heading.text(), dialog.count.text(), dialog.problem.text()]


def question_without_loop(parent, title, text, *rest):
    """``QMessageBox.question`` shown and not run: a modal loop would wait forever."""
    from PyQt6.QtWidgets import QMessageBox

    buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    QMessageBox(QMessageBox.Icon.Question, title, text, buttons, parent).show()
    return QMessageBox.StandardButton.No


def grid_dialog_scenario(window, project: Path) -> list[str]:
    """The Grids window over two open plots: the empty "Abrir…" menu, a grid that does not exist, a
    cell outside the grid, a saved grid, and the two questions (replace, delete)."""
    from PyQt6.QtWidgets import QMessageBox

    for kind in ("bands", "pdos"):
        ensure_plot(window, project, kind)
    window.grids.open()
    dialog = window.grids.dialog
    # One row of the first two open plots, whatever the scenarios before left open.
    from qe_studio.core.plotting.grid import GridCell

    first, second = (choice.ref for choice in window.grids.choices()[:2])
    dialog.cols.setValue(2)
    dialog.table.set_cells([GridCell(0, 0, first), GridCell(0, 1, second)])
    facts: list[str] = []
    real = QMessageBox.question
    QMessageBox.question = staticmethod(question_without_loop)  # type: ignore[assignment]
    try:
        dialog.open_menu.aboutToShow.emit()  # no grid saved yet
        dialog.open_grid("inexistente")
        facts.append(dialog.info.text())
        dialog.delete()
        facts.append(dialog.info.text())
        dialog.cols.setValue(1)  # the second cell is squeezed onto the first one's place
        facts.append(dialog.problem.text())
        dialog.cols.setValue(2)
        dialog.table.spin(1, 2).setValue(2)
        dialog.save()
        facts.append(dialog.info.text())
        dialog.open_grid(dialog.name.text())
        facts.append(dialog.info.text())
        dialog._saved_as = None  # a grid of the same name: replace?
        dialog.save()
        dialog.delete()  # delete the saved one?
        dialog.open_menu.aboutToShow.emit()
    finally:
        QMessageBox.question = real  # type: ignore[assignment]
    return facts + invalid_grids()


def invalid_grids() -> list[str]:
    """What ``GridSpec.validate`` says of grids the window cannot make (a saved file can hold them)."""
    from qe_studio.core.plotting.grid import MAX_SIZE, GridCell, GridSpec, PlotRef

    ref = PlotRef(FIXTURES / "al_bands", "bands")
    specs = (
        GridSpec(" ", 1, 1, []),
        GridSpec("a/b", MAX_SIZE + 1, 1, [GridCell(0, 0, None)]),
        GridSpec("g", 1, 1, [GridCell(0, 1, ref)]),
        GridSpec("g", 1, 2, [GridCell(0, 0, ref), GridCell(0, 0, ref)]),
    )
    return [message for spec in specs for message in spec.validate()]


def export_scenario(window, project: Path) -> list[str]:
    """The bands exported (the names of what is written), then again: the overwrite question, shown
    and answered "cancel". ``name:`` facts must be the same in every language."""
    from qe_studio.core.plotting.export import plan_export
    from qe_studio.ui import plot_export
    from qe_studio.ui.dialogs.overwrite import OverwriteChoice, OverwriteDialog

    open_plot(window, project, "bands")
    session = window.current_plot().session
    written: list[list[Path]] = []
    window.export_finished.connect(written.append)
    if not window.export_plot():
        raise RuntimeError("the export did not start")
    wait_for(window.export_finished)

    def ask(parent, existing, new_stem):
        OverwriteDialog(existing, new_stem, parent).show()
        return OverwriteChoice.CANCEL, False

    real = plot_export.ask_overwrite
    plot_export.ask_overwrite = ask  # type: ignore[assignment]
    try:
        window.export_plot()
    finally:
        plot_export.ask_overwrite = real  # type: ignore[assignment]
    plan = plan_export(session, window.config.paths.local_root)
    return [
        *(f"name: {path.name}" for path in written[0]),
        f"name: next {plan.new_stem}",
        f"message: {window.status.message.text()}",
    ]


def files_roles_scenario(window, project: Path) -> list[str]:
    """How the files of the bands plot were found: ``Method.label`` (shown) against its ``value``
    (the data), and the label of each role the panel's tooltips name."""
    from qe_studio.core.calculations.base import Method

    open_plot(window, project, "bands")
    result = window.current_plot().session.result
    facts = [f"{method.value} = {method.label}" for method in Method]
    facts += [f"{role}: {method.label}" for role, method in sorted(result.methods.items())]
    return facts


SCENARIOS: dict[str, Callable[..., list[str] | None]] = {
    "params_bands": params_scenario("bands"),
    "params_pdos": params_scenario("pdos"),
    "params_bands_dos": params_scenario("bands_dos"),
    "params_relax": params_scenario("relax"),
    "params_scf": params_scenario("scf"),
    "figures": figures_scenario,
    "csv": csv_scenario,
    "plot_files": plot_files_scenario,
    "atoms_dialog": atoms_dialog_scenario,
    "grid_dialog": grid_dialog_scenario,
    "export": export_scenario,
    "files_roles": files_roles_scenario,
}
