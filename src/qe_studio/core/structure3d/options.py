"""What one 3D window shows and how (spec 43 R4.4): each window has its own, nothing is saved."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["BACKGROUNDS", "LABEL_MODES", "MAX_REPEAT", "MIN_REPEAT", "STYLES", "DisplayOptions"]

STYLES: dict[str, str] = {
    "bola-vareta": "Bola e vareta",
    "vareta": "Vareta",
    "fio": "Fio",
    "espaco-cheio": "Espaço cheio",
}
LABEL_MODES: dict[str, str] = {
    "nenhum": "Nenhum",
    "simbolo": "Símbolo",
    "indice": "Número",
    "ambos": "Ambos",
}
BACKGROUNDS: dict[str, str] = {"escuro": "Escuro", "claro": "Claro"}
MIN_REPEAT, MAX_REPEAT = 1, 5
MIN_RADIUS, MAX_RADIUS = 0.20, 2.50  # radius scale
MIN_FACTOR, MAX_FACTOR = 0.60, 1.80  # bond factor


@dataclass
class DisplayOptions:
    style: str = "bola-vareta"
    radius_scale: float = 1.0
    bond_factor: float = 1.15
    show_bonds: bool = True
    reps: tuple[int, int, int] = (1, 1, 1)
    labels: str = "nenhum"
    show_cell: bool = True
    show_axes: bool = True  # a, b, c arrows and the x, y, z triad
    perspective: bool = True
    background: str = "escuro"
    species_colors: dict[int, tuple[int, int, int]] = field(default_factory=dict)  # 0..255
    species_hidden: set[int] = field(default_factory=set)

    @property
    def dark(self) -> bool:
        return self.background != "claro"
