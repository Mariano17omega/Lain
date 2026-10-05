"""Property tests (Hypothesis) for the parsers that read truncated or hand-edited files.

Profiles ``dev`` and ``ci`` are registered in ``conftest.py`` (``HYPOTHESIS_PROFILE=ci`` in CI).
Specs 9, 11 and 12 add the cases of their new parsers here.

Known limits of ``read_gnu`` the strategies stay clear of (not real ``bands.x`` output): bands
are split where x decreases, so a file with a single k-point (x = 0 for every band) or a band
cut down to one point at x = 0 cannot be split back into bands.
"""

import contextlib
import io
import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from fragment_helpers import SMALL
from qe_studio.core.calc_create.fragments import atom_rows, split_input
from qe_studio.core.calc_create.kpath import KMesh, KPath, KPoint, to_card
from qe_studio.core.filtering import name_matcher
from qe_studio.core.grid_store import GridStore
from qe_studio.core.navigation import NavigationHistory
from qe_studio.core.plotting.grid import MAX_SIZE, GridCell, GridSpec, PlotRef
from qe_studio.core.qe.bands_x import BandsFormatError, gnu_shape, read_gnu_text
from qe_studio.core.qe.input_edit import InputEditor, unquote
from qe_studio.core.qe.input_lexer import LexState, scan_line
from qe_studio.core.qe.input_lint import _lint
from qe_studio.core.qe.pw_input import parse_kpoints
from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.qe.relax import parse_relax
from qe_studio.core.qe.scf import parse_scf
from qe_studio.core.qe.summary import summarize, summarize_lines

from conftest import FIXTURES

# An empty or whitespace-only cut makes numpy warn "input contained no data" before read_gnu
# reports it as a format error.
pytestmark = pytest.mark.filterwarnings("ignore:loadtxt:UserWarning")

# -- bands.x .gnu ------------------------------------------------------------------------------
COLUMN = 12  # each value is written with Fortran's f12.6


@st.composite
def band_matrices(draw, min_bands=1, min_kpoints=2):
    """``(x, energies)``: x strictly increasing from 0, energies of shape (nbnd, nks)."""
    nbnd = draw(st.integers(min_bands, 8))
    nks = draw(st.integers(min_kpoints, 30))
    steps = draw(st.lists(st.floats(1e-3, 2.0), min_size=nks - 1, max_size=nks - 1))
    values = draw(
        st.lists(st.floats(-50, 50, allow_nan=False), min_size=nbnd * nks, max_size=nbnd * nks)
    )
    x = np.concatenate([[0.0], np.cumsum(steps)])
    return x, np.array(values).reshape(nbnd, nks)


def gnu_blocks(x, energies) -> list[list[str]]:
    return [
        [f"{xi:{COLUMN}.6f}{e:{COLUMN}.6f}\n" for xi, e in zip(x, band, strict=True)]
        for band in energies
    ]


def gnu_text(blocks, separator: str, trailing: bool = False) -> str:
    """Bands joined by a blank line (QE 7.3) or a line with one space (QE 7.1)."""
    text = (separator + "\n").join("".join(block) for block in blocks)
    return text + (separator + "\n" if trailing else "")


@given(band_matrices(), st.sampled_from(["", " "]), st.booleans())
def test_read_gnu_round_trip(matrix, separator, trailing):
    x, energies = matrix
    data = read_gnu_text(gnu_text(gnu_blocks(x, energies), separator, trailing))
    assert data.energies.shape == energies.shape
    np.testing.assert_allclose(data.x, x, atol=1e-6)
    np.testing.assert_allclose(data.energies, energies, atol=1e-6)


@given(band_matrices(), st.sampled_from(["", " "]), st.data())
def test_read_gnu_any_truncation_is_a_format_error_or_a_result(matrix, separator, draw):
    text = gnu_text(gnu_blocks(*matrix), separator)
    cut = draw.draw(st.integers(0, len(text)))
    with contextlib.suppress(BandsFormatError):  # any other exception type fails the test
        read_gnu_text(text[:cut])


