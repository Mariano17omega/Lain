"""Files the user edited by hand in the "Criar cálculo" window (spec 39 R2).

In the ``avancado`` mode the preview of each input and of the script can be edited. The typed text
*wins*: the fields keep planning (names, errors, the other files), but a file with an edit is written
as typed, and the errors a type reads in the texts (``CalcType.text_errors``) are read in it. Edits are
keyed by ``PlannedFile.key``, which a renamed file keeps. A text equal to the generated one (line ends
and the final newline aside) is no edit. What the editor holds has ``\\n`` line ends, so an edited file
is written with them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

from ..qe.input_lexer import LintIssue
from ..qe.input_lint import lint
from ..sniff import INPUT_READ_LIMIT
from ..viewer.qsub_lint import lint_script
from .types.base import CalcPlan, CalcType

__all__ = ["apply_overrides", "edit_issues", "edits_in_force", "is_edit", "normalized"]


def normalized(text: str) -> str:
    """``text`` with ``\\n`` line ends and one at the end (an empty text stays empty)."""
    text = text.replace("\r\n", "\n")
    return text if not text or text.endswith("\n") else text + "\n"


def is_edit(text: str, generated: str) -> bool:
    """Whether ``text`` differs from what the fields generated."""
    return normalized(text) != normalized(generated)


def edits_in_force(plan: CalcPlan, texts: Mapping[str, str]) -> dict[str, str]:
    """The edits of ``texts`` that still count: of a file of ``plan``, and not its text."""
    out: dict[str, str] = {}
    for key, text in texts.items():
        planned = plan.by_key(key)
        if planned is not None and is_edit(text, planned.text):
            out[key] = text
    return out


def apply_overrides(plan: CalcPlan, texts: Mapping[str, str], calc_type: CalcType) -> CalcPlan:
    """``plan`` (of ``calc_type``) with the text of each edited file replaced by the typed one;
    names, notes, problems and the fields' errors stay, the errors of the texts
    (``CalcType.text_errors``) are those of the files as typed. Unknown keys are ignored."""
    edits = edits_in_force(plan, texts)
    if not edits:
        return plan
    files = tuple(
        dataclasses.replace(planned, text=normalized(edits[planned.key]))
        if planned.key in edits
        else planned
        for planned in plan.files
    )
    fields = [error for error in plan.errors if error not in plan.text_errors]
    found = tuple(dict.fromkeys(calc_type.text_errors(files)))
    errors = tuple(dict.fromkeys([*fields, *found]))
    return dataclasses.replace(plan, files=files, errors=errors, text_errors=found)


def edit_issues(kind: str, text: str) -> list[LintIssue]:
    """The write problems of an edited file: ``lint_script`` for the script, the input linter for
    the inputs, none for the report (Markdown). None above the text viewer's limit
    (``INPUT_READ_LIMIT``). They never block "Criar"."""
    if len(text) > INPUT_READ_LIMIT or kind == "report":
        return []
    if kind == "qsub":
        return lint_script(text)
    return list(lint(text).issues)
