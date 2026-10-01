"""SCF convergence (pw.x): estimated accuracy, energy and magnetization per iteration.

One figure with up to three stacked panels sharing the iteration axis, in the style of the
relaxation plot: the accuracy against ``conv_thr``, |ΔE| (or the total energy) and, for spin
calculations, the magnetization. Plotted from a single output file (``plot_target``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from ..plotting.draw import (
    DASHED,
    MAX_TICKS,
    add_legend,
    empty_panel,
    finish,
    positive_for_log,
    stacked_axes,
    style_axes,
)
from ..plotting.style import PlotStyle
from ..qe.scf import ScfData, read_scf
from ..sniff import FileKind
from .base import AxesLimits, CalculationModule, DetectionResult, FileRole, LoadError, output_of
from .params import COMMON_FIELDS, CommonParams, ParamField, RenderInfo, apply_common_config
from .readout import signed

if TYPE_CHECKING:
    from ..config import AppConfig

ENERGY_MODES = (("delta", "|ΔE| entre iterações"), ("total", "E total"))
SCALES = (("log", "Log"), ("linear", "Linear"))
NO_DELTAS = "São necessárias pelo menos duas iterações para calcular |ΔE|."
NO_PANELS = "Nenhum painel selecionado"
NOT_CONVERGED = "convergência NÃO atingida"
RUNNING = "em andamento"


@dataclass
class ScfDataset:
    folder: Path
    path: Path  # the output file plotted
    data: ScfData
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScfParams(CommonParams):
    show_legend: bool = True  # the legend names conv_thr and the magnetization series
    show_accuracy: bool = True
    show_energy: bool = True
    energy_mode: str = "delta"
    show_magnetization: bool = True
    scale: str = "log"  # accuracy and |ΔE|
    show_threshold: bool = True
    xmin: float | None = None
    xmax: float | None = None
    accuracy_color: str = "#38bdf8"
    energy_color: str = "#10b981"
    # No schema field without magnetization, so the dataclass says how to validate a stored value.
    magnetization_color: str = field(default="#a78bfa", metadata={"kind": "color"})
    threshold_color: str = "#f43f5e"


def panels_shown(params: ScfParams, data: ScfData) -> list[str]:
    """The panels to draw, top to bottom."""
    shown = []
    if params.show_accuracy:
        shown.append("accuracy")
    if params.show_energy:
        shown.append("energy")
    if params.show_magnetization and data.spin:
        shown.append("magnetization")
    return shown


class ScfModule(CalculationModule[ScfDataset, ScfParams]):
    kind: ClassVar[str] = "scf"
    badge: ClassVar[str] = "SCF"
    badge_token: ClassVar[str | None] = "scf"
    view_fields: ClassVar[tuple[str, ...]] = ("xmin", "xmax")
    sections: ClassVar[tuple[tuple[str, str | None], ...]] = (("Convergência", "Eixo X"),)
    display_name: ClassVar[str] = "Convergência SCF"
    plottable: ClassVar[bool] = True
    fallback: ClassVar[bool] = True  # only when no other kind was detected in the folder
    single_file_role: ClassVar[str | None] = "scf_out"
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole(
            "scf_out",
            "Saída SCF (pw.x)",
            output_of(FileKind.PW_OUT, "scf"),
            ("scf*.out",),
            required=True,
            anchor=True,
        ),
    )

    def plot_target(self, folder: Path, files: dict[str, list[Path]]) -> Path:
        """One tab per output: a folder can hold several SCF runs."""
        paths = files.get("scf_out")
        return paths[0] if paths else folder

    def load(self, result: DetectionResult) -> ScfDataset:
        output = result.file("scf_out")
        if output is None:
            raise LoadError("Saída do SCF não encontrada.")
        try:
            data = read_scf(output)
        except OSError as exc:
            raise LoadError(f"{output.name}: {exc.strerror or exc}") from exc
        if not data.iterations:
            raise LoadError(f"Nenhuma iteração SCF completa em {output.name}.")
        warnings = list(result.warnings)
        if data.truncated == 1:
            warnings.append("1 iteração incompleta ignorada")
        elif data.truncated:
            warnings.append(f"{data.truncated} iterações incompletas ignoradas")
        if data.cycles > 1:
            warnings.append(f"saída com {data.cycles} ciclos SCF; mostrando o primeiro")
        if data.threshold_ry is None:
            warnings.append("limiar de convergência não encontrado no cabeçalho")
        return ScfDataset(result.folder, output, data, list(dict.fromkeys(warnings)))

    # -- plotting ------------------------------------------------------------------------------
    def default_params(self, config: AppConfig, dataset: ScfDataset) -> ScfParams:
        params = ScfParams()
        apply_common_config(params, config)
        extra = len(panels_shown(params, dataset.data)) - 1  # each panel beyond the first
        params.figure_height = round(params.figure_height * (1 + 0.5 * extra), 2)
        return params

    def param_schema(self, dataset: ScfDataset) -> list[ParamField]:
        spin = dataset.data.spin
        step = {"minimum": 0, "maximum": 1e5, "step": 1, "decimals": 1, "optional": True}
        section = "Convergência"
        return [
            ParamField("show_accuracy", "Precisão estimada", section, "bool"),
            ParamField("show_energy", "Energia", section, "bool"),
            ParamField("energy_mode", "Energia como", section, "choice", choices=ENERGY_MODES),
            *([ParamField("show_magnetization", "Magnetização", section, "bool")] if spin else []),
            ParamField("scale", "Escala Y", section, "choice", choices=SCALES),
            ParamField("show_threshold", "Limiar", section, "bool"),
            ParamField("xmin", "Iteração mín.", "Eixo X", "float", **step),
            ParamField("xmax", "Iteração máx.", "Eixo X", "float", **step),
            ParamField("accuracy_color", "Cor precisão", "Estilo", "color"),
            ParamField("energy_color", "Cor energia", "Estilo", "color"),
            *(
                [ParamField("magnetization_color", "Cor magnetização", "Estilo", "color")]
                if spin
                else []
            ),
            ParamField("threshold_color", "Cor limiar", "Estilo", "color"),
            *COMMON_FIELDS,
        ]

    def apply_limits(self, params: ScfParams, axes_limits: AxesLimits) -> None:
        """The iteration range only: Y stays automatic in each panel."""
        if axes_limits:
            params.xmin, params.xmax = axes_limits[0][0]

    def format_coordinates(
        self, x: float, y: float, axes_index: int, dataset: ScfDataset, params: ScfParams
    ) -> str:
        """The value at the nearest iteration: ``iteração 6 · precisão = 2.5e-05 Ry`` (or the
        energy / magnetization of the panel under the cursor)."""
        shown = panels_shown(params, dataset.data)
        if axes_index >= len(shown):
            return ""
        iterations = dataset.data.iterations
        n = round(x)
        position = next((i for i, it in enumerate(iterations) if it.index == n), None)
        if position is None:
            return ""
        it, text = iterations[position], f"iteração {n}"
        panel = shown[axes_index]
        if panel == "accuracy":
            return f"{text} · precisão = {it.accuracy_ry:.1e} Ry"
        if panel == "energy":
            if params.energy_mode == "total":
                return f"{text} · E = {signed(it.energy_ry, '.6f')} Ry"
            if position == 0:  # |ΔE| starts at the second iteration
                return ""
            delta = abs(it.energy_ry - iterations[position - 1].energy_ry)
            return f"{text} · |ΔE| = {delta:.1e} Ry"
        parts = [
            f"{name} = {signed(value, '.2f')} μB"
            for name, value in (("magnetização total", it.total_mag), ("absoluta", it.abs_mag))
            if value is not None
        ]
        return " · ".join([text, *parts])

    def render(
        self, figure: Figure, dataset: ScfDataset, params: ScfParams, style: PlotStyle
    ) -> RenderInfo:
        data = dataset.data
        shown = panels_shown(params, data)
        if not shown:
            # Figure-level text, no axes: the toolbar then has no limits to store in the params.
            figure.clear()
            figure.set_facecolor(style.figure_bg)
            figure.text(0.5, 0.5, NO_PANELS, ha="center", va="center", color=style.muted)
            return RenderInfo((0.0, 1.0), (0.0, 1.0), self.summary(dataset))
        axes = stacked_axes(figure, style, len(shown))
        draw = {"accuracy": self._accuracy, "energy": self._energy, "magnetization": self._magnet}
        log = params.scale == "log"
        legends = [draw[p](ax, data, params, style, log) for ax, p in zip(axes, shown, strict=True)]
        for ax, handles in zip(axes[1:], legends[1:], strict=True):
            add_legend(ax, params, handles)
        self._status_note(axes[0], data, params, style)

        first, last = data.iterations[0].index, data.iterations[-1].index
        bottom = axes[-1]
        bottom.set_xlabel("Iteração SCF")
        bottom.set_xticks(range(first, last + 1, max(1, (last - first + 1) // MAX_TICKS)))
        low = params.xmin if params.xmin is not None else first - 0.5
        high = params.xmax if params.xmax is not None else max(last + 0.5, low + 1)
        bottom.set_xlim(low, high)
        finish(figure, axes[0], params, legends[0])
        return RenderInfo(axes[0].get_xlim(), axes[0].get_ylim(), self.summary(dataset))

    @staticmethod
    def _line(ax: Axes, x: list, y: list, color: str, params: ScfParams, **kwargs) -> Line2D:
        (line,) = ax.plot(
            x,
            y,
            color=color,
            lw=params.line_width,
            marker="o",
            markersize=max(3.0, params.line_width * 3),
            zorder=3,
            **kwargs,
        )
        return line

    def _accuracy(
        self, ax: Axes, data: ScfData, params: ScfParams, style: PlotStyle, log: bool
    ) -> list:
        if log:
            ax.set_yscale("log")
        values = [it.accuracy_ry for it in data.iterations]
        x = [it.index for it in data.iterations]
        self._line(
            ax, x, positive_for_log(values) if log else values, params.accuracy_color, params
        )
        ax.set_ylabel("Precisão estimada (Ry)")
        style_axes(ax, style)
        if not params.show_threshold or data.threshold_ry is None:
            return []
        ax.axhline(data.threshold_ry, color=params.threshold_color, lw=1.0, ls=DASHED, zorder=3)
        label = f"conv_thr = {data.threshold_ry:.1e} Ry"
        return [Line2D([], [], color=params.threshold_color, lw=1.0, ls=DASHED, label=label)]

    def _energy(
        self, ax: Axes, data: ScfData, params: ScfParams, style: PlotStyle, log: bool
    ) -> list:
        if params.energy_mode == "total":
            x = [it.index for it in data.iterations]
            self._line(ax, x, [it.energy_ry for it in data.iterations], params.energy_color, params)
            ax.ticklabel_format(axis="y", style="plain", useOffset=False)
            ax.set_ylabel("Energia total (Ry)")
        else:
            deltas = data.energy_deltas
            if not deltas:
                empty_panel(ax, NO_DELTAS, style)
                return []
            if log:
                ax.set_yscale("log")
            x = [it.index for it in data.iterations[1:]]  # |ΔE| starts at the second iteration
            self._line(
                ax, x, positive_for_log(deltas) if log else deltas, params.energy_color, params
            )
            ax.set_ylabel("|ΔE| (Ry)")
        style_axes(ax, style)
        return []

    def _magnet(
        self, ax: Axes, data: ScfData, params: ScfParams, style: PlotStyle, log: bool
    ) -> list:
        handles = []
        for label, attr, ls in (("total", "total_mag", "-"), ("absoluta", "abs_mag", DASHED)):
            points = [(it.index, getattr(it, attr)) for it in data.iterations]
            points = [(x, y) for x, y in points if y is not None]
            if points:
                x, y = (list(values) for values in zip(*points, strict=True))
                handles.append(
                    self._line(ax, x, y, params.magnetization_color, params, ls=ls, label=label)
                )
        ax.set_ylabel("Magnetização (μB/célula)")
        style_axes(ax, style)
        return handles

    @staticmethod
    def _status_note(ax: Axes, data: ScfData, params: ScfParams, style: PlotStyle) -> None:
        """A note over the first panel unless the run converged."""
        if data.status == "converged":
            return
        text, color = (
            (NOT_CONVERGED, params.threshold_color)
            if data.status == "not_converged"
            else (RUNNING, style.muted)
        )
        ax.text(
            0.5, 0.94, text, transform=ax.transAxes, ha="center", va="top", color=color,
            fontweight="bold", zorder=5,
        )  # fmt: skip

    @staticmethod
    def summary(dataset: ScfDataset) -> str:
        data = dataset.data
        last = data.iterations[-1]
        count = data.n_reported if data.n_reported is not None else len(data.iterations)
        noun = "iteração" if count == 1 else "iterações"
        accuracy = f"precisão {last.accuracy_ry:.1e} Ry"
        if data.status == "running":
            return f"Em andamento · {count} {noun} · {accuracy}"
        if data.threshold_ry is not None:
            accuracy += f" (limiar {data.threshold_ry:.1e})"
        if data.status == "not_converged":
            return f"Não convergiu ✗ após {count} {noun} · {accuracy}"
        parts = [f"Convergiu ✓ em {count} {noun}", accuracy]
        if data.final_energy_ry is not None:
            parts.append(f"E = {data.final_energy_ry:.8f} Ry")
        return " · ".join(parts)
