"""The atom selection of a PDOS (spec 21): which atoms the compound has and which were saved."""

from __future__ import annotations

from typing import Any

from ...compounds import AtomChoices, normalize_selection
from ..base import Stores
from .data import PdosDataset
from .params import PdosParams


def atoms_of(dataset: PdosDataset) -> AtomChoices:
    """Always offered; ``sites`` is empty when the SCF / NSCF header could not be read."""
    return AtomChoices(dataset.sites, dataset.compound)


def stored_params(dataset: PdosDataset, stores: Stores) -> dict[str, Any]:
    """``{"atoms": [...]}`` when the compound has a saved selection that still means something:
    indices that do not exist are dropped, and nothing left or every atom is the default."""
    if dataset.compound is None:
        return {}
    saved = stores.compounds.selection(dataset.compound.key)
    atoms = normalize_selection(saved, [site.index for site in dataset.sites])
    return {} if atoms is None else {"atoms": atoms}


def save_stored(dataset: PdosDataset, params: PdosParams, name: str, stores: Stores) -> None:
    """The user chose atoms: remember them for every plot of this compound (None = all: forgotten)."""
    if name == "atoms" and dataset.compound is not None:
        stores.compounds.save(dataset.compound.key, dataset.compound.formula, params.atoms)
