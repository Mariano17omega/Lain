"""Spec 28: the naming standard, the self-contained folder and the "padrao" / "avancado" modes."""

import pytest

from qe_studio.core.calc_create.edits import put_text
from qe_studio.core.calc_create.types import REGISTRY, by_id, visible_fields
from qe_studio.core.calc_create.types.bandas import channel_filband
from qe_studio.core.calc_create.types.files import output_name, unit_stem
from qe_studio.core.calc_create.unit import PSEUDO_DIR_NOTE, unit_notes
from qe_studio.core.config import JobsConfig
from qe_studio.core.qe.input_edit import InputEditor

from calc_helpers import AL_PATH, AL_SCF, JOBS, al, from_text, ni, runs

AL_TEXT = AL_SCF.read_text()
PSEUDO = "/Cluster/Pseudo"  # case matters in a path


def plan(type_id, scf=None, mode="padrao", jobs=JOBS, **values):
    return by_id(type_id).plan(scf or al(), {"kpath": AL_PATH, **values}, jobs, mode)


def text_of(result, key: str) -> str:
    planned = result.by_key(key)
    assert planned is not None, key
    return planned.text


def shown(type_id, scf, mode="padrao") -> list[str]:
    calc_type = by_id(type_id)
    return [f.id for f in visible_fields(calc_type.fields(scf, JOBS), mode)]


# -- R1: names -------------------------------------------------------------------------------------
def test_the_standard_names_follow_the_prefix():
    scf = from_text(AL_TEXT.replace("prefix='al'", "prefix='Fe teste'"))
    result = plan("pdos", scf, nbnd=8)
    assert [f.name for f in result.files] == [
        "pdos.qsub",
        "scf_Fe_teste.in",
        "nscf_Fe_teste.in",
        "projwfc.in",
    ]
    no_prefix = from_text(AL_TEXT.replace("    prefix='al',\n", ""))
    assert [f.name for f in plan("relax", no_prefix).files] == ["relax.qsub", "relax_pwscf.in"]
    assert unit_stem(" ") == "pwscf" and output_name("scf_Al.in") == "scf_Al.out"


def test_scripts_run_the_standard_names():
    assert runs(plan("scf").files[0].text) == ["scf_al.in"]
    script = plan("pdos").files[0].text
    assert '-i "scf_al.in" > "scf_al.out"' in script
    assert '-i "nscf_al.in" > "nscf_al.out"' in script
    assert '-i "projwfc.in" > "projwfc.out"' in script


# -- R2: the self-contained folder -----------------------------------------------------------------
def test_pseudo_dir_from_the_config():
    jobs = JobsConfig(pseudo_dir=PSEUDO)
    for type_id in ("scf", "relax", "vc-relax", "bandas", "pdos"):
        result = plan(type_id, jobs=jobs)
        assert PSEUDO_DIR_NOTE not in result.notes
        for planned in result.files:
            if planned.kind == "pw_input":
                editor = InputEditor.from_text(planned.text)
                assert editor.get("control", "pseudo_dir") == PSEUDO, planned.name
                assert editor.get("control", "outdir") == "./tmp/"
    copy = text_of(plan("bandas", jobs=jobs), "scf")
    before = [line for line in AL_TEXT.splitlines() if line not in copy.splitlines()]
    assert before == ["    pseudo_dir = '/home/m/Documentos/pseudo',", "    outdir='./tmp' "]
    # Without one, the SCF's stays and a note says how to fix it.
    result = plan("scf")
    assert PSEUDO_DIR_NOTE in result.notes
    assert "pseudo_dir = '/home/m/Documentos/pseudo'" in text_of(result, "scf")


def test_a_missing_pseudo_dir_is_added():
    text = AL_TEXT.replace("    pseudo_dir = '/home/m/Documentos/pseudo',\n", "")
    copy = text_of(plan("scf", from_text(text), jobs=JobsConfig(pseudo_dir=PSEUDO)), "scf")
    assert InputEditor.from_text(copy).get("control", "pseudo_dir") == PSEUDO


def test_put_text_compares_with_case():
    editor = InputEditor.from_text("&control\n  pseudo_dir = '/cluster/pseudo'\n/\n")
    assert put_text(editor, "control", "pseudo_dir", PSEUDO)
    assert editor.get("control", "pseudo_dir") == PSEUDO
    assert not put_text(editor, "control", "pseudo_dir", PSEUDO)
    assert put_text(editor, "control", "outdir", "it's")
    assert "outdir = 'it''s'" in editor.text()


