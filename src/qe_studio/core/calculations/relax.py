"""Structural relaxation progress (relax / vc-relax): |ΔE| and total force per BFGS step.

One figure with up to two stacked panels sharing the step axis, after the Relax-Viewer
reference app (removed from ``Documentation/``, see git history); colours and background
follow the plot parameters instead. A vc-relax draws |ΔH| instead of |ΔE| (the BFGS compares the
enthalpy), and ``panels = "all"`` adds its pressure and volume (``relax_panels.py``, spec 27-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from matplotlib.axes import Axes
from matplotlib.figure import FigureBase
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
from ..qe.pw_input import parse_input
from ..qe.relax import QE_DEFAULT, RelaxData, read_relax
from ..sniff import FileKind
from .base import (
    AxesLimits,
    CalculationModule,
    DetectionResult,
    FileRole,
    LoadError,
    SniffFn,
    output_of,
)
from .params import COMMON_FIELDS, CommonParams, ParamField, RenderInfo, apply_common_config
from .relax_panels import cell_readout, cell_summary, draw_pressure, draw_volume

if TYPE_CHECKING:
    from ..config import AppConfig

PANELS = (
    ("both", "Ambos"),
    ("energy", "Energia / entalpia"),
    ("force", "Força"),
    ("all", "Todos"),
)
SCALES = (("log", "Log"), ("linear", "Linear"))
EXPORT_STEMS = {
    "both": "relax",
    "energy": "relax_energia",
    "force": "relax_forca",
    "all": "relax_todos",
}
NO_DELTAS = "São necessários pelo menos dois passos completos para calcular |ΔE|."
NO_ENTHALPY = "entalpia indisponível neste passo"
NO_STEPS = "Nenhum passo completo de relaxamento encontrado."


@dataclass
class RelaxDataset:
    folder: Path
    data: RelaxData
    formula: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class RelaxParams(CommonParams):
    show_legend: bool = True  # the legend names the convergence thresholds
    panels: str = "both"
    scale: str = "log"
    show_thresholds: bool = True
    xmin: float | None = None
    xmax: float | None = None
    energy_color: str = "#38bdf8"
    force_color: str = "#10b981"
    threshold_color: str = "#f43f5e"
    pressure_color: str = "#f59e0b"
    volume_color: str = "#8b5cf6"


class InputSettings(NamedTuple):
    """What the relax input sets that the output may not print."""

    thresholds: tuple[float | None, float | None] = (None, None)  # etot_conv_thr, forc_conv_thr
    press: float | None = None  # &CELL press (kbar)
    press_conv_thr: float | None = None  # &CELL press_conv_thr (kbar)


def input_settings(path: Path | None) -> InputSettings:
    """The thresholds of ``&CONTROL`` and the pressure settings of ``&CELL``, if any."""
    if path is None:
        return InputSettings()
    try:
        parsed = parse_input(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return InputSettings()

    def number(namelist: str, key: str) -> float | None:
        value = parsed.get(namelist, key)
        return float(value) if isinstance(value, int | float) else None

    return InputSettings(
        (number("control", "etot_conv_thr"), number("control", "forc_conv_thr")),
        number("cell", "press"),
        number("cell", "press_conv_thr"),
    )


class RelaxModule(CalculationModule[RelaxDataset, RelaxParams]):
    kind: ClassVar[str] = "relax"
    badge: ClassVar[str] = "RELAX"
    badge_token: ClassVar[str | None] = "relax"
    view_fields: ClassVar[tuple[str, ...]] = ("xmin", "xmax")
    sections: ClassVar[tuple[tuple[str, str | None], ...]] = (("Relaxamento", "Eixo X"),)
    display_name: ClassVar[str] = "Otimização estrutural"
    description: ClassVar[str] = "Saída de relax/vc-relax do pw.x com passos BFGS"
    plottable: ClassVar[bool] = True
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole(
            "relax_in",
            "Entrada relax/vc-relax (pw.x)",
            output_of(FileKind.PW_IN, "relax", "vc-relax"),
            ("relax*.in", "vc-relax*.in"),
            anchor=True,
        ),
        FileRole(
            "relax_out",
            "Saída relax/vc-relax (pw.x)",
            output_of(FileKind.PW_OUT, "relax", "vc-relax"),
            ("relax*.out", "vc-relax*.out"),
            required=True,
            anchor=True,
        ),
    )

    def load(self, result: DetectionResult, sniff: SniffFn) -> RelaxDataset:
        output = result.file("relax_out")
        if output is None:
            raise LoadError("Saída do relaxamento não encontrada.")
        try:
            settings = input_settings(result.file("relax_in"))
            data = read_relax(
                output,
                settings.thresholds,
                target_pressure=settings.press,
                press_conv_thr=settings.press_conv_thr,
            )
        except OSError as exc:
            raise LoadError(f"{output.name}: {exc.strerror or exc}") from exc
        if not data.steps:
            raise LoadError(f"Nenhum passo de relaxamento completo em {output.name}.")
        warnings = list(result.warnings)
        if data.truncated_steps == 1:
            warnings.append("1 passo incompleto ignorado")
        elif data.truncated_steps:
            warnings.append(f"{data.truncated_steps} passos incompletos ignorados")
        if data.defaulted_thresholds:
            warnings.append("limiares de convergência não encontrados: padrões do QE")
        return RelaxDataset(result.folder, data, data.formula, list(dict.fromkeys(warnings)))

    # -- plotting ------------------------------------------------------------------------------
    def default_params(self, config: AppConfig, dataset: RelaxDataset) -> RelaxParams:
        params = RelaxParams()
        apply_common_config(params, config)
        params.figure_height = round(params.figure_height * 1.5, 2)  # two panels by default
        return params

    def param_schema(self, dataset: RelaxDataset) -> list[ParamField]:
        step = {"minimum": -1, "maximum": 1e5, "step": 1, "decimals": 1, "optional": True}
        return [
            ParamField("panels", "Painéis", "Relaxamento", "choice", choices=PANELS),
            ParamField("scale", "Escala Y", "Relaxamento", "choice", choices=SCALES),
            ParamField("show_thresholds", "Limiares", "Relaxamento", "bool"),
            ParamField("xmin", "Passo mín.", "Eixo X", "float", **step),
            ParamField("xmax", "Passo máx.", "Eixo X", "float", **step),
            ParamField("energy_color", "Cor |ΔE| / |ΔH|", "Estilo", "color"),
            ParamField("force_color", "Cor força", "Estilo", "color"),
            ParamField("pressure_color", "Cor pressão", "Estilo", "color"),
            ParamField("volume_color", "Cor volume", "Estilo", "color"),
            ParamField("threshold_color", "Cor limiares", "Estilo", "color"),
            *COMMON_FIELDS,
        ]

    def apply_limits(self, params: RelaxParams, axes_limits: AxesLimits) -> None:
        """The step range only: Y stays automatic in each panel."""
        params.xmin, params.xmax = axes_limits[0][0]

    @staticmethod
    def panels_shown(params: RelaxParams, data: RelaxData) -> list[str]:
        """The panels drawn, top to bottom (``axes_index`` is the position in this list). ``all``
        adds the pressure and the volume the run printed: for a relax with none it is ``both``."""
        if params.panels == "all":
            extra = (("pressure", data.has_pressure), ("volume", data.has_volume))
            return ["energy", "force", *(name for name, present in extra if present)]
        return [p for p in ("energy", "force") if params.panels in (p, "both")]

    def format_coordinates(
        self, x: float, y: float, axes_index: int, dataset: RelaxDataset, params: RelaxParams
    ) -> str:
        """The value at the nearest step (a log axis makes the cursor's Y meaningless):
        ``passo 4 · |ΔE| = 1.2e-05 Ry`` (``|ΔH|`` in a vc-relax), ``passo 4 · F = 3.1e-04 Ry/Bohr``,
        ``passo 4 · P = 0.03 kbar`` or ``passo 4 · V = 334.00 Å³``."""
        data = dataset.data
        shown = self.panels_shown(params, data)
        if axes_index >= len(shown):
            return ""
        panel, step = shown[axes_index], round(x)
        if panel == "energy":
            deltas = data.convergence_deltas()
            if 1 <= step <= len(deltas):  # bar i is |E_i − E_(i-1)|
                value, enthalpy = deltas[step - 1]
                return f"passo {step} · {'|ΔH|' if enthalpy else '|ΔE|'} = {value:.1e} Ry"
        elif panel == "force":
            if 0 <= step < len(data.steps):
                return f"passo {step} · F = {data.steps[step].force_ry_bohr:.1e} Ry/Bohr"
        else:
            return cell_readout(data, step, panel)
        return ""

    def export_stem(self, params: RelaxParams) -> str:
        return EXPORT_STEMS.get(params.panels, self.kind)

    def render(
        self, figure: FigureBase, dataset: RelaxDataset, params: RelaxParams, style: PlotStyle
    ) -> RenderInfo:
        data = dataset.data
        shown = self.panels_shown(params, data)
        axes = stacked_axes(figure, style, len(shown))
        log = params.scale == "log"
        legends = []
        for ax, panel in zip(axes, shown, strict=True):
            if panel == "pressure":
                legends.append(draw_pressure(ax, data, params, style))
            elif panel == "volume":
                legends.append(draw_volume(ax, data, params, style))
            else:
                draw = self._energy if panel == "energy" else self._force
                legends.append(draw(ax, data, params, style, log))
        for ax, handles in zip(axes[1:], legends[1:], strict=True):
            add_legend(ax, params, handles)

        n = len(data.steps)
        first = 0 if "force" in shown else 1  # |ΔE| starts at the second step
        bottom = axes[-1]
        bottom.set_xlabel("Passo BFGS")
        bottom.set_xticks(range(first, n, max(1, n // MAX_TICKS)))
        low = params.xmin if params.xmin is not None else first - 0.5
        high = params.xmax if params.xmax is not None else max(n - 0.5, low + 1)
        bottom.set_xlim(low, high)
        finish(figure, axes[0], params, legends[0])
        top = axes[0]
        pairs = data.convergence_deltas()
        missing = data.calculation == "vc-relax" and not all(enthalpy for _, enthalpy in pairs)
        notes = (NO_ENTHALPY,) if "energy" in shown and missing else ()
        return RenderInfo(top.get_xlim(), top.get_ylim(), self.summary(dataset), notes)

    @staticmethod
    def _threshold(
        ax: Axes, value: float, source: str, name: str, unit: str, params: RelaxParams
    ) -> list:
        if not params.show_thresholds:
            return []
        label = f"{name} = {value:.1e} {unit}" + (
            f" ({QE_DEFAULT})" if source == QE_DEFAULT else ""
        )
        ax.axhline(value, color=params.threshold_color, lw=1.0, ls=DASHED, zorder=3)
        return [Line2D([], [], color=params.threshold_color, lw=1.0, ls=DASHED, label=label)]

    def _energy(
        self, ax: Axes, data: RelaxData, params: RelaxParams, style: PlotStyle, log: bool
    ) -> list:
        series = data.convergence_deltas()
        if not series:
            empty_panel(ax, NO_DELTAS, style)
            return []
        deltas = [value for value, _ in series]
        if log:
            ax.set_yscale("log")
        values = positive_for_log(deltas) if log else deltas
        x = range(1, len(deltas) + 1)
        ax.bar(x, values, width=0.72, color=params.energy_color, zorder=2)
        ax.set_ylabel("|ΔH| (Ry)" if any(enthalpy for _, enthalpy in series) else "|ΔE| (Ry)")
        style_axes(ax, style)
        return self._threshold(
            ax, data.energy_threshold, data.energy_threshold_source, "etot_conv_thr", "Ry", params
        )

    def _force(
        self, ax: Axes, data: RelaxData, params: RelaxParams, style: PlotStyle, log: bool
    ) -> list:
        if not data.steps:
            empty_panel(ax, NO_STEPS, style)
            return []
        if log:
            ax.set_yscale("log")
        forces = [step.force_ry_bohr for step in data.steps]
        values = positive_for_log(forces) if log else forces
        ax.plot(
            [step.index for step in data.steps],
            values,
            color=params.force_color,
            lw=params.line_width,
            marker="o",
            markersize=max(3.0, params.line_width * 3),
            zorder=3,
        )
        ax.set_ylabel("Força total (Ry/Bohr)")
        style_axes(ax, style)
        return self._threshold(
            ax,
            data.force_threshold,
            data.force_threshold_source,
            "forc_conv_thr",
            "Ry/Bohr",
            params,
        )

    @staticmethod
    def summary(dataset: RelaxDataset) -> str:
        data = dataset.data
        if data.converged:
            status = "Relaxado ✓"
        elif not data.job_done:
            status = "Em andamento"
        else:
            status = "Não relaxado"
        moves = data.steps[-1].bfgs_step  # as pw.x counts them ("… and M bfgs steps")
        parts = [status, f"{moves} passo BFGS" if moves == 1 else f"{moves} passos BFGS"]
        if series := data.convergence_deltas():
            value, enthalpy = series[-1]
            parts.append(f"{'|ΔH|' if enthalpy else '|ΔE|'} final {value:.1e} Ry")
        parts.append(f"F final {data.steps[-1].force_ry_bohr:.1e} Ry/Bohr")
        parts += cell_summary(data)
        if data.final_scf_energy is not None:
            parts.append(f"E final (SCF final) {data.final_scf_energy:.6f} Ry")
        return " · ".join(parts)
