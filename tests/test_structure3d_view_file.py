"""Spec 47 R1: ``view3d.plot``, a section per file, and the view state it keeps (no Qt)."""

import os
import shutil
from dataclasses import fields

import numpy as np
import pytest
import yaml

from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.core.structure3d.camera import Camera, frame_from
from qe_studio.core.structure3d.options import DisplayOptions
from qe_studio.core.structure3d.source import read_structure, structure_of_text
from qe_studio.core.structure3d.view_file import (
    HEADER,
    load_view,
    read_session,
    remove_session,
    view_file_path,
    write_session,
)
from qe_studio.core.structure3d.view_state import (
    CameraState,
    apply_options,
    camera_from_stored,
    session_of,
)

from conftest import FIXTURES

SI_SCF = FIXTURES / "si_bands" / "si.scf.in"
SLAB = FIXTURES / "kao_surface_inputs" / "scf-kaolinite-slab-001-2x1x1.in"
ISOMETRIC = frame_from(np.array([1.0, 1.0, 1.0]), np.array([0.0, 0.0, 1.0]))

TWO_SPECIES = """&CONTROL
/
&SYSTEM
  ibrav = 1, celldm(1) = 20.0, nat = 2, ntyp = 2
/
ATOMIC_SPECIES
{species}
ATOMIC_POSITIONS angstrom
O 1.0 1.0 1.0
H 1.96 1.0 1.0
"""
O_FIRST = "O 15.999 O.UPF\nH 1.008 H.UPF"
H_FIRST = "H 1.008 H.UPF\nO 15.999 O.UPF"

NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes anywhere"
)


def changed_options(structure) -> DisplayOptions:
    """Every option away from its default."""
    last = len(structure.species) - 1
    return DisplayOptions(
        style="fio",
        radius_scale=1.5,
        bond_factor=1.3,
        show_bonds=False,
        reps=(2, 1, 3),
        labels="ambos",
        label_size=16,
        show_cell=False,
        show_abc=False,
        show_xyz=False,
        abc_width=3.5,
        xyz_width=0.5,
        perspective=False,
        background="claro",
        species_colors={0: (255, 0, 255), last: (1, 2, 3)},
        species_hidden={last},
    )


def turned_camera() -> Camera:
    camera = Camera()
    camera.set_isometric()
    camera.rotate_world("x", 30.0)
    camera.rotate_world("z", -45.0)
    camera.zoom, camera.focal = 33.0, 40.0
    camera.pan = np.array([12.5, -3.25])
    return camera


def a_session(radius: float = 1.25) -> dict:
    structure = read_structure(SI_SCF)
    return session_of(structure, DisplayOptions(radius_scale=radius), CameraState.of(Camera()))


def sections_of(folder) -> dict:
    sections, warnings = read_plot_file(folder, "view3d")
    assert warnings == []
    assert sections is not None
    return sections


def stamp(path):
    return path.read_bytes(), path.stat().st_mtime_ns


# -- the state: round trip and validation -------------------------------------------------------------


@pytest.mark.parametrize("path", [SI_SCF, SLAB], ids=["si", "slab"])
def test_every_option_and_the_camera_make_the_round_trip(path):
    structure = read_structure(path)
    options = changed_options(structure)
    default = DisplayOptions()
    assert all(getattr(options, f.name) != getattr(default, f.name) for f in fields(options))
    camera = turned_camera()
    text = yaml.safe_dump(session_of(structure, options, CameraState.of(camera)), sort_keys=False)
    back = yaml.safe_load(text)

    restored = DisplayOptions()
    assert apply_options(restored, back["options"], structure) == []
    assert restored == options
    state = camera_from_stored(back["camera"])
    assert state is not None
    other = Camera()
    state.apply(other)
    np.testing.assert_allclose(other.rotation, camera.rotation, rtol=0, atol=1e-12)
    np.testing.assert_allclose(other.pan, camera.pan, rtol=0, atol=1e-12)
    assert (other.zoom, other.focal) == (33.0, 40.0)


