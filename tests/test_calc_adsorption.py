"""Spec 42 R4, R5: the "Molécula na superfície" type of "Criar cálculo": the plan of the user's scripts
(stage 3: the 2×1×1 (001) relaxed, H3CHg, mono and bidentate with the anchor's H removed), the species
and namelists of the two SCFs, its fields, errors and ``geracao.md``. Spec 75 R2, R3: the distance from
the site atom (the window's default), the shift and the molecule's anchor by its label. Spec 76 R2: the
table of the fixed atoms, its marks from the rules and what the marks write."""

from __future__ import annotations

import time

import numpy as np
import pytest

from qe_studio.core.calc_create.kpath import KMesh
from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.adsorb import SURFACE
from qe_studio.core.calc_create.surface.fixing import ALL_FIXED
from qe_studio.core.calc_create.surface.merge import NBND_NOTE, merge_namelists, merge_species
from qe_studio.core.calc_create.surface.report import REPORT_KEY, REPORT_NAME
from qe_studio.core.calc_create.types import by_id, shown_fields, visible_fields
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
    """28 of the surface atoms fixed both from the SCF's flags (the default) and by the script's rule.
    The bidentate pairs ask for the scripts' distance (spec 75); on a bare O both give the same."""
    sites = ADSORBED[case]
    values = {"fix_rule": rule} if rule else {}
    mode = "bidentado" if len(sites) == 2 else "monodentado"
    if len(sites) == 2:
        values["distance_from"] = SURFACE
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


def with_beta(text: str, beta: float | None) -> InputEditor:
    editor = InputEditor.from_text(text)
    editor.remove("electrons", "mixing_beta")
    if beta is not None:
        editor.set("electrons", "mixing_beta", repr(beta))
    return editor


@pytest.mark.parametrize(
    ("surface", "molecule", "expected"),
    [
        (0.4, 0.3, 0.3),
        (0.3, 0.4, 0.3),
        (None, 0.2, 0.2),  # the surface's is pw.x's 0.7
        (0.4, None, 0.4),
        (0.8, None, 0.7),
        (None, None, None),
    ],
)
def test_the_smaller_mixing_beta_counts_the_default_of_pw(surface, molecule, expected):
    editor = with_beta(SUPERCELL_001.read_text(), surface)
    merge_namelists(editor, from_text(with_beta(MOLECULE.read_text(), molecule).text()))
    written = editor.get("electrons", "mixing_beta")
    assert (fortran_float(written) if written is not None else None) == expected


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
        (  # 1.2 Å above O 41 is on its H 58
            {"site": (41,), "remove_h": False, "ads_distance": 1.2},
            "ads_distance",
            "O âncora fica a 0.24 Å de H 58: os dois átomos se sobrepõem",
        ),
        ({"site": (43,), "anchor": 9}, "anchor", "SCF da molécula: Átomo âncora 9 fora"),
        (
            {"site": (43,), "anchor": "H"},
            "anchor",
            "SCF da molécula: O rótulo H aparece em 3 átomos (3, 4, 5): use o número ou H3",
        ),
        ({"site": (43,), "shift_x": "abc"}, "shift_x", "Valor inválido em Δx (Å): abc"),
        (
            {"site_from": "coordenadas", "coords_1": "0.5 0.5 0.1"},
            "coords_1",
            "As coordenadas 0.5 0.5 0.1 estão a",
        ),
        ({"mode": "bidentado", "site": (43,)}, "site", "Bidentado: marque dois átomos"),
        ({"height_window": "0"}, "height_window", "A janela da superfície deve ser maior que zero"),
    ],
)
def test_each_error_is_marked_on_its_field(values, field_id, text):
    result = plan(**values)
    assert result.problems[field_id].startswith(text), result.problems


def test_an_atom_in_the_way_is_a_note():
    """O 43 with its H 59 kept: the anchor 2 Å above the O, 1.04 Å from the H, and no error."""
    result = plan(site=(43,), remove_h=False)
    assert result.errors == ()
    assert (
        "O âncora fica a 1.04 Å de H 59 (abaixo de 1.5 Å): confira a posição; o relax ajusta"
        in result.notes
    )
    assert "- **Distâncias âncora–sítio**: Hg–O 43 2.00 Å" in report(result).splitlines()


