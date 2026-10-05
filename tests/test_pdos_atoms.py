"""Choosing the atoms of a PDOS: the filter, the total, the colors and where the choice is kept
(spec 21 R3, R5)."""

import copy

import numpy as np
import pytest

from atoms_helpers import pdos_folder
from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.base import Stores
from qe_studio.core.compounds import CompoundStore
from qe_studio.core.detection import detect_folder
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.plotting.plot_file import (
    apply_stored,
    read_plot_file,
    stored_elsewhere,
    stored_params,
    write_plot_file,
)
from qe_studio.core.plotting.session import build_session
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe import projwfc
from qe_studio.core.qe.projwfc import Channel, PdosData, PdosSeries
from qe_studio.core.sniff import SniffCache
from spin_helpers import SPIN_PDOS
from test_bands_dos_render import combined
from test_legend_gap_pdos import ENERGY, GAP_TEXT, bands_dos, dataset_of, legend_texts
from test_plotting import CONFIG, load, render

TOTAL_LABEL = "Soma dos átomos selecionados"


@pytest.fixture
def two_al(tmp_path):
    return load(pdos_folder(tmp_path, ("Al", "Al")))


@pytest.fixture
def al_o(tmp_path):
    return load(pdos_folder(tmp_path, ("Al", "O")))


@pytest.fixture
def stores(tmp_path):
    return Stores(CompoundStore(tmp_path / "compounds.json"))


def lines_by_label(figure):
    """The drawn curves by legend label (the Fermi line and other helpers have ``_`` labels)."""
    lines = figure.axes[0].lines
    return {line.get_label(): line for line in lines if not line.get_label().startswith("_")}


# -- the filter ---------------------------------------------------------------------------------
def test_atom_two_is_twice_atom_one(two_al):
    _module, dataset, _params = two_al  # atom n = fixture projections * n
    both = projwfc.aggregate(dataset.data)
    one = projwfc.aggregate(dataset.data, atoms=[1])
    two = projwfc.aggregate(dataset.data, atoms=[2])
    assert set(both) == set(one) == set(two) == {("Al", "s"), ("Al", "p")}
    for key in both:
        assert np.allclose(two[key].up, 2 * one[key].up)
        assert np.allclose(both[key].up, 3 * one[key].up)


def test_no_atoms_means_all_of_them(two_al):
    _module, dataset, _params = two_al
    every = projwfc.aggregate(dataset.data, "species", None)
    explicit = projwfc.aggregate(dataset.data, "species", [1, 2])
    assert np.allclose(every[("Al", "")].up, explicit[("Al", "")].up)


def test_the_filter_runs_before_grouping_and_hidden_series(al_o):
    module, dataset, params = al_o
    params.grouping, params.atoms = "species", [2]
    assert list(projwfc.aggregate(dataset.data, "species", [2])) == [("O", "")]
    figure, _info = render(module, dataset, params)
    labels = lines_by_label(figure)
    assert "O" in labels and "Al" not in labels
    params.hidden_series = ["O"]
    figure, _info = render(module, dataset, params)
    assert "O" not in lines_by_label(figure)


def test_labels_and_colors_do_not_change_with_the_filter(al_o):
    module, dataset, params = al_o
    params.grouping = "species"
    everything = module.series_colors(dataset, params, LIGHT)
    assert set(everything) == {"Al", "O"}
    params.atoms = [2]
    chosen = module.series_colors(dataset, params, LIGHT)
    assert chosen == {"O": everything["O"]}  # only what is drawn, same color as before


# -- the total ----------------------------------------------------------------------------------
def test_total_is_pdos_tot_without_a_filter(two_al):
    module, dataset, params = two_al
    figure, _info = render(module, dataset, params)
    labels = lines_by_label(figure)
    assert "Total" in labels and TOTAL_LABEL not in labels


