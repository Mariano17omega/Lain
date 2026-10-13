"""Spec 42 R4, R5: the "Molécula na superfície" type of "Criar cálculo": the plan of the user's scripts
(stage 3: the 2×1×1 (001) relaxed, H3CHg, mono and bidentate with the anchor's H removed), the species
and namelists of the two SCFs, its fields, errors and ``geracao.md``."""

from __future__ import annotations

import time

import pytest

from qe_studio.core.calc_create.kpath import KMesh
from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.merge import NBND_NOTE, merge_species
from qe_studio.core.calc_create.surface.report import REPORT_KEY, REPORT_NAME
from qe_studio.core.calc_create.types import by_id, visible_fields
from qe_studio.core.calc_create.writer import create_folder
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.qe.pw_input import fortran_float

from calc_helpers import JOBS, from_text
from surface_helpers import (
    ADSORBED,
    MOLECULE,
    SUPERCELL_001,
    fixed_of,
    golden,
    golden_model,
    model_from_plan,
    read,
    same_atoms,
)

ADSORPTION = by_id("adsorption")
INPUT = "relax_kaolinite-slab-001-2x1x1.in"
VDW_NOTE = "vdw_corr: superfície 'grimme-d3', molécula 'grimme-d2'; vale o da superfície"


def plan(scf: ScfInfo | None = None, window: str = "avancado", **values):
    """``window``: the window's mode; ``values`` the fields' (``mode`` is the coordination)."""
    values.setdefault("molecule", read(MOLECULE))
    return ADSORPTION.plan(scf or read(SUPERCELL_001), values, JOBS, window)  # type: ignore[arg-type]


def mono(site=43, **values):
    return plan(site=(site,), remove_h=True, **values)


def input_text(result) -> str:
    return result.by_key("relax").text


def editor_of(result) -> InputEditor:
    return InputEditor.from_text(input_text(result))


def report(result) -> str:
    return result.by_key(REPORT_KEY).text


def number(editor: InputEditor, namelist: str, key: str) -> float | None:
    text = editor.get(namelist, key)
    return fortran_float(text) if text is not None else None


@pytest.mark.parametrize("case", list(ADSORBED))
@pytest.mark.parametrize("rule", ["", "espécies e vizinhos"])
def test_the_plan_reproduces_the_scripts(case, rule):
    """28 of the surface atoms fixed both from the SCF's flags (the default) and by the script's rule."""
    sites = ADSORBED[case]
    values = {"fix_rule": rule} if rule else {}
    mode = "bidentado" if len(sites) == 2 else "monodentado"
    result = plan(site=sites, remove_h=True, mode=mode, **values)
    assert result.errors == ()
    assert [f.name for f in result.files] == ["adsorption.qsub", INPUT, REPORT_NAME]
    text = input_text(result)
    data = golden(case)
    model = model_from_plan(text)
    assert same_atoms(model, golden_model(case))
    assert fixed_of(model) == data["fixed"] and len(data["fixed"]) == 28
    editor = InputEditor.from_text(text)
    assert KMesh.parse(editor.card("K_POINTS").lines[0]) == KMesh((3, 4, 1))
    assert editor.get("control", "calculation") == data["calculation"] == "relax"
    assert number(editor, "control", "etot_conv_thr") == 1e-4
    assert number(editor, "control", "forc_conv_thr") == 1e-3  # the SCF's 1e-4 is not inherited
    assert number(editor, "control", "nstep") == 50
    assert editor.get("ions", "ion_dynamics") == "bfgs"
    assert editor.get("system", "nat") == str(data["n_atoms"])
    assert [i for i in lint(text).issues if i.severity == "error"] == []


def test_species_and_namelists_of_the_two_scfs():
    result = mono()
    editor = editor_of(result)
    rows = editor.card_rows("ATOMIC_SPECIES")
    assert [row.split()[0] for row in rows] == ["Al", "Si", "O", "H", "Hg", "C"]
    assert (
        rows[4] == "Hg  200.59    Hg.pbe-spn-kjpaw_psl.1.0.0.UPF"
    )  # the molecule's row as written
    assert editor.get("system", "ntyp") == "6"
    assert editor.get("system", "occupations") == "smearing"  # the molecule's: it may close the gap
    assert editor.get("system", "smearing") == "gauss"
    assert number(editor, "system", "degauss") == 0.01
    assert number(editor, "electrons", "mixing_beta") == 0.3  # the smaller of 0.4 and 0.3
    assert editor.get("system", "vdw_corr") == "grimme-d3"  # the surface's
    assert editor.get("system", "nbnd") is None
    assert editor.keys("cell") == [] and "&CELL" not in input_text(result).upper()
    assert VDW_NOTE in result.notes
    assert editor.get("control", "prefix") == "kaolinite-slab-001-2x1x1-HgCH3-O43"
    assert editor.get("control", "outdir") == "./tmp/"


