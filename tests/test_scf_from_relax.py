"""Spec 24 R3, R4: the final structure of a relax, whether its geometry converged, and the SCF
generated from it."""

import dataclasses
import shutil

import pytest

from qe_studio.core.detection import detect_folder
from qe_studio.core.qe.final_structure import parse_final_structure, read_final_structure
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.qe.pw_input import parse_input
from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.qe.scf_from_relax import (
    NO_INPUT,
    VC_RELAX_CELL,
    ScfError,
    can_generate_scf,
    generate_scf_file,
    pair_input,
    pair_problem,
    scf_from_relax,
    scf_name,
)
from qe_studio.core.sniff import FileKind, SniffCache

from conftest import FIXTURES, copy_fixture

SI_OUT = FIXTURES / "si_relax/si.rel.out"
SI_IN = FIXTURES / "si_relax/si.rel.in"
VC_OUT = FIXTURES / "kao_vc_relax/vc-relax.out"
VC_IN = FIXTURES / "kao_vc_relax/vc-relax.in"
SLAB_OUT = FIXTURES / "kao_slab_relax/relax-kaolinite-slab-001.out"
SLAB_IN = FIXTURES / "kao_slab_relax/relax-kaolinite-slab-001.in"


def same_save_dir(prefix: str, save: str) -> str:
    """The warning every generated SCF carries (spec 27-6 R3)."""
    return (
        f"O SCF usa o mesmo prefix ({prefix}) e outdir do relax: rodá-lo regrava {save} e impede "
        "reiniciar o relax. Mude o prefix ou o outdir antes de rodar."
    )


RELAX_OUTPUTS = [
    SI_OUT,
    VC_OUT,
    SLAB_OUT,
    FIXTURES / "kao_supercell_relax/relax-kaolinite-slab-001-2x1x.out",
]


# -- R3.1: final structure ----------------------------------------------------------------------
def test_final_structure_of_a_relax_in_alat_keeps_if_pos():
    final = read_final_structure(SI_OUT)
    assert final is not None and final.cell is None
    assert final.positions.unit == "alat"
    assert final.positions.lines == (
        "Si               0.0000000000        0.0000000000        0.0000000000    0   0   0",
        "Si               0.2499999996        0.2499999996        0.2499999996",
    )


def test_final_structure_of_a_vc_relax_has_the_cell():
    final = read_final_structure(VC_OUT)
    assert final is not None and final.cell is not None
    assert final.cell.unit == "angstrom" and final.cell.alat is None
    assert final.cell.rows[0] == "   5.189525088  -0.000422155   0.002783029"
    assert len(final.cell.rows) == 3
    assert final.positions.unit == "crystal" and len(final.positions.lines) == 34
    # Step 24 printed other numbers: these are the ones between Begin and End.
    assert final.positions.lines[0].split()[1:] == ["0.2971900999", "0.4937797529", "0.4786875228"]


def test_final_structure_of_a_fixed_cell_relax():
    final = read_final_structure(SLAB_OUT)
    assert final is not None and final.cell is None
    assert final.positions.unit == "crystal" and len(final.positions.lines) == 34


def test_final_structure_takes_the_block_not_a_step():
    lines = [
        "CELL_PARAMETERS (alat= 10.00000000)",
        "  1 0 0",
        "  0 1 0",
        "  0 0 1",
        "ATOMIC_POSITIONS (bohr)",
        "X 9 9 9",
        "Begin final coordinates",
        "     new unit-cell volume =   1.0 a.u.^3 (   0.1 Ang^3 )",
        "",
        "CELL_PARAMETERS (alat= 10.16863713)",
        "   0.5 0.5 0.0",
        "   0.0 0.5 0.5",
        "   0.5 0.0 0.5",
        "",
        "ATOMIC_POSITIONS (alat)",
        "Si 0.0 0.0 0.0",
        "End final coordinates",
        "Begin final coordinates",
        "ATOMIC_POSITIONS (bohr)",
        "Y 1 1 1",
        "End final coordinates",
    ]
    final = parse_final_structure(f"{line}\n" for line in lines)
    assert final is not None and final.cell is not None
    assert (final.cell.unit, final.cell.alat) == ("alat", "10.16863713")
    assert final.cell.rows == ("   0.5 0.5 0.0", "   0.0 0.5 0.5", "   0.5 0.0 0.5")
    assert final.positions.lines == ("Si 0.0 0.0 0.0",)