@given(band_matrices(min_bands=2), st.sampled_from(["", " "]), st.integers(0, COLUMN))
def test_read_gnu_cut_inside_the_last_line_is_an_error(matrix, separator, offset):
    """With two or more bands, a last line cut before its energy leaves a short last band."""
    text = gnu_text(gnu_blocks(*matrix), separator)
    last_line = text.rstrip("\n").rfind("\n") + 1
    with pytest.raises(BandsFormatError):
        read_gnu_text(text[: last_line + offset])


@given(band_matrices(min_bands=2, min_kpoints=3), st.sampled_from(["", " "]), st.data())
def test_read_gnu_bands_of_different_lengths_are_an_error(matrix, separator, draw):
    blocks = gnu_blocks(*matrix)
    band = draw.draw(st.integers(0, len(blocks) - 1))
    row = draw.draw(st.integers(0, len(blocks[band]) - 1))
    del blocks[band][row]
    with pytest.raises(BandsFormatError):
        read_gnu_text(gnu_text(blocks, separator))


@given(band_matrices(), st.sampled_from(["", " "]), st.booleans(), st.integers(1, 200))
def test_gnu_shape_agrees_with_read_gnu(matrix, separator, trailing, chunk_size):
    """The streaming sniff (spec 14 R5.1) sees the shape ``read_gnu`` loads, at any chunk size."""
    text = gnu_text(gnu_blocks(*matrix), separator, trailing)
    shape = gnu_shape(io.BytesIO(text.encode()), chunk_size)
    assert shape == read_gnu_text(text).energies.shape == matrix[1].shape


@given(band_matrices(), st.sampled_from(["", " "]), st.integers(1, 64), st.data())
def test_gnu_shape_of_a_truncated_file_is_an_error_or_the_loaded_shape(
    matrix, separator, chunk_size, draw
):
    text = gnu_text(gnu_blocks(*matrix), separator)
    cut = text[: draw.draw(st.integers(0, len(text)))]
    try:
        shape = gnu_shape(io.BytesIO(cut.encode()), chunk_size)
    except BandsFormatError:
        return  # any other exception type fails the test
    with contextlib.suppress(BandsFormatError):
        assert shape == read_gnu_text(cut).energies.shape


# -- pw.x relax/vc-relax output ----------------------------------------------------------------
RELAX_HEADER = """\
     Program PWSCF v.7.3.1 starts on 30Sep2026 at 12:00:00

     bravais-lattice index     =            0
     number of atoms/cell      =            2
     convergence thresholds EPS_SCF =  1.0E-06 energy convergence thresh.=   1.0000E-04
     force convergence thresh. =   1.0000E-03

   site n.     atom                  positions (alat units)
     1           Si  tau(   1) = (   0.0000000   0.0000000   0.0000000  )
     2           Si  tau(   2) = (   0.2500000   0.2500000   0.2500000  )

"""


def relax_step_lines(energy: float, force: float, k: int, last: str | None) -> str:
    """One BFGS step as pw.x prints it; ``last`` replaces the step line of a converged run."""
    ending = last or f"     number of bfgs steps    =  {k:2d}"
    return (
        "     iteration #  1     ecut=    30.00 Ry     beta= 0.70\n"
        f"!    total energy              =  {energy:16.8f} Ry\n"
        f"     Total force = {force:12.6f}     Total SCF correction = {0.00001:12.6f}\n"
        f"     number of scf cycles    =  {k + 1:2d}\n"
        f"{ending}\n\n"
    )


@st.composite
def relax_runs(draw):
    """``(text, steps)`` of a complete run: ``steps`` is a list of (energy, force)."""
    count = draw(st.integers(1, 8))
    energies = [
        round(v, 8) for v in draw(st.lists(st.floats(-500, -1), min_size=count, max_size=count))
    ]
    forces = [
        round(v, 6) for v in draw(st.lists(st.floats(1e-5, 1.0), min_size=count, max_size=count))
    ]
    converged = draw(st.booleans())
    text = RELAX_HEADER
    for k, (energy, force) in enumerate(zip(energies, forces, strict=True)):
        end = None
        if converged and k == count - 1:
            end = f"     bfgs converged in {count:3d} scf cycles and {k:3d} bfgs steps"
        text += relax_step_lines(energy, force, k, end)
    if converged:
        text += "     End of BFGS Geometry Optimization\n"
    if draw(st.booleans()):
        text += "     JOB DONE.\n"
    return text, list(zip(energies, forces, strict=True))


