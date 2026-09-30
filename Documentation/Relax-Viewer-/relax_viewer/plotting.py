from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from .models import RelaxationResult, Atom, Structure

CPK_COLORS = {
    "H": "#f0f0f0",
    "He": "#c0ffff",
    "Li": "#b22222",
    "Be": "#00ff00",
    "B": "#ff1493",
    "C": "#4b5563",
    "N": "#2563eb",
    "O": "#dc2626",
    "F": "#daa520",
    "Ne": "#ff00ff",
    "Na": "#0000ff",
    "Mg": "#228b22",
    "Al": "#93c5fd",
    "Si": "#f59e0b",
    "P": "#ff8c00",
    "S": "#eab308",
    "Cl": "#1e90ff",
    "Ar": "#800080",
    "K": "#ff00ff",
    "Ca": "#ffc0cb",
    "Fe": "#d97706",
}

COVALENT_RADII = {
    "H": 0.31,
    "He": 0.28,
    "Li": 1.28,
    "Be": 0.96,
    "B": 0.84,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "F": 0.57,
    "Ne": 0.58,
    "Na": 1.66,
    "Mg": 1.41,
    "Al": 1.21,
    "Si": 1.11,
    "P": 1.07,
    "S": 1.05,
    "Cl": 1.02,
    "Ar": 1.06,
    "K": 2.03,
    "Ca": 1.76,
    "Sc": 1.70,
    "Ti": 1.60,
    "V": 1.53,
    "Cr": 1.39,
    "Mn": 1.39,
    "Fe": 1.32,
    "Co": 1.26,
    "Ni": 1.24,
    "Cu": 1.32,
    "Zn": 1.22,
}


@dataclass(frozen=True)
class PlotPaths:
    energy: Path
    force: Path
    structure: Path


def generate_plots(result: RelaxationResult, output_dir: str | Path = "data") -> PlotPaths:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(result.source_path.stem or "relax")

    energy_path = target_dir / f"{stem}_energy.png"
    force_path = target_dir / f"{stem}_force.png"
    structure_path = target_dir / f"{stem}_structure.png"

    plot_energy_delta(result, energy_path)
    plot_total_force(result, force_path)
    plot_structure(result, structure_path)

    return PlotPaths(energy=energy_path, force=force_path, structure=structure_path)