def test_the_session_holds_plain_values_and_species_by_label():
    structure = read_structure(SLAB)  # Al, Si, O, H
    options = DisplayOptions(species_colors={1: (255, 0, 255)}, species_hidden={3})
    session = session_of(structure, options, None)
    assert "camera" not in session  # a view never framed has no camera
    assert session["options"]["species_colors"] == {"Si": "#ff00ff"}
    assert session["options"]["species_hidden"] == ["H"]
    assert session["options"]["reps"] == [1, 1, 1]
    yaml.safe_dump(session)  # no numpy scalar in it


def test_species_go_by_label_whatever_the_order_of_atomic_species():
    first = structure_of_text(TWO_SPECIES.format(species=O_FIRST))
    second = structure_of_text(TWO_SPECIES.format(species=H_FIRST))
    options = DisplayOptions(
        species_colors={1: (0, 255, 0)}, species_hidden={0}
    )  # H green, O hidden
    stored = yaml.safe_load(yaml.safe_dump(session_of(first, options, None)))["options"]
    restored = DisplayOptions()
    assert apply_options(restored, stored, second) == []
    assert restored.species_colors == {0: (0, 255, 0)}  # H is the first species there
    assert restored.species_hidden == {1}


def test_invalid_values_fall_one_by_one_and_the_rest_holds():
    structure = read_structure(SI_SCF)
    stored = {
        "style": "foo",
        "radius_scale": 99,
        "reps": [0, 9, 1],
        "show_cell": "sim",
        "label_size": 3.5,
        "species_colors": {"Si": "vermelho", "Zz": "#ffffff"},
        "species_hidden": ["Nope"],
        "bond_factor": 1.3,
        "labels": "simbolo",
        "abc_width": 2,  # an int is a number
        "futuro": "ignorado",  # unknown: skipped, not counted
    }
    options = DisplayOptions()
    ignored = apply_options(options, stored, structure)
    assert sorted(ignored) == sorted(
        [
            "style",
            "radius_scale",
            "reps",
            "show_cell",
            "label_size",
            "species_colors",
            "species_hidden",
        ]
    )
    assert options == DisplayOptions(bond_factor=1.3, labels="simbolo", abc_width=2.0)
    assert isinstance(options.abc_width, float)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("radius_scale", True),  # a bool is no number
        ("radius_scale", float("nan")),
        ("bond_factor", float("inf")),
        ("xyz_width", 10**400),  # beyond a float
        ("label_size", True),
        ("label_size", 99),
        ("reps", [1, 1]),
        ("reps", [1, True, 1]),
        ("reps", (1, 1, 1)),
        ("show_bonds", 1),
        ("background", "azul"),
        ("species_colors", {"Si": "#ff00f"}),
        ("species_colors", {"Zz": "#ffffff"}),
        ("species_colors", ["Si"]),
        ("species_hidden", "Si"),
    ],
)
def test_one_bad_value_is_ignored(name, value):
    options = DisplayOptions()
    assert apply_options(options, {name: value}, read_structure(SI_SCF)) == [name]
    assert options == DisplayOptions()


def test_options_that_are_no_mapping_are_ignored():
    options = DisplayOptions()
    assert apply_options(options, ["style", "fio"], read_structure(SI_SCF)) == ["options"]
    assert options == DisplayOptions()


def valid_camera() -> dict:
    return {"rotation": ISOMETRIC.tolist(), "zoom": 24.71, "pan": [3.0, -1.5], "focal": 12.0}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("rotation", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.1]]),  # not orthonormal
        ("rotation", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]]),  # a mirror
        ("rotation", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        ("rotation", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, "1"]]),
        ("rotation", None),
        ("zoom", float("nan")),
        ("zoom", 0.0),
        ("zoom", -2.0),
        ("zoom", True),
        ("pan", [0.0, 0.0, 0.0]),
        ("pan", [0.0, float("inf")]),
        ("focal", 0),
    ],
)
def test_a_camera_with_one_bad_value_is_dropped_whole(key, value):
    data = valid_camera()
    data[key] = value
    assert camera_from_stored(data) is None


