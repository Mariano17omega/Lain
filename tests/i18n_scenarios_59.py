"""Probe scenarios of spec 59: the 3D visualization window, panel, measures and Print.

- ``view3d_window``: the 3D window on ``scf.in``, toolbar, status bar and left panel with every
  accordion section opened.
- ``view3d_measures``: the measures section with a distance and an angle in their tables.
- ``view3d_atom_panel``: an atom selected and the "Átomo" section with its data and neighbors.
- ``view3d_print``: the Print action results (success status and error notice).
- ``view3d_plot_file``: language invariance of the ``view3d.plot`` file.

Modules with texts are imported inside the functions: the language is installed before them.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

PLOT_DIR: Path | None = None


def _make_window(window, project: Path):
    from qe_studio.core.structure3d.source import read_structure
    from qe_studio.ui.widgets.structure3d.window import StructureWindow

    scf_in = project / "02_scf" / "scf.in"
    structure = read_structure(scf_in)
    view = StructureWindow(structure, window.theme, window.settings, root=lambda: project)
    view.show()
    view.canvas.grab()  # initialize picking and render data
    return view


def view3d_window(window, project: Path) -> list[str]:
    """The 3D window on ``scf.in`` with all sections opened, the toolbar and the status bar."""
    view = _make_window(window, project)
    for section in view.panel.sections.values():
        section.header.setChecked(True)

    facts = [
        f"title: {view.windowTitle()}",
        f"status: {view.info.text()}",
        f"reset: {view.reset_button.text()} | {view.reset_button.toolTip()}",
        f"view_button: {view.view_button.text()} | {view.view_button.toolTip()}",
        f"print_button: {view.print_button.text()} | {view.print_button.toolTip()}",
    ]
    for name, action in view.view_actions.items():
        facts.append(f"view_{name}: {action.text()}")
    return facts


def view3d_measures(window, project: Path) -> list[str]:
    """The measures section with a distance and an angle in the tables."""
    from qe_studio.core.structure3d.measurements import Measurement, row_text, to_tsv
    from qe_studio.core.structure3d.model import AtomRef

    view = _make_window(window, project)
    view.panel.sections["measures"].header.setChecked(True)
    measures = view.panel.measures

    # Measure distance between atom 0 and a shifted copy (the demo structure has nat=1)
    m_dist = Measurement("distancia", (AtomRef(0), AtomRef(0, (1, 0, 0))), 2.863)
    atoms_d, val_d = row_text(view.structure, m_dist)
    measures.tables["distancia"].add(m_dist, atoms_d, val_d)
    measures.measurements.append(m_dist)

    # Measure angle using atom 0 and two shifted copies
    m_ang = Measurement("angulo", (AtomRef(0), AtomRef(0, (1, 0, 0)), AtomRef(0, (0, 1, 0))), 60.0)
    atoms_a, val_a = row_text(view.structure, m_ang)
    measures.tables["angulo"].add(m_ang, atoms_a, val_a)
    measures.measurements.append(m_ang)

    measures._refresh()

    return [
        f"tsv:\n{to_tsv(view.structure, measures.measurements)}",
        f"dist_rows: {measures.tables['distancia'].texts()}",
        f"ang_rows: {measures.tables['angulo'].texts()}",
        f"hint: {measures.hint.text()}",
    ]


def view3d_atom_panel(window, project: Path) -> list[str]:
    """An atom selected: the 'Átomo' section with its data and bonded neighbors table."""
    from qe_studio.core.structure3d.model import AtomRef

    view = _make_window(window, project)
    view.panel.sections["atom"].header.setChecked(True)
    ref = AtomRef(0)
    view.canvas.select(ref)
    view.panel.atom.show_atom(ref, view.canvas.graph)

    atom = view.panel.atom
    facts = [
        f"atom_title: {atom.title.text()}",
        f"placeholder: {atom.placeholder.text()}",
        f"neighbors_caption: {atom.neighbors_caption.text()}",
    ]
    for key in (
        "species",
        "element",
        "mass",
        "pseudo",
        "cart",
        "frac",
        "image",
        "flags",
        "magnetization",
        "coordination",
    ):
        facts.append(f"{key}: {atom.value(key)}")
    return facts


def view3d_print(window, project: Path) -> list[str]:
    """The Print messages: success message and error reasons."""
    view = _make_window(window, project)

    # Success notice
    view._print_done(Path("scf.png"))
    done_msg = view.statusBar().currentMessage() if view.statusBar() else ""

    # Error notice
    view._print_error(FileNotFoundError())
    error_msg = view.statusBar().currentMessage() if view.statusBar() else ""

    return [
        f"print_done: {done_msg}",
        f"print_error: {error_msg}",
    ]


def view3d_plot_file(window, project: Path) -> list[str]:
    """Language invariance of view3d.plot: options in Portuguese stay identical in English."""
    import yaml

    from qe_studio.core.structure3d.options import DisplayOptions
    from qe_studio.core.structure3d.source import read_structure
    from qe_studio.core.structure3d.view_file import (
        read_session,
        view_file_path,
        write_session,
    )
    from qe_studio.core.structure3d.view_state import session_of

    keep = PLOT_DIR or Path(tempfile.mkdtemp(prefix="lain-i18n-3d-plots-"))
    scf_in = project / "02_scf" / "scf.in"
    structure = read_structure(scf_in)
    folder = keep / "scf"
    folder.mkdir(parents=True, exist_ok=True)
    target = view_file_path(folder)

    if not target.exists():
        # First language writes it
        opts = DisplayOptions(
            style="vareta",
            background="claro",
            labels="simbolo",
            show_cell=False,
            show_abc=False,
            show_xyz=False,
            reps=(2, 2, 2),
        )
        session = session_of(structure, opts, camera=None)
        write_session(folder, scf_in.name, session)

    original_yaml = target.read_text(encoding="utf-8")
    session, _ = read_session(folder, scf_in.name)
    assert session is not None

    with tempfile.TemporaryDirectory(prefix="lain-i18n-3d-again-") as where:
        scratch = Path(where)
        write_session(scratch, scf_in.name, session)
        again_yaml = view_file_path(scratch).read_text(encoding="utf-8")

    orig_data = yaml.safe_load(original_yaml)
    again_data = yaml.safe_load(again_yaml)
    return [
        f"original_json: {json.dumps(orig_data, sort_keys=True)}",
        f"again_json: {json.dumps(again_data, sort_keys=True)}",
    ]


SCENARIOS = {
    "view3d_window": view3d_window,
    "view3d_measures": view3d_measures,
    "view3d_atom_panel": view3d_atom_panel,
    "view3d_print": view3d_print,
    "view3d_plot_file": view3d_plot_file,
}