def test_the_prefix_of_a_pair_is_ascending():
    result = plan(site=(50, 43), remove_h=True, mode="bidentado")
    assert editor_of(result).get("control", "prefix") == "kaolinite-slab-001-2x1x1-HgCH3-O43-O50"


def test_the_surfaces_cell_and_nbnd_go():
    """A surface SCF with ``&CELL`` and ``nbnd``: a relax of the whole system has neither."""
    text = read(SUPERCELL_001).text.replace(
        "   nat              = 68\n", "   nat              = 68\n   nbnd = 300\n"
    )
    text = text.replace("ATOMIC_SPECIES", "&CELL\n  cell_dofree = '2Dxy'\n/\nATOMIC_SPECIES", 1)
    result = mono(scf=from_text(text, "scf.in"))
    assert result.errors == ()
    editor = editor_of(result)
    assert editor.get("system", "nbnd") is None and editor.keys("cell") == []
    assert NBND_NOTE in result.notes


def test_a_species_in_both_keeps_the_surfaces_pseudo():
    merged = merge_species(
        ["O 15.99 O.upf", "H 1.008 H.pbe.UPF"], [" H 1.008 H.outro.UPF", "C 12.0 C.UPF"]
    )
    assert merged.rows == ("O 15.99 O.upf", "H 1.008 H.pbe.UPF", "C 12.0 C.UPF")
    assert merged.added == ("C",)
    assert merged.notes == ("H: vale o pseudopotencial da superfície (H.pbe.UPF)",)
    mass = merge_species(["H 1.008 H.UPF"], ["H 2.014 H.UPF"])
    assert mass.notes == ("H: vale a massa da superfície (1.008)",)


def test_cutoffs_and_pseudo_dir_differences_are_noted():
    molecule = read(MOLECULE)
    text = molecule.text.replace("ecutwfc = 90.0,", "ecutwfc = 120.0,").replace(
        "/home/seu_usuario/PSEUDO/", "/outro/PSEUDO/"
    )
    result = mono(molecule=from_text(text, "mol.in"))
    assert "ecutwfc: molécula 120 Ry, superfície 90 Ry; vale o da superfície" in result.notes
    assert "ecutrho: molécula 480 Ry, superfície 360 Ry; vale o da superfície" in result.notes
    assert (
        "pseudo_dir: superfície '/home/seu_usuario/PSEUDO/', molécula '/outro/PSEUDO/'; os "
        "pseudopotenciais de Hg, C precisam estar no da superfície"
    ) in result.notes


def test_without_the_molecule():
    result = plan(molecule=None, site=(43,))
    assert "Preencha SCF da molécula" in result.errors
    assert result.problems["molecule"] == "Preencha SCF da molécula"
    assert [f.name for f in result.files] == ["adsorption.qsub", INPUT, REPORT_NAME]
    assert "- **Estrutura não gerada**: falta o SCF da molécula" in report(result)


def test_no_atom_marked_is_the_tables_problem():
    result = plan()
    assert result.problems == {"site": "Monodentado: marque um átomo da lista (marcados: 0)"}
    assert "Estrutura não gerada" in report(result)


@pytest.mark.parametrize(
    "values, field_id, text",
    [
        (
            {"site": (41,), "remove_h": False, "ads_distance": 1.2},
            "ads_distance",
            "O âncora fica a",
        ),
        ({"site": (43,), "anchor": 9}, "anchor", "SCF da molécula: Átomo âncora 9 fora"),
        (
            {"site_from": "coordenadas", "coords_1": "0.5 0.5 0.1"},
            "coords_1",
            "As coordenadas 0,5 0,5 0,1 estão a",
        ),
        ({"mode": "bidentado", "site": (43,)}, "site", "Bidentado: marque dois átomos"),
        ({"height_window": "0"}, "height_window", "A janela da superfície deve ser maior que zero"),
    ],
)
def test_each_error_is_marked_on_its_field(values, field_id, text):
    result = plan(**values)
    assert result.problems[field_id].startswith(text), result.problems