def test_no_final_block_is_none():
    assert read_final_structure(FIXTURES / "al_bands/al.scf.out") is None
    cut = SI_OUT.read_text().splitlines(keepends=True)
    end = next(i for i, line in enumerate(cut) if "End final coordinates" in line)
    assert parse_final_structure(cut[:end]) is None  # cut before its End


# -- R3.2: geometry convergence -----------------------------------------------------------------
@pytest.mark.parametrize("path", RELAX_OUTPUTS, ids=lambda p: p.parent.name)
def test_geometry_converged_in_the_relax_fixtures(path):
    assert parse_pw_output(path.read_text()).geometry_converged is True


def test_geometry_not_converged_or_unknown():
    text = SI_OUT.read_text()
    failed = text.replace(
        "bfgs converged in   7 scf cycles and   6 bfgs steps",
        "bfgs failed after   7 scf cycles and   6 bfgs steps, convergence not achieved",
    )
    assert parse_pw_output(failed).geometry_converged is False
    steps = text.replace(
        "bfgs converged in   7 scf cycles and   6 bfgs steps",
        "The maximum number of steps has been reached.",
    )
    assert parse_pw_output(steps).geometry_converged is False  # "End of BFGS" alone is no proof
    assert (
        parse_pw_output((FIXTURES / "al_bands/al.scf.out").read_text()).geometry_converged is None
    )
    head, tail = text[:2000], text[-200:]  # a tail that misses the marker (huge output)
    assert parse_pw_output(head, tail).geometry_converged is None


# -- R3.3: what the menu offers -----------------------------------------------------------------
def test_can_generate_scf_only_for_a_converged_finished_relax():
    sniff = SniffCache().sniff(SI_OUT)
    assert can_generate_scf(sniff)
    assert sniff.pw is not None
    for change in (
        {"geometry_converged": None},
        {"geometry_converged": False},
        {"job_done": False},
    ):
        pw = dataclasses.replace(sniff.pw, **change)
        assert not can_generate_scf(dataclasses.replace(sniff, pw=pw))
    assert not can_generate_scf(SniffCache().sniff(FIXTURES / "al_bands/al.scf.out"))
    assert not can_generate_scf(SniffCache().sniff(SI_IN))
    assert not can_generate_scf(None)


# -- R4.2: the SCF ------------------------------------------------------------------------------
def scf_of(out_path, in_path):
    final = read_final_structure(out_path)
    assert final is not None
    return scf_from_relax(final, in_path.read_text())


def assert_scf(text: str, nat: int) -> InputEditor:
    assert [i for i in lint(text).issues if i.severity == "error"] == []
    parsed = parse_input(text)
    assert parsed.calculation == "scf" and parsed.get("system", "nat") == nat
    editor = InputEditor.from_text(text)
    assert not editor.has_namelist("ions") and not editor.has_namelist("cell")
    assert editor.get("control", "restart_mode") is None and editor.get("control", "nstep") is None
    return editor


def test_scf_of_a_relax_keeps_the_input_and_the_cell():
    result = scf_of(SI_OUT, SI_IN)
    editor = assert_scf(result.text, 2)
    assert result.prefix == "silicon"
    assert result.warnings == (same_save_dir("silicon", "./tmp/silicon.save"),)
    assert (
        editor.get("system", "ibrav") == "2" and editor.get("system", "celldm(1)") == "10.16863713"
    )
    card = editor.card("ATOMIC_POSITIONS")
    assert card is not None and card.option == "alat"
    assert card.lines[0].endswith("0   0   0")  # if_pos kept
    assert editor.card("CELL_PARAMETERS") is None
    original = SI_IN.read_text()
    for line in (
        "    prefix='silicon',",
        " Si  28.086  Si.pz-rrkj.UPF",
        "8 8 8 0 0 0",
        "    ecutwfc = 25      ",
    ):
        assert line in original and line in result.text