def test_the_anchor_by_its_label():
    """``anchor = "C"``: the C 2 Å above O 43 and the Hg along the normal, above it."""
    result = mono(anchor="C")
    assert result.errors == ()
    model = model_from_plan(input_text(result))
    hg, c = len(model) - 5, len(model) - 4
    assert model.labels[hg : c + 1] == ("Hg", "C")
    frac = model.frac[c] - model.frac[42]  # O 43: no atom before it was removed
    frac -= np.round(frac)
    assert np.allclose(frac @ model.cell, [0.0, 0.0, 2.0], atol=1e-5)
    axis = model.cart[hg] - model.cart[c]
    assert np.allclose(axis / np.linalg.norm(axis), [0.0, 0.0, 1.0], atol=1e-5)
    assert "âncora C2" in report(result)


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


def test_the_standard_mode_shows_the_position_fields():
    scf = read(SUPERCELL_001)
    shown = [f.id for f in visible_fields(ADSORPTION.fields(scf, JOBS), "padrao")]
    assert shown == [
        "molecule",
        "anchor",
        "ads_distance",
        "mode",
        "site",
        "remove_h",
        "shift_x",
        "shift_y",
        "fixed_atoms",
    ]
    fields = {f.id: f for f in ADSORPTION.input_fields(scf)}
    assert fields["distance_from"].default == "átomo do sítio"
    assert fields["distance_from"].choices[1] == SURFACE
    tabs = {f.id: f.group for f in ADSORPTION.input_fields(scf)}
    assert tabs["molecule"] == "Molécula" and tabs["site"] == "Sítio" and tabs["kmesh"] == "relax"
    assert [key for key, tab in tabs.items() if tab == "Molécula"] == [
        "molecule",
        "anchor",
        "ads_distance",
    ]
    moved = ("shift_x", "shift_y", "distance_from", "h_clearance", "vacuum_min")
    assert {tabs[key] for key in moved} == {"Sítio"}  # spec 87 R2


def test_the_order_of_the_site_tab():
    """Spec 87 R2.2: how the site is chosen comes before what it shows."""
    scf = read(SUPERCELL_001)
    assert [f.id for f in ADSORPTION.input_fields(scf) if f.group == "Sítio"] == [
        "mode",
        "site_from",
        "site",
        "coords_1",
        "coords_2",
        "site_tol",
        "remove_h",
        "shift_x",
        "shift_y",
        "distance_from",
        "h_clearance",
        "vacuum_min",
        "height_window",
        "symprec",
        "bond_scale",
    ]


def conditional(window: str = "avancado", **values) -> set[str]:
    """Which of the fields of "Escolher o sítio por" the window shows."""
    fields = ADSORPTION.fields(read(SUPERCELL_001), JOBS)
    asked = {"site", "coords_1", "coords_2", "site_tol"}
    return {f.id for f in shown_fields(fields, window, values)} & asked  # type: ignore[arg-type]


def test_the_choice_of_the_site_shows_its_fields():
    """Spec 87 R3.2, R3.5: the table or the coordinates, and how many follow the coordination; a choice
    the mode hides counts as its default."""
    by_list = {"site"}
    by_coords = {"coords_1", "site_tol"}
    assert conditional() == by_list
    assert conditional(site_from="lista de candidatos", mode="bidentado") == by_list
    assert conditional(site_from="coordenadas") == by_coords
    assert conditional(site_from="coordenadas", mode="bidentado") == by_coords | {"coords_2"}
    assert conditional("padrao", site_from="coordenadas", mode="bidentado") == by_list


def test_a_field_hidden_by_the_choice_takes_its_default():
    """Spec 87 R3.3: what is not on the screen does not block "Criar"."""
    assert mono(site_tol="abc").errors == ()
    assert mono(site_tol="0").errors == ()
    bad = plan(site_from="coordenadas", site_tol="abc", coords_1="0.5 0.5 0.5")
    assert bad.problems["site_tol"] == "Valor inválido em Tolerância das coordenadas (Å): abc"
    frac = read(SUPERCELL_001).crystal.frac[42]
    typed = plan(
        site_from="coordenadas",
        coords_1=" ".join(f"{v:.5f}" for v in frac),
        coords_2="abc",  # the second atom of a bidentate: hidden in a monodentate
        site=(1, 2, 3),  # the marks of the table: hidden with the coordinates
        remove_h=True,
    )
    assert typed.errors == ()
    assert input_text(typed) == input_text(mono())


