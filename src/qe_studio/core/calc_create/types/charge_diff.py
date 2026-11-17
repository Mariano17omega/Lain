"""Diferença de carga: three SCFs and pp.x making Δρ = ρ(base) − ρ(clean) − ρ(isolated) (spec 30),
or, with ``nspin = 2``, Δm = m(base) − m(clean) − m(isolated), m = ρ↑ − ρ↓ (spec 100).

From the user's SCF the folder gets the SCF itself, ``scf_<p>_clean.in`` (without the atoms picked in
the "Átomos" tab) and ``scf_<p>_isolated.in`` (only those atoms), the three on the same cell, cutoffs
and mesh (``fragments.split_input`` touches only atoms and species), a pp.x input for each SCF's density
and ``pp_charge_diff.in``, which subtracts them. The script runs the three SCFs alike, with MPI and the
same pools (they share the ``K_POINTS automatic``), then the four pp.x. ``padrao`` asks for the atoms
alone; ``avancado`` adds the quantity (``plot_num`` 0 or 6), the format of the XSF files and the folder
they go to, the same for the four. With ``plot_num = 6`` the data files say ``spin`` where they say
``charge``; the names of the inputs (the tabs) stay.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any, ClassVar

from ....i18n import N_, _
from ...qe.input_edit import InputEditor
from ..edits import ensure_disk_io, put_text
from ..fragments import CLEAN, ISOLATED, atom_rows, split_input
from ..render import render
from ..scf_info import ScfInfo
from ..unit import UNIT_OUTDIR, absolute, climbs
from .base import CalcType, FormField, PlannedFile, Work
from .charge import (
    DEFAULT_IFLAG,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_PLOT_NUM,
    DIFF_PLOT_NUMS,
    FILEOUT_DIR,
    PP_TEMPLATE,
    SPIN_PLOT_NUM,
    choice,
    code_of,
    fileout_dir,
    format_problem,
    iflag_field,
    output_format_field,
    plot_problems,
    spin_problem,
    with_paw_note,
)
from .files import InputFile, unit_stem
from .scf import KEY as SCF_KEY
from .scf import scf_input

CLEAN_KEY = "scf_clean"
ISOLATED_KEY = "scf_isolated"
PP_BASE = "pp_base"
PP_CLEAN = "pp_clean"
PP_ISOLATED = "pp_isolated"
PP_DIFF = "pp_diff"
ATOMS_TAB = N_(
    "Átomos"
)  # the group of the atoms field: no file is named so, so it is a tab of its own
DIFF_TEMPLATE = "qe/charge_diff/pp_charge_diff.in.j2"
ATOMS_HINT = _(
    "Selecionados → isolated (só eles); o resto → clean (sem eles). "
    "Δρ = ρ(base) − ρ(clean) − ρ(isolated)"
)
XSF_DIR_FIELD = "xsf_dir"
ALL_PP_NOTE = _(". Vale para os quatro inputs do pp.x")
# The tooltip of ``plot_num``, one line each, before ``PAW_NOTE``.
PLOT_NUM_TIP = (
    N_("&INPUTPP plot_num dos quatro pp.x: a grandeza que eles extraem e subtraem."),
    N_(
        "0 = Δρ = ρ(base) − ρ(clean) − ρ(isolated): onde a ligação acumula (> 0) ou tira (< 0) elétrons."
    ),
    N_(
        "6 = Δm = m(base) − m(clean) − m(isolated), com m = ρ↑ − ρ↓: como a adsorção muda o magnetismo"
    ),
    N_("(momento apagado no sítio, fragmento que se polariza). Exige nspin = 2 no SCF."),
)


def data_word(plot_num: int) -> str:
    """The word of the data files' names, so that a magnetization never passes for a density."""
    return "spin" if plot_num == SPIN_PLOT_NUM else "charge"


def xsf_dir_of(values: dict[str, Any]) -> str:
    """The folder of the XSF files as the form holds it (the default when empty)."""
    return str(PurePosixPath(str(values.get(XSF_DIR_FIELD) or FILEOUT_DIR)))


def _xsf(folder: str, stem: str) -> str:
    return str(PurePosixPath(folder) / f"{stem}.xsf")


