"""The fields of the "Molécula na superfície" type (spec 42 R5.2–R5.4, spec 87): the "Molécula" and
"Sítio" tabs, with every parameter of the user's scripts, and the relax keys and fixed atoms of the
input's tab.

The site's table is a field of kind ``atoms`` whose rows are all the atoms of the surface's window
(``surface/candidates``), of any species, which the table filters by itself; they follow the window,
the symmetry tolerance and the bond tolerance typed (``depends_on``, ``site_rows``), which never raise:
a problem is the table's message. "Escolher o sítio por" shows that table or the coordinates
(``shown_when``), and the list of the anchor follows the molecule's SCF. The fixed atoms are another
such table, marked by the rules (spec 76, ``adsorption_fixed``).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from ....i18n import N_, _
from ..fragments import AtomRow, AtomRows
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.adsorb import REFERENCES, REMOVE_H_LABEL
from ..surface.candidates import candidate_note, candidates_for
from ..surface.fixing import FIX_RULES
from ..surface.model import model_of
from ..surface.molecule import anchor_choices
from .adsorption_fixed import FIXED_ATOMS, FIXED_HINT, FIXED_PARAMS, default_rule, fixed_rows
from .base import FieldKind, FormField, resolve
from .relax import DEFAULT_FORC_CONV_THR, DEFAULT_NSTEP, ION_DYNAMICS
from .surface_fields import (
    BOND_SCALE,
    FIX_RULE,
    MOLECULE,
    bond_scale_field,
    fix_fields,
    molecule_field,
)

__all__ = [
    "BIDENTATE",
    "COORDS",
    "DISTANCE_FROM",
    "FROM_COORDS",
    "FROM_LIST",
    "MODES",
    "MOLECULE_TAB",
    "MONODENTATE",
    "SHIFT_FIELDS",
    "SITE",
    "SITE_PARAMS",
    "SITE_TAB",
    "input_tab_fields",
    "molecule_fields",
    "site_fields",
    "site_rows",
    "surface_species",
]

# Group names double as the tabs' keys and titles: data, shown through ``_()`` by the dialog.
MOLECULE_TAB = N_("Molécula")  # no file is named so: tabs of their own, before the input's
SITE_TAB = N_("Sítio")
SITE = "site"
MONODENTATE, BIDENTATE = N_("monodentado"), N_("bidentado")
MODES = (MONODENTATE, BIDENTATE)
FROM_LIST, FROM_COORDS = N_("lista de candidatos"), N_("coordenadas")
# What shows the coordinates (``FormField.shown_when``).
BY_COORDS = (("site_from", (FROM_COORDS,)),)
COORDS = ("coords_1", "coords_2")
SHIFT_FIELDS = ("shift_x", "shift_y")  # the anchor's (Δx, Δy) in the plane, spec 75
DISTANCE_FROM = "distance_from"
DEFAULT_WINDOW = 1.5  # Å, HEIGHT_WINDOW = ASF_HEIGHT of the scripts
DEFAULT_SYMPREC = 1e-3  # Å, SYMPREC
DEFAULT_ETOT_CONV_THR = 1e-4  # Ry, pw.x's default and the scripts' value
SITE_PARAMS = ("height_window", "symprec", BOND_SCALE)  # what the table follows
SITE_HINT = _(
    "Monodentado: marque um átomo. Bidentado: marque dois. Mesma letra = sítios equivalentes por "
    "simetria"
)


def _field(
    group: str,
    field_id: str,
    label: str,
    kind: FieldKind,
    default: object,
    tooltip: str,
    standard: bool = False,
    choices: tuple[str, ...] = (),
    hint: str = "",
    shown_when: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> FormField:
    return FormField(
        field_id,
        label,
        kind,
        default,
        group=group,
        tooltip=tooltip,
        choices=choices,
        standard=standard,
        hint=hint,
        shown_when=shown_when,
    )


def molecule_fields() -> list[FormField]:
    """The "Molécula" tab (spec 87 R2): its SCF, the anchor, a list of its atoms, and how high it goes.
    Every other parameter of the position is the "Sítio" tab's."""
    return [
        molecule_field(
            MOLECULE_TAB,
            _("SCF da molécula"),
            _(
                "O átomo âncora vai sobre o sítio e o eixo âncora → resto da molécula, na normal da "
                "superfície"
            ),
            required=True,
        ),
        FormField(
            "anchor",
            _("Átomo âncora da molécula"),
            "atom_choice",
            group=MOLECULE_TAB,
            tooltip=_("O átomo da molécula que fica sobre o sítio. Automático: o mais pesado"),
            standard=True,
            data=anchor_choices(None),
            depends_on=(MOLECULE,),
        ),
        _field(
            MOLECULE_TAB,
            "ads_distance",
            _("Distância de adsorção relativa (Å)"),
            "float",
            2.0,
            _(
                "Altura do átomo âncora acima do O do sítio (no bidentado, acima do ponto médio dos "
                "dois O), ao longo da normal da superfície. Átomos no caminho, como o H da hidroxila, "
                "não mudam a posição"
            ),
            standard=True,
        ),
    ]