def test_any_atom_of_the_window_can_be_the_site():
    """Spec 87 R4: the species no longer limit the coordinates or the list; the H 59 is on top."""
    frac = read(SUPERCELL_001).crystal.frac[58]
    typed = plan(site_from="coordenadas", coords_1=" ".join(f"{v:.5f}" for v in frac))
    assert typed.errors == (), typed.errors
    assert "H 59" in report(typed)
    assert plan(site=(59,)).errors == ()
    low = plan(site=(1,))
    assert low.problems["site"].startswith("O átomo 1 (")
    assert "não está na superfície" in low.problems["site"]


def test_the_anchor_list_gives_what_was_typed():
    """Spec 87 R1: the value of an option is the atom's number, which ``anchor_index`` reads."""
    choices = ADSORPTION.field_data("anchor", read(SUPERCELL_001), {"molecule": read(MOLECULE)})
    assert [choice.value for choice in choices] == ["", "1", "2", "3", "4", "5"]
    assert input_text(mono(anchor=choices[2].value)) == input_text(mono(anchor="C"))
    assert input_text(mono(anchor=choices[0].value)) == input_text(mono())
    empty = ADSORPTION.field_data("anchor", read(SUPERCELL_001), {})
    assert [choice.text for choice in empty] == ["Automático: o mais pesado"]


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
    assert site.depends_on == ("height_window", "symprec", "bond_scale")
    assert len(site.data.rows) == 24
    narrow = ADSORPTION.field_data("site", scf, {"height_window": "0.5"})
    assert narrow.rows and {row.label for row in narrow.rows} == {"H"}


def test_the_report():
    text = report(plan(site=(43, 46), remove_h=True, mode="bidentado", distance_from=SURFACE))
    assert text.startswith(
        "# Relatório da geração\n\n- **SCF da superfície**: scf-kaolinite-slab-001-2x1x1.in\n"
    )
    lines = text.splitlines()
    for line in (
        "- **SCF da molécula**: scf-H3CHg.in: HgCH3 (Hg 1, C 1, H 3), altura 2.60 Å, âncora Hg1",
        "- **Coordenação**: bidentado (sítio pela lista de candidatos)",
        "- **H removidos**: H 59, H 62",
        "- **Átomos**: 71 (66 da superfície + 5 da molécula: Al 8, Si 8, O 36, H 17, Hg 1, C 1)",
        "- **Distâncias âncora–sítio**: Hg–O 43 2.00 Å; Hg–O 46 2.00 Å",
        "- **Vácuo acima da molécula**: 12.36 Å",
        "- **Átomos fixos**: 28/66 (Si 8, O 20), regra 'do SCF'",
        "- **k-points**: 3 4 1 0 0 0 (da superfície: a célula não muda)",
    ):
        assert line in lines, line
    anchors = next(line for line in lines if line.startswith("- **Átomos âncora**"))
    assert "O 43 (" in anchors and "; grupo A)" in anchors and "O 46 (" in anchors
    assert any(
        line.startswith(
            "- **Posição do âncora**: ao menos 2.000 Å de todo átomo da superfície (scripts), "
            "erguido 1.08 Å, Δx 0.000 Å, Δy 0.000 Å; em "
        )
        for line in lines
    )


