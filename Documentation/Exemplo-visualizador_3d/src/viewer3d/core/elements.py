"""Species label -> chemical element, with radii and colours (tables from ``ase.data``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

UNKNOWN_RADIUS = 1.0  # Å, covalent and van der Waals radius of an unknown element
UNKNOWN_COLOR = (0.5, 0.5, 0.5)
VDW_FALLBACK = 1.8  # Å, for elements with no van der Waals radius in ASE
_FALLBACK_COLOR = (0.7, 0.7, 0.7)  # elements beyond the Jmol table

_NAMES_PT = (
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
).split()


@dataclass(frozen=True)
class ElementInfo:
    symbol: str  # chemical symbol, or the raw label when the element is unknown
    z: int  # atomic number (0 when unknown)
    name: str  # Portuguese element name
    r_cov: float  # covalent radius, Å
    r_vdw: float  # van der Waals radius, Å
    color: tuple[float, float, float]  # Jmol colour, 0..1
    known: bool


@lru_cache(maxsize=1)
def _tables():
    """Import ASE lazily: only ``ase.data`` is ever touched (never ``ase.io``)."""
    from ase.data import chemical_symbols, covalent_radii, vdw_radii
    from ase.data.colors import jmol_colors

    return (
        tuple(chemical_symbols),
        np.asarray(covalent_radii, dtype=float),
        np.asarray(vdw_radii, dtype=float),
        np.asarray(jmol_colors, dtype=float),
    )


@lru_cache(maxsize=1)
def _symbol_to_z() -> dict[str, int]:
    symbols = _tables()[0]
    return {s: z for z, s in enumerate(symbols) if z > 0}


_TWO_LETTERS = re.compile(r"[A-Za-z]{2}")


def symbol_from_label(label: str) -> str | None:
    """Apply the QE-style label rule; ``None`` when no element matches.

    Try the first two letters (first upper case, second lower case), then the first letter:
    ``Fe1``, ``Fe_up`` -> Fe; ``C2`` -> C; ``H_ads`` -> H; ``X`` -> None.
    """
    text = label.strip()
    table = _symbol_to_z()
    if _TWO_LETTERS.match(text):
        candidate = text[0].upper() + text[1].lower()
        if candidate in table:
            return candidate
    if text[:1].isalpha() and text[:1].upper() in table:
        return text[:1].upper()
    return None


def element_by_z(z: int) -> ElementInfo:
    symbols, r_cov, r_vdw, colors = _tables()
    vdw = float(r_vdw[z]) if z < len(r_vdw) else float("nan")
    color = tuple(float(c) for c in colors[z]) if z < len(colors) else _FALLBACK_COLOR
    return ElementInfo(
        symbol=symbols[z],
        z=z,
        name=_NAMES_PT[z - 1],
        r_cov=float(r_cov[z]),
        r_vdw=VDW_FALLBACK if np.isnan(vdw) else vdw,
        color=color,  # type: ignore[arg-type]
        known=True,
    )


@lru_cache(maxsize=256)
def element_for_label(label: str) -> ElementInfo:
    """Element information for a species label; unknown labels never raise."""
    symbol = symbol_from_label(label)
    if symbol is None:
        return ElementInfo(
            symbol=label.strip() or "X",
            z=0,
            name="Desconhecido",
            r_cov=UNKNOWN_RADIUS,
            r_vdw=UNKNOWN_RADIUS,
            color=UNKNOWN_COLOR,
            known=False,
        )
    return element_by_z(_symbol_to_z()[symbol])