def notes_of(text: str, jobs=JOBS) -> list[str]:
    return unit_notes(from_text(text), jobs)


def test_paths_the_folder_does_not_control_are_notes():
    assert notes_of(AL_TEXT) == [PSEUDO_DIR_NOTE]
    climbs = AL_TEXT.replace("'/home/m/Documentos/pseudo'", "'../pseudo'")
    assert "O SCF usa um caminho fora da pasta: pseudo_dir = ../pseudo" in notes_of(climbs)
    relative = AL_TEXT.replace("'/home/m/Documentos/pseudo'", "'pseudo'")
    assert any("pseudo_dir relativo (pseudo)" in note for note in notes_of(relative))
    missing = AL_TEXT.replace("    pseudo_dir = '/home/m/Documentos/pseudo',\n", "")
    assert any("$ESPRESSO_PSEUDO" in note for note in notes_of(missing))
    assert notes_of(climbs, JobsConfig(pseudo_dir=PSEUDO)) == []  # the config's replaces it
    wfc = AL_TEXT.replace("outdir='./tmp' ", "outdir='./tmp', wfcdir='/scratch/wfc'")
    assert "O SCF usa um caminho fora da pasta: wfcdir = /scratch/wfc" in notes_of(wfc)
    inside = AL_TEXT.replace("outdir='./tmp' ", "outdir='./tmp', wfcdir='./wfc'")
    assert notes_of(inside) == [PSEUDO_DIR_NOTE]
    absolute_outdir = AL_TEXT.replace("outdir='./tmp'", "outdir='/scratch/m'")
    assert notes_of(absolute_outdir) == [PSEUDO_DIR_NOTE]  # the folder's own './tmp/' replaces it
    result = plan("scf", from_text(wfc))
    assert not result.errors and any("wfcdir" in note for note in result.notes)  # never blocks


# -- R3: modes -------------------------------------------------------------------------------------
def test_fields_of_the_standard_mode():
    without_output = from_text(AL_TEXT)  # no al.scf.out next to it: no nbnd to start from
    assert {t.id: shown(t.id, al()) for t in REGISTRY} == {
        "scf": [],
        "relax": [],
        "vc-relax": [],
        "bandas": ["kpath"],
        "pdos": ["e_min", "e_max"],
    }
    assert shown("bandas", without_output) == ["nbnd", "kpath"]  # required, no default
    assert shown("pdos", without_output) == ["nbnd", "e_min", "e_max"]
    gamma = from_text(AL_TEXT.replace("K_POINTS automatic\n10 10 10 0 0 0", "K_POINTS gamma"))
    assert "kmesh" in shown("pdos", gamma)  # no mesh to take from the SCF
    for calc_type in REGISTRY:
        fields = calc_type.fields(al(), JOBS)
        assert visible_fields(fields, "avancado") == fields


@pytest.mark.parametrize(
    "type_id, values",
    [
        ("scf", {"kmesh": "2 2 2 0 0 0", "np": 8, "nk": 2, "job_name": "x"}),
        ("relax", {"nstep": 7, "forc_conv_thr": 0.5, "ion_dynamics": "damp"}),
        ("vc-relax", {"press": 99.0, "cell_dynamics": "damp-w"}),
        ("bandas", {"nbnd": 99, "filband": "outro.dat"}),
        ("pdos", {"nbnd": 99, "kmesh": "2 2 2 0 0 0", "delta_e": 0.5, "degauss": 0.3}),
    ],
)
def test_the_standard_mode_ignores_hidden_fields(type_id, values):
    standard = plan(type_id)
    edited = plan(type_id, **values)
    assert [f.text for f in edited.files] == [f.text for f in standard.files]
    assert not edited.errors
    advanced = plan(type_id, mode="avancado", **values)
    assert [f.text for f in advanced.files] != [f.text for f in standard.files]
    bad = {key: "?" for key in values if key != "ion_dynamics"}
    assert not plan(type_id, **bad).errors  # a hidden field can hold anything
    assert plan(type_id, mode="avancado", **bad).errors


def test_standard_bands():
    result = plan("bandas")
    assert not result.errors
    bands_x = InputEditor.from_text(text_of(result, "bands_pp"))
    assert [bands_x.get("bands", key) for key in ("prefix", "outdir", "filband")] == [
        "al",
        "./tmp/",
        "./band",
    ]
    bands = InputEditor.from_text(text_of(result, "bands"))
    assert bands.get("control", "calculation") == "bands"
    assert bands.get("system", "nbnd") == "8"  # 1.2 × the 6 states of al.scf.out
    assert bands.card("K_POINTS").option == "crystal_b"
    spin = plan("bandas", ni())
    for key, filband in (("bands_pp_up", "./band_up"), ("bands_pp_dw", "./band_dw")):
        assert InputEditor.from_text(text_of(spin, key)).get("bands", "filband") == filband