def test_the_report_of_a_position_from_the_site():
    """Spec 75 R2.4: the window's default, a shift and the bidentate's midpoint."""
    lines = report(mono(shift_x="1", shift_y="-0.5")).splitlines()
    assert any(
        line.startswith(
            "- **Posição do âncora**: 2.000 Å acima de O 43 (relativa ao sítio), Δx 1.000 Å, "
            "Δy -0.500 Å; em "
        )
        for line in lines
    )
    assert "- **Distâncias âncora–sítio**: Hg–O 43 2.29 Å" in lines
    lines = report(plan(site=(43, 46), remove_h=True, mode="bidentado")).splitlines()
    assert any(
        line.startswith(
            "- **Posição do âncora**: 2.000 Å acima do ponto médio de O 43 e O 46 (relativa ao "
            "sítio), Δx 0.000 Å, Δy 0.000 Å; em "
        )
        for line in lines
    )
    assert "- **Distâncias âncora–sítio**: Hg–O 43 2.62 Å; Hg–O 46 2.62 Å" in lines


def test_the_folder_is_written(tmp_path):
    created = create_folder(tmp_path, ADSORPTION, "HgCH3", mono())
    assert created.folder.name == "Adsorption_HgCH3"
    assert [p.name for p in created.files] == ["adsorption.qsub", INPUT, REPORT_NAME]
    assert "relax_kaolinite-slab-001-2x1x1.in" in (created.folder / "adsorption.qsub").read_text()


# -- spec 76: the table of the fixed atoms -----------------------------------------------------------
# The 28 atoms the 2×1×1 (001) SCF writes with 0 0 0: Si 9–16, O 17–36.
SCF_FIXED = tuple(range(9, 37))
BOTTOM_HALF = (*range(9, 41), 53, 54, 55, 56)  # below its middle plane: Si, the lower O and H


def fixed_rows(scf: ScfInfo | None = None, **values):
    return ADSORPTION.field_data("fixed_atoms", scf or read(SUPERCELL_001), values)


def fact_of(result) -> str:
    return next(line for line in report(result).splitlines() if "**Átomos fixos**" in line)


def test_the_fixed_table_starts_with_the_scfs_flags():
    scf = read(SUPERCELL_001)
    field = next(f for f in ADSORPTION.input_fields(scf) if f.id == "fixed_atoms")
    assert (field.kind, field.group, field.default) == ("atoms", "relax", None) and field.standard
    assert field.depends_on == (
        "fix_rule",
        "fix_fraction",
        "fix_species",
        "fix_neighbors",
        "bond_scale",
    )
    rows = fixed_rows()
    assert rows == field.data and rows.marked == SCF_FIXED and rows.error == ""
    assert (rows.check_header, rows.note_header, rows.unit) == ("Fixo", "if_pos no SCF", "crystal")
    assert len(rows.rows) == 68 and rows.rows[8].x == "0.4960977240"  # as the SCF writes it
    assert (rows.rows[8].note, rows.rows[0].note) == ("0 0 0", "")
    bare = from_text(scf.text.replace("    0   0   0", ""), "scf.in")
    assert fixed_rows(bare).marked == BOTTOM_HALF
    by_rule = fixed_of(model_from_plan(input_text(mono(scf=bare))))  # H 59 is above them all
    assert tuple(i + 1 for i in by_rule) == BOTTOM_HALF
    lines = scf.text.splitlines(keepends=True)  # every atom fixed: no relax, the bottom half
    start = lines.index("ATOMIC_POSITIONS (crystal)\n")
    for k in range(start + 1, start + 69):
        if len(lines[k].split()) == 4:
            lines[k] = lines[k].rstrip("\n") + "    0   0   0\n"
    frozen = from_text("".join(lines), "scf.in")
    defaults = {f.id: f.default for f in ADSORPTION.input_fields(frozen)}
    assert defaults["fix_rule"] == "camada inferior"
    assert fixed_rows(frozen).marked == BOTTOM_HALF


def test_a_rule_refills_the_table():
    assert fixed_rows(fix_rule="nenhum").marked == ()
    assert fixed_rows(fix_rule="espécies e vizinhos").marked == SCF_FIXED  # the scripts' rule
    assert fixed_rows(fix_rule="camada inferior").marked == BOTTOM_HALF
    bad = fixed_rows(fix_rule="espécies e vizinhos", fix_species="Xx")
    assert bad.marked is None and len(bad.rows) == 68  # the table keeps its marks
    assert bad.error == "Espécies fixas: Xx não está em ATOMIC_SPECIES do SCF"
    out = fixed_rows(fix_rule="camada inferior", fix_fraction="2")
    assert out.error == "A fração fixa da espessura vai de 0 (exclusive) a 1" and out.marked is None
    assert fixed_rows(fix_fraction="abc").error.startswith("Valor inválido em Fração fixa")
    # In the plan a bad rule still blocks, though the table holds marks.
    result = mono(fixed_atoms=SCF_FIXED, fix_rule="espécies e vizinhos", fix_species="Xx")
    assert result.problems["fix_species"] == bad.error


