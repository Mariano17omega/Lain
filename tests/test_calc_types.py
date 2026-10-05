"""Spec 25 R3, R4: the calculation types, their fields and the inputs derived from the SCF."""

import difflib

import pytest

from qe_studio.core.calc_create.kpath import KMesh, KPath, KPoint
from qe_studio.core.calc_create.types import REGISTRY, by_id
from qe_studio.core.calc_create.types.pdos import NO_BROADENING_NOTE
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint

from calc_helpers import AL_PATH, AL_SCF, JOBS, SI_SCF, al, from_text, ni, runs

FILES = {
    "scf": ["scf.qsub", "scf.in"],
    "relax": ["relax.qsub", "relax.in"],
    "vc-relax": ["vc-relax.qsub", "vc-relax.in"],
    "bandas": ["bandas.qsub", "scf.in", "bands.in", "bands_pp.in"],
    "pdos": ["pdos.qsub", "scf.in", "nscf.in", "projwfc.in"],
}


def plan(type_id, scf=None, **values):
    return by_id(type_id).plan(scf or al(), {"kpath": AL_PATH, **values}, JOBS)


def changed(before: str, after: str) -> tuple[list[str], list[str]]:
    """Lines removed from and added to ``before``."""
    removed, added = [], []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith("- "):
            removed.append(line[2:])
        elif line.startswith("+ "):
            added.append(line[2:])
    return removed, added


def test_registry():
    assert [t.id for t in REGISTRY] == ["scf", "relax", "vc-relax", "bandas", "pdos"]
    assert [t.label for t in REGISTRY] == ["SCF", "Relax", "VC-Relax", "Bandas", "PDOS"]
    assert [t.folder_prefix for t in REGISTRY] == ["scf", "relax", "vc-relax", "bandas", "pdos"]
    with pytest.raises(KeyError):
        by_id("dos")


@pytest.mark.parametrize("type_id", FILES)
def test_files_in_tab_order_and_fields_in_their_tabs(type_id):
    result = plan(type_id)
    assert not result.errors, result.errors
    assert [f.name for f in result.files] == FILES[type_id]
    assert result.files[0].kind == "qsub" and result.files[0].tab_label.startswith("Script (")
    names = {f.name for f in result.files}
    for field in by_id(type_id).fields(al(), JOBS):
        assert field.group in names, field


def test_tab_labels():
    assert [f.tab_label for f in plan("pdos").files] == [
        "Script (pdos.qsub)",
        "SCF (scf.in)",
        "NSCF (nscf.in)",
        "projwfc.in",
    ]
    assert [f.tab_label for f in plan("bandas").files] == [
        "Script (bandas.qsub)",
        "SCF (scf.in)",
        "Bandas (bands.in)",
        "bands_pp.in",
    ]


@pytest.mark.parametrize("type_id", FILES)
def test_inputs_lint_clean_with_the_scf_prefix_and_outdir(type_id):
    for scf in (al(), ni(), from_text(SI_SCF.read_text())):
        for planned in plan(type_id, scf).files:
            if not planned.name.endswith(".in"):
                continue
            errors = [i for i in lint(planned.text).issues if i.severity == "error"]
            assert not errors, (planned.name, errors)
            editor = InputEditor.from_text(planned.text)
            namelist = {"pw_input": "control"}.get(planned.kind) or (
                "bands" if planned.name.startswith("bands_pp") else "projwfc"
            )
            assert editor.get(namelist, "prefix") == scf.prefix
            assert editor.get(namelist, "outdir") == scf.outdir


def test_scf_copies_are_the_scf_byte_for_byte():
    text = AL_SCF.read_text()
    for type_id in ("scf", "bandas", "pdos"):
        assert plan(type_id).file("scf.in").text == text


def test_scf_mesh_field():
    gamma = AL_SCF.read_text().replace("K_POINTS automatic\n10 10 10 0 0 0", "K_POINTS gamma")
    scf = from_text(gamma)
    field = next(f for f in by_id("scf").fields(scf, JOBS) if f.id == "kmesh")
    assert field.default is None and not field.required  # empty keeps the SCF's card
    assert plan("scf", scf).file("scf.in").text == gamma
    denser = plan("scf", kmesh="12 12 12 1 1 1").file("scf.in").text
    assert changed(AL_SCF.read_text(), denser) == (["10 10 10 0 0 0"], ["12 12 12 1 1 1"])


def test_relax_changes_only_its_keys():
    removed, added = changed(AL_SCF.read_text(), plan("relax").file("relax.in").text)
    assert removed == ["    calculation = 'scf',"]
    assert added == [
        "    calculation = 'relax',",
        "    nstep = 50",
        "    forc_conv_thr = 0.001",
        "&ions",
        "  ion_dynamics = 'bfgs'",
        "/",
    ]


