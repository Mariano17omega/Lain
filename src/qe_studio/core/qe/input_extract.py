"""The key parameters of a QE input, for the viewer's extract strip (spec 11 R5).

Works on the tolerant reader's ``InputDoc``, so an input with write errors still gives its extract.
A parameter that is absent shows QE's default when it is well known (``calculation``, ``nspin``,
``occupations``) and is marked as such; nothing else gets an invented value.
"""

from __future__ import annotations

from dataclasses import dataclass

from .input_lint import Card, Entry, InputDoc

# QE's defaults of the few parameters worth showing when absent: (namelist, key) → value.
DEFAULTS = {
    ("control", "calculation"): "scf",
    ("system", "nspin"): "1",
    ("system", "occupations"): "fixed",
}

# What each program's strip lists, in order: (label, namelist, key). Labels keep QE's spelling.
_PARAMS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "bands": (
        ("filband", "bands", "filband"),
        ("spin_component", "bands", "spin_component"),
        ("lsym", "bands", "lsym"),
    ),
    "projwfc": (
        ("filpdos", "projwfc", "filpdos"),
        ("degauss", "projwfc", "degauss"),
        ("DeltaE", "projwfc", "deltae"),
        ("Emin", "projwfc", "emin"),
        ("Emax", "projwfc", "emax"),
    ),
    "dos": (
        ("fildos", "dos", "fildos"),
        ("degauss", "dos", "degauss"),
        ("DeltaE", "dos", "deltae"),
        ("Emin", "dos", "emin"),
        ("Emax", "dos", "emax"),
    ),
}
# pw.x is the same shape; K_POINTS and nspin are special (below) and sit at their own slot.
_PW_ORDER = (
    "calculation", "prefix", "ecutwfc", "ecutrho", "K_POINTS", "nat", "ntyp", "nspin",
    "occupations", "smearing", "degauss", "conv_thr", "pseudo_dir",
)  # fmt: skip
_PW_NAMELISTS = {
    "calculation": "control", "prefix": "control", "pseudo_dir": "control",
    "ecutwfc": "system", "ecutrho": "system", "nat": "system", "ntyp": "system",
    "occupations": "system", "smearing": "system", "degauss": "system",
    "conv_thr": "electrons",
}  # fmt: skip
_TRUE = {".true.", ".t.", "t"}


@dataclass(frozen=True)
class Chip:
    label: str
    value: str
    line: int | None  # where a click goes: the parameter's line, or its namelist's for a default
    is_default: bool = False

    @property
    def text(self) -> str:
        return f"{self.label}: {self.value}" + (" (padrão)" if self.is_default else "")


def clean(value_text: str) -> str:
    """The value without the quotes of a string."""
    text = value_text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1].strip()
    return text


def _is_true(entry: Entry | None) -> bool:
    return entry is not None and entry.value_text.strip().lower() in _TRUE


def _param(doc: InputDoc, label: str, namelist: str, key: str) -> Chip | None:
    entry = doc.get(namelist, key)
    if entry is not None:
        return Chip(label, clean(entry.value_text), entry.line)
    default = DEFAULTS.get((namelist, key))
    if default is not None:
        return Chip(label, default, doc.namelist_lines.get(namelist), is_default=True)
    return None


def _k_points(card: Card) -> Chip:
    """``automatic 8×8×8 (0 0 0)``, ``crystal_b 5 pontos``, ``gamma``."""
    mode = card.option or "tpiba"
    first = card.lines[0].split() if card.lines else []
    if mode == "automatic":
        if len(first) >= 3:
            shift = f" ({' '.join(first[3:6])})" if len(first) >= 6 else ""
            return Chip("K_POINTS", f"{mode} {'×'.join(first[:3])}{shift}", card.line)
    elif mode != "gamma" and len(first) == 1 and first[0].isdigit():
        return Chip("K_POINTS", f"{mode} {first[0]} pontos", card.line)
    return Chip("K_POINTS", mode, card.line)


def _spin(doc: InputDoc) -> Chip | None:
    noncolinear = doc.get("system", "noncolin")
    if noncolinear is not None and _is_true(noncolinear):
        mode = "SO" if _is_true(doc.get("system", "lspinorb")) else "não colinear"
        return Chip("nspin", mode, noncolinear.line)
    return _param(doc, "nspin", "system", "nspin")


def extract(doc: InputDoc) -> tuple[Chip, ...]:
    """The chips of ``doc``'s program, in display order (none for an unrecognized program)."""
    if doc.program == "pw":
        chips = []
        for label in _PW_ORDER:
            if label == "K_POINTS":
                card = doc.card("K_POINTS")
                chip = _k_points(card) if card is not None else None
            elif label == "nspin":
                chip = _spin(doc)
            else:
                chip = _param(doc, label, _PW_NAMELISTS[label], label)
            if chip is not None:
                chips.append(chip)
        return tuple(chips)
    params = _PARAMS.get(doc.program or "", ())
    return tuple(chip for p in params if (chip := _param(doc, *p)) is not None)
