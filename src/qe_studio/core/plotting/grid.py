"""A grid of plots in one figure (spec 23): what it holds and whether it can be drawn.

Plain data, no Qt and no calculation modules (the grid module imports this one). Rows and columns are
0-based here; the window shows them from 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MAX_SIZE = 6  # rows and columns: the figure size and the memory stay reasonable


@dataclass(frozen=True)
class PlotRef:
    """A plot to put in a cell: what it shows (a folder, or the output file of a single-file module
    such as SCF), its kind, and the second folder of a figure of two (bands + DOS)."""

    path: Path
    kind: str
    partner: Path | None = None

    @property
    def paths(self) -> tuple[Path, ...]:
        return (self.path,) if self.partner is None else (self.path, self.partner)


@dataclass(frozen=True)
class GridCell:
    row: int
    col: int
    ref: PlotRef | None  # None: no plot chosen yet (the window's table)
    title: str = ""  # empty: the plot's own title


@dataclass
class GridSpec:
    name: str
    rows: int
    cols: int
    cells: list[GridCell] = field(default_factory=list)

    def validate(self) -> list[str]:
        """What keeps the grid from being drawn, one sentence each (empty when it can be)."""
        errors = []
        name = self.name.strip()
        if not name:
            errors.append("Dê um nome à grade.")
        elif "/" in name:
            errors.append("O nome não pode conter “/”.")
        sized = 1 <= self.rows <= MAX_SIZE and 1 <= self.cols <= MAX_SIZE
        if not sized:
            errors.append(f"Linhas e colunas vão de 1 a {MAX_SIZE}.")
        if not self.cells:
            errors.append("Adicione ao menos uma célula.")
        taken: dict[tuple[int, int], int] = {}
        for number, cell in enumerate(self.cells, 1):
            where = f"({cell.row + 1}, {cell.col + 1})"
            if cell.ref is None:
                errors.append(f"Célula {number}: escolha um gráfico.")
            if not (0 <= cell.row < self.rows and 0 <= cell.col < self.cols):
                if not sized:
                    continue  # the size is the problem: said once, above
                errors.append(
                    f"Célula {number}: posição {where} fora da grade {self.rows} × {self.cols}."
                )
            elif (first := taken.setdefault((cell.row, cell.col), number)) != number:
                errors.append(f"Células {first} e {number} estão na mesma posição {where}.")
        return errors