def site_fields(scf: ScfInfo | None) -> list[FormField]:
    """The "Sítio" tab: the coordination and how the site is chosen, which shows the table or the
    coordinates (spec 87 R3); the H, the anchor's position and its checks; then the parameters of the
    candidates. Padrão shows the coordination, the table, the H and the shift. Without ``scf`` the table
    has no rows (no structure read)."""
    return [
        _field(
            SITE_TAB,
            "mode",
            _("Coordenação"),
            "choice",
            MONODENTATE,
            _("Monodentado: o âncora sobre um átomo. Bidentado: entre dois átomos, no ponto médio"),
            standard=True,
            choices=MODES,
        ),
        _field(
            SITE_TAB,
            "site_from",
            _("Escolher o sítio por"),
            "choice",
            FROM_LIST,
            _(
                "Pela lista: os átomos marcados na tabela. Por coordenadas: o átomo mais próximo de "
                "cada x y z"
            ),
            choices=(FROM_LIST, FROM_COORDS),
        ),
        FormField(
            SITE,
            _("Átomo âncora na superfície"),
            "atoms",
            (),
            group=SITE_TAB,
            tooltip=_("Os átomos da superfície (na janela do topo)"),
            standard=True,
            hint=SITE_HINT,
            data=site_rows(scf, {}) if scf is not None else None,
            depends_on=SITE_PARAMS,
            shown_when=(("site_from", (FROM_LIST,)),),
        ),
        *(
            _field(
                SITE_TAB,
                field_id,
                _("Coordenadas do átomo {k} (crystal)").format(k=k),
                "text",
                None,
                _("Frações x y z: escolhem o átomo mais próximo, até a tolerância")
                + (_(" (só no bidentado)") if k == 2 else ""),
                hint="x y z",
                shown_when=BY_COORDS + ((("mode", (BIDENTATE,)),) if k == 2 else ()),
            )
            for k, field_id in enumerate(COORDS, 1)
        ),
        _field(
            SITE_TAB,
            "site_tol",
            _("Tolerância das coordenadas (Å)"),
            "float",
            0.5,
            _("Distância máxima entre as coordenadas e o átomo que elas escolhem"),
            shown_when=BY_COORDS,
        ),
        _field(
            SITE_TAB,
            "remove_h",
            REMOVE_H_LABEL,
            "bool",
            False,
            _(
                "Desprotona o sítio: o único H ligado a cada átomo âncora sai, e a molécula toma o "
                "lugar dele"
            ),
            standard=True,
        ),
        *(
            _field(
                SITE_TAB,
                field_id,
                _("Δ{axis} (Å)").format(axis=axis),
                "float",
                0.0,
                _(
                    "Deslocamento do âncora ao longo de {axis} cartesiano, projetado no plano da "
                    "superfície, a partir do ponto acima do sítio"
                ).format(axis=axis),
                standard=True,
            )
            for field_id, axis in zip(SHIFT_FIELDS, "xy", strict=True)
        ),
        _field(
            SITE_TAB,
            DISTANCE_FROM,
            _("Distância medida a partir de"),
            "choice",
            REFERENCES[0],
            _(
                "Átomo do sítio: o âncora fica a esta distância acima do O escolhido. Todos os átomos "
                "da superfície (scripts): o âncora sobe até ficar a esta distância de todo átomo "
                "próximo, como nos scripts de Exemplo-SLAB"
            ),
            choices=REFERENCES,
        ),
        _field(
            SITE_TAB,
            "h_clearance",
            _("Folga mínima (Å)"),
            "float",
            1.9,
            _(
                "Só avisa: abaixo dela, a folga do âncora aos H da superfície ou do resto da molécula à "
                "superfície (o relax ajusta)"
            ),
        ),
        _field(
            SITE_TAB,
            "vacuum_min",
            _("Vácuo mínimo (Å)"),
            "float",
            10.5,
            _("Só verifica: abaixo dele, acima da molécula, o plano avisa (a célula não muda)"),
        ),
        _field(
            SITE_TAB,
            "height_window",
            _("Janela da superfície (Å)"),
            "float",
            DEFAULT_WINDOW,
            _(
                "A superfície: os átomos até esta distância abaixo do mais alto, ao longo da normal. "
                "Vale para a lista e para aceitar o átomo escolhido"
            ),
        ),
        _field(
            SITE_TAB,
            "symprec",
            _("Tolerância de simetria (Å)"),
            "float",
            DEFAULT_SYMPREC,
            _("symprec do spglib, que agrupa os átomos equivalentes (as letras da coluna Sítio)"),
        ),
        bond_scale_field(SITE_TAB),
    ]