def test_scf_of_a_vc_relax_writes_the_final_cell():
    result = scf_of(VC_OUT, VC_IN)
    editor = assert_scf(result.text, 34)
    assert editor.get("system", "ibrav") == "0"
    assert not [key for key in editor.keys("system") if key.startswith("celldm")]
    card = editor.card("CELL_PARAMETERS")
    assert card is not None and card.option == "angstrom"
    assert card.lines[0] == "5.189525088  -0.000422155   0.002783029"
    assert result.text.count("CELL_PARAMETERS") == 1
    assert (
        editor.get("control", "prefix") == "kaolinite"
        and editor.get("control", "outdir") == "./tmp"
    )
    assert result.warnings[0] == same_save_dir("kaolinite", "./tmp/kaolinite.save")
    assert result.warnings[-1] == VC_RELAX_CELL


def test_scf_of_a_slab_removes_every_ions_and_cell_namelist():
    result = scf_of(SLAB_OUT, SLAB_IN)
    assert_scf(result.text, 34)
    assert "&IONS" not in result.text and "&ions" not in result.text and "&CELL" not in result.text
    assert result.text.count("CELL_PARAMETERS") == 1  # the input's, untouched
    assert "-5.49164572447609 -0.62874356621983 20.39048531806534" in result.text


def test_vc_relax_with_an_alat_cell_keeps_celldm1_as_printed():
    text = "\n".join([
        "&control", "  calculation = 'vc-relax'", "/",
        "&system", "  ibrav = 2, celldm(1) = 10.2, celldm(3) = 1.0, nat = 1, ntyp = 1, A = 5.4", "/",
        "&ions", "/", "&cell", "/",
        "ATOMIC_SPECIES", "Si 28.086 Si.UPF", "ATOMIC_POSITIONS alat", "Si 0 0 0", "K_POINTS gamma", "",
    ])  # fmt: skip
    block = [
        "Begin final coordinates",
        "CELL_PARAMETERS (alat= 10.16863713)",
        "  -0.5 0.0 0.5",
        "   0.0 0.5 0.5",
        "  -0.5 0.5 0.0",
        "ATOMIC_POSITIONS (alat)",
        "Si 0.0 0.0 0.0",
        "End final coordinates",
    ]
    final = parse_final_structure(block)
    assert final is not None
    result = scf_from_relax(final, text)
    editor = assert_scf(result.text, 1)
    assert editor.get("system", "ibrav") == "0"
    assert editor.get("system", "celldm(1)") == "10.16863713"
    assert editor.get("system", "celldm(3)") is None and editor.get("system", "a") is None
    card = editor.card("CELL_PARAMETERS")
    assert card is not None and card.option == "alat"
    assert result.warnings == (
        same_save_dir("pwscf", "./pwscf.save"),  # neither prefix nor outdir: pw.x's defaults
        "ibrav = 2 trocado por 0: a célula final vai em CELL_PARAMETERS",
        VC_RELAX_CELL,
    )
    angstrom = parse_final_structure(
        [line.replace("(alat= 10.16863713)", "(angstrom)") for line in block]
    )
    assert angstrom is not None
    with pytest.raises(ScfError, match="Posições em alat"):
        scf_from_relax(angstrom, text)


@pytest.mark.parametrize(
    ("outdir", "save"),
    [("'/scratch/run/'", "/scratch/run/si.save"), ("'/'", "/si.save"), ("'out'", "out/si.save")],
)
def test_the_warning_names_the_save_dir_the_scf_would_overwrite(outdir, save):
    final = read_final_structure(SI_OUT)
    assert final is not None
    text = SI_IN.read_text().replace("prefix='silicon'", "prefix='si'")
    text = text.replace("outdir='./tmp'", f"outdir={outdir}")
    assert f"outdir={outdir}" in text
    assert scf_from_relax(final, text).warnings[0] == same_save_dir("si", save)


