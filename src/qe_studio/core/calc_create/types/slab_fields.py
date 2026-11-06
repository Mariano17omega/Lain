"""The fields of the Slab type (spec 40 R5.2, R5.3): the "Superfície" tab, with every parameter of the
user's scripts, and the k-point mesh and ``cell_dofree`` of the input's tab (the Supercélula's too, spec 41)."""

from __future__ import annotations

import numpy as np

from ....i18n import N_, _
from ..surface.fixing import BOTTOM, NONE, SPECIES
from ..surface.geometry import skewed
from .base import FieldKind, FormField
from .surface_fields import bond_scale_field, fix_fields, molecule_field

__all__ = [
    "AXIS_CHOICES",
    "AXIS_OF",
    "CELL_DOFREE",
    "COMPLETE_LABEL",
    "DEFAULT_CELL_DOFREE",
    "GROUP",
    "MESH_HINT",
    "METALS_LABEL",
    "SLAB_FIX_RULES",
    "dofree_field",
    "mesh_field",
    "non_orthogonal_notes",
    "surface_fields",
]

GROUP = N_("Superfície")  # no file is named so: a tab of its own, before the input's
AXIS_CHOICES = ("c (001)", "b (010)", "a (100)")
AXIS_OF: dict[str, str] = dict(zip(AXIS_CHOICES, ("c", "b", "a"), strict=True))
SLAB_FIX_RULES = (BOTTOM, SPECIES, NONE)
CELL_DOFREE = (
    *("all", "ibrav", "a", "b", "c", "fixa", "fixb", "fixc", "x", "y", "z"),
    *("xy", "xz", "yz", "xyz", "shape", "volume", "2Dxy", "2Dshape"),
    *("epitaxial_ab", "epitaxial_ac", "epitaxial_bc"),
)
DEFAULT_CELL_DOFREE = "2Dxy"
COMPLETE_LABEL = _("Completar poliedros de borda (O + H)")
METALS_LABEL = _("Metais da borda")
MESH_HINT = _("Vazio = a do SCF reescalada: o eixo do vácuo vale 1")
NON_ORTHOGONAL = _(
    "cell_dofree = '{}' numa célula de eixos não ortogonais: o INPUT_PW avisa que algumas opções de "
    "cell_dofree não funcionam com eixos não ortogonais"
)


def _field(
    field_id: str,
    label: str,
    kind: FieldKind,
    default: object,
    tooltip: str,
    standard: bool = False,
    choices: tuple[str, ...] = (),
) -> FormField:
    return FormField(
        field_id,
        label,
        kind,
        default,
        group=GROUP,
        tooltip=tooltip,
        choices=choices,
        standard=standard,
    )


def surface_fields() -> list[FormField]:
    """The "Superfície" tab: the four of the ``padrao`` mode, then the scripts' other parameters."""
    return [
        molecule_field(
            GROUP,
            _("SCF da molécula (opcional)"),
            _(
                "Só para o vácuo: soma a altura da molécula e a distância de adsorção ao vácuo mínimo"
            ),
        ),
        _field(
            "axis",
            _("Superfície (eixo empilhado)"),
            "choice",
            AXIS_CHOICES[0],
            _(
                "O eixo da célula do SCF que é esticado para abrir o vácuo; os outros dois formam o plano"
            ),
            standard=True,
            choices=AXIS_CHOICES,
        ),
        _field(
            "flip",
            _("Inverter a superfície"),
            "bool",
            False,
            _(
                "Toma o segundo vetor do plano com o sinal trocado: o lado de cima da camada vai para baixo"
            ),
        ),
        _field(
            "vacuum_min",
            _("Vácuo mínimo (Å)"),
            "float",
            10.5,
            _(
                "Vácuo perpendicular acima da camada; com a molécula, soma a altura dela e a distância "
                "de adsorção"
            ),
            standard=True,
        ),
        _field(
            "ads_distance",
            _("Distância de adsorção (Å)"),
            "float",
            2.0,
            _("Somada ao vácuo só quando há molécula"),
        ),
        _field(
            "complete",
            COMPLETE_LABEL,
            "bool",
            False,
            _("Fecha cada ligação metal–O cortada com um O novo e o seu H: Al–OH, Si–OH"),
            standard=True,
        ),
        _field(
            "heal",
            _("Reconectar H cortados"),
            "bool",
            True,
            _("Um H cuja ligação cruza o corte vai para junto do átomo a que está ligado"),
        ),
        _field(
            "metals",
            METALS_LABEL,
            "text",
            "Al Si",
            _("Rótulos das espécies cujas ligações a O cortadas são completadas com O + H"),
        ),
        bond_scale_field(GROUP),
        *fix_fields(GROUP, SLAB_FIX_RULES),
    ]


def mesh_field(group: str, hint: str = MESH_HINT, of: str = _("do slab")) -> FormField:
    """Empty by default: the SCF's mesh would be wrong, the cell changes (R5.3)."""
    return FormField(
        "kmesh",
        _("Rede de k-points"),
        "kmesh",
        None,
        group=group,
        tooltip=_("K_POINTS automatic {of}. {hint}").format(of=of, hint=hint),
        hint=hint,
    )


def dofree_field(group: str, default: str = DEFAULT_CELL_DOFREE) -> FormField:
    return FormField(
        "cell_dofree",
        _("Graus de liberdade da célula (cell_dofree)"),
        "choice",
        default,
        group=group,
        choices=CELL_DOFREE,
        tooltip=_("&CELL cell_dofree; '2Dxy' relaxa só o plano e a altura do vácuo não encolhe"),
    )


def non_orthogonal_notes(dofree: str, cell: np.ndarray) -> list[str]:
    """The INPUT_PW warning when ``dofree`` constrains a cell whose axes are not orthogonal."""
    return [NON_ORTHOGONAL.format(dofree)] if dofree != "all" and skewed(cell) else []
