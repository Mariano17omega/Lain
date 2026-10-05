"""The edits that turn the SCF's text into the other pw.x inputs (spec 25 R4.2).

Every helper changes a value only when it differs from what the SCF has, so a field left at the
SCF's value keeps its line byte for byte (``InputEditor`` keeps everything else).
"""

from __future__ import annotations

from ..qe.input_edit import InputEditor
from ..qe.pw_input import fortran_float
from .kpath import KMesh, KPath, to_card
from .render import fortran_number

__all__ = ["ensure_smearing", "put_mesh", "put_number", "put_path", "put_string", "put_text"]

DEFAULT_SMEARING = "gaussian"
DEFAULT_DEGAUSS = 0.01


def _quote(editor: InputEditor, namelist: str, key: str) -> str:
    written = editor.raw(namelist, key) or ""
    return written[0] if written[:1] in ("'", '"') else "'"


def put_string(editor: InputEditor, namelist: str, key: str, value: str) -> bool:
    """A keyword value (``'bands'``), compared without case; the written quote is kept."""
    current = editor.get(namelist, key)
    if current is not None and current.strip().lower() == value.lower():
        return False
    quote = _quote(editor, namelist, key)
    editor.set(namelist, key, f"{quote}{value}{quote}")
    return True


def put_text(editor: InputEditor, namelist: str, key: str, value: str) -> bool:
    """A string compared as written (a path: case matters); the written quote is kept."""
    if editor.get(namelist, key) == value:
        return False
    quote = _quote(editor, namelist, key)
    editor.set(namelist, key, quote + value.replace(quote, quote * 2) + quote)
    return True


def put_number(editor: InputEditor, namelist: str, key: str, value: int | float) -> bool:
    current = editor.get(namelist, key)
    number = fortran_float(current) if current is not None else None
    if number is not None and number == float(value):
        return False
    editor.set(namelist, key, fortran_number(value))
    return True


def put_mesh(editor: InputEditor, mesh: KMesh) -> bool:
    card = editor.card("K_POINTS")
    if (
        card is not None
        and card.option == "automatic"
        and card.lines
        and KMesh.parse(card.lines[0]) == mesh
    ):
        return False
    editor.replace_card("K_POINTS", *mesh.card())
    return True


def put_path(editor: InputEditor, path: KPath) -> None:
    editor.replace_card("K_POINTS", *to_card(path))


def ensure_smearing(editor: InputEditor, replace_tetrahedra: bool = True) -> list[str]:
    """With ``occupations`` tetrahedra* (when ``replace_tetrahedra``) or smearing, leave a
    smearing with ``smearing`` and ``degauss`` set; the notes say what changed."""
    notes = []
    occupations = (editor.get("system", "occupations") or "").strip().lower()
    if occupations.startswith("tetrahedra") and replace_tetrahedra:
        put_string(editor, "system", "occupations", "smearing")
        notes.append(f"occupations = '{occupations}' trocado por 'smearing'")
        occupations = "smearing"
    if occupations != "smearing":
        return notes
    if editor.get("system", "smearing") is None:
        editor.set("system", "smearing", f"'{DEFAULT_SMEARING}'")
        notes.append(f"smearing = '{DEFAULT_SMEARING}' acrescentado")
    if editor.get("system", "degauss") is None:
        editor.set("system", "degauss", fortran_number(DEFAULT_DEGAUSS))
        notes.append(f"degauss = {DEFAULT_DEGAUSS} acrescentado")
    return notes
