"""What a pw.x input means, checked from its text alone (spec 104).

``input_lint`` checks how an input is *written*; this module adds what pw.x refuses, or computes badly,
although every line is well written: the cutoffs, smearing, spin, the namelists a dynamics reads, the
atom count and a k mesh with one point along a periodic axis. Each rule copies the test pw.x makes (the
QE 7.3 source is cited at each one). Severity follows pw.x: ``error`` when it stops, or silently
computes something other than what is written; ``warning`` when it runs as written but the result is
probably poor.

``check_input`` is what the viewer and the "Criar cálculo" preview show. ``lint`` stays the write
checks, for the readers that only need the document (and so that ``lattice``, which this module needs,
can keep importing ``input_edit``, which imports ``input_lint``).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ...i18n import _, ngettext
from .input_edit import InputEditor, unquote
from .input_lexer import Entry, LintIssue, Severity
from .input_lint import Card, InputDoc, lint
from .lattice import MIN_SURFACE_GAP, StructureError, crystal_from_editor, interplanar, vacuum_gaps
from .pw_input import fortran_float, fortran_int

__all__ = ["US_PAW_NAME", "check_input", "semantic_issues"]

# What pw.x computes; cp.x inputs share its namelists but say 'cp', 'cp-wf', 'vc-cp'… (spec 104 R1.3).
PW_CALCULATIONS = frozenset({"scf", "nscf", "bands", "relax", "md", "vc-relax", "vc-md"})
_NON_SCF = frozenset({"nscf", "bands"})  # ``lscf`` stays false (``PW/src/input.f90:464-474``)
_NEED_IONS = frozenset({"relax", "md", "vc-relax", "vc-md"})
_NEED_CELL = frozenset({"vc-relax", "vc-md"})
# US and PAW pseudopotentials by file name: pslibrary (``kjpaw``, ``rrkjus``), GBRV (``uspp``) and the
# Vanderbilt ones (``van``, ``US``). ``gipaw`` is a norm-conserving one with GIPAW data. An old name
# that matches nothing (``AgUSPBE.RRKJ3``) gives no warning: the rule speaks only when it is sure.
US_PAW_NAME = re.compile(r"(?<!gi)paw|rrkjus|uspp|(?:^|[-_.])(?:us|van)(?:[-_.]|$)", re.IGNORECASE)
# Ry. The augmentation charges need a dense cutoff of their own, not a ratio: at a high ecutwfc 4 ×
# already passes it (90/360, the user's runs). Below this, 4 × is an NC habit (decision of 12/11/2026).
US_PAW_FLOOR = 300.0
SHORT_AXIS = 15.0  # Å: one k point along a longer periodic axis can be a deliberate choice
_EPS = 1e-8  # pw.x's ``eps8`` in ``set_cutoff``


def _number(entry: Entry | None) -> float | None:
    return None if entry is None else fortran_float(entry.value_text)


def _word(entry: Entry | None) -> str:
    """A string value, unquoted and lowercase; "" when absent."""
    return "" if entry is None else unquote(entry.value_text).strip().lower()


def _at(entry: Entry, severity: Severity, message: str) -> LintIssue:
    return LintIssue(entry.line, entry.value_start, entry.value_end, severity, message)


def _at_card(lines: list[str], card: Card, severity: Severity, message: str) -> LintIssue:
    """An issue under the card's name in its header line."""
    row = lines[card.line - 1].rstrip("\r") if card.line <= len(lines) else ""
    start = row.upper().find(card.name)
    if start < 0:
        return LintIssue(card.line, 0, len(row), severity, message)
    return LintIssue(card.line, start, start + len(card.name), severity, message)


def _short(value: float, digits: int = 6) -> str:
    """With a decimal point, as QE reads it, and no trailing zeros: ``120``, ``2.5``, ``4.67``."""
    return f"{value:.{digits}g}"


def _us_paw_file(doc: InputDoc) -> str | None:
    """The first ``ATOMIC_SPECIES`` file named like a US or PAW pseudopotential."""
    card = doc.card("ATOMIC_SPECIES")
    for row in card.lines if card is not None else ():
        words = row.split()
        if len(words) >= 3 and US_PAW_NAME.search(words[2]):
            return words[2]
    return None