def test_nat_that_disagrees_and_an_input_that_is_no_relax_are_errors():
    final = read_final_structure(SI_OUT)
    assert final is not None
    with pytest.raises(ScfError, match="nat = 3 no input, 2 posições na saída"):
        scf_from_relax(final, SI_IN.read_text().replace("nat=  2", "nat=  3"))
    scf = SI_IN.read_text().replace("'relax'", "'scf'")
    with pytest.raises(
        ScfError, match=r"si.rel.in não é um relax/vc-relax \(calculation = 'scf'\)"
    ):
        scf_from_relax(final, scf, "si.rel.in")


def test_scf_name():
    assert scf_name("si") == "scf_convergido_si.in"
    assert scf_name(None) == "scf_convergido_pwscf.in"
    assert scf_name(" a/b ") == "scf_convergido_a_b.in"


# -- R4.1, R4.3: the input and the file -----------------------------------------------------------
def test_pair_input_by_name_then_by_role(tmp_path):
    si = copy_fixture("si_relax", tmp_path)
    assert pair_input(si / "si.rel.out", None) == si / "si.rel.in"
    supercell = copy_fixture("kao_supercell_relax", tmp_path)  # the stems differ
    output = supercell / "relax-kaolinite-slab-001-2x1x.out"
    assert pair_input(output, None) is None
    results = detect_folder(supercell)
    assert pair_input(output, results) == supercell / "relax-kaolinite-slab-001-2x1x1.in"
    other = supercell / "other.out"
    shutil.copy(output, other)  # two outputs: only the one of the relax result pairs by role
    results = detect_folder(supercell)
    chosen = next(r.file("relax_out") for r in results if r.file("relax_out") is not None)
    assert pair_input(chosen, results) == supercell / "relax-kaolinite-slab-001-2x1x1.in"
    assert pair_input(other if chosen == output else output, results) is None
    (si / "si.rel.in").unlink()
    assert pair_input(si / "si.rel.out", detect_folder(si)) is None


def test_pair_problem():
    assert pair_problem(None, None) == NO_INPUT
    cache = SniffCache()
    assert pair_problem(SI_IN, cache.sniff(SI_IN)) == ""
    assert pair_problem(SI_IN, None) == ""
    scf_in = FIXTURES / "al_bands/al.scf.in"
    sniff = cache.sniff(scf_in)
    assert sniff.kind is FileKind.PW_IN
    assert pair_problem(scf_in, sniff) == "al.scf.in não é um relax/vc-relax (calculation = 'scf')"


def test_generate_scf_file_never_overwrites(tmp_path):
    folder = copy_fixture("kao_vc_relax", tmp_path)
    output = folder / "vc-relax.out"
    first = generate_scf_file(output, None)
    assert first.path == folder / "scf_convergido_kaolinite.in"
    assert parse_input(first.path.read_text()).calculation == "scf"
    second = generate_scf_file(output, None)
    assert second.path == folder / "scf_convergido_kaolinite_1.in"
    assert second.path.read_bytes() == first.path.read_bytes()


def test_generate_scf_file_failures_write_nothing(tmp_path):
    folder = copy_fixture("si_relax", tmp_path)
    output = folder / "si.rel.out"
    (folder / "si.rel.in").write_text(SI_IN.read_text().replace("nat=  2", "nat=  3"))
    with pytest.raises(ScfError, match="nat = 3"):
        generate_scf_file(output, None)
    (folder / "si.rel.in").write_text(SI_IN.read_text())
    output.write_text(SI_OUT.read_text().replace("Begin final coordinates", "Begin"))
    with pytest.raises(ScfError, match="bloco final"):
        generate_scf_file(output, None)
    (folder / "si.rel.in").unlink()
    with pytest.raises(ScfError, match=NO_INPUT):
        generate_scf_file(output, None)
    assert sorted(p.name for p in folder.iterdir()) == ["si.rel.out"]
