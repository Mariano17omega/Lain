"""The calculation types of "Criar cálculo" (spec 25 R3): a module per type plus this registry.

A new type is a module with a ``CalcType`` subclass (and its templates) registered here.
"""

from __future__ import annotations

from .bandas import BandasType
from .base import (
    DEFAULT_MODE,
    MODES,
    CalcPlan,
    CalcType,
    FormField,
    Mode,
    PlannedFile,
    field_problems,
    resolve,
    visible_fields,
)
from .files import InputFile
from .pdos import PdosType
from .relax import RelaxType
from .scf import ScfType
from .vc_relax import VcRelaxType

__all__ = [
    "DEFAULT_MODE",
    "MODES",
    "REGISTRY",
    "CalcPlan",
    "CalcType",
    "FormField",
    "InputFile",
    "Mode",
    "PlannedFile",
    "by_id",
    "field_problems",
    "resolve",
    "visible_fields",
]

REGISTRY: tuple[CalcType, ...] = (ScfType(), RelaxType(), VcRelaxType(), BandasType(), PdosType())


def by_id(type_id: str) -> CalcType:
    """The registered type ``type_id``; KeyError when there is none."""
    for calc_type in REGISTRY:
        if calc_type.id == type_id:
            return calc_type
    raise KeyError(type_id)
