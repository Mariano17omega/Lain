"""Carga: the SCF and pp.x writing the charge density as an XSF file (spec 29).

The folder holds ``charge.qsub``, the SCF copy and ``pp_<name>_charge.in`` (``<name>`` is the folder's
name typed in step 1; none → ``pp_charge.in``). The ``padrao`` mode asks for nothing but the name and
the SCF: ``plot_num``, ``iflag``, ``output_format`` and ``fileout`` are ``avancado`` fields, whose
defaults are the validated template (``iflag = 3``, ``output_format = 5``, 3D XSF in ``cdd_xsf/``).
The script makes the folder of ``fileout`` (pp.x does not) and runs pp.x without MPI.
"""

from __future__ import annotations

import dataclasses
import shlex
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any, ClassVar

from ....i18n import N_, _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_int
from ..edits import ensure_disk_io
from ..render import render
from ..scf_info import ScfInfo
from ..unit import UNIT_OUTDIR, absolute, climbs
from .base import CalcType, FormField, PlannedFile, Work
from .files import InputFile
from .scf import KEY as SCF_KEY
from .scf import scf_input

PP_KEY = "pp_charge"  # key of the pp.x input
PP_TEMPLATE = "qe/charge/pp_charge.in.j2"
FILEOUT_DIR = "cdd_xsf"
DEFAULT_PLOT_NUM = 0  # electron (pseudo-)charge density
DEFAULT_IFLAG = 3
DEFAULT_OUTPUT_FORMAT = 5

# The codes of INPUT_PP (QE 7.1) the form offers. A choice is the code and its label in one token,
# the same in every language (the combo shows it through _(), spec 57 R3.1); ``code_of`` reads the
# code back.
IFLAGS = {
    0: N_("0 — média esférica (1D)"),
    1: N_("1 — gráfico 1D"),
    2: N_("2 — gráfico 2D"),
    3: N_("3 — grade 3D"),
    4: N_("4 — gráfico 2D polar numa esfera"),
}
OUTPUT_FORMATS = {
    0: N_("0 — gnuplot (1D)"),
    2: N_("2 — plotrho (2D)"),
    3: N_("3 — XCrySDen (2D ou região 3D)"),
    5: N_("5 — XSF para XCrySDen (3D, grade FFT inteira)"),
    6: N_("6 — cube do Gaussian (3D)"),
    7: N_("7 — gnuplot (2D)"),
}
CODE_SEPARATOR = " — "  # between the code and the label of a choice, in every language
# rho(up) - rho(down): without lsda pp.x writes zeros and no error (PP/src/punch_plot.f90, QE 7.3).
SPIN_PLOT_NUM = 6
# What the "Diferença de carga" extracts and subtracts (spec 100); 0 is the default of every type.
DIFF_PLOT_NUMS = {
    0: N_("0 — Δρ: diferença de densidade de carga eletrônica (pseudo-carga de valência)"),
    6: N_("6 — Δm: diferença de polarização de spin, m = ρ↑ − ρ↓ (exige nspin = 2)"),
}
# The end of every plot_num tooltip, one line each (a tooltip is plain text: Qt breaks only at "\n").
# The plan cannot tell PAW (that is in the .upf), so the note is always there and says when it holds.
PAW_NOTE = (
    N_("PAW: plot_num 0 e 6 dão pseudo-densidades. Perto dos núcleos, dentro das esferas PAW,"),
    N_("elas não são as reais; na região da ligação, longe dos núcleos, a diferença é pequena."),
    N_("A densidade all-electron é plot_num 17 (valência) ou 21 (com caroço): só PAW e com uma"),
    N_("grade real muito densa."),
)
# The formats pp.x writes for an ``iflag``; it ignores ``output_format`` on the others (1D, polar).
FORMATS_OF_IFLAG = {2: (2, 3, 7), 3: (3, 5, 6)}
# What pp.x stops without in ``&PLOT``. The form has no field for these: they are typed in the pp.x tab.
PLOT_KEYS_OF_IFLAG = {
    0: ("e1", "nx"),
    1: ("e1", "nx"),
    2: ("e1", "e2", "nx", "ny"),
    4: ("radius", "nx", "ny"),
}