def test_total_is_the_sum_of_the_chosen_atoms(two_al):
    module, dataset, params = two_al
    params.atoms = [2]
    figure, _info = render(module, dataset, params)
    labels = lines_by_label(figure)
    assert "Total" not in labels
    expected = sum(s.channel.up for s in dataset.data.series if s.atom == 2)
    assert np.allclose(labels[TOTAL_LABEL].get_ydata(), expected)
    assert TOTAL_LABEL in legend_texts(figure)


def test_total_off_stays_off(two_al):
    module, dataset, params = two_al
    params.atoms, params.show_total = [2], False
    figure, _info = render(module, dataset, params)
    assert TOTAL_LABEL not in lines_by_label(figure)


def test_atoms_without_projections_draw_no_total(two_al):
    module, dataset, params = two_al
    params.atoms, params.show_legend = [7], False
    figure, info = render(module, dataset, params)
    assert lines_by_label(figure).keys() == set()
    assert "0 de 2 átomos" in info.summary


def test_selected_total_keeps_both_spin_channels():
    data = load(SPIN_PDOS)[1].data
    total = projwfc.selected_total(data, [1])
    assert total is not None and total.down is not None
    assert projwfc.selected_total(data, [9]) is None


def test_summary_counts_the_atoms(two_al):
    module, dataset, params = two_al
    assert "átomos" not in module.summary(dataset, params)
    params.atoms = [1]
    _figure, info = render(module, dataset, params)
    assert "1 de 2 átomos" in info.summary


def test_the_gap_is_of_the_system_not_of_the_chosen_atoms():
    gapped = Channel(bands_dos((0.0, 1.2)))
    metal = Channel(np.ones_like(ENERGY))
    series = (PdosSeries(1, "Si", 1, "s", None, gapped), PdosSeries(2, "Si", 1, "s", None, metal))
    dataset = dataset_of(PdosData(ENERGY, series, gapped))
    assert dataset.gap is not None
    module = module_for("pdos")
    params = module.default_params(CONFIG, dataset)
    params.legend_gap = True
    gap = dataset.gap
    for atoms in (None, [1], [2]):
        params.atoms = atoms
        figure, _info = render(module, dataset, params)
        assert any(GAP_TEXT in text for text in legend_texts(figure)), atoms
        assert dataset.gap is gap


# -- the sites and the compound -------------------------------------------------------------------
def test_the_dataset_reads_the_atoms_of_the_scf(al_o):
    _module, dataset, _params = al_o
    assert [(s.index, s.species) for s in dataset.sites] == [(1, "Al"), (2, "O")]
    assert dataset.compound is not None and dataset.compound.formula == "AlO"


def test_an_unreadable_site_list_leaves_the_atoms_empty(tmp_path):
    folder = pdos_folder(tmp_path)
    for name in ("scf.out", "nscf.out"):
        text = (folder / name).read_text().replace("tau(", "xyz(")
        (folder / name).write_text(text)
    module, dataset, _params = load(folder)
    assert dataset.sites == () and dataset.compound is None
    choices = module.atoms_of(dataset)
    assert choices is not None and not choices.available


def test_only_the_pdos_module_has_atoms():
    assert module_for("bands").atoms_of(object()) is None  # type: ignore[arg-type]


# -- where the choice is kept ---------------------------------------------------------------------
def test_the_atoms_are_not_in_the_plot_file(two_al, tmp_path):
    _module, _dataset, params = two_al
    params.atoms = [1]
    assert stored_elsewhere(params) == {"atoms"}
    assert "atoms" not in stored_params(params)
    folder = tmp_path / "sim"
    folder.mkdir()
    path = write_plot_file(folder, "pdos", params)
    assert "atoms" not in path.read_text()


def test_an_old_plot_file_with_atoms_is_ignored_quietly(two_al, tmp_path):
    module, dataset, params = two_al
    ignored = apply_stored(params, {"atoms": [1], "emin": -3.0}, module.param_schema(dataset))
    assert params.atoms is None and params.emin == -3.0 and ignored == []
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / "pdos.plot").write_text(
        "lain_plot: 1\nkind: pdos\nparams:\n  atoms: [1]\n  emin: -2.0\n"
    )
    stored, warnings = read_plot_file(folder, "pdos")
    assert warnings == []
    assert stored is not None
    apply_stored(params, stored, module.param_schema(dataset))
    assert params.atoms is None and params.emin == -2.0


