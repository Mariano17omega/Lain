"""The data of a plot as a table, and its CSV text (spec 32 R4).

Columns side by side, each with its own name and length: a plot with two axes of different grids
(bands + DOS) is two blocks in one table, the shorter one blank at its end. The CSV is made for the
Excel / LibreOffice / Origin of a Portuguese-speaking user: the decimal is a comma, so the
columns are separated by ``;``.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

DELIMITER = ";"
LINE_END = "\n"
BOM = "\ufeff"  # Excel in a Portuguese locale reads a CSV as UTF-8 only with it


@dataclass(frozen=True)
class Column:
    name: str
    values: np.ndarray


@dataclass(frozen=True)
class PlotTable:
    columns: tuple[Column, ...]

    @classmethod
    def of(cls, columns: Iterable[Column]) -> PlotTable:
        return cls(tuple(columns))

    def __add__(self, other: PlotTable) -> PlotTable:
        """The columns of ``other`` after these (the blocks of a plot with two axes)."""
        return PlotTable(self.columns + other.columns)

    @property
    def rows(self) -> int:
        return max((len(column.values) for column in self.columns), default=0)


SIGNIFICANT = (
    10  # digits: QE prints at most 8, and E − E_F carries ~1e-16 of rounding noise to drop
)


def cell(value: float) -> str:
    """A number as text with a decimal comma, ``SIGNIFICANT`` digits (the rounding noise of
    ``E − E_F`` does not become digits of the file); empty for NaN and infinity (nothing plotted)."""
    number = float(value)
    if not math.isfinite(number):
        return ""
    return format(number, f".{SIGNIFICANT}g").replace(".", ",")


def to_csv(table: PlotTable) -> str:
    """The names of the columns, then one line per row; no byte-order mark (the file writer adds it,
    ``BOM``)."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=DELIMITER, lineterminator=LINE_END)
    writer.writerow([column.name for column in table.columns])
    values: list[Sequence[float]] = [
        np.asarray(c.values, dtype=float).tolist() for c in table.columns
    ]
    for row in range(table.rows):
        writer.writerow([cell(v[row]) if row < len(v) else "" for v in values])
    return out.getvalue()