def parse_text(text: str):
    return parse_relax(text.splitlines(keepends=True))


@given(relax_runs())
def test_parse_relax_reads_every_complete_step(run):
    text, expected = run
    data = parse_text(text)
    assert [(s.energy_ry, s.force_ry_bohr) for s in data.steps] == expected
    assert [s.index for s in data.steps] == list(range(len(expected)))
    assert [s.bfgs_step for s in data.steps] == list(range(len(expected)))  # as printed
    assert data.truncated_steps == 0
    assert data.formula == "Si2"


@given(relax_runs(), st.data())
def test_parse_relax_cut_anywhere_never_raises_and_keeps_a_prefix(run, draw):
    text, expected = run
    cut = draw.draw(st.integers(0, len(text)))
    data = parse_text(text[:cut])
    got = [(s.energy_ry, s.force_ry_bohr) for s in data.steps]
    # The printed step number is not compared: a cut inside "= 12" reads "1".
    assert got == expected[: len(got)]
    assert data.truncated_steps <= 1
    assert [s.index for s in data.steps] == list(range(len(got)))


# -- pw.x SCF output ---------------------------------------------------------------------------
SCF_HEADER = """\
     Program PWSCF v.7.3.1 starts on 30Sep2026 at 12:00:00

     scf convergence threshold =      1.0E-08
     mixing beta               =       0.7000
     number of iterations used =            8  plain     mixing

     Self-consistent Calculation

"""


@st.composite
def scf_runs(draw):
    """``(text, iterations)`` of a run: ``iterations`` is a list of (energy, accuracy)."""
    count = draw(st.integers(1, 8))
    energies = [
        round(v, 8) for v in draw(st.lists(st.floats(-500, -1), min_size=count, max_size=count))
    ]
    accuracies = [
        f"{v:.3E}" for v in draw(st.lists(st.floats(1e-12, 1.0), min_size=count, max_size=count))
    ]
    converged = draw(st.booleans())
    text = SCF_HEADER
    for k, (energy, accuracy) in enumerate(zip(energies, accuracies, strict=True), start=1):
        mark = "!" if converged and k == count else " "
        text += (
            f"     iteration #{k:3d}     ecut=    30.00 Ry     beta= 0.70\n"
            f"     total cpu time spent up to now is {k:10.1f} secs\n\n"
            f"{mark}    total energy              =  {energy:14.8f} Ry\n"
            f"     estimated scf accuracy    <  {accuracy} Ry\n\n"
        )
    if converged:
        text += f"     convergence has been achieved in {count:3d} iterations\n"
    if draw(st.booleans()):
        text += "     JOB DONE.\n"
    return text, [(e, float(a)) for e, a in zip(energies, accuracies, strict=True)]


@given(scf_runs())
def test_parse_scf_reads_every_iteration(run):
    text, expected = run
    data = parse_scf(text.splitlines(keepends=True))
    assert [(it.energy_ry, it.accuracy_ry) for it in data.iterations] == expected
    assert [it.index for it in data.iterations] == list(range(1, len(expected) + 1))
    assert data.truncated == 0 and data.cycles == 1 and data.threshold_ry == 1e-8


@given(scf_runs(), st.data())
def test_parse_scf_cut_anywhere_never_raises_and_keeps_a_prefix(run, draw):
    text, expected = run
    cut = draw.draw(st.integers(0, len(text)))
    data = parse_scf(text[:cut].splitlines(keepends=True))
    got = [(it.energy_ry, it.accuracy_ry) for it in data.iterations]
    assert got == expected[: len(got)]
    assert data.truncated <= 1 and data.cycles <= 1
    assert [it.index for it in data.iterations] == list(range(1, len(got) + 1))


# -- QE inputs (spec 11) -----------------------------------------------------------------------
# Pieces that matter to the lexer, so that random text reaches its branches.
INPUT_PIECES = st.sampled_from(
    ["&", "&control", "&end", "/", "=", ",", "(", ")", "'", '"', "!", "#", " ", "\n", "\r\n", ".true.",
     "1.0e", "1d-8", "K_POINTS", "ATOMIC_POSITIONS", "{crystal}", "key", "x(1)", "3*", "\t", "é"]
)  # fmt: skip
INPUT_TEXT = st.one_of(st.text(max_size=200), st.lists(INPUT_PIECES, max_size=60).map("".join))


