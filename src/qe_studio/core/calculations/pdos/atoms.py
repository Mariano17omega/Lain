"""The atom selection of a PDOS (spec 21): which atoms the compound has and which were saved."""

from __future__ import annotations

from typing import Any

from ...compounds import AtomChoices, GeometryDrift, geometry_drift, normalize_selection
from ..base import Stores
from .data import PdosDataset
from .params import PdosParams

CHECK_ATOMS = "Confira em ‘Átomos…’"


def atoms_of(dataset: PdosDataset) -> AtomChoices:
    """Always offered; ``sites`` is empty when the SCF / NSCF header could not be read."""
    return AtomChoices(dataset.sites, dataset.compound)


def stored_params(dataset: PdosDataset, stores: Stores) -> dict[str, Any]:
    """``{"atoms": [...]}`` when the compound has a saved selection that still means something:
    indices that do not exist are dropped, and nothing left or every atom is the default.

    A selection in force that was saved with other positions sets ``dataset.selection_drift``
    (spec 27-6): the plot warns, the selection stays."""
    dataset.selection_drift = None
    if dataset.compound is None:
        return {}
    key = dataset.compound.key
    atoms = normalize_selection(stores.compounds.selection(key), [s.index for s in dataset.sites])
    if atoms is None:
        return {}
    saved = stores.compounds.stored_sites(key)
    if saved is not None:
        dataset.selection_drift = geometry_drift(saved, [(s.x, s.y, s.z) for s in dataset.sites])
    return {"atoms": atoms}


def save_stored(dataset: PdosDataset, params: PdosParams, name: str, stores: Stores) -> None:
    """The user chose atoms: remember them, with the positions they were chosen with, for every
    plot of this compound (None = all: forgotten). The chosen ones fit these positions now."""
    if name == "atoms" and dataset.compound is not None:
        sites = [(s.x, s.y, s.z) for s in dataset.sites]
        stores.compounds.save(dataset.compound.key, dataset.compound.formula, params.atoms, sites)
        dataset.selection_drift = None


def notes(dataset: PdosDataset) -> tuple[str, ...]:
    """The readout's warning about a selection saved with another geometry (spec 27-6 R2.4)."""
    drift = dataset.selection_drift
    return () if drift is None else (drift_note(drift),)


def drift_note(drift: GeometryDrift) -> str:
    if drift.counts is not None:
        saved, current = drift.counts
        return (
            f"A seleção de átomos salva foi feita com outra estrutura ({saved} átomos; esta tem "
            f"{current}). {CHECK_ATOMS}"
        )
    distance = f"{drift.distance or 0.0:.1f}".replace(".", ",")
    return (
        "A seleção de átomos salva foi feita com outras coordenadas "
        f"(átomo {drift.atom} moveu {distance} Å). {CHECK_ATOMS}"
    )
