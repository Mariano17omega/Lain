"""Helpers of the cursor readout (``CalculationModule.format_coordinates``, spec 10 R6)."""

from __future__ import annotations

import re

_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "omicron": "ο", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
}  # fmt: skip
_GREEK.update({name.capitalize(): letter.upper() for name, letter in _GREEK.items()})


def signed(value: float, spec: str) -> str:
    """``format(value, spec)`` with a real minus sign (U+2212), as the readout shows energies."""
    return format(value, spec).replace("-", "−")


def plain_kpoint_label(label: str) -> str:
    """Plain text of a matplotlib k-point label: ``$\\Gamma$`` → Γ, ``Y$_2$`` → Y₂."""
    text = re.sub(r"\\([A-Za-z]+)", lambda m: _GREEK.get(m.group(1), m.group(0)), label)
    text = re.sub(r"_\{?(\d+)\}?", lambda m: m.group(1).translate(_SUBSCRIPT), text)
    return text.replace("$", "")


def nearest_tick_label(
    x: float, ticks: list[float], labels: list[str], span: float, tolerance: float = 0.01
) -> str:
    """Label of the tick within ``tolerance`` of the axis ``span`` from ``x``; "" when none."""
    if not ticks or span <= 0:
        return ""
    distance, label = min(
        (abs(x - tick), label) for tick, label in zip(ticks, labels, strict=False)
    )
    return plain_kpoint_label(label) if distance <= tolerance * span else ""