@given(INPUT_TEXT)
def test_lint_never_raises_and_its_issues_point_inside_the_text(text):
    doc = _lint(text)  # not `lint`: that one swallows bugs
    lines = text.split("\n")
    for issue in doc.issues:
        assert 1 <= issue.line <= len(lines)
        shown = lines[issue.line - 1].removesuffix("\r")
        assert 0 <= issue.col_start <= issue.col_end <= len(shown)
    assert [(i.line, i.col_start) for i in doc.issues] == sorted(
        (i.line, i.col_start) for i in doc.issues
    )


@given(st.text(max_size=120), st.integers(-1, 20))
def test_scan_line_is_total_for_any_line_and_block_state(line, code):
    state = LexState.from_code(code)
    scan = scan_line(line, state, 1)
    assert LexState.from_code(scan.state.code) == scan.state
    for token in scan.tokens:
        assert 0 <= token.start < token.end <= len(line)


KEYS = st.sampled_from(
    ["ecutwfc", "conv_thr", "nat", "degauss", "celldm(1)", "starting_magnetization(2)"]
)
VALUES = st.one_of(
    st.floats(-1e6, 1e6, allow_nan=False).map(repr),
    st.integers(-999, 999).map(str),
    st.sampled_from([".true.", ".false.", ".T.", "1.0d-8", "1.E-8", "'si'", '"x y"', "'a/b'"]),
)


@given(
    st.lists(st.tuples(KEYS, VALUES), min_size=1, max_size=12),
    st.sampled_from([",\n", "\n", ", ", " "]),
    st.sampled_from(["\n", "\r\n"]),
)
def test_well_formed_namelists_have_no_issues(pairs, separator, newline):
    body = "".join(f"  {key} = {value}{separator}" for key, value in pairs)
    text = f"&control{newline}{body}{newline}/{newline}&system{newline}/{newline}"
    doc = _lint(text)
    assert doc.issues == []
    assert [e.key for e in doc.namelists["control"]] == [key for key, _ in pairs]


# -- input editor (spec 24) ----------------------------------------------------------------------
@given(INPUT_TEXT)
def test_editor_without_operations_gives_the_text_back(text):
    assert InputEditor.from_text(text).text() == text


@given(INPUT_TEXT, KEYS, VALUES, st.sampled_from(["control", "system", "ions"]))
def test_editor_operations_never_fail_on_any_text(text, key, value, namelist):
    editor = InputEditor.from_text(text)
    editor.set(namelist, key, value)
    editor.get(namelist, key)
    editor.remove(namelist, key)
    editor.remove_namelist(namelist)
    editor.replace_card("K_POINTS", "gamma", ["  "])
    assert editor.issues == []  # an operation that raised would be listed here
    assert isinstance(editor.text(), str)


@given(
    INPUT_TEXT,
    st.lists(st.sampled_from([" Fe 0 0 0", " O 1 1 1 ! c", "", "  "]), max_size=4),
    KEYS,
)
def test_editor_card_row_and_rename_operations_never_fail_on_any_text(text, rows, key):
    editor = InputEditor.from_text(text)
    editor.card_rows("ATOMIC_POSITIONS")
    editor.replace_card_rows("ATOMIC_POSITIONS", rows)
    editor.remove_card("K_POINTS")
    editor.rename_key("system", key, "starting_magnetization(1)")
    assert editor.issues == []
    assert isinstance(editor.text(), str)


