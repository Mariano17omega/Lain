"""Display options shared by the canvas, the renderer and the panels (no Qt here)."""

from __future__ import annotations

from dataclasses import dataclass, field

STYLES: dict[str, str] = {
    "bola-vareta": "Bola e vareta",
    "vareta": "Vareta",
    "fio": "Fio",
    "espaco-cheio": "Espaço cheio",
}
LABEL_MODES: dict[str, str] = {
    "nenhum": "Nenhum",
    "simbolo": "Símbolo",
    "indice": "Índice",
    "ambos": "Ambos",
}
MIN_REPEAT, MAX_REPEAT = 1, 5


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
    dark: bool = True
    species_colors: dict[int, tuple[int, int, int]] = field(default_factory=dict)  # 0..255
    species_hidden: set[int] = field(default_factory=set)
