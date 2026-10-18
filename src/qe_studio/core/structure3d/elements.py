"""Species label → chemical element, with radii and Jmol colors (tables from ``ase.data``).

The label rule is ``surface/elements.element_of``'s (ASE's ``label_to_symbol``: the first two characters when
they are a symbol, else the first one: ``Fe1``, ``Fe_up`` → Fe; ``C2`` → C), but an unknown label never
raises here: it is a gray atom of 1.0 Å (``known=False``). ``ase.data`` is imported on first use only.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np

from ...i18n import _

__all__ = ["ElementInfo", "element_by_z", "element_for_label", "symbol_from_label"]

UNKNOWN_RADIUS = 1.0  # Å, covalent and van der Waals radius of an unknown element
UNKNOWN_COLOR = (0.5, 0.5, 0.5)
VDW_FALLBACK = 1.8  # Å, for elements with no van der Waals radius in ASE
_FALLBACK_COLOR = (0.7, 0.7, 0.7)  # elements beyond the Jmol table

_NAMES = (  # Portuguese element names by Z
    _(
        "Hidrogênio Hélio Lítio Berílio Boro Carbono Nitrogênio Oxigênio Flúor Neônio Sódio Magnésio "
        "Alumínio Silício Fósforo Enxofre Cloro Argônio Potássio Cálcio Escândio Titânio Vanádio Cromo "
        "Manganês Ferro Cobalto Níquel Cobre Zinco Gálio Germânio Arsênio Selênio Bromo Criptônio "
        "Rubídio Estrôncio Ítrio Zircônio Nióbio Molibdênio Tecnécio Rutênio Ródio Paládio Prata "
        "Cádmio Índio Estanho Antimônio Telúrio Iodo Xenônio Césio Bário Lantânio Cério Praseodímio "
        "Neodímio Promécio Samário Európio Gadolínio Térbio Disprósio Hólmio Érbio Túlio Itérbio "
        "Lutécio Háfnio Tântalo Tungstênio Rênio Ósmio Irídio Platina Ouro Mercúrio Tálio Chumbo "
        "Bismuto Polônio Astato Radônio Frâncio Rádio Actínio Tório Protactínio Urânio Netúnio "
        "Plutônio Amerício Cúrio Berquélio Califórnio Einstênio Férmio Mendelévio Nobélio "
        "Laurêncio Rutherfórdio Dúbnio Seabórgio Bóhrio Hássio Meitnério Darmstádio Roentgênio "
        "Copernício Nihônio Fleróvio Moscóvio Livermório Tenessino Oganessônio"
    )
)
_NAMES_PT = _NAMES.split()


@dataclass(frozen=True)
class ElementInfo:
    symbol: str  # chemical symbol, or the raw label when the element is unknown
    z: int  # atomic number (0 when unknown)
    name: str  # Portuguese element name
    r_cov: float  # covalent radius, Å
    r_vdw: float  # van der Waals radius, Å
    color: tuple[float, float, float]  # Jmol color, 0..1
    known: bool


@cache
def _tables() -> tuple[tuple[str, ...], np.ndarray, np.ndarray, np.ndarray]:
    """``ase.data`` on first use (never ``ase.io``)."""
    from ase.data import chemical_symbols, covalent_radii, vdw_radii
    from ase.data.colors import jmol_colors

    return (
        tuple(chemical_symbols),
        np.asarray(covalent_radii, dtype=float),
        np.asarray(vdw_radii, dtype=float),
        np.asarray(jmol_colors, dtype=float),
    )


@cache
def _symbol_to_z() -> dict[str, int]:
    return {symbol: z for z, symbol in enumerate(_tables()[0]) if z > 0}


def symbol_from_label(label: str) -> str | None:
    """The element symbol of a species label, None when no element matches (``X``)."""
    table = _symbol_to_z()
    if len(label) >= 2 and (two := label[0].upper() + label[1].lower()) in table:
        return two
    if label[:1].upper() in table:
        return label[:1].upper()
    return None


def element_by_z(z: int) -> ElementInfo:
    symbols, r_cov, r_vdw, colors = _tables()
    vdw = float(r_vdw[z]) if z < len(r_vdw) else float("nan")
    rgb = colors[z] if z < len(colors) else _FALLBACK_COLOR
    return ElementInfo(
        symbol=symbols[z],
        z=z,
        name=_NAMES_PT[z - 1],
        r_cov=float(r_cov[z]),
        r_vdw=VDW_FALLBACK if np.isnan(vdw) else vdw,
        color=(float(rgb[0]), float(rgb[1]), float(rgb[2])),
        known=True,
    )


@cache
def element_for_label(label: str) -> ElementInfo:
    """Element information for a species label; an unknown label never raises."""
    symbol = symbol_from_label(label)
    if symbol is None:
        return ElementInfo(
            symbol=label.strip() or "X",
            z=0,
            name=_("Desconhecido"),
            r_cov=UNKNOWN_RADIUS,
            r_vdw=UNKNOWN_RADIUS,
            color=UNKNOWN_COLOR,
            known=False,
        )
    return element_by_z(_symbol_to_z()[symbol])