@given(
    st.lists(st.tuples(KEYS, VALUES), min_size=1, max_size=8, unique_by=lambda pair: pair[0]),
    st.sampled_from([",\n", "\n", ", "]),
    st.sampled_from(["\n", "\r\n"]),
    KEYS,
    VALUES,
)
def test_editor_set_then_get_gives_the_value_and_touches_one_line(
    pairs, separator, newline, key, value
):
    body = "".join(f"  {k} = {v}{separator}" for k, v in pairs)
    text = newline.join(
        ["&control", body, "/", "&system", "  nat = 2 ! two", "/", "K_POINTS gamma", ""]
    )
    editor = InputEditor.from_text(text)
    editor.set("control", key, value)
    assert editor.issues == []
    assert editor.get("control", key) == unquote(value)
    before, after = text.split("\n"), editor.text().split("\n")
    if key in dict(pairs):  # replaced in place: only the lines of that entry differ
        assert len(after) == len(before)
        changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
        assert all(key in before[i] for i in changed)
    else:  # one new line, the rest byte for byte
        at = next(i for i, (a, b) in enumerate(zip(before, after, strict=False)) if a != b)
        assert after[:at] + after[at + 1 :] == before


# -- output summary (spec 12) ------------------------------------------------------------------
SUMMARY_RUNS = [
    (FIXTURES / "al_bands" / "al.scf.out").read_text(),
    (FIXTURES / "kao_vc_relax" / "vc-relax.out").read_text(),
    (FIXTURES / "al_bands" / "bands.out").read_text(),
]
# Lines that matter to the scanner's state machine, so that random text reaches its branches
# (error block, message + next line, pseudopotential + next line, stress rows after P=).
SUMMARY_PIECES = st.sampled_from(
    ["     Program PWSCF v.7.1 starts on  1Jan2025 at  1: 0: 0\n", " %%%%%%%%%%\n",
     "     Error in routine cdiaghg (1):\n", "     Message from routine setup :\n",
     "     PseudoPot. # 1 for Al read from file:\n", "     /x/Al.UPF\n", "\n", "     text\n",
     "          total   stress  (Ry/bohr**3)   (kbar)     P=       -0.13\n",
     "  0.1  0.2  0.3  0.4  0.5  0.6\n", "!    total energy              =    -5.5 Ry\n",
     "     number of k points=    47  Gaussian smearing, width (Ry)=  0.0100\n",
     "     PWSCF        :      1.88s CPU      1.90s WALL\n", "     JOB DONE.\n",
     "     1           Al  tau(   1) = (   0.0   0.0   0.0  )\n", "     Self-consistent Calculation\n",
     "     iteration #  1     ecut=   100.00 Ry     beta= 0.70\n",
     "     convergence has been achieved in   4 iterations\n",
     "     bfgs converged in  25 scf cycles and  24 bfgs steps\n",
     "     new unit-cell volume =   2253.94778 a.u.^3 (   334.00060 Ang^3 )\n"]
)  # fmt: skip


def check_summary(summary, lines):
    titles = [section.title for section in summary.sections]
    assert titles[0] == "Geral" and titles[-1] == "Avisos e erros"
    for section in summary.sections:
        assert section.rows
        for row in section.rows:
            for shown in (row, *row.children):
                assert shown.line is None or 1 <= shown.line <= lines
    for issue in summary.issues:
        assert issue.count >= 1 and (issue.line is None or 1 <= issue.line <= lines)


@given(st.integers(0, len(SUMMARY_RUNS) - 1), st.data())
def test_summary_of_a_cut_output_never_raises(index, draw):
    text = SUMMARY_RUNS[index]
    cut = text[: draw.draw(st.integers(0, len(text)))]  # mid-line too
    lines = cut.splitlines(keepends=True)
    check_summary(summarize_lines(lines, parse_pw_output(cut)), len(lines))


@given(st.lists(SUMMARY_PIECES, max_size=40))
def test_summary_of_random_scanner_lines_never_raises(pieces):
    text = "".join(pieces)
    check_summary(
        summarize_lines(text.splitlines(keepends=True), parse_pw_output(text)),
        len(text.splitlines()),
    )


@given(st.integers(0, len(SUMMARY_RUNS) - 1), st.data())
def test_summarize_a_cut_file_never_raises(index, draw):
    text = SUMMARY_RUNS[index]
    cut = text[: draw.draw(st.integers(0, len(text)))]
    with tempfile.TemporaryDirectory() as folder:  # not `tmp_path`: Hypothesis health check
        out = Path(folder) / "run.out"
        out.write_text(cut)
        check_summary(summarize(out), len(cut.splitlines()))


