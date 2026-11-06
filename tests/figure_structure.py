"""The artists of a rendered figure as plain data, to compare figures before and after a refactor."""

from matplotlib.collections import LineCollection
from matplotlib.colors import to_hex
from matplotlib.figure import Figure


def _dash(style) -> object:
    return style if isinstance(style, str) else tuple(style)


def figure_structure(figure: Figure) -> list[dict]:
    """Per axes: limits, labels, ticks, line collections, lines, filled areas, legend entries."""
    out = []
    for ax in figure.axes:
        collections = [c for c in ax.collections if isinstance(c, LineCollection)]
        legend = ax.get_legend()
        out.append(
            {
                "xlim": tuple(round(float(v), 4) for v in ax.get_xlim()),
                "ylim": tuple(round(float(v), 4) for v in ax.get_ylim()),
                "xlabel": ax.get_xlabel(),
                "ylabel": ax.get_ylabel(),
                "title": ax.get_title(),
                "xticklabels": [t.get_text() for t in ax.get_xticklabels()],
                "line_collections": [
                    {
                        "segments": len(c.get_segments()),
                        "colors": sorted({to_hex(color) for color in c.get_colors()}),
                        "linewidths": sorted({round(float(w), 3) for w in c.get_linewidths()}),
                        "linestyles": [
                            (
                                float(offset),
                                tuple(round(float(v), 3) for v in dashes) if dashes else None,
                            )
                            for offset, dashes in c.get_linestyles()
                        ],
                    }
                    for c in collections
                ],
                "lines": [
                    {
                        "label": "_" if line.get_label().startswith("_") else line.get_label(),
                        "color": to_hex(line.get_color()),
                        "lw": round(float(line.get_linewidth()), 3),
                        "ls": _dash(line.get_linestyle()),
                        "n": len(line.get_xdata()),
                    }
                    for line in ax.get_lines()
                ],
                "fills": len(ax.collections) - len(collections),
                "legend": [t.get_text() for t in legend.get_texts()] if legend else None,
            }
        )
    return out