def test_vc_relax_adds_cell():
    text = plan("vc-relax", press=10, cell_dynamics="damp-w").file("vc-relax.in").text
    editor = InputEditor.from_text(text)
    assert editor.get("control", "calculation") == "vc-relax"
    assert (editor.get("cell", "cell_dynamics"), editor.get("cell", "press")) == ("damp-w", "10.0")
    assert editor.get("ions", "ion_dynamics") == "bfgs"
    assert not InputEditor.from_text(plan("relax").file("relax.in").text).has_namelist("cell")


def test_relax_keeps_what_the_scf_already_has():
    text = (
        AL_SCF.read_text()
        .replace(
            "&electrons\n    conv_thr =  1.0d-8\n/\n",
            "&electrons\n    conv_thr =  1.0d-8\n/\n&IONS\n  ion_dynamics='damp'\n/\n",
        )
        .replace("outdir='./tmp' ", "outdir='./tmp', nstep=200")
    )
    scf = from_text(text)
    fields = {f.id: f.default for f in by_id("relax").fields(scf, JOBS)}
    assert (fields["nstep"], fields["ion_dynamics"]) == (200, "damp")
    removed, added = changed(text, plan("relax", scf).file("relax.in").text)
    assert removed == ["    calculation = 'scf',"]
    assert added == ["    calculation = 'relax',", "    forc_conv_thr = 0.001"]


def test_bands_input():
    text = plan("bandas", nbnd=12).file("bands.in").text
    removed, added = changed(AL_SCF.read_text(), text)
    assert removed == ["    calculation = 'scf',", "K_POINTS automatic", "10 10 10 0 0 0"]
    assert added[:2] == ["    calculation = 'bands',", "    nbnd = 12"]
    assert added[2:4] == ["K_POINTS crystal_b", "5"]
    assert added[4].endswith("20  ! L") and added[-1].endswith("1  ! Gamma")


def test_bands_swaps_tetrahedra_for_smearing():
    text = AL_SCF.read_text().replace(
        "    occupations= 'smearing',\n    smearing= 'gaussian',\n    degauss= 0.01\n",
        "    occupations= 'tetrahedra_opt'\n",
    )
    result = plan("bandas", from_text(text))
    editor = InputEditor.from_text(result.file("bands.in").text)
    assert editor.get("system", "occupations") == "smearing"
    assert (editor.get("system", "smearing"), editor.get("system", "degauss")) == (
        "gaussian",
        "0.01",
    )
    assert any("tetrahedra_opt" in note for note in result.notes)
    pdos = InputEditor.from_text(plan("pdos", from_text(text)).file("nscf.in").text)
    assert pdos.get("system", "occupations") == "tetrahedra_opt"  # the NSCF keeps tetrahedra


def test_spin_bands_run_bands_x_per_channel():
    result = plan("bandas", ni())
    assert [f.name for f in result.files] == [
        "bandas.qsub",
        "scf.in",
        "bands.in",
        "bands_pp_up.in",
        "bands_pp_dw.in",
    ]
    for name, filband, component in (
        ("bands_pp_up.in", "bands_up.dat", "1"),
        ("bands_pp_dw.in", "bands_dw.dat", "2"),
    ):
        editor = InputEditor.from_text(result.file(name).text)
        assert editor.get("bands", "filband") == filband
        assert editor.get("bands", "spin_component") == component
    assert runs(result.files[0].text)[2:] == ["bands_pp_up.in", "bands_pp_dw.in"]
    assert any("nspin = 2" in note for note in result.notes)


def test_pdos_inputs():
    result = plan("pdos", nbnd=20, kmesh=KMesh((20, 20, 20)), occupations="tetrahedra")
    removed, added = changed(AL_SCF.read_text(), result.file("nscf.in").text)
    assert removed == [
        "    calculation = 'scf',",
        "    occupations= 'smearing',",
        "10 10 10 0 0 0",
    ]
    assert added == [
        "    calculation = 'nscf',",
        "    occupations= 'tetrahedra',",
        "    nbnd = 20",
        "20 20 20 0 0 0",
    ]
    projwfc = InputEditor.from_text(result.file("projwfc.in").text)
    assert projwfc.get("projwfc", "filpdos") == "al.dat"
    assert [projwfc.get("projwfc", k) for k in ("DeltaE", "Emin", "Emax", "ngauss", "degauss")] == [
        "0.01",
        "-25.0",
        "25.0",
        None,  # tetrahedra: no broadening in projwfc.in
        None,
    ]
    assert NO_BROADENING_NOTE in result.notes


