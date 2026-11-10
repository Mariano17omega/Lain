"""The edits that turn the SCF's text into the other pw.x inputs (spec 25 R4.2).

Every helper changes a value only when it differs from what the SCF has, so a field left at the
SCF's value keeps its line byte for byte (``InputEditor`` keeps everything else).
"""

from __future__ import annotations

from ...i18n import _
from ..qe.input_edit import InputEditor
from ..qe.pw_input import fortran_float
from .kpath import KMesh, KPath, to_card
from .render import fortran_number

__all__ = [
    "ensure_disk_io",
    "ensure_smearing",
    "put_mesh",
    "put_number",
    "put_path",
    "put_string",
    "put_text",
]

DEFAULT_SMEARING = "gaussian"
DEFAULT_DEGAUSS = 0.01
# pw.x's ``disk_io`` (QE:PW/src/input.f90:884-908; the default is ``low`` in an scf, ``medium`` otherwise).
# ``minimal`` and ``none`` keep no charge density, so a run that starts from it cannot; ``nowf`` keeps it
# but no ``wfc*.dat``, which bands.x and projwfc.x read (L-14).
DISK_IO_NO_CHARGE = frozenset({"minimal", "none"})
DISK_IO_NO_WFC = frozenset({"nowf", "minimal", "none"})


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


def ensure_disk_io(editor: InputEditor, reader: str | None = None) -> list[str]:
    """Take out a ``disk_io`` that would leave the next program without its data (L-14); the notes say
    what was removed, and the QE default (which keeps what is needed) takes over.

    ``reader`` is the program that reads the wavefunctions this run writes (``bands.x``,
    ``projwfc.x``): with it the run needs ``wfc*.dat`` too (``nowf`` is refused as well). Without it
    the run is the SCF that the next one starts from, and only its charge density is needed.
    """
    current = editor.get("control", "disk_io")
    value = (current or "").strip().lower()
    if value not in (DISK_IO_NO_WFC if reader else DISK_IO_NO_CHARGE):
        return []
    editor.remove("control", "disk_io")
    if reader:
        return [
            _(
                "disk_io = '{value}' removido: sem os wfc*.dat o {reader} não lê as funções de onda (o padrão do QE os grava)"
            ).format(value=value, reader=reader)
        ]
    return [
        _(
            "disk_io = '{value}' removido: sem a densidade de carga do SCF o cálculo seguinte não parte (o padrão do QE a grava)"
        ).format(value=value)
    ]


def ensure_smearing(editor: InputEditor, replace_tetrahedra: bool = True) -> list[str]:
    """With ``occupations`` tetrahedra* (when ``replace_tetrahedra``) or smearing, leave a
    smearing with ``smearing`` and ``degauss`` set; the notes say what changed."""
    notes = []
    occupations = (editor.get("system", "occupations") or "").strip().lower()
    if occupations.startswith("tetrahedra") and replace_tetrahedra:
        put_string(editor, "system", "occupations", "smearing")
        notes.append(
            _("occupations = '{occupations}' trocado por 'smearing'").format(
                occupations=occupations
            )
        )
        occupations = "smearing"
    if occupations != "smearing":
        return notes
    if editor.get("system", "smearing") is None:
        editor.set("system", "smearing", f"'{DEFAULT_SMEARING}'")
        notes.append(
            _("smearing = '{DEFAULT_SMEARING}' acrescentado").format(
                DEFAULT_SMEARING=DEFAULT_SMEARING
            )
        )
    if editor.get("system", "degauss") is None:
        editor.set("system", "degauss", fortran_number(DEFAULT_DEGAUSS))
        notes.append(
            _("degauss = {DEFAULT_DEGAUSS} acrescentado").format(DEFAULT_DEGAUSS=DEFAULT_DEGAUSS)
        )
    return notes