def choice(code: int, labels: dict[int, str]) -> str:
    """``5`` → ``'5 — XSF para XCrySDen (3D, grade FFT inteira)'``: the value of the choice."""
    return labels[code]


def label_of(code: int, labels: dict[int, str]) -> str:
    """The label of a choice as the combo shows it, without its code: ``'gráfico 2D'``."""
    return _(labels[code]).partition(CODE_SEPARATOR)[2]


def code_of(text: object, default: int) -> int:
    """The code a ``choice`` starts with (``default`` for an empty or foreign text)."""
    head = str(text or "").split(maxsplit=1)
    return int(head[0]) if head and head[0].isdigit() else default


def with_paw_note(*lines: str) -> str:
    """A ``plot_num`` tooltip: ``lines`` (translated already), then ``PAW_NOTE``, one per line."""
    return "\n".join([*lines, *(_(line) for line in PAW_NOTE)])


def spin_problem(plot_num: int, scf: ScfInfo) -> str | None:
    """Why ``plot_num`` = 6 does not fit an SCF without collinear spin (a file of zeros), or None."""
    if plot_num != SPIN_PLOT_NUM or scf.spin:
        return None
    return _(
        "plot_num = 6 (polarização de spin) exige nspin = 2 no SCF; este tem nspin = {nspin}: o pp.x escreveria um .xsf só de zeros"
    ).format(nspin=scf.nspin)


def fileout_dir(fileout: str) -> str | None:
    """The folder ``mkdir -p`` makes for ``fileout`` (shell-quoted); None when it has none."""
    parent = PurePosixPath(fileout).parent
    return None if str(parent) == "." else shlex.quote(str(parent))


def default_fileout(scf: ScfInfo) -> str:
    return f"{FILEOUT_DIR}/{scf.prefix}_charge.xsf"


def _field(
    key: str,
    label: str,
    kind,
    default,
    tooltip: str,
    choices: tuple[str, ...] = (),
    group: str = PP_KEY,
) -> FormField:
    return FormField(key, label, kind, default, group=group, tooltip=tooltip, choices=choices)


def iflag_field(group: str = PP_KEY, note: str = "") -> FormField:
    """``iflag`` of ``&PLOT`` (``note``: a sentence the type adds to the tooltip)."""
    return _field(
        "iflag",
        _("Tipo de gráfico (iflag)"),
        "choice",
        choice(DEFAULT_IFLAG, IFLAGS),
        _("&PLOT iflag: dimensão do gráfico; 3 = grade 3D{note}").format(note=note),
        tuple(choice(code, IFLAGS) for code in IFLAGS),
        group,
    )


def output_format_field(group: str = PP_KEY, note: str = "") -> FormField:
    """``output_format`` of ``&PLOT``, shown for the ``iflag`` whose format pp.x reads."""
    field = _field(
        "output_format",
        _("Formato de saída (output_format)"),
        "choice",
        choice(DEFAULT_OUTPUT_FORMAT, OUTPUT_FORMATS),
        _(
            "&PLOT output_format: 5 = XSF 3D para o XCrySDen (exige iflag = 3); o pp.x ignora o formato nos gráficos 1D e polar{note}"
        ).format(note=note),
        tuple(choice(code, OUTPUT_FORMATS) for code in OUTPUT_FORMATS),
        group,
    )
    with_format = tuple(choice(code, IFLAGS) for code in FORMATS_OF_IFLAG)
    return dataclasses.replace(field, shown_when=(("iflag", with_format),))


def format_problem(iflag: int, output_format: int) -> str | None:
    """Why ``output_format`` does not fit ``iflag`` (pp.x checks it), or None."""
    allowed = FORMATS_OF_IFLAG.get(iflag)
    if allowed is None or output_format in allowed:
        return None
    return _(
        "output_format = {output_format} não vale para iflag = {iflag} ({IFLAGS}): use {join}"
    ).format(
        output_format=output_format,
        iflag=iflag,
        IFLAGS=label_of(iflag, IFLAGS),
        join=", ".join(str(code) for code in allowed),
    )


