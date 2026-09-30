from __future__ import annotations

from .models import RelaxationResult

RELAXED = "Relaxado"
NOT_RELAXED = "Não relaxado"


def is_relaxed(result: RelaxationResult) -> bool:
    if result.bfgs_converged:
        return True

    if result.energy_threshold_ry is None or result.force_threshold_ry_bohr is None:
        return False

    final_step = result.final_step
    energy_deltas = result.energy_deltas
    if final_step is None or not energy_deltas:
        return False

    return (
        energy_deltas[-1].delta_ry <= result.energy_threshold_ry
        and final_step.total_force_ry_bohr <= result.force_threshold_ry_bohr
    )


def status_label(result: RelaxationResult) -> str:
    return RELAXED if is_relaxed(result) else NOT_RELAXED


def status_summary(result: RelaxationResult) -> str:
    final_step = result.final_step
    last_delta = result.energy_deltas[-1].delta_ry if result.energy_deltas else None

    lines = [
        f"Arquivo: {result.source_path}",
        f"Passos completos: {len(result.steps)}",
    ]
    if result.truncated_steps:
        lines.append(f"Passos incompletos ignorados: {result.truncated_steps}")
    if result.energy_threshold_ry is not None:
        lines.append(f"etot_conv_thr: {result.energy_threshold_ry:.3e} Ry")
    if result.force_threshold_ry_bohr is not None:
        lines.append(f"forc_conv_thr: {result.force_threshold_ry_bohr:.3e} Ry/Bohr")
    if last_delta is not None:
        lines.append(f"Último |ΔE|: {last_delta:.3e} Ry")
    if final_step is not None:
        lines.append(f"Última força total: {final_step.total_force_ry_bohr:.3e} Ry/Bohr")

    return "\n".join(lines)
