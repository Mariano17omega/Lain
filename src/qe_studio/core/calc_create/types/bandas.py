"""Bandas: SCF, pw.x ``bands`` along a high-symmetry path and bands.x (one run per spin channel).

In the ``padrao`` mode only the path is asked for: ``nbnd`` comes from the SCF (spec 25 rule) and
``filband`` is ``./band`` (``./band_up`` / ``./band_dw`` per channel).
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..edits import ensure_smearing, put_number, put_path, put_string
from ..kpath import KPath, collapse_note, collapsed_segments
from ..render import render
from ..scf_info import ScfInfo
from ..unit import UNIT_OUTDIR
from .base import CalcType, FormField, PlannedFile, Work
from .fields import nbnd_field
from .files import InputFile
from .scf import KEY as SCF_KEY
from .scf import scf_input

BANDS_KEY = "bands"
BANDS = "bands.in"
BANDS_X = "qe/bandas/bands_pp.in.j2"
DEFAULT_FILBAND = "./band"
CHANNELS = (("up", 1), ("dw", 2))  # the ↑/↓ names spec 13 pairs (band_up, band_dw)


def bands_x_keys(scf: ScfInfo) -> list[str]:
    """The bands.x inputs (their keys are their standard names without ``.in``): one, or one per
    channel of a collinear spin run."""
    return [f"bands_pp_{tag}" for tag, _ in CHANNELS] if scf.spin else ["bands_pp"]


def channel_filband(filband: str, tag: str) -> str:
    """``./band`` → ``./band_up``, ``bands.dat`` → ``bands_up.dat`` (the tag before the suffix;
    the folder part kept as written)."""
    head, sep, tail = filband.rpartition("/")
    stem, dot, suffix = tail.rpartition(".")
    if not stem:  # no suffix, or a name that starts with its only dot
        stem, dot, suffix = tail, "", ""
    return f"{head}{sep}{stem}_{tag}{dot}{suffix}"


class BandasType(CalcType):
    id: ClassVar[str] = "bandas"
    label: ClassVar[str] = "Bandas"
    folder_prefix: ClassVar[str] = "Bands"
    script_stem: ClassVar[str] = "bands"
    script_template: ClassVar[str] = "qsub/bands.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (BANDS_X,)

    def input_files(self, scf: ScfInfo) -> list[InputFile]:
        return [
            scf_input(scf),
            InputFile(BANDS_KEY, BANDS, "Bandas"),
            *(InputFile(key, f"{key}.in") for key in bands_x_keys(scf)),
        ]

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [
            nbnd_field(scf, BANDS_KEY),
            FormField(
                "kpath",
                "Caminho de alta simetria",
                "kpath",
                None,
                required=True,
                group=BANDS_KEY,
                tooltip="K_POINTS crystal_b: pontos de alta simetria e pontos até o próximo",
                standard=True,
            ),
            FormField(
                "filband",
                "Arquivo das bandas (filband)",
                "text",
                DEFAULT_FILBAND,
                group=bands_x_keys(scf)[0],
                tooltip="bands.x grava <filband> e <filband>.gnu"
                + (" (_up / _dw por canal de spin)" if scf.spin else ""),
            ),
        ]

    def script_values(self, work: Work) -> dict[str, Any]:
        return {
            "pw_runs": [work.run(SCF_KEY), work.run(BANDS_KEY)],
            "bands_x": [work.run(key) for key in bands_x_keys(work.scf)],
        }

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        path: KPath = values["kpath"] or KPath(())
        if scf.crystal is None:
            work.notes.append(
                f"Estrutura do SCF não lida ({scf.structure_problem}): digite o caminho à mão; "
                "checagem do eixo x das bandas não feita"
            )
        else:
            work.notes.extend(
                collapse_note(path, segment)
                for segment in collapsed_segments(path, scf.crystal.cell)
            )
        editor = work.editor()
        put_string(editor, "control", "calculation", "bands")
        if values["nbnd"] is not None:
            put_number(editor, "system", "nbnd", values["nbnd"])
        if values["kpath"] is not None:
            work.errors.extend(path.problems())
        put_path(editor, path)
        bands = work.name(BANDS_KEY)
        work.notes.extend(f"{bands}: {note}" for note in ensure_smearing(editor))
        files = [work.pw_file(SCF_KEY, work.editor()), work.pw_file(BANDS_KEY, editor)]
        filband = values["filband"] or DEFAULT_FILBAND
        if scf.spin:
            work.notes.append("nspin = 2: o bands.x roda uma vez por canal (spin_component 1 e 2)")
            runs = [(channel_filband(filband, tag), component) for tag, component in CHANNELS]
        else:
            runs = [(filband, None)]
        for key, (name, component) in zip(bands_x_keys(scf), runs, strict=True):
            text = render(
                BANDS_X,
                {
                    "prefix": scf.prefix,
                    "outdir": UNIT_OUTDIR,
                    "filband": name,
                    "spin_component": component,
                },
            )
            files.append(work.planned(key, "qe_input", text))
        return files