def test_a_valid_camera_comes_back_and_no_mapping_is_none():
    state = camera_from_stored(valid_camera())
    assert state is not None
    np.testing.assert_allclose(np.array(state.rotation), ISOMETRIC, rtol=0, atol=1e-12)
    assert (state.zoom, state.pan, state.focal) == (24.71, (3.0, -1.5), 12.0)
    assert camera_from_stored(None) is None
    assert camera_from_stored([1, 2]) is None


# -- the file ------------------------------------------------------------------------------------------


def put_view(folder, text: str) -> None:
    """``text`` as the folder's ``plots/view3d.plot``, written by hand."""
    path = view_file_path(folder)
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_write_session_creates_the_file_of_the_plot_family(tmp_path):
    session = a_session()
    assert write_session(tmp_path, "scf.in", session) is None
    text = view_file_path(tmp_path).read_text(encoding="utf-8")
    assert view_file_path(tmp_path) == tmp_path / "plots" / "view3d.plot"
    assert text.startswith(HEADER)
    data = yaml.safe_load(text)
    assert (data["lain_plot"], data["kind"]) == (1, "view3d")
    assert sections_of(tmp_path) == {"scf.in": session}
    assert read_session(tmp_path, "scf.in") == (session, [])
    assert read_session(tmp_path, "outro.in") == (None, [])


