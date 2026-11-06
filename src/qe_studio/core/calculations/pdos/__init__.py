"""Projected density of states (PRD §4.3), split by responsibility like ``bands``."""

from .data import PdosDataset
from .module import PdosModule
from .params import PdosParams
from .render import series_label

__all__ = ["PdosDataset", "PdosModule", "PdosParams", "series_label"]