def fixed_field(scf: ScfInfo, group: str) -> FormField:
    """The table of the fixed atoms (spec 76): the surface's, marked by the rule of the fields after
    it (the SCF's own by default)."""
    return FormField(
        FIXED_ATOMS,
        _("Átomos fixos (if_pos 0 0 0)"),
        "atoms",
        group=group,
        tooltip=_(
            "Os átomos da superfície, na numeração do SCF: os marcados saem com if_pos 0 0 0 (ou o "
            "do SCF, se ele já fixava o átomo); a molécula fica livre"
        ),
        standard=True,
        hint=FIXED_HINT,
        data=fixed_rows(scf, {}),
        depends_on=FIXED_PARAMS,
    )


def input_tab_fields(scf: ScfInfo, group: str, relax: list[FormField]) -> list[FormField]:
    """The relax keys with the scripts' values (never the SCF's), ``etot_conv_thr``, the table of the
    fixed atoms and the rules that mark it; ``relax`` are the Relax type's fields (k-points, nstep,
    forces, ion dynamics)."""
    defaults = {
        "nstep": DEFAULT_NSTEP,
        "forc_conv_thr": DEFAULT_FORC_CONV_THR,
        "ion_dynamics": ION_DYNAMICS[0],
    }
    fields = [
        dataclasses.replace(f, default=defaults[f.id]) if f.id in defaults else f for f in relax
    ]
    return [
        *fields,
        FormField(
            "etot_conv_thr",
            _("Convergência da energia (etot_conv_thr)"),
            "float",
            DEFAULT_ETOT_CONV_THR,
            group=group,
            tooltip=_("&CONTROL etot_conv_thr, em Ry"),
        ),
        fixed_field(scf, group),
        *(
            # The table already says "Átomos fixos": the choice is the rule that marks it.
            dataclasses.replace(f, label=_("Regra dos átomos fixos")) if f.id == FIX_RULE else f
            for f in fix_fields(group, FIX_RULES, default_rule(scf))
        ),
    ]


# The names the checks of these numbers use ("A janela da superfície deve ser maior que zero").
NOUNS = {
    "height_window": _("A janela da superfície"),
    "symprec": _("A tolerância de simetria"),
    BOND_SCALE: _("A tolerância de ligação"),
}


def _site_params(values: Mapping[str, Any]) -> tuple[float, float, float] | str:
    """The table's parameters from the values typed (empty: the defaults), or the first problem."""
    params = [f for f in site_fields(None) if f.id in SITE_PARAMS]
    resolved, errors = resolve(params, values)
    if errors:
        return errors[0]
    numbers = []
    for key in SITE_PARAMS:
        if resolved[key] <= 0:
            return _("{NOUNS} deve ser maior que zero").format(NOUNS=NOUNS[key])
        numbers.append(float(resolved[key]))
    return numbers[0], numbers[1], numbers[2]


def surface_species(scf: ScfInfo) -> tuple[str, ...]:
    """Every species label of the structure, in order: any atom of the window can be the site (spec 87
    R4). Raises ``SurfaceError``."""
    return tuple(dict.fromkeys(model_of(scf).labels))


def site_rows(scf: ScfInfo, values: Mapping[str, Any]) -> AtomRows:
    """The candidates' table for the values typed (empty: the defaults): every atom of the window, as
    the highest atom is always in it, and the table filters them by species. Never raises."""
    params = _site_params(values)
    if isinstance(params, str):
        return AtomRows("crystal", (), params, species_filter=True)
    window, symprec, scale = params
    try:
        found = candidates_for(scf, surface_species(scf), window, symprec, scale)
    except SurfaceError as exc:
        return AtomRows("crystal", (), str(exc), species_filter=True)
    rows = tuple(
        AtomRow(c.index, c.label, *(f"{v:.5f}" for v in c.frac), note=candidate_note(c))
        for c in found
    )
    return AtomRows("crystal", rows, species_filter=True)
