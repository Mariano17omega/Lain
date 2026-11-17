"""Copy a curated set of real Quantum ESPRESSO runs into ``tests/fixtures/qe_examples/``.

The QE sources in ``Documentation/`` hold real inputs (inside the ``run_example`` shell scripts, as
heredocs) and real outputs (their ``reference/`` folders). This script expands the scripts without
running them, pairs each input with the output of the same run and copies the chosen cases.

    uv run python scripts/import_qe_examples.py [--source DIR] [--target DIR] [--replace]

Only the development repository has ``Documentation/``. The copy it makes is what the tests read.
Every fact in ``manifest.json`` is read from QE's own text, never through Lain's parsers: the tests
compare those parsers with it.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Documentation" / "Quantum_ESPRESSO-qe-7.3"
TARGET = ROOT / "tests" / "fixtures" / "qe_examples"
EXAMPLE_TREES = ("PW/examples", "PP/examples")
SUPPORTED_VERSION = (7, 1)
ENCODING = {"encoding": "utf-8", "errors": "surrogateescape"}

# The only change made to an input's text; the same convention as kao_surface_inputs/.
PLACEHOLDERS = {
    "PSEUDO_DIR": "/home/seu_usuario/PSEUDO",
    "TMP_DIR": "/home/seu_usuario/tmp",
    "EXAMPLE_DIR": "/home/seu_usuario/example",
    "BIN_DIR": "/home/seu_usuario/bin",
}

_HEREDOC = re.compile(
    r"^\s*cat\s+(?:>\s*(?P<name>\S+)\s*<<-?\s*(?P<tag>\\?['\"]?\w+['\"]?)"
    r"|<<-?\s*(?P<tag2>\\?['\"]?\w+['\"]?)\s*>\s*(?P<name2>\S+))\s*$"
)
_RUN = re.compile(
    r"\$(?P<command>\w*COMMAND)\b.*?(?:<|-(?:inp|in|i)\s)\s*(?P<in>\S+)\s*>\s*(?P<out>\S+)"
)
_FOR = re.compile(r"^\s*for\s+(?P<var>\w+)\s+in\s+(?P<values>.*?)\s*(?P<do>;\s*do)?\s*$")
_ASSIGN = re.compile(r"^\s*(?P<var>[A-Za-z_]\w*)=(?P<value>.*)$")
_VARIABLE = re.compile(r"\$\{?(\w+)\}?")
_LOOP_OPEN = re.compile(r"^(for|while)\b")
_BANNER = re.compile(
    r"Program\s+(?P<program>[A-Z0-9_.-]+)\s+v\.?\s*(?P<version>\d+\.\d+(?:\.\d+)?)"
)
_BENCHMARK = re.compile(r"^benchmark\.out\.git\.inp=(?P<input>.+?\.in)(?:\.args=\w+)?$")
_CALCULATION = re.compile(r"\bcalculation\s*=\s*['\"]([\w-]+)['\"]", re.I)

PROGRAMS = {
    "PWSCF": "pw.x",
    "BANDS": "bands.x",
    "PROJWFC": "projwfc.x",
    "DOS": "dos.x",
    "POST-PROC": "pp.x",
}

# What an input can vary in, as far as Lain reads it: one case per (calculation, variation).
_INPUT_FEATURES = {
    "spin": r"nspin\s*=\s*2",
    "noncollinear": r"noncolin\s*=\s*\.t",
    "spin_orbit": r"lspinorb\s*=\s*\.t",
    "hubbard": r"lda_plus_u\s*=\s*\.t|^\s*HUBBARD",
    "hybrid": r"input_dft\s*=\s*['\"](pbe0|hse|b3lyp|gaupbe)|nqx1",
    "vdw": r"vdw_corr|vdw-df|dftd3|input_dft\s*=\s*['\"]vdw",
    "isolated": r"assume_isolated|esm_bc",
    "rism": r"trism\s*=\s*\.t",
    "electric_field": r"tefield|lelfield|lberry|gate\s*=",
    "occupations_fixed": r"occupations\s*=\s*['\"]fixed",
    "occupations_smearing": r"occupations\s*=\s*['\"]smearing",
    "occupations_tetrahedra": r"occupations\s*=\s*['\"]tetra",
    "fixed_magnetization": r"tot_magnetization",
    "ibrav_0": r"ibrav\s*=\s*0\b",
    "cell_parameters": r"^\s*CELL_PARAMETERS",
    "celldm": r"celldm\(1\)",
    "cell_abc": r"^\s*[Aa]\s*=",
    "k_automatic": r"^\s*K_POINTS\W*automatic",
    "k_gamma": r"^\s*K_POINTS\W*gamma",
    "k_crystal_b": r"^\s*K_POINTS\W*crystal_b",
    "k_tpiba_b": r"^\s*K_POINTS\W*tpiba_b",
    "k_crystal": r"^\s*K_POINTS\W*crystal\s*\)?\s*$",
    "k_no_unit": r"^\s*K_POINTS\s*$",
    "positions_alat": r"^\s*ATOMIC_POSITIONS\W*alat",
    "positions_angstrom": r"^\s*ATOMIC_POSITIONS\W*angstrom",
    "positions_crystal": r"^\s*ATOMIC_POSITIONS\W*crystal",
    "positions_bohr": r"^\s*ATOMIC_POSITIONS\W*bohr",
    "positions_no_unit": r"^\s*ATOMIC_POSITIONS\s*$",
    "ions_bfgs": r"ion_dynamics\s*=\s*['\"]bfgs",
    "ions_damp": r"ion_dynamics\s*=\s*['\"]damp",
    "cell_damp": r"cell_dynamics\s*=\s*['\"](damp|w)",
    "uppercase_namelist": r"^\s*&CONTROL",
    "fixed_atoms": r"^\s*\w+\s+\S+\s+\S+\s+\S+\s+[01]\s+[01]\s+[01]\s*$",
}
_INPUT_PATTERNS = {key: re.compile(value, re.I | re.M) for key, value in _INPUT_FEATURES.items()}
_OUTPUT_FEATURES = {
    "fermi": "the Fermi energy is",
    "fermi_spin": "the spin up/dw Fermi energies are",
    "homo_lumo": "highest occupied, lowest unoccupied level",
    "homo": "highest occupied level",
    "converged": "convergence has been achieved",
    "not_converged": "convergence NOT achieved",
}

# The chosen outputs, relative to the sources. Every QE >= 7.1 output joins them on its own.
# Together they hold every (calculation, variation) of the sources (tests check it).
COVERAGE = (
    "PP/examples/BGW_example/references/si.scf.out",
    "PP/examples/ForceTheorem_example/reference/per.out",
    "PP/examples/ForceTheorem_example/reference/proj_par.out",
    "PP/examples/MolDos_example/reference/H2.bands.out",
    "PP/examples/MolDos_example/reference/H2.scf.out",
    "PP/examples/WannierHam_example/reference/NiO.nscf.out",
    "PP/examples/WorkFct_example/reference/Al.bulkref.avg.out",
    "PP/examples/dipole_example/reference/water.scf.out",
    "PP/examples/example02/reference/ni.fs_SP.out",
    "PP/examples/example04/reference/pt.nscf.out",
    "PP/examples/example04/reference/pt.scf.out",
    "PP/examples/fermisurf_example/reference/mgb2.scf.out",
    "PW/examples/cluster_example/reference/n.out-16",
    "PW/examples/cluster_example/reference/nh4+.out-16",
    "PW/examples/example01/reference/al.band.david.out",
    "PW/examples/example02/reference/co.rx.out",
    "PW/examples/example03/reference/si.md2.out",
    "PW/examples/example03/reference/si.md2_G3X.out",
    "PW/examples/example04/reference/BP.out",
    "PW/examples/example06/reference/o2.relax.out",
    "PW/examples/example11/reference/Fe.band_pbe.out",
    "PW/examples/example14/reference/srvo3.dmft_scf.out",
    "PW/examples/example14/reference/srvo3.nscf.out",
    "PW/examples/gatefield/reference/single_+0.10_nobarrier.bands.out",
    "PW/examples/gatefield/reference/single_-0.10.out",
    "PW/examples/vdwDF_example/reference/graphite.scf.out",
)
# Post-processing runs with the pw.x runs they follow: varied in system and spin.
POST_PROCESSING = (
    "PP/examples/MolDos_example/reference/H2.projwfc.out",
    "PP/examples/dipole_example/reference/water.pp.out",
    "PP/examples/example01/reference/si.band.out",
    "PP/examples/example01/reference/si.bands.out",
    "PP/examples/example01/reference/si.pp_rho.out",
    "PP/examples/example01/reference/si.scf.out",
    "PP/examples/example02/reference/ni.dos.out",
    "PP/examples/example02/reference/ni.dos2.out",
    "PP/examples/example02/reference/ni.pdos.out",
    "PP/examples/example02/reference/ni.scf.out",
    "PP/examples/example04/reference/pt.bands.out",
    "PP/examples/example04/reference/pt.pdos.out",
    "PP/examples/example06/reference/Fe.band_pbe.out",
    "PP/examples/example06/reference/Fe.bands.out",
    "PP/examples/example06/reference/Fe.scf_pbe.out",
    "PP/examples/exx_scf_bands_example/reference/si.bands.out",
    "PP/examples/fermisurf_example/reference/mgb2.proj.out",
)
# Runs Lain refuses or misreads today: the tests hold them to that, with the reason written.
KNOWN_LIMITS = (
    "PW/examples/ESM_example/reference/Al001_bc2_FCP_v00.out",
    "PW/examples/RISM_example/reference/H2O.NaCl_aq.out",
    "PW/examples/RISM_example/reference/HCHO.aq.out",
    "PW/examples/VCSexample/reference/As.vcs00.out",
    "PW/examples/example02/reference/al001.mm.out",
)
# Files a run wrote beside its output, which no heredoc names.
DATA_FILES = (
    "PP/examples/example01/reference/sibands.dat",
    "PP/examples/example02/reference/ni.dos",
    "PP/examples/example02/reference/ni.pdos_atm#1(Ni)_wfc#1(s)",
    "PP/examples/example02/reference/ni.pdos_atm#1(Ni)_wfc#2(d)",
    "PP/examples/example02/reference/ni.pdos_tot",
    "PP/examples/exx_scf_bands_example/reference/sibands.dat",
    "PP/examples/exx_scf_bands_example/reference/sibands.dat.gnu",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_atm#1(Mg)_wfc#1(s)",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_atm#1(Mg)_wfc#2(p)",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_atm#2(B)_wfc#1(s)",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_atm#2(B)_wfc#2(p)",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_atm#3(B)_wfc#1(s)",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_atm#3(B)_wfc#2(p)",
    "PP/examples/fermisurf_example/reference/mgb2.pdos_tot",
)


@dataclass(frozen=True)
class Run:
    command: str
    input: str
    output: str
    text: str | None  # the input as the script had written it when this run started


@dataclass
class Extraction:
    inputs: dict[str, str] = field(default_factory=dict)
    runs: list[Run] = field(default_factory=list)


@dataclass(frozen=True)
class Case:
    script: str  # relative to the sources
    input_name: str
    input_text: str
    output: Path

    def relative_output(self, source: Path) -> str:
        return self.output.relative_to(source).as_posix()


def _expand(text: str, env: dict[str, str]) -> str:
    return _VARIABLE.sub(lambda match: env.get(match.group(1), match.group(0)), text)


def _words(text: str) -> list[str]:
    try:
        return shlex.split(text, comments=True)
    except ValueError:
        return text.split()


def _loop_end(lines: list[str], start: int) -> int:
    depth = 1
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if _LOOP_OPEN.match(stripped):
            depth += 1
        elif stripped == "done" or stripped.startswith(("done ", "done;")):
            depth -= 1
            if depth == 0:
                return index
    return len(lines)


def _walk(lines: list[str], env: dict[str, str], found: Extraction) -> None:
    index = 0
    while index < len(lines):
        line = lines[index]
        if heredoc := _HEREDOC.match(line):
            tag = heredoc["tag"] or heredoc["tag2"]
            name = heredoc["name"] or heredoc["name2"]
            end = tag.strip("\\'\"")
            stop = index + 1
            while stop < len(lines) and lines[stop].strip() != end:
                stop += 1
            body = "\n".join(lines[index + 1 : stop]) + "\n"
            quoted = tag != end  # a quoted delimiter means the shell expands nothing
            found.inputs[_expand(name, env)] = body if quoted else _expand(body, env)
            index = stop + 1
            continue
        if loop := _FOR.match(line):
            start = index + 1
            if not loop["do"] and start < len(lines) and lines[start].strip() == "do":
                start += 1
            stop = _loop_end(lines, start)
            for value in _words(_expand(loop["values"], env)):
                env[loop["var"]] = value
                _walk(lines[start:stop], env, found)
            index = stop + 1
            continue
        stripped = line.strip()
        if stripped.startswith(("#", "$ECHO")):
            index += 1
            continue
        if assign := _ASSIGN.match(line):
            value = assign["value"]
            if "`" not in value and "$(" not in value:
                env[assign["var"]] = " ".join(_words(_expand(value, env)))
        elif run := _RUN.search(line):
            name = _expand(run["in"], env)
            found.runs.append(
                Run(run["command"], name, _expand(run["out"], env), found.inputs.get(name))
            )
        index += 1


def extract_script(text: str) -> Extraction:
    """The heredocs of a ``run_example`` and the runs that read them, without running anything."""
    found = Extraction()
    _walk(text.splitlines(), dict(PLACEHOLDERS), found)
    return found


def banner(head: bytes) -> tuple[str | None, str | None]:
    """The program (``pw.x``…) and version an output announces, or ``(None, None)``."""
    match = _BANNER.search(head.decode("utf-8", "replace"))
    if match is None:
        return None, None
    return PROGRAMS.get(match["program"]), match["version"]


def is_supported(version: str | None) -> bool:
    if version is None:
        return False
    return tuple(int(part) for part in version.split(".")[:2]) >= SUPPORTED_VERSION


def _head(path: Path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(4096)


def _example_cases(source: Path) -> Iterable[Case]:
    for tree in EXAMPLE_TREES:
        for script in sorted((source / tree).rglob("run_example*")):
            if not script.is_file():
                continue
            found = extract_script(script.read_text(**ENCODING))
            references = sorted(
                path
                for path in script.parent.iterdir()
                if path.is_dir() and path.name.startswith("reference")
            )
            for run in found.runs:
                if run.text is None:
                    continue
                for folder in references:
                    if (folder / run.output).is_file():
                        relative = script.relative_to(source).as_posix()
                        yield Case(relative, run.input, run.text, folder / run.output)


def _suite_cases(source: Path) -> Iterable[Case]:
    for output in sorted((source / "test-suite").glob("pw_*/benchmark*")):
        match = _BENCHMARK.match(output.name)
        if match is None or not is_supported(banner(_head(output))[1]):
            continue
        given = output.parent / match["input"]
        if given.is_file():
            relative = given.relative_to(source).as_posix()
            yield Case(relative, match["input"], given.read_text(**ENCODING), output)


def catalog(source: Path) -> list[Case]:
    """Every run of the sources whose output Lain reads, in a stable order."""
    cases = [*_example_cases(source), *_suite_cases(source)]
    return [case for case in cases if banner(_head(case.output))[0] is not None]


def calculation_of(input_text: str) -> str:
    match = _CALCULATION.search(input_text)
    return match.group(1).lower() if match else "scf"


def group_of(case: Case) -> str:
    """The calculation of a pw.x run, otherwise the program: what a variation is counted within."""
    program = banner(_head(case.output))[0]
    return calculation_of(case.input_text) if program == "pw.x" else str(program)


def variations(case: Case) -> list[str]:
    """What this run exercises, from the text of its input and of its output."""
    found = {"any"}
    found |= {key for key, regex in _INPUT_PATTERNS.items() if regex.search(case.input_text)}
    output = case.output.read_text(**ENCODING)
    found |= {key for key, marker in _OUTPUT_FEATURES.items() if marker in output}
    if is_supported(banner(_head(case.output))[1]):
        found.add("supported_version")
    return sorted(found)


def combinations(cases: Iterable[Case]) -> set[tuple[str, str]]:
    return {(group_of(case), name) for case in cases for name in variations(case)}


def reason_of(relative: str, version: str | None) -> str | None:
    for reason, chosen in (
        ("known_limit", KNOWN_LIMITS),
        ("post_processing", POST_PROCESSING),
        ("coverage", COVERAGE),
    ):
        if relative in chosen:
            return reason
    return "supported_version" if is_supported(version) else None


def selected(source: Path) -> list[Case]:
    return [
        case
        for case in catalog(source)
        if reason_of(case.relative_output(source), banner(_head(case.output))[1])
    ]


def destination(relative: str) -> Path:
    """Where a file of the sources lands: ``PW/examples/x/reference/a`` is ``PW/x/a``."""
    path = Path(relative)
    if path.parts[0] == "test-suite":
        match = _BENCHMARK.match(path.name)
        name = f"{match['input'].removesuffix('.in')}.out" if match else path.name
        return path.with_name(name)
    tree, _examples, example, folder, *rest = path.parts
    kept = () if folder == "reference" else (folder,)
    return Path(tree, example, *kept, *rest)


README = """\
# Real runs from the Quantum ESPRESSO 7.3 distribution