def test_channel_filband():
    assert channel_filband("./band", "up") == "./band_up"
    assert channel_filband("bands.dat", "dw") == "bands_dw.dat"
    assert channel_filband("out/a.b.c", "up") == "out/a.b_up.c"
    assert channel_filband(".x", "up") == ".x_up"


def test_standard_pdos():
    result = plan("pdos", e_min=-10, e_max=5)
    assert not result.errors
    projwfc = InputEditor.from_text(text_of(result, "projwfc"))
    keys = ("prefix", "outdir", "DeltaE", "filpdos", "Emin", "Emax", "ngauss", "degauss")
    assert [projwfc.get("projwfc", key) for key in keys] == [
        "al",
        "./tmp/",
        "0.01",
        "al.dat",
        "-10.0",
        "5.0",
        "0",
        "0.000735",
    ]
    nscf = InputEditor.from_text(text_of(result, "nscf"))
    card = nscf.card("K_POINTS")
    assert card is not None and card.lines[0] == "10 10 10 0 0 0"  # the SCF's
    tetrahedra = AL_TEXT.replace(
        "    occupations= 'smearing',\n    smearing= 'gaussian',\n    degauss= 0.01\n",
        "    occupations= 'tetrahedra'\n",
    )
    no_broadening = InputEditor.from_text(
        text_of(plan("pdos", from_text(tetrahedra), nbnd=8), "projwfc")
    )
    assert no_broadening.get("projwfc", "ngauss") is None
    assert no_broadening.get("projwfc", "degauss") is None


def test_degauss_default_is_the_same_in_both_modes():
    fields = {f.id: f.default for f in by_id("pdos").fields(al(), JOBS)}
    assert fields["degauss"] == 0.000735
    advanced = InputEditor.from_text(text_of(plan("pdos", mode="avancado"), "projwfc"))
    assert advanced.get("projwfc", "degauss") == "0.000735"
    filband = {f.id: f.default for f in by_id("bandas").fields(al(), JOBS)}["filband"]
    assert filband == "./band"


# -- R4: file names in the "avancado" mode ---------------------------------------------------------
def test_a_name_field_per_input_first_in_its_tab():
    fields = by_id("bandas").fields(ni(), JOBS)
    names = [f for f in fields if f.id.startswith("name:")]
    assert [(f.group, f.default) for f in names] == [
        ("scf", "scf_ni.in"),
        ("bands", "bands.in"),
        ("bands_pp_up", "bands_pp_up.in"),
        ("bands_pp_dw", "bands_pp_dw.in"),
    ]
    for name in names:
        assert not name.standard and name.label == "Nome do arquivo"
        assert next(f for f in fields if f.group == name.group) is name


def test_a_new_name_renames_the_file_its_output_and_its_tab():
    result = plan("pdos", mode="avancado", **{"name:scf": "scf_teste.in", "name:projwfc": "p.in"})
    assert not result.errors
    assert [f.name for f in result.files] == ["pdos.qsub", "scf_teste.in", "nscf_al.in", "p.in"]
    assert result.by_key("scf").tab_label == "SCF (scf_teste.in)"
    assert result.by_key("projwfc").tab_label == "p.in"
    script = result.files[0].text
    assert '-i "scf_teste.in" > "scf_teste.out"' in script
    assert '-i "p.in" > "p.out"' in script
    assert "mv *pdos_atm#* orbitals/" in script
    # The "padrao" mode keeps the standard names.
    standard = plan("pdos", **{"name:scf": "scf_teste.in"})
    assert standard.by_key("scf").name == "scf_al.in"


@pytest.mark.parametrize(
    "name, problem",
    [
        ("scf", "use <nome>.in"),
        (".in", "use <nome>.in"),
        ("a/b.in", "só letras sem acento"),
        ("açaí.in", "só letras sem acento"),
        ("bands.in", "Nome de arquivo repetido: bands.in"),
    ],
)
def test_bad_names_block_create(name, problem):
    result = plan("bandas", mode="avancado", **{"name:scf": name})
    assert any(problem in error for error in result.errors), result.errors
    assert problem in result.problems["name:scf"]
    assert by_id("bandas").plan(al(), {"kpath": AL_PATH}, JOBS, "avancado").problems == {}
