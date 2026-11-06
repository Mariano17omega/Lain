"""Energia de adsorção (spec 79): SCFs already prepared (the complex, the clean surface, the isolated
molecule…) gathered in one folder and run one after the other by one script.

Nothing is generated but the copies: each SCF of step 1's list becomes ``scf_<prefix>.in`` with the
folder's unit (``outdir = './tmp/'``, ``jobs.pseudo_dir``) and nothing else changed, in the order of the
list, and ``ads_energy.qsub`` runs them in that order. The energies and the equation are the "Calcular
adsorção…" window's (spec 78), which reads the outputs once they ran. Two SCFs whose names would be the
same (the same ``prefix``, or two that differ only in characters a file name drops) get ``_2``, ``_3``…
Two inputs with the same ``prefix`` block "Criar" (``text_errors``, read in the texts as they will be
written, a hand edit included): they would share ``<prefix>.EXIT``, which pw.x looks for in the working
folder whatever the ``outdir`` (spec 70), and, with one ``outdir``, ``<prefix>.save``. The prefix is
changed by hand, never renamed here (spec 78 reads it).
"""

from __future__ import annotations

import dataclasses
import functools
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from ....i18n import _
from ...qe.input_edit import InputEditor
from ..scf_info import DEFAULT_PREFIX, ScfInfo
from ..unit import unit_notes
from .base import CalcType, FormField, PlannedFile, Work
from .files import INPUT_SUFFIX, InputFile, pw_input

SAME_PREFIX = _(
    "Dois SCFs com o prefix {prefix}: cancelar o job pararia só o primeiro (o {prefix}.EXIT é um só) "
    "e, com o mesmo outdir, eles escreveriam o mesmo {prefix}.save; "
    "mude o prefix de um deles no modo Avançado"
)
SOURCES = _("SCFs de origem:")


def key_of(index: int) -> str:
    """The key of the ``index``-th SCF of the list (0-based)."""
    return f"scf{index}"


def listed(scf: ScfInfo, scfs: tuple[ScfInfo, ...]) -> tuple[ScfInfo, ...]:
    """The SCFs to copy: step 1's list, or ``scf`` alone when there is none (the two-SCF minimum is
    step 1's rule; ``plan`` itself never refuses)."""
    return scfs or (scf,)


def _free(name: str, taken: set[str]) -> str:
    """``name``, or ``<stem>_2.in``, ``_3``… when an earlier input of the list has it."""
    stem, candidate, number = name.removesuffix(INPUT_SUFFIX), name, 1
    while candidate in taken:
        number += 1
        candidate = f"{stem}_{number}{INPUT_SUFFIX}"
    taken.add(candidate)
    return candidate


@functools.lru_cache(maxsize=128)
def prefix_of(text: str) -> str:
    """The ``prefix`` of a pw.x input (pw.x's default without one). Never raises. Cached: ``text_errors``
    runs with every input of the list on each keystroke in a preview, on the GUI thread."""
    prefix = InputEditor.from_text(text).get("control", "prefix")
    return (prefix or "").rstrip() or DEFAULT_PREFIX


class AdsEnergyType(CalcType):
    id: ClassVar[str] = "ads_energy"
    label: ClassVar[str] = _("Energia de adsorção")
    folder_prefix: ClassVar[str] = "Ads_energy"
    script_stem: ClassVar[str] = "ads_energy"
    script_template: ClassVar[str] = "qsub/scf.qsub.j2"
    multi_scf: ClassVar[bool] = True
    scf_label: ClassVar[str] = _("Inputs de SCF")

    def input_files(
        self, scf: ScfInfo, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[InputFile]:
        taken: set[str] = set()
        files = []
        for index, each in enumerate(listed(scf, scfs)):
            standard = pw_input(key_of(index), "scf", each, "SCF")
            files.append(dataclasses.replace(standard, name=_free(standard.name, taken)))
        return files

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return []

    def script_values(self, work: Work) -> dict[str, Any]:
        count = len(listed(work.scf, work.scfs))
        return {"pw_runs": [work.run(key_of(index)) for index in range(count)]}

    def inputs(self, work: Work) -> list[PlannedFile]:
        scfs = listed(work.scf, work.scfs)
        for each in scfs[1:]:  # ``plan`` gave the first one's
            work.notes.extend(unit_notes(each, work.jobs))
        return [
            work.pw_file(key_of(index), work.editor(each), source=each.text)
            for index, each in enumerate(scfs)
        ]

    def text_errors(self, files: Sequence[PlannedFile]) -> list[str]:
        """Two inputs with the same ``prefix`` would share one ``<prefix>.EXIT``: cancelling stops the
        first, pw.x deletes the file and the next run goes on (spec 70), whatever their ``outdir``."""
        counts = Counter(prefix_of(planned.text) for planned in files if planned.kind == "pw_input")
        return [SAME_PREFIX.format(prefix=prefix) for prefix, n in counts.items() if n > 1]

    def default_notes(
        self,
        scfs: tuple[ScfInfo, ...],
        root: Path | None = None,
        real: Mapping[Path, Path] | None = None,
    ) -> str:
        if not scfs:
            return ""
        from ..fingerprint import shown_path  # it imports the types

        known = real or {}

        def where(each: ScfInfo) -> str:
            if each.path is None:
                return each.name
            if root is None:
                return str(each.path)
            path, base = known.get(each.path, each.path), known.get(root, root)
            return shown_path(path, base, resolve=False)

        return "\n".join([SOURCES, *(f"- {where(each)}" for each in scfs)]) + "\n"
