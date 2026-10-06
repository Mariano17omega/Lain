"""Names of the exported files (spec 32 R3): the path from the project root, then the plot's name."""

from pathlib import Path

import pytest

from qe_studio.core.calculations.base import DetectionResult
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.plotting import export as export_module
from qe_studio.core.plotting.export import ExportPlan, _remove_orphans, plan_export
from qe_studio.core.plotting.names import MAX_STEM_BYTES, export_prefix, join_stem
from qe_studio.core.plotting.session import build_session, load_plot
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES

ROOT = Path("/sim")


def test_the_prefix_is_the_path_from_the_root():
    assert export_prefix(ROOT / "projeto_ilita/bulk/bandas", ROOT) == "projeto_ilita-bulk-bandas"
    assert export_prefix(ROOT / "projeto_ilita", ROOT) == "projeto_ilita"


def test_the_root_itself_has_no_prefix_and_a_folder_outside_it_only_its_name():
    assert export_prefix(ROOT, ROOT) == ""
    assert export_prefix(Path("/elsewhere/dummy_sim"), ROOT) == "dummy_sim"
    assert export_prefix(Path("/"), ROOT) == ""


def test_the_prefix_reads_no_disk(tmp_path):
    assert export_prefix(tmp_path / "gone" / "x", tmp_path) == "gone-x"  # nothing there


def test_the_stem_is_the_prefix_then_the_modules_name():
    assert join_stem("projeto_ilita-bulk-bandas", "bands") == "projeto_ilita-bulk-bandas-bands"
    assert join_stem("", "bands") == "bands"
    assert join_stem("a-VC-Relax_Si", "relax_energia") == "a-VC-Relax_Si-relax_energia"


def test_a_leading_dot_never_makes_a_hidden_file():
    assert join_stem(".hidden-run", "bands") == "hidden-run-bands"
    assert join_stem("..", "bands") == "bands"
    assert join_stem("ok-.dotted", "bands") == "ok-.dotted-bands"  # only the start of the name


def test_a_long_prefix_loses_whole_parts_from_the_left():
    parts = [f"pasta{n:02d}_" + "x" * 20 for n in range(12)]
    stem = join_stem("-".join(parts), "bands")
    assert len(stem.encode()) <= MAX_STEM_BYTES
    assert stem.endswith(f"{parts[-1]}-bands") and parts[0] not in stem
    kept = stem.removesuffix("-bands").split("-")
    assert kept == parts[-len(kept) :]  # a block of the last ones, never a piece of one


def test_one_part_too_long_is_cut_at_a_character_not_a_byte():
    stem = join_stem("ç" * 300, "bands")
    assert len(stem.encode()) <= MAX_STEM_BYTES and stem.endswith("-bands")
    stem.encode().decode()  # whole characters


# -- the plan --------------------------------------------------------------------------------------
CONFIG = AppConfig()


@pytest.fixture
def bands():
    (result,) = detect_folder(FIXTURES / "al_bands", sniff=SniffCache().sniff)
    _result, dataset = load_plot(result, SniffCache().sniff)
    return result, dataset


def session_in(folder, bands, tmp_path):
    result, dataset = bands
    session, _ = build_session(
        result, dataset, CONFIG, (None, []), FolderMemory(tmp_path / "m.json")
    )
    session.result = DetectionResult(result.module, folder, result.files, result.methods)
    return session


def test_plan_export_names_the_files_from_the_root(bands, tmp_path):
    folder = tmp_path / "projeto_ilita" / "bulk" / "bandas"
    folder.mkdir(parents=True)
    session = session_in(folder, bands, tmp_path)
    plan = plan_export(session, tmp_path)
    assert plan.stem == "projeto_ilita-bulk-bandas-bands" and plan.table
    assert plan_export(session).stem == "bands"  # no root: the module's own name


def test_the_csv_is_part_of_the_set_that_exists_and_of_its_new_version(bands, tmp_path):
    folder = tmp_path / "p" / "b"
    (folder / "plots").mkdir(parents=True)
    session = session_in(folder, bands, tmp_path)
    (folder / "plots" / "p-b-bands.csv").write_text("x")  # only the CSV is there
    plan = plan_export(session, tmp_path)
    assert [p.name for p in plan.existing] == ["p-b-bands.csv"] and plan.new_stem == "p-b-bands_2"
    (folder / "plots" / "p-b-bands_2.csv").write_text("x")
    assert plan_export(session, tmp_path).new_stem == "p-b-bands_3"


def test_a_plan_without_a_format_still_explains(bands, tmp_path):
    session = session_in(tmp_path / "p", bands, tmp_path)
    session.params.export_png = session.params.export_svg = session.params.export_pdf = False
    plan = plan_export(session, tmp_path)
    assert isinstance(plan, ExportPlan) and plan.error is not None and plan.stem == "p-bands"


def test_orphans_are_matched_literally(tmp_path):
    plots = tmp_path / "plots"
    plots.mkdir()
    for name in (".a[1]-bands.png.tmp", ".a1-bands.png.tmp", ".a[1]-bands.csv.tmp"):
        (plots / name).write_text("x")
    _remove_orphans(tmp_path, "a[1]-bands")
    assert [p.name for p in plots.iterdir()] == [".a1-bands.png.tmp"]  # [1] is not a class
    assert export_module.PLOTS_DIR == "plots"