@pytest.mark.parametrize("case", list(ADSORBED))
def test_the_table_of_the_scfs_marks_gives_the_scripts_input(case):
    sites = ADSORBED[case]
    values = {"mode": "bidentado", "distance_from": SURFACE} if len(sites) == 2 else {}
    by_rule = plan(site=sites, remove_h=True, **values)
    by_table = plan(site=sites, remove_h=True, fixed_atoms=fixed_rows().marked, **values)
    assert by_table.errors == ()
    assert input_text(by_table) == input_text(by_rule)
    assert fixed_of(model_from_plan(input_text(by_table))) == golden(case)["fixed"]
    assert fact_of(by_table).endswith("(Si 8, O 20), marcados na tabela")
    assert fact_of(by_rule).endswith("(Si 8, O 20), regra 'do SCF'")


def test_marking_one_more_atom():
    """Al 1 marked (free in the SCF): 0 0 0. Si 9 unmarked: no flags. Si 10, 0 0 1 in the SCF and
    still marked: 0 0 1. The molecule stays free."""
    scf = read(SUPERCELL_001)
    row = "0.9960977240        0.3374135760        0.3984388000    0   0   "
    partial = from_text(scf.text.replace(row + "0", row + "1"), "scf.in")
    assert fixed_rows(partial).marked == SCF_FIXED  # a 0 in its if_pos: fixed
    marks = (1, *SCF_FIXED[1:])
    result = mono(scf=partial, fixed_atoms=marks)
    assert result.errors == ()
    model = model_from_plan(input_text(result))
    assert [model.flag(i) for i in range(4)] == [(0, 0, 0), None, None, None]
    assert [model.flag(i) for i in (8, 9, 10)] == [None, (0, 0, 1), (0, 0, 0)]
    assert all(model.flag(i) is None for i in range(len(model) - 5, len(model)))
    assert fact_of(result) == (
        "- **Átomos fixos**: 28/67 (Al 1, Si 7, O 20), marcados na tabela "
        "(2 diferentes da regra 'do SCF')"
    )
    one = mono(scf=partial, fixed_atoms=SCF_FIXED[1:])
    assert fact_of(one).endswith("marcados na tabela (1 diferente da regra 'do SCF')")


def test_marked_removed_h_is_ignored():
    """H 59 goes with the site O 43: marked or not, the same input."""
    with_h = mono(fixed_atoms=(*SCF_FIXED, 59))
    assert with_h.errors == ()
    assert input_text(with_h) == input_text(mono(fixed_atoms=SCF_FIXED))
    assert fact_of(with_h) == "- **Átomos fixos**: 28/67 (Si 8, O 20), marcados na tabela"


def test_all_marked_is_an_error():
    every = tuple(range(1, 69))
    assert mono(fixed_atoms=every).problems["fixed_atoms"] == ALL_FIXED
    written = tuple(n for n in every if n != 59)  # the H removed is not written
    assert mono(fixed_atoms=written).problems["fixed_atoms"] == ALL_FIXED
    assert "fixed_atoms" not in mono(fixed_atoms=written[1:]).problems
    nothing = mono(fixed_atoms=())
    assert nothing.errors == () and fixed_of(model_from_plan(input_text(nothing))) == []
    assert fact_of(nothing).startswith("- **Átomos fixos**: 0/67, marcados na tabela (28 difer")


@pytest.mark.perf
def test_the_plan_is_fast_once_cached():
    mono()  # spglib, the reads and the templates once
    started = time.perf_counter()
    for _ in range(5):
        mono()
    each = (time.perf_counter() - started) / 5
    print(f"\nplan (68 atoms, cached): {each * 1000:.1f} ms")
    assert each < 0.1