# -- R2: cutoffs (``PW/src/input.f90:1764-1780``, ``set_cutoff``) ---------------------------------
def _cutoffs(doc: InputDoc) -> Iterator[LintIssue]:
    wfc_entry = doc.get("system", "ecutwfc")
    wfc = _number(wfc_entry)
    if wfc_entry is None or wfc is None or wfc <= 0:
        return  # pw.x takes it from the pseudopotentials: the text cannot tell
    rho_entry = doc.get("system", "ecutrho")
    written = _number(rho_entry)
    if rho_entry is not None and written is None:
        return  # a malformed number: the lexer marks it
    explicit = rho_entry is not None and written is not None and written > 0
    rho = written if explicit and written is not None else 4.0 * wfc
    ratio = rho / wfc
    if ratio <= 1.0 and rho_entry is not None:
        yield _at(
            rho_entry,
            "error",
            _("ecutrho ({rho} Ry) não passa de ecutwfc ({wfc} Ry): o pw.x para").format(
                rho=_short(rho), wfc=_short(wfc)
            ),
        )
        return
    pseudo = _us_paw_file(doc)
    if pseudo is not None and ratio <= 4.0 + _EPS and rho < US_PAW_FLOOR:
        if explicit and rho_entry is not None:
            message = _(
                "Pseudopotencial US/PAW ({file}) com ecutrho = {rho} Ry ({ratio} × ecutwfc): "
                "costuma precisar de 8 a 12 ×; confira o corte sugerido no UPF"
            ).format(file=pseudo, rho=_short(rho), ratio=_short(ratio, 3))
            yield _at(rho_entry, "warning", message)
        else:
            message = _(
                "Pseudopotencial US/PAW ({file}) sem ecutrho: o padrão é 4 × ecutwfc = {rho} Ry; "
                "costuma precisar de 8 a 12 ×; confira o corte sugerido no UPF"
            ).format(file=pseudo, rho=_short(rho))
            yield _at(wfc_entry, "warning", message)
    elif ratio < 4.0 - _EPS and rho_entry is not None:
        message = _(
            'ecutrho = {ratio} × ecutwfc, abaixo de 4 ×: a densidade perde componentes (o pw.x pergunta "are you sure?")'
        ).format(ratio=_short(ratio, 3))
        yield _at(rho_entry, "warning", message)


# -- R3: smearing and spin ------------------------------------------------------------------------
def _smearing(doc: InputDoc) -> Iterator[LintIssue]:
    """``PW/src/set_occupations.f90:44-46``: smearing without a positive degauss stops pw.x."""
    occupations = doc.get("system", "occupations")
    if occupations is None or _word(occupations) != "smearing":
        return
    degauss_entry = doc.get("system", "degauss")
    degauss = _number(degauss_entry)
    if degauss_entry is not None and degauss is None:
        return  # a malformed number: the lexer marks it
    if degauss is None or degauss <= 0:
        message = _("occupations = 'smearing' exige degauss > 0: o pw.x para")
        yield _at(occupations, "error", message)


def _spin(doc: InputDoc, calculation: str) -> Iterator[LintIssue]:
    """``PW/src/input.f90:1436,1465-1467``: ``lscf .and. lsda .and. .not. tfixed_occ .and. .not.
    two_fermi_energies`` with no starting_magnetization set stops pw.x (constraint 'none')."""
    nspin = doc.get("system", "nspin")
    if nspin is None or fortran_int(nspin.value_text) != 2 or calculation in _NON_SCF:
        return
    if _word(doc.get("system", "occupations")) == "from_input":  # tfixed_occ
        return
    keys = {entry.key for entry in doc.namelists.get("system", ())}
    if "tot_magnetization" in keys or any(k.startswith("starting_magnetization") for k in keys):
        return
    if (_word(doc.get("system", "constrained_magnetization")) or "none") != "none":
        return  # the other constraints have checks of their own
    message = _("nspin = 2 sem starting_magnetization nem tot_magnetization: o pw.x para")
    yield _at(nspin, "error", message)


# -- R4: the namelists a dynamics reads (``Modules/read_namelists.f90:2452-2488``) -----------------
def _namelists(doc: InputDoc, calculation: str) -> Iterator[LintIssue]:
    entry = doc.get("control", "calculation")
    if entry is None:
        return  # scf, which reads neither
    if calculation in _NEED_IONS and "ions" not in doc.namelists:
        message = _("calculation = '{calc}' exige a namelist &IONS: o pw.x para")
        yield _at(entry, "error", message.format(calc=calculation))
    if calculation in _NEED_CELL and "cell" not in doc.namelists:
        message = _("calculation = '{calc}' exige a namelist &CELL: o pw.x para")
        yield _at(entry, "error", message.format(calc=calculation))


