"""The fields of the "Molécula na superfície" type (spec 42 R5.2–R5.4): the "Molécula" and "Sítio" tabs, with
every parameter of the user's scripts, and the relax keys and fixed atoms of the input's tab.

The site's table is a field of kind ``atoms`` whose rows are the candidates of the surface
(``surface/candidates``); they follow the species, the window, the symmetry tolerance and the bond
tolerance typed (``depends_on``, ``site_rows``), which never raise: a problem is the table's message.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from ....i18n import N_, _
from ..fragments import AtomRow, AtomRows
from ..scf_info import ScfInfo
from ..surface import SurfaceError
from ..surface.adsorb import REMOVE_H_LABEL
from ..surface.candidates import candidate_note, candidates_for, no_candidates_text
from ..surface.fixing import BOTTOM, FIX_RULES, FROM_SCF
from ..surface.model import flags_of
from .base import FieldKind, FormField, resolve
from .relax import DEFAULT_FORC_CONV_THR, DEFAULT_NSTEP, ION_DYNAMICS
from .surface_fields import (
    BOND_SCALE,
    bond_scale_field,
    fix_fields,
    labels_of,
    molecule_field,
)

__all__ = [
    "BIDENTATE",
    "COORDS",
    "FROM_COORDS",
    "FROM_LIST",
    "MODES",
    "MOLECULE_TAB",
    "SITE",
    "SITE_PARAMS",
    "SITE_TAB",
    "default_rule",
    "input_tab_fields",
    "molecule_fields",
    "site_fields",
    "site_rows",
]

# Group names double as the tabs' keys and titles: data, shown through ``_()`` by the dialog.
MOLECULE_TAB = N_("Molécula")  # no file is named so: tabs of their own, before the input's
SITE_TAB = N_("Sítio")
SITE = "site"
MONODENTATE, BIDENTATE = N_("monodentado"), N_("bidentado")
MODES = (MONODENTATE, BIDENTATE)
FROM_LIST, FROM_COORDS = N_("lista de candidatos"), N_("coordenadas")
COORDS = ("coords_1", "coords_2")
DEFAULT_SPECIES = "O"  # SITE_SYMBOLS of the scripts: the molecule anchors on O
DEFAULT_WINDOW = 1.5  # Å, HEIGHT_WINDOW = ASF_HEIGHT of the scripts
DEFAULT_SYMPREC = 1e-3  # Å, SYMPREC
DEFAULT_ETOT_CONV_THR = 1e-4  # Ry, pw.x's default and the scripts' value
SITE_PARAMS = ("site_species", "height_window", "symprec", BOND_SCALE)  # what the table follows
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
    )


def molecule_fields() -> list[FormField]:
    """The "Molécula" tab: its SCF (Padrão), then the anchor, the distances and the checks."""
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
        _field(
            MOLECULE_TAB,
            "anchor",
            _("Átomo âncora (nº na molécula)"),
            "int",
            None,
            _(
                "Número do átomo na ordem do SCF da molécula; vazio = o mais pesado (o primeiro num "
                "empate)"
            ),
            hint=_("vazio = o mais pesado"),
        ),
        _field(
            MOLECULE_TAB,
            "ads_distance",
            _("Distância de adsorção (Å)"),
            "float",
            2.0,
            _(
                "Distância mínima do âncora a cada átomo da superfície: acima de um átomo, a altura; "
                "entre dois, o âncora sobe até ficar a esta distância de todos"
            ),
        ),
        _field(
            MOLECULE_TAB,
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
            MOLECULE_TAB,
            "vacuum_min",
            _("Vácuo mínimo (Å)"),
            "float",
            10.5,
            _("Só verifica: abaixo dele, acima da molécula, o plano avisa (a célula não muda)"),
        ),
    ]


def site_fields(scf: ScfInfo | None) -> list[FormField]:
    """The "Sítio" tab: the coordination, the table and the H (Padrão), then how the site is chosen
    and the parameters of the candidates. Without ``scf`` the table has no rows (no structure read)."""
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
        FormField(
            SITE,
            _("Átomo âncora na superfície"),
            "atoms",
            (),
            group=SITE_TAB,
            tooltip=_("Os átomos da superfície (na janela do topo) das espécies candidatas"),
            standard=True,
            hint=SITE_HINT,
            data=site_rows(scf, {}) if scf is not None else None,
            depends_on=SITE_PARAMS,
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
        ),
        _field(
            SITE_TAB,
            "site_species",
            _("Espécies candidatas"),
            "text",
            DEFAULT_SPECIES,
            _("Rótulos ou elementos, separados por espaço, dos átomos da lista"),
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


def default_rule(scf: ScfInfo) -> str:
    """ "do SCF" when the surface fixes some atom, else the bottom half."""
    if any(flag is not None and 0 in flag for flag in flags_of(scf.text)):
        return FROM_SCF
    return BOTTOM


def input_tab_fields(scf: ScfInfo, group: str, relax: list[FormField]) -> list[FormField]:
    """The relax keys with the scripts' values (never the SCF's), ``etot_conv_thr`` and the fixed
    atoms; ``relax`` are the Relax type's fields (k-points, nstep, forces, ion dynamics)."""
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
        *fix_fields(group, FIX_RULES, default_rule(scf)),
    ]


# The names the checks of these numbers use ("A janela da superfície deve ser maior que zero").
NOUNS = {
    "height_window": _("A janela da superfície"),
    "symprec": _("A tolerância de simetria"),
    BOND_SCALE: _("A tolerância de ligação"),
}


def _site_params(values: Mapping[str, Any]) -> tuple[tuple[str, ...], float, float, float] | str:
    """The table's parameters from the values typed (empty: the defaults), or the first problem."""
    params = [f for f in site_fields(None) if f.id in SITE_PARAMS]
    resolved, errors = resolve(params, values)
    if errors:
        return errors[0]
    species = labels_of(resolved["site_species"])
    if not species:
        return _("Preencha Espécies candidatas")
    numbers = []
    for key in SITE_PARAMS[1:]:
        if resolved[key] <= 0:
            return _("{NOUNS} deve ser maior que zero").format(NOUNS=NOUNS[key])
        numbers.append(float(resolved[key]))
    return species, numbers[0], numbers[1], numbers[2]


def site_rows(scf: ScfInfo, values: Mapping[str, Any]) -> AtomRows:
    """The candidates' table for the values typed (empty: the defaults). Never raises."""
    params = _site_params(values)
    if isinstance(params, str):
        return AtomRows("crystal", (), params)
    species, window, symprec, scale = params
    try:
        found = candidates_for(scf, species, window, symprec, scale)
    except SurfaceError as exc:
        return AtomRows("crystal", (), str(exc))
    if not found:
        return AtomRows("crystal", (), no_candidates_text(species, window))
    rows = tuple(
        AtomRow(c.index, c.label, *(f"{v:.5f}" for v in c.frac), note=candidate_note(c))
        for c in found
    )
    return AtomRows("crystal", rows)