def session_of(folder, stores, **kwargs):
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    dataset = result.module.load(result, SniffCache().sniff)
    memory = FolderMemory(folder.parent / "memory.json")
    return build_session(result, dataset, CONFIG, (None, []), memory, stores=stores, **kwargs)[0]


def save(stores, session, atoms):
    compound = session.dataset.compound
    stores.compounds.save(compound.key, compound.formula, atoms)


def test_a_saved_selection_is_applied_over_the_defaults(tmp_path, stores):
    folder = pdos_folder(tmp_path, ("Al", "O"))
    assert session_of(folder, stores).params.atoms is None  # nothing saved: every atom
    save(stores, session_of(folder, stores), [2])
    session = session_of(folder, stores)
    assert session.params.atoms == [2]
    assert session.defaults.atoms == [2] and not session.edited


def test_the_same_compound_in_another_folder_is_filtered(tmp_path, stores):
    first = session_of(pdos_folder(tmp_path, ("Al", "O"), "a"), stores)
    save(stores, first, [2])
    other = session_of(pdos_folder(tmp_path, ("Al", "O"), "b"), stores)
    assert other.params.atoms == [2]


def test_another_order_of_species_is_another_compound(tmp_path, stores):
    save(stores, session_of(pdos_folder(tmp_path, ("Al", "O"), "a"), stores), [2])
    assert session_of(pdos_folder(tmp_path, ("O", "Al"), "b"), stores).params.atoms is None


@pytest.mark.parametrize("saved", [[2, 9], [9, 10], [1, 2], []])
def test_a_saved_selection_that_no_longer_fits_is_dropped(tmp_path, stores, saved):
    folder = pdos_folder(tmp_path, ("Al", "O"))
    session = session_of(folder, stores)
    key = session.dataset.compound.key
    stores.compounds.save(key, "AlO", saved)
    atoms = session_of(folder, stores).params.atoms
    assert atoms == ([2] if saved == [2, 9] else None)


def test_regenerating_reads_the_store_not_the_open_tab(tmp_path, stores):
    folder = pdos_folder(tmp_path, ("Al", "O"))
    first = session_of(folder, stores)
    first.params.atoms = [1]  # edited in the open tab...
    first.params.emin = -4.0
    save(stores, first, [2])  # ...but the compound's saved choice is another
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    again, _warnings = build_session(
        result, first.dataset, CONFIG, (None, []), FolderMemory(tmp_path / "m.json"), first, stores
    )
    assert again.params.atoms == [2]
    assert again.params.emin == -4.0  # the plot edits still survive


def test_persist_saves_in_the_store_and_is_not_a_plot_edit(tmp_path, stores):
    session = session_of(pdos_folder(tmp_path, ("Al", "O")), stores)
    session.params.atoms = [1]
    assert session.persist("atoms", stores) is True
    assert stores.compounds.selection(session.dataset.compound.key) == [1]
    assert session.defaults.atoms == [1] and not session.edited  # nothing for the .plot
    restored = copy.deepcopy(session.defaults)
    assert restored.atoms == [1]  # "Restaurar padrões" keeps the compound's choice
    session.params.atoms = None  # back to every atom
    assert session.persist("atoms", stores) is True
    assert stores.compounds.selection(session.dataset.compound.key) is None


def test_persist_leaves_ordinary_parameters_alone(tmp_path, stores):
    session = session_of(pdos_folder(tmp_path, ("Al", "O")), stores)
    session.params.emin = -2.0
    assert session.persist("emin", stores) is False
    assert session.edited
    assert not (tmp_path / "compounds.json").exists()


def test_without_stores_a_session_is_the_old_one(tmp_path):
    session = session_of(pdos_folder(tmp_path, ("Al", "O")), None)
    assert session.params.atoms is None