# -- spec 16: name filter and navigation history ------------------------------------------------
@given(st.text(max_size=30), st.text(max_size=30))
def test_name_matcher_never_raises_and_a_substring_always_matches(text, name):
    name_matcher(text)(name)
    plain = text.replace("*", "").replace("?", "")
    assert name_matcher(plain)(name + plain + name)  # what is typed is found inside a name


@given(st.text(alphabet="ab*?.", max_size=8), st.text(alphabet="ab.", max_size=10))
def test_wildcards_agree_with_a_brute_force_reading(text, name):
    """``*`` is any run, ``?`` any one character, unanchored: a slice of ``name`` fits."""

    def fits(pattern: str, chunk: str) -> bool:
        if not pattern:
            return not chunk
        head, rest = pattern[0], pattern[1:]
        if head == "*":
            return any(fits(rest, chunk[n:]) for n in range(len(chunk) + 1))
        return bool(chunk) and (head == "?" or head == chunk[0]) and fits(rest, chunk[1:])

    expected = any(
        fits(text, name[i:j]) for i in range(len(name) + 1) for j in range(i, len(name) + 1)
    )
    assert name_matcher(text)(name) is expected


@given(st.lists(st.tuples(st.sampled_from("vbf"), st.sampled_from("abcd")), max_size=60))
def test_history_invariants_hold_for_any_walk(steps):
    """Visits, backs and forwards in any order: no repeats in a row, bounded stacks, and going back
    then forward returns to the same folder."""
    history = NavigationHistory(limit=5)
    for action, name in steps:
        folder = Path("/p") / name
        if action == "v":
            history.visit(folder)
        elif action == "b":
            before = history.current
            target, skipped = history.back(lambda path: True)
            assert skipped == []
            if target is not None:
                assert history.forward(lambda path: True)[0] == before
                assert history.back(lambda path: True)[0] == target
        else:
            history.forward(lambda path: True)
        for stack in (history.back_stack, history.forward_stack):
            assert len(stack) <= 5
            assert all(a != b for a, b in zip(stack, stack[1:], strict=False))
        if history.current is not None and history.back_stack:
            assert history.back_stack[-1] != history.current


# -- saved grids (spec 23) -------------------------------------------------------------------------
SEGMENT = st.text("abcxyz_-.áç 0123456789", min_size=1, max_size=8).filter(
    lambda name: name.strip(".") and name == name.strip()
)
INSIDE = st.lists(SEGMENT, min_size=1, max_size=3).map(lambda parts: ("in", parts))
OUTSIDE = st.lists(SEGMENT, min_size=1, max_size=3).map(lambda parts: ("out", parts))


@st.composite
def grid_specs(draw):
    rows, cols = draw(st.integers(1, MAX_SIZE)), draw(st.integers(1, MAX_SIZE))
    positions = draw(
        st.lists(
            st.tuples(st.integers(0, rows - 1), st.integers(0, cols - 1)),
            min_size=1,
            max_size=rows * cols,
            unique=True,
        )
    )
    cells = []
    for row, col in positions:
        path = draw(st.one_of(INSIDE, OUTSIDE))
        partner = draw(st.none() | INSIDE | OUTSIDE)
        kind = draw(st.sampled_from(["bands", "pdos", "relax", "scf", "bands_dos"]))
        title = draw(st.text(max_size=12))
        cells.append(GridCell(row, col, (path, kind, partner), title))  # paths placed per root
    name = draw(st.text(min_size=1, max_size=10).filter(lambda n: n.strip() and "/" not in n))
    return GridSpec(name, rows, cols, cells)


def _placed(spec: GridSpec, root: Path, outside: Path) -> GridSpec:
    def where(path):
        side, parts = path
        return (root if side == "in" else outside).joinpath(*parts)

    cells = []
    for cell in spec.cells:
        path, kind, partner = cell.ref
        ref = PlotRef(where(path), kind, where(partner) if partner is not None else None)
        cells.append(GridCell(cell.row, cell.col, ref, cell.title))
    return GridSpec(spec.name, spec.rows, spec.cols, cells)


