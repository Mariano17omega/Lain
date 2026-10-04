"""Bandas: SCF, pw.x ``bands`` along a high-symmetry path and bands.x (one run per spin channel)."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, ClassVar

from ..edits import ensure_smearing, put_number, put_path, put_string
from ..kpath import KPath
from ..render import render
from ..scf_info import ScfInfo
from .base import CalcType, FormField, PlannedFile, Work
from .fields import nbnd_field

SCF = "scf.in"
BANDS = "bands.in"
BANDS_X = "qe/bandas/bands_pp.in.j2"
DEFAULT_FILBAND = "bands.dat"
CHANNELS = (("up", 1), ("dw", 2))  # the ↑/↓ names spec 13 pairs (bands_up.dat, bands_dw.dat)


def bands_x_stems(scf: ScfInfo) -> list[str]:
    """The bands.x inputs (without ``.in``): one, or one per channel of a collinear spin run."""
    return [f"bands_pp_{tag}" for tag, _ in CHANNELS] if scf.spin else ["bands_pp"]


def channel_filband(filband: str, tag: str) -> str:
    """``bands.dat`` → ``bands_up.dat`` (the tag before the suffix)."""
    path = PurePosixPath(filband)
    return str(path.with_name(f"{path.stem}_{tag}{path.suffix}"))


class BandasType(CalcType):
    id: ClassVar[str] = "bandas"
    label: ClassVar[str] = "Bandas"
    folder_prefix: ClassVar[str] = "bandas"
    script_template: ClassVar[str] = "qsub/bandas.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (BANDS_X,)
    default_nk: ClassVar[int] = 4

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [
            nbnd_field(scf, BANDS),
            FormField(
                "kpath",
                "Caminho de alta simetria",
                "kpath",
                None,
                required=True,
                group=BANDS,
                tooltip="K_POINTS crystal_b: pontos de alta simetria e pontos até o próximo",
            ),
            FormField(
                "filband",
                "Arquivo das bandas (filband)",
                "text",
                DEFAULT_FILBAND,
                group=f"{bands_x_stems(scf)[0]}.in",
                tooltip="bands.x grava <filband> e <filband>.gnu"
                + (" (_up / _dw por canal de spin)" if scf.spin else ""),
            ),
        ]

    def script_values(self, work: Work) -> dict[str, Any]:
        return {"bands_x": bands_x_stems(work.scf)}

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        if scf.crystal is None:
            work.notes.append(
                f"Estrutura do SCF não lida ({scf.structure_problem}): digite o caminho à mão"
            )
        editor = work.editor()
        put_string(editor, "control", "calculation", "bands")
        if values["nbnd"] is not None:
            put_number(editor, "system", "nbnd", values["nbnd"])
        path: KPath = values["kpath"] or KPath(())
        if values["kpath"] is not None:
            work.errors.extend(path.problems())
        put_path(editor, path)
        work.notes.extend(f"{BANDS}: {note}" for note in ensure_smearing(editor))
        files = [
            PlannedFile(SCF, "pw_input", scf.text, f"SCF ({SCF})"),
            PlannedFile(BANDS, "pw_input", work.finish(editor, BANDS), f"Bandas ({BANDS})"),
        ]
        filband = values["filband"] or DEFAULT_FILBAND
        if scf.spin:
            work.notes.append("nspin = 2: o bands.x roda uma vez por canal (spin_component 1 e 2)")
            runs = [(channel_filband(filband, tag), component) for tag, component in CHANNELS]
        else:
            runs = [(filband, None)]
        for stem, (name, component) in zip(bands_x_stems(scf), runs, strict=True):
            text = render(
                BANDS_X,
                {
                    "prefix": scf.prefix,
                    "outdir": scf.outdir,
                    "filband": name,
                    "spin_component": component,
                },
            )
            files.append(PlannedFile(f"{stem}.in", "qe_input", text, f"{stem}.in"))
        return files