# -- a selection saved with another geometry (spec 27-6 R2) ---------------------------------------
ALAT = 7.6307 * 0.529177210903  # Å, of the fixture the folders are built from


def notes_of(session):
    return render(session.module, session.dataset, session.params, LIGHT)[1].notes


def choose(session, stores, atoms):
    """The "Átomos…" dialog: the session's choice saved through the module (with the positions)."""
    session.params.atoms = atoms
    assert session.persist("atoms", stores) is True


def test_saving_keeps_the_positions_the_atoms_were_chosen_with(tmp_path, stores):
    session = session_of(pdos_folder(tmp_path, ("Al", "O")), stores)
    choose(session, stores, [2])
    saved = stores.compounds.stored_sites(session.dataset.compound.key)
    assert saved == [(round(s.x, 2), round(s.y, 2), round(s.z, 2)) for s in session.dataset.sites]
    assert notes_of(session) == ()


def test_another_geometry_keeps_the_selection_and_warns(tmp_path, stores):
    choose(session_of(pdos_folder(tmp_path, ("Al", "O"), "a"), stores), stores, [2])
    moved = session_of(pdos_folder(tmp_path, ("Al", "O"), "b", moved={2: 0.5}), stores)
    assert moved.params.atoms == [2] and moved.defaults.atoms == [2]
    distance = f"{0.5 * ALAT:.1f}".replace(".", ",")
    assert notes_of(moved) == (
        "A seleção de átomos salva foi feita com outras coordenadas "
        f"(átomo 2 moveu {distance} Å). Confira em ‘Átomos…’",
    )
    choose(moved, stores, [2])  # saved again from this geometry: the warning goes
    assert notes_of(moved) == ()
    again = session_of(pdos_folder(tmp_path, ("Al", "O"), "c", moved={2: 0.5}), stores)
    assert again.params.atoms == [2] and notes_of(again) == ()


def test_a_small_move_or_an_old_entry_without_positions_does_not_warn(tmp_path, stores):
    choose(session_of(pdos_folder(tmp_path, ("Al", "O"), "a"), stores), stores, [2])
    near = session_of(pdos_folder(tmp_path, ("Al", "O"), "b", moved={1: 0.05}), stores)
    assert near.params.atoms == [2] and notes_of(near) == ()  # 0.2 Å: a relax
    old = session_of(pdos_folder(tmp_path, ("Al", "O"), "c", moved={2: 0.5}), stores)
    stores.compounds.forget(old.dataset.compound.key)
    save(stores, old, [1])  # as saved before spec 27-6: no positions to compare
    assert stores.compounds.stored_sites(old.dataset.compound.key) is None
    old = session_of(pdos_folder(tmp_path, ("Al", "O"), "d", moved={2: 1.0}), stores)
    assert old.params.atoms == [1] and notes_of(old) == ()


def test_no_warning_while_every_atom_is_shown(tmp_path, stores):
    choose(session_of(pdos_folder(tmp_path, ("Al", "O"), "a"), stores), stores, [2])
    moved = session_of(pdos_folder(tmp_path, ("Al", "O"), "b", moved={2: 0.5}), stores)
    choose(moved, stores, None)  # every atom: the entry is gone
    assert notes_of(moved) == ()
    assert notes_of(session_of(pdos_folder(tmp_path, ("Al", "O"), "c"), stores)) == ()


def test_bands_and_dos_carry_the_warning_of_the_dos(tmp_path, stores):
    dos = pdos_folder(tmp_path, ("Al", "O"), "dos", moved={2: 0.5})
    key, formula = _entry(dos)
    stores.compounds.save(key, formula, [2], [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
    module, dataset, params = combined(dos=dos)
    for name, value in module.stored_params(dataset, stores).items():
        setattr(params, name, value)
    notes = render(module, dataset, params, LIGHT)[1].notes
    assert params.atoms == [2]
    assert notes[0].startswith(
        "A seleção de átomos salva foi feita com outras coordenadas (átomo 2"
    )


def _entry(folder):
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    compound = result.module.load(result, SniffCache().sniff).compound
    return compound.key, compound.formula
