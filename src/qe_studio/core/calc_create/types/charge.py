"""Carga: the SCF and pp.x writing the charge density as an XSF file (spec 29).

The folder holds ``charge.qsub``, the SCF copy and ``pp_<name>_charge.in`` (``<name>`` is the folder's
name typed in step 1; none → ``pp_charge.in``). The ``padrao`` mode asks for nothing but the name and
the SCF: ``plot_num``, ``iflag``, ``output_format`` and ``fileout`` are ``avancado`` fields, whose
defaults are the validated template (``iflag = 3``, ``output_format = 5``, 3D XSF in ``cdd_xsf/``).
The script makes the folder of ``fileout`` (pp.x does not) and runs pp.x without MPI.
"""

from __future__ import annotations

import shlex
from pathlib import PurePosixPath
from typing import Any, ClassVar

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

# The codes of INPUT_PP (QE 7.1) the form offers, with the label the window shows.
IFLAGS = {
    0: "média esférica (1D)",
    1: "gráfico 1D",
    2: "gráfico 2D",
    3: "grade 3D",
    4: "gráfico 2D polar numa esfera",
}
OUTPUT_FORMATS = {
    0: "gnuplot (1D)",
    2: "plotrho (2D)",
    3: "XCrySDen (2D ou região 3D)",
    5: "XSF para XCrySDen (3D, grade FFT inteira)",
    6: "cube do Gaussian (3D)",
    7: "gnuplot (2D)",
}
# The formats pp.x writes for an ``iflag``; it ignores ``output_format`` on the others (1D, polar).
FORMATS_OF_IFLAG = {2: (2, 3, 7), 3: (3, 5, 6)}


def choice(code: int, labels: dict[int, str]) -> str:
    """``5`` → ``'5 — XSF para XCrySDen (3D, grade FFT inteira)'``: what the combo shows."""
    return f"{code} — {labels[code]}"


def code_of(text: object, default: int) -> int:
    """The code a ``choice`` starts with (``default`` for an empty or foreign text)."""
    head = str(text or "").split(maxsplit=1)
    return int(head[0]) if head and head[0].isdigit() else default


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
        "Tipo de gráfico (iflag)",
        "choice",
        choice(DEFAULT_IFLAG, IFLAGS),
        f"&PLOT iflag: dimensão do gráfico; 3 = grade 3D{note}",
        tuple(choice(code, IFLAGS) for code in IFLAGS),
        group,
    )


def output_format_field(group: str = PP_KEY, note: str = "") -> FormField:
    """``output_format`` of ``&PLOT``."""
    return _field(
        "output_format",
        "Formato de saída (output_format)",
        "choice",
        choice(DEFAULT_OUTPUT_FORMAT, OUTPUT_FORMATS),
        "&PLOT output_format: 5 = XSF 3D para o XCrySDen (exige iflag = 3); "
        f"o pp.x ignora o formato nos gráficos 1D e polar{note}",
        tuple(choice(code, OUTPUT_FORMATS) for code in OUTPUT_FORMATS),
        group,
    )


def format_problem(iflag: int, output_format: int) -> str | None:
    """Why ``output_format`` does not fit ``iflag`` (pp.x checks it), or None."""
    allowed = FORMATS_OF_IFLAG.get(iflag)
    if allowed is None or output_format in allowed:
        return None
    return (
        f"output_format = {output_format} não vale para iflag = {iflag} "
        f"({IFLAGS[iflag]}): use {', '.join(str(code) for code in allowed)}"
    )


class ChargeType(CalcType):
    id: ClassVar[str] = "charge"
    label: ClassVar[str] = "Carga"
    folder_prefix: ClassVar[str] = "Charge"
    script_stem: ClassVar[str] = "charge"
    script_template: ClassVar[str] = "qsub/charge.qsub.j2"
    input_templates: ClassVar[tuple[str, ...]] = (PP_TEMPLATE,)
    uses_name: ClassVar[bool] = True

    def input_files(self, scf: ScfInfo, name: str = "") -> list[InputFile]:
        name = name.strip()
        return [
            scf_input(scf),
            InputFile(PP_KEY, f"pp_{name}_charge.in" if name else "pp_charge.in"),
        ]

    def input_fields(self, scf: ScfInfo) -> list[FormField]:
        return [
            _field(
                "plot_num",
                "Grandeza (plot_num)",
                "int",
                DEFAULT_PLOT_NUM,
                "&INPUTPP plot_num: 0 = densidade de carga eletrônica (pseudo)",
            ),
            iflag_field(),
            output_format_field(),
            _field(
                "fileout",
                "Arquivo de saída (fileout)",
                "text",
                default_fileout(scf),
                "&PLOT fileout: relativo e dentro da pasta; o script cria a pasta dele",
            ),
        ]

    def script_values(self, work: Work) -> dict[str, Any]:
        fileout = work.values["fileout"] or default_fileout(work.scf)
        return {
            "pw_runs": [work.run(SCF_KEY)],
            "pp": work.run(PP_KEY),
            "fileout_dir": fileout_dir(fileout),
        }

    def inputs(self, work: Work) -> list[PlannedFile]:
        scf, values = work.scf, work.values
        plot_num = values["plot_num"] if values["plot_num"] is not None else DEFAULT_PLOT_NUM
        iflag = code_of(values["iflag"], DEFAULT_IFLAG)
        output_format = code_of(values["output_format"], DEFAULT_OUTPUT_FORMAT)
        fileout = values["fileout"] or default_fileout(scf)
        if plot_num < 0:
            work.problem("plot_num", "plot_num deve ser 0 ou maior")
        if absolute(fileout) or climbs(fileout):
            work.problem(
                "fileout",
                f"fileout deve ser relativo e ficar dentro da pasta (sem .. nem / inicial): {fileout}",
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
        return [work.pw_file(SCF_KEY, work.editor()), work.planned(PP_KEY, "qe_input", text)]