# -- R5: nat and the rows of ATOMIC_POSITIONS (``Modules/read_cards.f90:436-492``, ``:238``) -------
def _atom_count(doc: InputDoc) -> Iterator[LintIssue]:
    entry = doc.get("system", "nat")
    card = doc.card("ATOMIC_POSITIONS")
    nat = fortran_int(entry.value_text) if entry is not None else None
    if entry is None or card is None or nat is None:
        return
    count = len(card.lines)  # blank lines and ``#`` in column 1 dropped, as ``read_line`` does
    if count < nat:  # the next card is read as an atom, or the file ends: pw.x stops
        message = ngettext(
            "nat = {nat}, mas ATOMIC_POSITIONS tem {count} linha: o pw.x para",
            "nat = {nat}, mas ATOMIC_POSITIONS tem {count} linhas: o pw.x para",
            count,
        )
        yield _at(entry, "error", message.format(nat=nat, count=count))
    elif count > nat:  # each extra row is "card … ignored": atoms lost without an error
        message = ngettext(
            "nat = {nat}, mas ATOMIC_POSITIONS tem {count} linha: o pw.x ignora as que sobram",
            "nat = {nat}, mas ATOMIC_POSITIONS tem {count} linhas: o pw.x ignora as que sobram",
            count,
        )
        yield _at(entry, "error", message.format(nat=nat, count=count))


# -- R6: one k point along a periodic axis --------------------------------------------------------
def _thin_mesh(doc: InputDoc, text: str, lines: list[str]) -> Iterator[LintIssue]:
    card = doc.card("K_POINTS")
    if card is None or card.option != "automatic" or not card.lines:
        return
    mesh = [fortran_int(word) for word in card.lines[0].split()[:3]]
    if (
        len(mesh) < 3
        or any(n is None for n in mesh)
        or 1 not in mesh
        or max(n or 0 for n in mesh) <= 1
    ):
        return  # a mesh of all ones is a deliberate Γ
    try:
        crystal = crystal_from_editor(InputEditor.from_text(text))
        gaps = vacuum_gaps(crystal.cell, crystal.frac)
        spacing = interplanar(crystal.cell)
    except (StructureError, ValueError, ArithmeticError):
        return  # no readable structure: nothing to say
    for axis, name in enumerate("abc"):
        length = float(spacing[axis])
        if mesh[axis] == 1 and gaps[axis] < MIN_SURFACE_GAP and length < SHORT_AXIS:
            message = _(
                "K_POINTS com 1 ponto ao longo de {axis}, que não tem vácuo e mede {length} Å: "
                "a amostragem fica rala nessa direção"
            ).format(axis=name, length=f"{length:.1f}")
            yield _at_card(lines, card, "warning", message)


def semantic_issues(doc: InputDoc, text: str) -> list[LintIssue]:
    """The meaning checks of the pw.x input ``doc`` read from ``text`` (spec 104); none for another
    program or a calculation pw.x does not run."""
    if doc.program != "pw":
        return []
    calculation = _word(doc.get("control", "calculation")) or "scf"
    if calculation not in PW_CALCULATIONS:
        return []
    lines = text.split("\n")
    return [
        *_cutoffs(doc),
        *_smearing(doc),
        *_spin(doc, calculation),
        *_namelists(doc, calculation),
        *_atom_count(doc),
        *_thin_mesh(doc, text, lines),
    ]


def _order(issue: LintIssue) -> tuple[int, int, int]:
    return issue.line, issue.col_start, issue.col_end  # as ``input_lint._lint`` sorts


def _check_input(text: str) -> InputDoc:
    doc = lint(text)
    extra = semantic_issues(doc, text)
    if extra:
        doc.issues = sorted([*doc.issues, *extra], key=_order)
    return doc


def check_input(text: str) -> InputDoc:
    """``lint(text)`` plus the meaning checks, in one sorted list: what the viewer and the "Criar
    cálculo" preview show. Never raises: on a failure of the checks, the write checks alone."""
    try:
        return _check_input(text)
    except Exception:  # noqa: BLE001 - the viewer must open any file; tests call ``_check_input`` bare
        return lint(text)
