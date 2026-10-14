"""What one 3D window shows and how (spec 43 R4.4, spec 46 R2): each window has its own, nothing is saved."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "BACKGROUNDS",
    "DEFAULT_ABC_WIDTH",
    "DEFAULT_LABEL_SIZE",
    "DEFAULT_XYZ_WIDTH",
    "LABEL_MODES",
    "MAX_AXIS_WIDTH",
    "MAX_FACTOR",
    "MAX_LABEL_SIZE",
    "MAX_RADIUS",
    "MAX_REPEAT",
    "MIN_AXIS_WIDTH",
    "MIN_FACTOR",
    "MIN_LABEL_SIZE",
    "MIN_RADIUS",
    "MIN_REPEAT",
    "STYLES",
    "DisplayOptions",
    "background_of_theme",
]

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
MIN_AXIS_WIDTH, MAX_AXIS_WIDTH = 0.5, 8.0  # px on the screen
MIN_LABEL_SIZE, MAX_LABEL_SIZE = 8, 32  # px at font scale 1
DEFAULT_ABC_WIDTH = 1.8  # the a, b, c arrows
DEFAULT_XYZ_WIDTH = 2.0  # the x, y, z triad
DEFAULT_LABEL_SIZE = 11


def background_of_theme(theme_name: str) -> str:
    """The scene background that goes with an app theme (``light`` → ``claro``, else ``escuro``)."""
    return "claro" if theme_name == "light" else "escuro"


@dataclass
class DisplayOptions:
    style: str = "bola-vareta"
    radius_scale: float = 1.0
    bond_factor: float = 1.15
    show_bonds: bool = True
    reps: tuple[int, int, int] = (1, 1, 1)
    labels: str = "nenhum"
    label_size: int = DEFAULT_LABEL_SIZE  # atom labels and the a, b, c / x, y, z names
    show_cell: bool = True
    show_abc: bool = True  # the a, b, c arrows and their names
    show_xyz: bool = True  # the x, y, z triad
    abc_width: float = DEFAULT_ABC_WIDTH
    xyz_width: float = DEFAULT_XYZ_WIDTH
    perspective: bool = True
    background: str = "escuro"
    species_colors: dict[int, tuple[int, int, int]] = field(default_factory=dict)  # 0..255
    species_hidden: set[int] = field(default_factory=set)

    @property
    def dark(self) -> bool:
        return self.background != "claro"