def test_a_second_name_adds_a_section_and_the_same_name_replaces_only_its_own(tmp_path):
    first, second = a_session(1.25), a_session(1.75)
    write_session(tmp_path, "a.in", first)
    write_session(tmp_path, "b.in", second)
    assert list(sections_of(tmp_path)) == ["a.in", "b.in"]
    assert sections_of(tmp_path)["a.in"] == first

    # an unknown key (a newer Lain's) in another section survives a write of this one
    data = yaml.safe_load(view_file_path(tmp_path).read_text(encoding="utf-8"))
    data["params"]["b.in"]["futuro"] = [1, 2]
    view_file_path(tmp_path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    newer = a_session(2.0)
    assert write_session(tmp_path, "a.in", newer) is None
    sections = sections_of(tmp_path)
    assert list(sections) == ["a.in", "b.in"]  # replaced in place
    assert sections["a.in"] == newer
    assert sections["b.in"] == {**second, "futuro": [1, 2]}


@pytest.mark.parametrize(
    "text",
    ["params: [unclosed", "lain_plot: 2\nkind: view3d\nparams: {velho.in: {}}\n"],
    ids=["broken", "version-2"],
)
def test_an_unreadable_file_is_replaced(tmp_path, text):
    put_view(tmp_path, text)
    session, warnings = read_session(tmp_path, "scf.in")
    assert session is None and len(warnings) == 1
    assert write_session(tmp_path, "scf.in", a_session()) is None
    assert list(sections_of(tmp_path)) == ["scf.in"]


def test_a_section_that_is_no_mapping_reads_as_none(tmp_path):
    put_view(tmp_path, "lain_plot: 1\nkind: view3d\nparams: {scf.in: [1, 2]}\n")
    assert read_session(tmp_path, "scf.in") == (None, [])


def test_a_folder_that_is_gone_is_not_created_again(tmp_path):
    gone = tmp_path / "Analise_1"
    message = write_session(gone, "scf.in", a_session())
    assert message == (
        "A pasta Analise_1 não existe mais: a vista de scf.in não foi salva em view3d.plot."
    )
    assert not gone.exists()


@NOT_ROOT
def test_a_folder_without_write_permission_gives_a_warning_and_leaves_no_temp(tmp_path):
    folder = tmp_path / "travada"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        message = write_session(folder, "scf.in", a_session())
        assert message is not None
        assert message.startswith(f"Não foi possível salvar view3d.plot em {folder}: ")
        assert list(folder.iterdir()) == []
    finally:
        folder.chmod(0o700)


def test_remove_session_takes_out_only_its_section(tmp_path):
    for name, radius in (("a.in", 1.25), ("b.in", 1.5), ("c.in", 1.75)):
        write_session(tmp_path, name, a_session(radius))
    data = yaml.safe_load(view_file_path(tmp_path).read_text(encoding="utf-8"))
    data["params"]["c.in"]["futuro"] = True
    view_file_path(tmp_path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    before = sections_of(tmp_path)

    assert remove_session(tmp_path, "b.in") is None
    after = sections_of(tmp_path)
    assert list(after) == ["a.in", "c.in"]
    assert after == {"a.in": before["a.in"], "c.in": before["c.in"]}
    assert view_file_path(tmp_path).read_text(encoding="utf-8").startswith(HEADER)


def test_removing_the_last_section_removes_the_file(tmp_path):
    write_session(tmp_path, "scf.in", a_session())
    assert remove_session(tmp_path, "scf.in") is None
    assert not view_file_path(tmp_path).exists()
    assert list(tmp_path.iterdir()) == [tmp_path / "plots"]  # made by the write, left empty
    assert list((tmp_path / "plots").iterdir()) == []


def test_nothing_to_remove_creates_or_changes_nothing(tmp_path):
    assert remove_session(tmp_path, "scf.in") is None  # no file
    assert list(tmp_path.iterdir()) == []
    gone = tmp_path / "sumiu"
    assert remove_session(gone, "scf.in") is None
    assert not gone.exists()

    write_session(tmp_path, "scf.in", a_session())
    before = stamp(view_file_path(tmp_path))
    assert remove_session(tmp_path, "outro.in") is None  # no such section
    assert stamp(view_file_path(tmp_path)) == before

    view_file_path(tmp_path).write_text("params: [unclosed", encoding="utf-8")
    before = stamp(view_file_path(tmp_path))
    assert remove_session(tmp_path, "scf.in") is None  # unreadable: left as it is
    assert stamp(view_file_path(tmp_path)) == before


@NOT_ROOT
@pytest.mark.parametrize("names", [("scf.in",), ("scf.in", "outro.in")], ids=["last", "rewrite"])
def test_a_removal_without_write_permission_gives_a_warning(tmp_path, names):
    folder = tmp_path / "travada"
    folder.mkdir()
    for name in names:
        write_session(folder, name, a_session())
    before = stamp(view_file_path(folder))
    plots = view_file_path(folder).parent
    plots.chmod(0o500)
    try:
        message = remove_session(folder, "scf.in")
        assert message is not None
        assert message.startswith(f"Não foi possível atualizar view3d.plot em {folder}: ")
        assert stamp(view_file_path(folder)) == before
        assert sorted(p.name for p in plots.iterdir()) == ["view3d.plot"]
    finally:
        plots.chmod(0o700)


def test_load_view_reads_the_structure_and_the_section_of_its_file(tmp_path):
    shutil.copy(SI_SCF, tmp_path / "si.scf.in")
    loaded = load_view(tmp_path / "si.scf.in")
    assert loaded.structure.formula == "Si2"
    assert (loaded.session, loaded.warnings) == (None, [])
    session = a_session()
    write_session(tmp_path, "si.scf.in", session)
    assert load_view(tmp_path / "si.scf.in").session == session
    view_file_path(tmp_path).write_text("params: [unclosed", encoding="utf-8")
    loaded = load_view(tmp_path / "si.scf.in")
    assert loaded.session is None
    assert loaded.warnings == ["view3d.plot inválido; usando ajustes padrão."]
