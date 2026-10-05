"""Spec 26: what the "Criar cálculo" window shows, without Qt (``core/calc_create/preview.py``)
and the per-field problems the form marks."""

from pathlib import Path

from qe_studio.core.calc_create.kpath import KMesh
from qe_studio.core.calc_create.preview import (
    changed_lines,
    created_notice,
    field_text,
    file_rows,
    mesh_summary,
    outside_project,
    target_text,
)
from qe_studio.core.calc_create.types import by_id, field_problems
from qe_studio.core.calc_create.types.base import PlannedFile
from qe_studio.core.calc_create.writer import Created

from calc_helpers import AL_PATH, JOBS, al


def test_changed_lines_are_the_replaced_and_inserted_ones():
    original = "a\nb\nc\nd\n"
    assert changed_lines(original, original) == []
    assert changed_lines(original, "a\nB\nc\nd\n") == [1]
    assert changed_lines(original, "a\nb\nnew\nc\nd\n") == [2]
    assert changed_lines(original, "a\nc\nd\n") == []  # a removed line has no row to paint


def test_changed_lines_of_a_derived_input():
    scf = al()
    bands = by_id("bandas").plan(scf, {"kpath": AL_PATH}, JOBS).file("bands.in")
    assert bands is not None
    lines = bands.text.splitlines()
    marked = [lines[i] for i in changed_lines(scf.text, bands.text)]
    assert any("calculation" in line and "bands" in line for line in marked)
    assert any("K_POINTS crystal_b" in line for line in marked)
    assert not any("ecutwfc" in line for line in marked)


def test_field_text():
    assert field_text(None) == ""
    assert field_text(8) == "8"
    assert field_text(0.001) == "0.001"
    assert field_text(-25.0) == "-25.0"
    assert field_text("al.dat") == "al.dat"
    assert field_text(KMesh((4, 4, 2), (1, 1, 0))) == "4 4 2 1 1 0"
    assert field_text(True) == ""


def test_mesh_summary():
    assert mesh_summary(KMesh((4, 4, 2))) == (
        "4×4×2 = 32 k-points na rede (o pw.x reduz pela simetria)"
    )
    assert "mantém o K_POINTS do SCF" in mesh_summary(None)


def test_file_rows():
    files = [
        PlannedFile("pdos.qsub", "qsub", "#!/bin/bash\n", "Script"),
        PlannedFile("scf.in", "pw_input", "x" * 2048, "SCF"),
        PlannedFile("projwfc.in", "qe_input", "", "projwfc.in"),
        PlannedFile("descricao.md", "notes", "ção\n", "Descrição"),
    ]
    rows = file_rows(files)
    assert [(r.name, r.kind) for r in rows] == [
        ("pdos.qsub", "Script SGE"),
        ("scf.in", "Input do pw.x"),
        ("projwfc.in", "Input do QE"),
        ("descricao.md", "Anotações"),
    ]
    assert [r.size for r in rows] == ["12 B", "2.0 KB", "0 B", "6 B"]  # bytes of the UTF-8 text


def test_target_text(tmp_path):
    bandas = by_id("bandas")
    assert target_text(tmp_path, bandas, "Al") == "Será criada: Bands_Al"
    assert target_text(tmp_path, bandas, "") == "Será criada: Bands"
    (tmp_path / "Bands_Al").mkdir()
    assert target_text(tmp_path, bandas, "Al") == "Será criada: Bands_Al_1 — já existe Bands_Al"


def test_outside_project(tmp_path):
    root = tmp_path / "proj"
    (root / "a").mkdir(parents=True)
    assert not outside_project(root, root)
    assert not outside_project(root / "a", root)
    assert outside_project(tmp_path, root)


def test_created_notice():
    folder = Path("/p/Bands_Al_1")
    files = tuple(folder / n for n in ("bands.qsub", "scf_al.in", "bands.in", "bands_pp.in"))
    text, details = created_notice(Created(folder, files, "Bands_Al"))
    assert text == "Pasta Bands_Al_1 criada com 4 arquivos"
    assert details.splitlines()[0] == "/p/Bands_Al_1"
    assert "  bands_pp.in" in details.splitlines()
    assert details.endswith("Bands_Al já existia: criada como Bands_Al_1")
    one, details = created_notice(Created(Path("/p/SCF_x"), (Path("/p/SCF_x/scf_x.in"),)))
    assert one == "Pasta SCF_x criada com 1 arquivo"
    assert "já existia" not in details
    reminded, _ = created_notice(Created(folder, files), sync=True)  # spec 26 R5.3, spec 27
    assert reminded == (
        "Pasta Bands_Al_1 criada com 4 arquivos. Use ‘Enviar ao cluster’ para levar a pasta ao "
        "cluster"
    )


def test_field_problems_name_each_field():
    scf = al()
    fields = by_id("pdos").fields(scf, JOBS)
    assert field_problems(fields, {}) == {}  # every field has a default
    problems = field_problems(fields, {"np": "muitos", "delta_e": "x", "kmesh": "4 4"})
    assert problems == {
        "np": "Valor inválido em Núcleos (NP): muitos",
        "delta_e": "Valor inválido em Passo de energia (DeltaE, eV): x",
        "kmesh": "Valor inválido em Rede de k-points: 4 4",
    }
    bandas = by_id("bandas").fields(scf, JOBS)
    assert field_problems(bandas, {}) == {"kpath": "Preencha Caminho de alta simetria"}
    # The plan carries them too, with the file names' (spec 28 R4.2): what the window marks.
    plan = by_id("bandas").plan(scf, {"np": "x", "name:bands": "b"}, JOBS, "avancado")
    assert set(plan.problems) == {"np", "kpath", "name:bands"}
    assert by_id("bandas").plan(scf, {"np": "x"}, JOBS).problems == {
        "kpath": plan.problems["kpath"]
    }