def plot_problems(files: Sequence[PlannedFile]) -> list[str]:
    """What the ``&PLOT`` of each pp.x input lacks for its ``iflag``, read from the texts as they will
    be written, so that typing the keys in the tab clears it."""
    problems = []
    for planned in files:
        if planned.kind != "qe_input":
            continue
        editor = InputEditor.from_text(planned.text)
        iflag = fortran_int(editor.get("plot", "iflag"))
        if iflag not in PLOT_KEYS_OF_IFLAG:
            continue
        have = {key.partition("(")[0] for key in editor.keys("plot")}
        missing = [key for key in PLOT_KEYS_OF_IFLAG[iflag] if key not in have]
        if missing:
            problems.append(
                _(
                    "{name}: iflag = {iflag} exige {keys} em &PLOT; o formulário não tem esses campos: escreva-os na aba deste arquivo (Avançado)"
                ).format(name=planned.name, iflag=iflag, keys=", ".join(missing))
            )
    return problems


class ChargeType(CalcType):
    id: ClassVar[str] = "charge"
    label: ClassVar[str] = _("Carga")
    folder_prefix: ClassVar[str] = "Charge"
    script_stem: ClassVar[str] = "charge"
    script_template: ClassVar[str] = "qsub/charge.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (PP_TEMPLATE,)
    uses_name: ClassVar[bool] = True

    def input_files(
        self, scf: ScfInfo, name: str = "", scfs: tuple[ScfInfo, ...] = ()
    ) -> list[InputFile]:
        name = name.strip()
        return [
            scf_input(scf),
            InputFile(PP_KEY, f"pp_{name}_charge.in" if name else "pp_charge.in"),
        ]

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [
            _field(
                "plot_num",
                _("Grandeza (plot_num)"),
                "int",
                DEFAULT_PLOT_NUM,
                with_paw_note(
                    _(
                        "&INPUTPP plot_num: 0 = densidade de carga eletrônica (pseudo-carga de valência);"
                    ),
                    _("6 = polarização de spin, ρ↑ − ρ↓ (exige nspin = 2)."),
                ),
            ),
            iflag_field(),
            output_format_field(),
            _field(
                "fileout",
                _("Arquivo de saída (fileout)"),
                "text",
                default_fileout(scf),
                _("&PLOT fileout: relativo e dentro da pasta; o script cria a pasta dele"),
            ),
        ]

    def script_values(self, work: Work) -> dict[str, Any]:
        fileout = work.values["fileout"] or default_fileout(work.scf)
        return {
            "pw_runs": [work.run(SCF_KEY)],
            "pp": work.run(PP_KEY),
            "fileout_dir": fileout_dir(fileout),
        }

    def text_errors(self, files: Sequence[PlannedFile]) -> list[str]:
        return plot_problems(files)

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        plot_num = values["plot_num"] if values["plot_num"] is not None else DEFAULT_PLOT_NUM
        iflag = code_of(values["iflag"], DEFAULT_IFLAG)
        output_format = code_of(values["output_format"], DEFAULT_OUTPUT_FORMAT)
        fileout = values["fileout"] or default_fileout(scf)
        if plot_num < 0:
            work.problem("plot_num", _("plot_num deve ser 0 ou maior"))
        if (problem := spin_problem(plot_num, scf)) is not None:
            work.problem("plot_num", problem)
        if absolute(fileout) or climbs(fileout):
            work.problem(
                "fileout",
                _(
                    "fileout deve ser relativo e ficar dentro da pasta (sem .. nem / inicial): {fileout}"
                ).format(fileout=fileout),
            )
        if (problem := format_problem(iflag, output_format)) is not None:
            work.problem("output_format", problem)
        text = render(
            PP_TEMPLATE,
            {
                "prefix": scf.prefix,
                "outdir": UNIT_OUTDIR,
                "filplot": f"{scf.prefix}.charge",
                "plot_num": plot_num,
                "iflag": iflag,
                "output_format": output_format,
                "fileout": fileout,
            },
        )
        # pp.x reads the SCF's charge density: a disk_io that does not save it goes (L-14).
        scf_editor = work.editor()
        work.notes.extend(f"{work.name(SCF_KEY)}: {note}" for note in ensure_disk_io(scf_editor))
        return [work.pw_file(SCF_KEY, scf_editor), work.planned(PP_KEY, "qe_input", text)]