@pytest.mark.parametrize(
    "occupations, broadening",
    [
        ("smearing", True),
        ("fixed", True),
        ("tetrahedra", False),
        ("tetrahedra_opt", False),
        ("tetrahedra_lin", False),
    ],
)
def test_pdos_broadening_follows_the_occupations(occupations, broadening):
    result = plan("pdos", occupations=occupations, ngauss=1, degauss=0.02)
    projwfc = InputEditor.from_text(result.file("projwfc.in").text)
    assert projwfc.get("projwfc", "ngauss") == ("1" if broadening else None)
    assert projwfc.get("projwfc", "degauss") == ("0.02" if broadening else None)
    assert [projwfc.get("projwfc", k) for k in ("DeltaE", "Emin", "Emax")] == [
        "0.01",
        "-25.0",
        "25.0",
    ]
    assert (NO_BROADENING_NOTE in result.notes) is not broadening


def test_pdos_tooltips_explain_occupations_and_the_energy_window():
    fields = {f.id: f.tooltip for f in by_id("pdos").fields(al(), JOBS)}
    for key in ("occupations", "degauss", "ngauss"):
        assert "tetraedros" in fields[key]
    assert "Ry" in fields["degauss"] and "ignorado com tetraedros" in fields["ngauss"]
    for key in ("nbnd", "e_max"):
        assert "energias absolutas" in fields[key] and "a DOS é zero" in fields[key]
    bands = {f.id: f.tooltip for f in by_id("bandas").fields(al(), JOBS)}
    assert "energias absolutas" not in bands["nbnd"]  # the hint is the PDOS's


def test_pdos_defaults():
    fields = {f.id: f for f in by_id("pdos").fields(al(), JOBS)}
    assert fields["kmesh"].default == KMesh((10, 10, 10)) and fields["kmesh"].required
    assert fields["occupations"].default == "smearing"
    assert fields["nbnd"].default == 8 and fields["nbnd"].required  # 1.2 × 6 states of al.scf.out
    si = {f.id: f.default for f in by_id("pdos").fields(from_text(SI_SCF.read_text()), JOBS)}
    assert si["nbnd"] == 16 and si["occupations"] == "fixed"
    nscf = InputEditor.from_text(plan("pdos", from_text(SI_SCF.read_text())).file("nscf.in").text)
    assert nscf.get("system", "occupations") is None  # "fixed" is pw.x's default: no line added


def test_pdos_smearing_gets_its_width():
    text = SI_SCF.read_text()
    result = plan("pdos", from_text(text), occupations="smearing")
    editor = InputEditor.from_text(result.file("nscf.in").text)
    assert (editor.get("system", "smearing"), editor.get("system", "degauss")) == (
        "gaussian",
        "0.01",
    )


def test_script_fields_and_pool_warnings():
    fields = {f.id: f.default for f in by_id("bandas").fields(al(), JOBS)}
    assert fields["job_name"] == "al" and fields["np"] == 64 and fields["nk"] == 4
    assert {f.id: f.default for f in by_id("relax").fields(al(), JOBS)}["nk"] == 8
    result = plan("pdos", np=10, nk=4)
    assert not result.errors
    assert any("NP = 10 não é múltiplo de nk = 4" in note for note in result.notes)
    assert any("maior que NP" in note for note in plan("pdos", np=4, nk=8).notes)
    long = plan("scf", job_name="meu cálculo muito longo")
    assert '#$ -N "meu_c_lculo_mui"' in long.files[0].text
    assert any("ajustado" in note for note in long.notes)


def test_missing_and_invalid_values_are_errors():
    no_path = by_id("bandas").plan(al(), {}, JOBS)
    assert "Preencha Caminho de alta simetria" in no_path.errors
    assert "K_POINTS crystal_b\n0\n" in no_path.file("bands.in").text  # the preview still renders
    one_point = plan("bandas", kpath=KPath((KPoint("Gamma", (0, 0, 0)),)))
    assert "Defina ao menos 2 pontos do caminho" in one_point.errors
    no_bands = plan("bandas", from_text(AL_SCF.read_text()))  # no output next to it
    assert "Preencha Número de bandas (nbnd)" in no_bands.errors
    assert any("Valor inválido em Núcleos (NP)" in e for e in plan("scf", np="muitos").errors)
    assert any("rede de k-points" in e for e in plan("scf", kmesh=KMesh((0, 4, 4))).errors)
    assert "Emin deve ser menor que Emax" in plan("pdos", e_min=5, e_max=-5).errors


def test_an_empty_value_falls_back_to_the_default():
    assert (
        plan("pdos", nbnd="", kmesh=" ").file("nscf.in").text == plan("pdos").file("nscf.in").text
    )


def test_unreadable_structure_is_a_note_of_bands():
    text = AL_SCF.read_text().replace("    celldm(1)=  7.630781648,\n", "")
    result = plan("bandas", from_text(text), nbnd=8)
    assert not result.errors
    assert any("Estrutura do SCF não lida" in note for note in result.notes)


def test_scf_warnings_reach_the_notes():
    text = AL_SCF.read_text().replace("outdir='./tmp'", "outdir='/scratch/m'")
    assert any("outdir é absoluto" in note for note in plan("scf", from_text(text)).notes)