def draw_energy_on_ax(ax: plt.Axes, result: RelaxationResult, *, log_scale: bool = True) -> None:
    deltas = result.energy_deltas
    if not deltas:
        _draw_empty(ax, "São necessários pelo menos dois passos completos para calcular |ΔE|.")
    else:
        # Use sequential indices (1..N) as bar positions to avoid a phantom gap
        # at position 0; the true BFGS step number is shown as the tick label.
        n = len(deltas)
        seq = np.arange(1, n + 1, dtype=int)
        bfgs_labels = [item.step.bfgs_step for item in deltas]
        raw_values = [item.delta_ry for item in deltas]
        values = _positive_for_log(raw_values, result.energy_threshold_ry) if log_scale else raw_values

        ax.bar(seq, values, color="#38bdf8", edgecolor="#0284c7", width=0.72)

        # Show every other tick when there are many steps
        step = max(1, n // 20)
        tick_positions = seq[::step]
        tick_labels = [str(bfgs_labels[i - 1]) for i in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels)
        ax.set_xlim(0.5, n + 0.5)

        if result.energy_threshold_ry is not None:
            ax.axhline(
                result.energy_threshold_ry,
                color="#f43f5e",
                linestyle="--",
                linewidth=1.5,
                label=f"etot_conv_thr = {result.energy_threshold_ry:.1e} Ry",
            )
            legend = ax.legend(loc="best", framealpha=0.2, facecolor="#1e293b", edgecolor="#334155")
            plt.setp(legend.get_texts(), color="#94a3b8")

        ax.set_yscale("log" if log_scale else "linear")
        ax.set_xlabel("Passo BFGS", color="#94a3b8")
        ax.set_ylabel("|ΔE| (Ry)", color="#94a3b8")
        ax.set_title("Convergência da energia", color="#f8fafc")
        ax.tick_params(colors="#94a3b8")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        which = "both" if log_scale else "major"
        ax.grid(axis="y", which=which, linestyle=":", linewidth=0.7, alpha=0.2, color="#94a3b8")


def plot_energy_delta(result: RelaxationResult, output_path: str | Path) -> Path:
    output = Path(output_path)
    fig, ax = plt.subplots(figsize=(8.0, 4.5), dpi=150)
    fig.patch.set_facecolor("#1e293b")
    ax.set_facecolor("#1e293b")
    draw_energy_on_ax(ax, result)
    fig.tight_layout()
    fig.savefig(output, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return output


def draw_force_on_ax(ax: plt.Axes, result: RelaxationResult, *, log_scale: bool = True) -> None:
    if not result.steps:
        _draw_empty(ax, "Nenhum passo completo de relaxamento foi encontrado.")
    else:
        x_values = np.array([step.bfgs_step for step in result.steps], dtype=int)
        raw_values = [step.total_force_ry_bohr for step in result.steps]
        values = _positive_for_log(raw_values, result.force_threshold_ry_bohr) if log_scale else raw_values

        ax.plot(
            x_values,
            values,
            color="#34d399",
            marker="o",
            linewidth=1.8,
            markersize=5,
            markerfacecolor="#059669",
            markeredgecolor="#34d399"
        )
        if result.force_threshold_ry_bohr is not None:
            ax.axhline(
                result.force_threshold_ry_bohr,
                color="#f43f5e",
                linestyle="--",
                linewidth=1.5,
                label=f"forc_conv_thr = {result.force_threshold_ry_bohr:.1e} Ry/Bohr",
            )
            legend = ax.legend(loc="best", framealpha=0.2, facecolor="#1e293b", edgecolor="#334155")
            plt.setp(legend.get_texts(), color="#94a3b8")

        # Explicit integer ticks; thin the labels when there are many steps
        n = len(x_values)
        step = max(1, n // 20)
        ax.set_xticks(x_values[::step])
        ax.set_xticklabels([str(v) for v in x_values[::step]])
        ax.set_xlim(x_values[0] - 0.5, x_values[-1] + 0.5)

        ax.set_yscale("log" if log_scale else "linear")
        ax.set_xlabel("Passo BFGS", color="#94a3b8")
        ax.set_ylabel("Força total (Ry/Bohr)", color="#94a3b8")
        ax.set_title("Convergência da força", color="#f8fafc")
        ax.tick_params(colors="#94a3b8")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        which = "both" if log_scale else "major"
        ax.grid(axis="y", which=which, linestyle=":", linewidth=0.7, alpha=0.2, color="#94a3b8")


def plot_total_force(result: RelaxationResult, output_path: str | Path) -> Path:
    output = Path(output_path)
    fig, ax = plt.subplots(figsize=(8.0, 4.5), dpi=150)
    fig.patch.set_facecolor("#1e293b")
    ax.set_facecolor("#1e293b")
    draw_force_on_ax(ax, result)
    fig.tight_layout()
    fig.savefig(output, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return output


def get_cartesian_coordinates(structure: Structure) -> list[tuple[str, float, float, float]]:
    if not structure or not structure.atoms:
        return []
    
    if structure.cell_parameters:
        cell = np.array(structure.cell_parameters, dtype=float)
        if structure.cell_unit == "bohr":
            cell = cell * 0.5291772109
    else:
        cell = np.eye(3)

    converted_atoms = []
    for atom in structure.atoms:
        pos = np.array([atom.x, atom.y, atom.z], dtype=float)
        if structure.unit == "crystal":
            cart_pos = pos @ cell
        elif structure.unit == "bohr":
            cart_pos = pos * 0.5291772109
        else:
            cart_pos = pos
        converted_atoms.append((atom.element, float(cart_pos[0]), float(cart_pos[1]), float(cart_pos[2])))
    return converted_atoms


def draw_unit_cell(ax: plt.Axes, cell_parameters: tuple[tuple[float, float, float], ...], cell_unit: str) -> None:
    if not cell_parameters:
        return
    cell = np.array(cell_parameters, dtype=float)
    if cell_unit == "bohr":
        cell = cell * 0.5291772109

    corners = np.zeros((8, 3))
    corners[1] = cell[0]
    corners[2] = cell[1]
    corners[3] = cell[2]
    corners[4] = cell[0] + cell[1]
    corners[5] = cell[0] + cell[2]
    corners[6] = cell[1] + cell[2]
    corners[7] = cell[0] + cell[1] + cell[2]

    edges = [
        (0, 1), (0, 2), (0, 3),
        (1, 4), (1, 5),
        (2, 4), (2, 6),
        (3, 5), (3, 6),
        (7, 4), (7, 5), (7, 6)
    ]
    for start, end in edges:
        xs = [corners[start, 0], corners[end, 0]]
        ys = [corners[start, 1], corners[end, 1]]
        zs = [corners[start, 2], corners[end, 2]]
        ax.plot(xs, ys, zs, color="#64748b", alpha=0.5, linestyle="--", linewidth=1.2)


def draw_bonds(ax: plt.Axes, cart_atoms: list[tuple[str, float, float, float]]) -> None:
    """Draw two-tone bonds: each half coloured with the respective atom's CPK colour."""
    n_atoms = len(cart_atoms)
    for i in range(n_atoms):
        el_i, xi, yi, zi = cart_atoms[i]
        r_i = COVALENT_RADII.get(el_i, 1.2)
        color_i = CPK_COLORS.get(el_i, "#d1d5db")
        for j in range(i + 1, n_atoms):
            el_j, xj, yj, zj = cart_atoms[j]
            r_j = COVALENT_RADII.get(el_j, 1.2)
            color_j = CPK_COLORS.get(el_j, "#d1d5db")
            dist = np.sqrt((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2)
            if 0.55 <= dist <= (r_i + r_j) * 1.25:
                mx, my, mz = (xi + xj) / 2, (yi + yj) / 2, (zi + zj) / 2
                # First half — atom i colour
                ax.plot(
                    [xi, mx], [yi, my], [zi, mz],
                    color=color_i, linewidth=3.5, alpha=1.0,
                    solid_capstyle="round", zorder=2,
                )
                # Second half — atom j colour
                ax.plot(
                    [mx, xj], [my, yj], [mz, zj],
                    color=color_j, linewidth=3.5, alpha=1.0,
                    solid_capstyle="round", zorder=2,
                )


def draw_structure_on_ax(
    ax: plt.Axes,
    result: RelaxationResult,
    *,
    zoom: float = 1.0,
    elev: float = 30.0,
    azim: float = -60.0,
    show_legend: bool = True,
) -> None:
    """Render the structure for *result* onto a 3-D axes.

    The structure shown is determined by the parser:
      - Converged relaxation  → relaxed geometry (last ATOMIC_POSITIONS before
        the Final SCF block).
      - Non-converged run    → geometry of the last completed BFGS step.

    Args:
        zoom: Values > 1 zoom in; values < 1 zoom out.
        elev: Elevation viewing angle in degrees (matplotlib default 30).
        azim: Azimuthal viewing angle in degrees (matplotlib default -60).
        show_legend: If False, skip the in-axes legend (use a Qt widget instead).
    """
    from collections import defaultdict
    from matplotlib.lines import Line2D

    structure = result.structure
    if not structure or not structure.atoms:
        _draw_empty_3d(ax, "Nenhuma estrutura encontrada no arquivo.")
        return

    cart_atoms = get_cartesian_coordinates(structure)

    # 1. Unit-cell wireframe (draw first so atoms/bonds appear on top)
    if structure.cell_parameters:
        draw_unit_cell(ax, structure.cell_parameters, structure.cell_unit or "bohr")

    # 2. Two-tone bonds
    draw_bonds(ax, cart_atoms)

    # 3. Atoms — single batch rendering to ensure correct depth sorting
    xs = [a[1] for a in cart_atoms]
    ys = [a[2] for a in cart_atoms]
    zs = [a[3] for a in cart_atoms]
    colors = [CPK_COLORS.get(a[0], "#d1d5db") for a in cart_atoms]
    radii = [COVALENT_RADII.get(a[0], 1.2) for a in cart_atoms]
    sizes = [max(60.0, r * 560.0) for r in radii]

    ax.scatter(
        xs, ys, zs,
        c=colors,
        edgecolors="#0f172a",
        linewidths=0.7,
        s=sizes,
        alpha=1.0,
        depthshade=False,
        zorder=5,
    )

    # Build legend handles
    unique_elements = sorted(list(set(a[0] for a in cart_atoms)))
    legend_handles = []
    for el in unique_elements:
        color = CPK_COLORS.get(el, "#d1d5db")
        legend_handles.append(
            Line2D(
                [0], [0], marker="o", color="none",
                markerfacecolor=color, markeredgecolor="#0f172a",
                markeredgewidth=0.5, markersize=10, label=el,
            )
        )

    # 4. Element legend (optional — omit in interactive mode, use Qt panel instead)
    if show_legend:
        legend = ax.legend(
            handles=legend_handles,
            loc="upper left",
            framealpha=0.35,
            facecolor="#0f172a",
            edgecolor="#475569",
            fontsize=9,
            title="Elementos",
            title_fontsize=8,
        )
        if legend:
            legend.get_title().set_color("#64748b")
            plt.setp(legend.get_texts(), color="#e2e8f0")

    # 5. Compute bounding box including cell corners
    xs_all = [a[1] for a in cart_atoms]
    ys_all = [a[2] for a in cart_atoms]
    zs_all = [a[3] for a in cart_atoms]

    if structure.cell_parameters:
        cell = np.array(structure.cell_parameters, dtype=float)
        if (structure.cell_unit or "bohr") == "bohr":
            cell = cell * 0.5291772109
        corners = np.zeros((8, 3))
        corners[1] = cell[0]
        corners[2] = cell[1]
        corners[3] = cell[2]
        corners[4] = cell[0] + cell[1]
        corners[5] = cell[0] + cell[2]
        corners[6] = cell[1] + cell[2]
        corners[7] = cell[0] + cell[1] + cell[2]
        xs_all.extend(corners[:, 0].tolist())
        ys_all.extend(corners[:, 1].tolist())
        zs_all.extend(corners[:, 2].tolist())

    min_x, max_x = min(xs_all), max(xs_all)
    min_y, max_y = min(ys_all), max(ys_all)
    min_z, max_z = min(zs_all), max(zs_all)
    max_range = max(max_x - min_x, max_y - min_y, max_z - min_z) or 1.0
    mid_x = (max_x + min_x) * 0.5
    mid_y = (max_y + min_y) * 0.5
    mid_z = (max_z + min_z) * 0.5

    half = max_range * 0.55 / zoom
    ax.set_xlim(mid_x - half, mid_x + half)
    ax.set_ylim(mid_y - half, mid_y + half)
    ax.set_zlim(mid_z - half, mid_z + half)

    # 6. Clean axis decoration
    ax.grid(False)
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = False
        pane.set_edgecolor("none")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    for line in (ax.xaxis.line, ax.yaxis.line, ax.zaxis.line):
        line.set_color((1.0, 1.0, 1.0, 0.0))

    # 7. Apply viewing angle
    ax.view_init(elev=elev, azim=azim)

    # 8. Title with convergence status
    if result.bfgs_converged:
        status = "Relaxada ✓"
    else:
        status = "Não convergida — último passo"
    n_atoms = len(structure.atoms)
    ax.set_title(
        f"Estrutura {status}    {n_atoms} átomos",
        color="#f8fafc",
        fontsize=10,
        pad=10,
    )


def plot_structure(result: RelaxationResult, output_path: str | Path) -> Path:
    output = Path(output_path)
    fig = plt.figure(figsize=(8.0, 6.0), dpi=150)
    ax = fig.add_subplot(111, projection="3d")

    fig.patch.set_facecolor("#1e293b")
    ax.set_facecolor("#1e293b")

    draw_structure_on_ax(ax, result)

    fig.tight_layout()
    fig.savefig(output, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return output


def _positive_for_log(values: list[float], threshold: float | None) -> list[float]:
    """Replace non-positive values with a small floor so log-scale axes work.

    The floor is derived only from the actual data values, not the threshold,
    so that the threshold line is not artificially compressed.
    """
    positive_data = [value for value in values if value > 0]
    floor = min(positive_data) / 10.0 if positive_data else 1.0e-12
    return [value if value > 0 else floor for value in values]


def _draw_empty(ax: plt.Axes, message: str) -> None:
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True, fontsize=11, color="#94a3b8")


def _draw_empty_3d(ax: plt.Axes, message: str) -> None:
    ax.axis("off")
    ax.text(0.5, 0.5, 0.5, message, ha="center", va="center", wrap=True, fontsize=11, color="#94a3b8")


def _safe_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.strip())
    return cleaned or "relax"