Inputs and outputs of QE's own examples (`PW/examples`, `PP/examples`) and of its test suite,
written by `scripts/import_qe_examples.py`. Do not edit these files: run the script again.

Most outputs come from QE older than 7.1, which Lain does not support. They are a corpus of real
text to read, each marked with its version in `manifest.json`: no code handles older formats.

Quantum ESPRESSO is distributed under the GNU General Public License, version 2: see `LICENSE`.
Inputs were taken from the example scripts with their shell variables expanded; the pseudopotential
and scratch folders are placeholders. Outputs are unchanged.
"""


def _write_case(case: Case, source: Path, target: Path) -> dict[str, object]:
    relative = case.relative_output(source)
    output = destination(relative)
    input_path = output.with_name(case.input_name)
    (target / output).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(case.output, target / output)
    (target / input_path).write_text(case.input_text, newline="\n", **ENCODING)
    program, version = banner(_head(case.output))
    return {
        "id": output.with_suffix("").as_posix(),
        "source": case.script,
        "program": program,
        "version": version,
        "supported": is_supported(version),
        "calculation": calculation_of(case.input_text) if program == "pw.x" else None,
        "input": input_path.as_posix(),
        "output": output.as_posix(),
        "reason": reason_of(relative, version),
        "covers": variations(case),
    }


def build(source: Path, target: Path) -> int:
    """Write the corpus into the empty ``target``; returns how many cases it holds."""
    target.mkdir(parents=True, exist_ok=True)
    cases = sorted(
        (_write_case(case, source, target) for case in selected(source)),
        key=lambda entry: str(entry["id"]),
    )
    data = []
    for relative in DATA_FILES:
        landed = destination(relative)
        (target / landed).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target / landed)
        data.append(landed.as_posix())
    manifest = {"cases": cases, "data_files": sorted(data)}
    text = json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    (target / "manifest.json").write_text(text, encoding="utf-8", newline="\n")
    (target / "README.md").write_text(README, encoding="utf-8", newline="\n")
    shutil.copyfile(source / "License", target / "LICENSE")
    return len(cases)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--replace", action="store_true", help="replace an existing corpus")
    args = parser.parse_args(argv)
    if not args.source.is_dir():
        print(f"error: {args.source} not found (only the development repository has it)")
        return 1
    if args.target.exists() and any(args.target.iterdir()):
        if not args.replace:
            print(f"error: {args.target} is not empty (use --replace)")
            return 1
        shutil.rmtree(args.target)
    print(f"wrote {build(args.source, args.target)} cases to {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