class ChargeDiffType(CalcType):
    id: ClassVar[str] = "charge_diff"
    label: ClassVar[str] = _("Diferença de carga")
    folder_prefix: ClassVar[str] = "Diff_Charge"
    script_stem: ClassVar[str] = "charge_diff"
    script_template: ClassVar[str] = "qsub/charge_diff.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (PP_TEMPLATE, DIFF_TEMPLATE)

    def input_files(
        self, scf: ScfInfo, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[InputFile]:
        stem = unit_stem(scf.prefix)
        return [
            scf_input(scf),
            InputFile(CLEAN_KEY, f"scf_{stem}_clean.in", "SCF clean"),
            InputFile(ISOLATED_KEY, f"scf_{stem}_isolated.in", "SCF isolated"),
            InputFile(PP_BASE, f"pp_{stem}_charge.in", "pp.x base"),
            InputFile(PP_CLEAN, f"pp_{stem}_clean_charge.in", "pp.x clean"),
            InputFile(PP_ISOLATED, f"pp_{stem}_isolated_charge.in", "pp.x isolated"),
            InputFile(PP_DIFF, "pp_charge_diff.in", _("pp.x diferença")),
        ]

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        # Cell, cutoffs and mesh are the SCF's in the three runs: pp.x only subtracts densities on one
        # FFT grid, so none of them is a field.
        return [
            FormField(
                "atoms",
                _("Átomos do fragmento isolado"),
                "atoms",
                (),
                required=True,
                group=ATOMS_TAB,
                tooltip=_("Átomos do SCF isolated; os demais formam o SCF clean"),
                standard=True,
                hint=ATOMS_HINT,
                data=atom_rows(scf.text),
            ),
            FormField(
                "plot_num",
                _("Grandeza (plot_num)"),
                "choice",
                choice(DEFAULT_PLOT_NUM, DIFF_PLOT_NUMS),
                group=PP_DIFF,
                tooltip=with_paw_note(*(_(line) for line in PLOT_NUM_TIP)),
                choices=tuple(choice(code, DIFF_PLOT_NUMS) for code in DIFF_PLOT_NUMS),
            ),
            iflag_field(PP_DIFF, ALL_PP_NOTE),
            output_format_field(PP_DIFF, ALL_PP_NOTE),
            FormField(
                XSF_DIR_FIELD,
                _("Pasta dos .xsf"),
                "text",
                FILEOUT_DIR,
                group=PP_DIFF,
                tooltip=(
                    _(
                        "&PLOT fileout dos quatro pp.x: <pasta>/<nome>.xsf. Relativa e dentro da "
                        "pasta; o script cria a pasta"
                    )
                ),
            ),
        ]

    def script_values(self, work: Work) -> dict[str, Any]:
        return {
            "pw_runs": [work.run(key) for key in (SCF_KEY, CLEAN_KEY, ISOLATED_KEY)],
            "pps": [work.run(key) for key in (PP_BASE, PP_CLEAN, PP_ISOLATED)],
            "diff": work.run(PP_DIFF),
            "xsf_dir": fileout_dir(_xsf(xsf_dir_of(work.values), "x")),
        }

    def text_errors(self, files: Sequence[PlannedFile]) -> list[str]:
        return plot_problems(files)

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        prefix = scf.prefix
        plot_num = code_of(values["plot_num"], DEFAULT_PLOT_NUM)
        word = data_word(plot_num)
        iflag = code_of(values["iflag"], DEFAULT_IFLAG)
        output_format = code_of(values["output_format"], DEFAULT_OUTPUT_FORMAT)
        folder = xsf_dir_of(values)
        if (problem := spin_problem(plot_num, scf)) is not None:
            work.problem("plot_num", problem)
        if absolute(folder) or climbs(folder):
            work.problem(
                XSF_DIR_FIELD,
                _(
                    "A pasta dos .xsf deve ser relativa e ficar dentro da pasta (sem .. nem / inicial): {folder}"
                ).format(folder=folder),
            )
        if (problem := format_problem(iflag, output_format)) is not None:
            work.problem("output_format", problem)

        base = work.editor()
        split = split_input(base.text(), values["atoms"] or ())
        for error in split.errors:
            work.problem("atoms", error)
        key_of = {CLEAN: CLEAN_KEY, ISOLATED: ISOLATED_KEY}
        work.notes.extend(f"{work.name(key_of[which])}: {note}" for which, note in split.notes)

        def keep_density(key: str, editor: InputEditor) -> None:
            """pp.x reads each SCF's charge density: a disk_io that does not save it goes (L-14).
            Each SCF has its own note: the fragments were split from the text as typed."""
            work.notes.extend(f"{work.name(key)}: {note}" for note in ensure_disk_io(editor))

        keep_density(SCF_KEY, base)

        def fragment(key: str, text: str, suffix: str) -> PlannedFile:
            editor = InputEditor.from_text(text)
            put_text(editor, "control", "prefix", f"{prefix}_{suffix}")
            keep_density(key, editor)
            return work.pw_file(key, editor)

        def pp_file(key: str, fragment_prefix: str) -> PlannedFile:
            text = render(
                PP_TEMPLATE,
                {
                    "prefix": fragment_prefix,
                    "outdir": UNIT_OUTDIR,
                    "filplot": f"{fragment_prefix}.{word}",
                    "plot_num": plot_num,
                    "iflag": iflag,
                    "output_format": output_format,
                    "fileout": _xsf(folder, f"{fragment_prefix}_{word}"),
                },
            )
            return work.planned(key, "qe_input", text)

        clean, isolated = f"{prefix}_{CLEAN}", f"{prefix}_{ISOLATED}"
        diff = render(
            DIFF_TEMPLATE,
            {
                "prefix": prefix,
                "outdir": UNIT_OUTDIR,
                "filplot": f"{prefix}_{word}_diff",
                "plot_num": plot_num,
                "files": [f"{name}.{word}" for name in (prefix, clean, isolated)],
                "iflag": iflag,
                "output_format": output_format,
                "fileout": _xsf(folder, f"{prefix}_{word}_diff"),
            },
        )
        return [
            work.pw_file(SCF_KEY, base),
            fragment(CLEAN_KEY, split.clean, CLEAN),
            fragment(ISOLATED_KEY, split.isolated, ISOLATED),
            pp_file(PP_BASE, prefix),
            pp_file(PP_CLEAN, clean),
            pp_file(PP_ISOLATED, isolated),
            work.planned(PP_DIFF, "qe_input", diff),
        ]