@given(grid_specs())
def test_grid_store_round_trip_in_a_moved_project(spec):
    """Any valid grid comes back the same, and a moved project finds its folders where it is now
    (folders outside it stay where they were)."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root, moved, outside = base / "project", base / "moved", base / "elsewhere"
        saved = _placed(spec, root, outside)
        assert saved.validate() == []
        GridStore(base / "grids.json", root).save(saved)
        assert GridStore(base / "grids.json", root).get(spec.name) == saved
        assert GridStore(base / "grids.json", moved).get(spec.name) == _placed(spec, moved, outside)


# -- K_POINTS cards of "Criar cálculo" (spec 25 R5) ------------------------------------------------
_FRACTION = st.floats(-1, 1, allow_nan=False).map(lambda v: round(v, 8))
_LABEL = st.text("ABGKLMNRSUWXYZ_0123456789ag", max_size=6).filter(lambda t: t == t.strip())


@st.composite
def kpaths(draw):
    points = draw(
        st.lists(
            st.builds(
                KPoint, _LABEL, st.tuples(_FRACTION, _FRACTION, _FRACTION), st.integers(1, 200)
            ),
            min_size=2,
            max_size=15,
        )
    )
    breaks = draw(st.sets(st.integers(0, len(points) - 2)))
    return KPath(tuple(points), frozenset(breaks))


@given(kpaths())
def test_crystal_b_card_round_trip(path):
    """What ``to_card`` writes, Lain's own ``K_POINTS`` reader reads back: points, weights (1 at a
    break and at the end) and labels, and the path has as many points as pw.x will compute."""
    option, body = to_card(path)
    card = parse_kpoints([f"K_POINTS {option}", *body])
    assert card.mode == "crystal_b"
    np.testing.assert_allclose(card.points, [p.frac for p in path.points], atol=1e-8)
    assert card.weights.tolist() == path.weights()
    assert card.weights[-1] == 1 and all(card.weights[i] == 1 for i in path.breaks)
    assert card.labels == tuple(p.label for p in path.points)
    assert card.path_length == sum(path.weights()[:-1]) + 1


@given(st.tuples(*[st.integers(1, 60)] * 3), st.tuples(*[st.integers(0, 1)] * 3))
def test_automatic_card_round_trip(n, shift):
    mesh = KMesh(n, shift)
    option, body = mesh.card()
    card = parse_kpoints([f"K_POINTS {option}", *body])
    assert card.points.tolist() == [list(n)] and card.weights.tolist() == list(shift)
    assert KMesh.parse(body[0]) == mesh


# -- fragments of a charge difference (spec 30) ---------------------------------------------------
def cards_agree_with_the_counts(text: str) -> set[str]:
    """nat and ntyp as the cards hold them; the labels the atoms use (they must all be species)."""
    editor = InputEditor.from_text(text)
    positions, species = editor.card("ATOMIC_POSITIONS"), editor.card("ATOMIC_SPECIES")
    assert positions is not None and species is not None
    assert editor.get("system", "nat") == str(len(positions.lines))
    assert editor.get("system", "ntyp") == str(len(species.lines))
    labels = {line.split()[0] for line in positions.lines}
    assert labels <= {line.split()[0] for line in species.lines}
    return labels


@given(st.sets(st.integers(-2, 9), max_size=8))
def test_split_input_keeps_nat_and_ntyp_coherent_with_the_cards(selected):
    result = split_input(SMALL, selected)
    if result.errors:
        assert result.clean == result.isolated == SMALL
        return
    clean, isolated = (
        cards_agree_with_the_counts(result.clean),
        cards_agree_with_the_counts(result.isolated),
    )
    chosen = {index for index in selected if 1 <= index <= 6}
    assert len(chosen) == len(InputEditor.from_text(result.isolated).card("ATOMIC_POSITIONS").lines)  # type: ignore[union-attr]
    assert clean | isolated == {"Fe", "O", "H"}
    for text in (result.clean, result.isolated):
        assert InputEditor.from_text(text).issues == []


@given(INPUT_TEXT, st.sets(st.integers(-1, 5), max_size=4))
def test_split_input_never_raises_on_any_text(text, selected):
    result = split_input(text, selected)
    assert isinstance(result.clean, str) and isinstance(result.isolated, str)
    if result.errors:
        assert result.clean == result.isolated == text
    assert atom_rows(text).error == "" or result.errors