def test_removing_the_h_of_an_o_without_one():
    """Atom 43 without its H 59 first (a bare O on top): 0 H to remove, on the field that asks."""
    scf = read(SUPERCELL_001)
    lines = scf.text.splitlines(keepends=True)
    positions = lines.index("ATOMIC_POSITIONS (crystal)\n")
    del lines[positions + 59]  # H 59
    text = "".join(lines).replace("nat              = 68", "nat              = 67")
    result = mono(scf=from_text(text, "scf.in"))
    assert result.problems["remove_h"].startswith("O 43 tem 0 H ligados")


def test_coordinates_give_the_list_s_structure():
    listed = mono()
    frac = read(SUPERCELL_001).crystal.frac[42]  # atom 43
    coords = " ".join(f"{v:.5f}" for v in frac)
    typed = plan(site_from="coordenadas", coords_1=coords, remove_h=True)
    assert typed.errors == ()
    assert input_text(typed) == input_text(listed)


def test_the_standard_mode_shows_four_fields():
    scf = read(SUPERCELL_001)
    shown = [f.id for f in visible_fields(ADSORPTION.fields(scf, JOBS), "padrao")]
    assert shown == ["molecule", "mode", "site", "remove_h"]
    tabs = {f.id: f.group for f in ADSORPTION.input_fields(scf)}
    assert tabs["molecule"] == "Molécula" and tabs["site"] == "Sítio" and tabs["kmesh"] == "relax"


def test_the_fixed_atoms_default_follows_the_scf():
    scf = read(SUPERCELL_001)
    fields = {f.id: f.default for f in ADSORPTION.input_fields(scf)}
    assert fields["fix_rule"] == "do SCF"
    bare = from_text(scf.text.replace("    0   0   0", ""), "scf.in")
    assert {f.id: f.default for f in ADSORPTION.input_fields(bare)}["fix_rule"] == "camada inferior"
    result = mono(scf=bare)
    model = model_from_plan(input_text(result))
    fixed = fixed_of(model)
    assert fixed and max(fixed) < len(model) - 5  # the molecule stays free
    assert "regra 'camada inferior'" in report(result)


def test_the_site_table_follows_its_fields():
    scf = read(SUPERCELL_001)
    site = next(f for f in ADSORPTION.input_fields(scf) if f.id == "site")
    assert site.depends_on == ("site_species", "height_window", "symprec", "bond_scale")
    assert len(site.data.rows) == 12
    assert len(ADSORPTION.field_data("site", scf, {"site_species": "O H"}).rows) == 24
    assert ADSORPTION.field_data("site", scf, {"height_window": "0.5"}).rows == ()


def test_the_report():
    text = report(plan(site=(43, 46), remove_h=True, mode="bidentado"))
    assert text.startswith(
        "# Relatório da geração\n\n- **SCF da superfície**: scf-kaolinite-slab-001-2x1x1.in\n"
    )
    lines = text.splitlines()
    for line in (
        "- **SCF da molécula**: scf-H3CHg.in: HgCH3 (Hg 1, C 1, H 3), altura 2,60 Å, âncora Hg1",
        "- **Coordenação**: bidentado (sítio pela lista de candidatos)",
        "- **H removidos**: H 59, H 62",
        "- **Átomos**: 71 (66 da superfície + 5 da molécula: Al 8, Si 8, O 36, H 17, Hg 1, C 1)",
        "- **Distâncias âncora–sítio**: Hg–O 43 2,00 Å; Hg–O 46 2,00 Å",
        "- **Vácuo acima da molécula**: 12,36 Å",
        "- **Átomos fixos**: 28/66 (Si 8, O 20), regra 'do SCF'",
        "- **k-points**: 3 4 1 0 0 0 (da superfície: a célula não muda)",
    ):
        assert line in lines, line
    anchors = next(line for line in lines if line.startswith("- **Átomos âncora**"))
    assert "O 43 (" in anchors and "; grupo A)" in anchors and "O 46 (" in anchors
    assert any(
        line.startswith("- **Posição do âncora**") and "erguido 1,08 Å" in line for line in lines
    )


def test_the_folder_is_written(tmp_path):
    created = create_folder(tmp_path, ADSORPTION, "HgCH3", mono())
    assert created.folder.name == "Adsorption_HgCH3"
    assert [p.name for p in created.files] == ["adsorption.qsub", INPUT, REPORT_NAME]
    assert "relax_kaolinite-slab-001-2x1x1.in" in (created.folder / "adsorption.qsub").read_text()


@pytest.mark.perf
def test_the_plan_is_fast_once_cached():
    mono()  # spglib, the reads and the templates once
    started = time.perf_counter()
    for _ in range(5):
        mono()
    each = (time.perf_counter() - started) / 5
    print(f"\nplan (68 atoms, cached): {each * 1000:.1f} ms")
    assert each < 0.1
