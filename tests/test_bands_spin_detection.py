"""Spin (two channels) in band detection: which bands.x files are ↑ and which ↓ (spec 13, R1)."""

import shutil

import numpy as np
import pytest

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.base import Method
from qe_studio.core.detection import manual_result
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.qe.bands_x import read_gnu
from qe_studio.core.sniff import sniff
from spin_helpers import (
    FIXTURES,
    SPIN_BANDS,
    SPIN_FIXED,
    copy_fixture,
    detect_one,
    names,
    spin_bands_copy,
    write_gnu,
)

ONLY_UP = "só o canal ↑ foi encontrado: rode o bands.x com spin_component = 2"
UNKNOWN = "não foi possível identificar o canal ↑/↓"
BANDSX_FILES = ("bands_up.in", "bands_dw.in", "bands_up.out", "bands_dw.out")


def test_channels_follow_the_spin_component_of_the_bandsx_inputs():
    result = detect_one(SPIN_BANDS)
    assert names(result, "bandsx_in") == ["bands_dw.in", "bands_up.in"]
    assert names(result, "gnu") == ["bands_up.dat.gnu"]
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]
    assert names(result, "filband") == ["bands_up.dat"]
    assert names(result, "filband_down") == ["bands_dw.dat"]
    assert result.warnings == [] and result.complete


def test_the_spin_component_decides_not_the_file_name(tmp_path):
    folder = spin_bands_copy(tmp_path)
    (folder / "bands_up.in").write_text(
        (folder / "bands_up.in").read_text().replace("spin_component = 1", "spin_component = 2")
    )
    (folder / "bands_dw.in").write_text(
        (folder / "bands_dw.in").read_text().replace("spin_component = 2", "spin_component = 1")
    )
    result = detect_one(folder)
    assert names(result, "gnu") == ["bands_dw.dat.gnu"]
    assert names(result, "gnu_down") == ["bands_up.dat.gnu"]


def test_an_input_without_spin_component_is_the_up_channel(tmp_path):
    folder = spin_bands_copy(tmp_path)
    text = (folder / "bands_up.in").read_text().replace("    spin_component = 1\n", "")
    (folder / "bands_up.in").write_text(text)
    result = detect_one(folder)
    assert names(result, "gnu") == ["bands_up.dat.gnu"]
    assert result.warnings == []


def test_the_down_channel_without_input_is_the_file_a_bandsx_output_names(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_dw.in",))
    result = detect_one(folder)
    assert names(result, "gnu") == ["bands_up.dat.gnu"]
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]
    assert result.warnings == []


def test_channels_by_name_when_no_bandsx_file_is_left(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=BANDSX_FILES)
    result = detect_one(folder)
    assert names(result, "gnu") == ["bands_up.dat.gnu"]
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]
    assert names(result, "filband_down") == ["bands_dw.dat"]
    assert result.warnings == []


@pytest.mark.parametrize(
    ("down_name", "channel"),
    [("run.DW.gnu", "down"), ("run.dn.gnu", "down"), ("run.down.gnu", "down"), ("group.gnu", None)],
)
def test_name_tokens_are_whole_words(tmp_path, down_name, channel):
    folder = spin_bands_copy(tmp_path, remove=(*BANDSX_FILES, "bands_dw.dat", "bands_up.dat"))
    (folder / "bands_dw.dat.gnu").rename(folder / down_name)
    (folder / "bands_up.dat.gnu").rename(folder / "other.gnu")
    result = detect_one(folder)
    if channel is None:  # "group" holds "up" but not as a word: nothing identifies the files
        assert names(result, "gnu_down") == []
        assert any(UNKNOWN in w for w in result.warnings)
    else:
        assert names(result, "gnu_down") == [down_name]
        assert names(result, "gnu") == ["other.gnu"]


def test_files_nothing_identifies_are_not_guessed_by_order(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=(*BANDSX_FILES, "bands_dw.dat", "bands_up.dat"))
    (folder / "bands_up.dat.gnu").rename(folder / "a.gnu")
    (folder / "bands_dw.dat.gnu").rename(folder / "b.gnu")
    result = detect_one(folder)
    assert "gnu_down" not in result.files and len(result.files["gnu"]) == 1
    assert sum(UNKNOWN in w for w in result.warnings) == 1
    assert not any("foi encontrado" in w for w in result.warnings)


def test_missing_down_channel_warns_and_the_plot_has_the_up_channel_only(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_dw.dat.gnu", "bands_dw.dat"))
    result = detect_one(folder)
    assert names(result, "gnu") == ["bands_up.dat.gnu"]
    assert "gnu_down" not in result.files and "filband_down" not in result.files
    assert ONLY_UP in result.warnings
    dataset = result.module.load(result, sniff)
    assert dataset.bands_down is None and not dataset.spin
    assert dataset.bands.n_bands == 14


def test_a_lone_gnu_is_the_up_channel_and_still_warns(tmp_path):
    folder = spin_bands_copy(
        tmp_path, remove=(*BANDSX_FILES, "bands_dw.dat.gnu", "bands_dw.dat", "bands_up.dat")
    )
    result = detect_one(folder)
    assert names(result, "gnu") == ["bands_up.dat.gnu"] and "gnu_down" not in result.files
    assert ONLY_UP in result.warnings


def test_only_the_down_channel_found_warns_the_other_way(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_up.dat.gnu", "bands_up.dat"))
    result = detect_one(folder)
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]
    assert "gnu" not in result.files
    assert "só o canal ↓ foi encontrado: rode o bands.x com spin_component = 1" in result.warnings


def test_inputs_of_both_channels_writing_one_file_give_it_to_no_channel(tmp_path):
    # Both bands.x runs wrote bands.dat: the file holds the last run, whichever it was.
    folder = spin_bands_copy(tmp_path, remove=("bands_up.dat", "bands_up.dat.gnu"))
    (folder / "bands_dw.dat").rename(folder / "bands.dat")
    (folder / "bands_dw.dat.gnu").rename(folder / "bands.dat.gnu")
    for name in BANDSX_FILES:
        text = (folder / name).read_text()
        (folder / name).write_text(
            text.replace("bands_up.dat", "bands.dat").replace("bands_dw.dat", "bands.dat")
        )
    result = detect_one(folder)
    assert "gnu_down" not in result.files and "filband_down" not in result.files
    assert result.warnings == [
        "as entradas do bands.x de ↑ e ↓ escrevem o mesmo arquivo (bands.dat): ele guarda só a "
        "última execução; use filband diferentes ou o mapeamento manual"
    ]


def test_channels_with_different_k_counts_warn(tmp_path):
    folder = spin_bands_copy(tmp_path)
    data = read_gnu(folder / "bands_dw.dat.gnu")
    write_gnu(folder / "bands_dw.dat.gnu", data.x[:-1], [band[:-1] for band in data.energies])
    result = detect_one(folder)
    assert "os canais ↑/↓ têm pontos k diferentes" in result.warnings
    assert any("↓ têm 44 pontos k, mas o cálculo de bandas tem 45" in w for w in result.warnings)
    assert not any("↑ têm" in w for w in result.warnings)


def test_a_run_without_spin_keeps_a_single_channel():
    for folder in ("al_bands", "si_bands"):
        result = detect_one(FIXTURES / folder)
        assert names(result, "bandsx_in") == ["bands.in"]
        assert "gnu_down" not in result.files and "filband_down" not in result.files
        assert result.warnings == []


def test_the_scf_output_of_a_neighbour_folder_tells_there_is_spin(tmp_path):
    scf_dir, bands_dir = tmp_path / "1_scf", tmp_path / "2_bands"
    scf_dir.mkdir()
    bands_dir.mkdir()
    shutil.copy(SPIN_BANDS / "ni.scf.out", scf_dir / "scf.out")
    for path in SPIN_BANDS.iterdir():
        if path.name != "ni.scf.out":
            shutil.copy(path, bands_dir / path.name)
    result = detect_one(bands_dir)
    assert result.methods["scf_out"] is Method.INFERRED
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]


def test_the_pw_bands_output_tells_there_is_spin_without_any_scf(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("ni.scf.out",))
    result = detect_one(folder)
    assert "scf_out" in result.missing
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]


def test_the_down_roles_are_found_by_content_and_labelled():
    module = module_for("bands")
    assert module.role("gnu_down").label == "Dados de bandas ↓ (.gnu)"
    assert not module.role("gnu_down").anchor and not module.role("bandsx_in").anchor
    assert module.role("bandsx_in").multiple


def test_manual_mapping_of_the_down_channel_is_kept(tmp_path):
    folder = spin_bands_copy(tmp_path, remove=("bands_dw.dat.gnu",))
    other = tmp_path / "elsewhere" / "any-name.gnu"
    other.parent.mkdir()
    shutil.copy(SPIN_BANDS / "bands_dw.dat.gnu", other)
    module = module_for("bands")
    mapping = {
        "scf_out": [folder / "ni.scf.out"],
        "gnu": [folder / "bands_up.dat.gnu"],
        "gnu_down": [other],
    }
    result = manual_result(module, folder, mapping)
    assert result.files["gnu_down"] == [other] and result.methods["gnu_down"] is Method.MANUAL
    assert result.warnings == []
    assert module.load(result, sniff).spin

    memory = FolderMemory(tmp_path / "folders.json")
    memory.set_mapping(folder, "bands", mapping)
    assert FolderMemory(tmp_path / "folders.json").mapping(folder, "bands") == mapping


def test_a_manually_mapped_up_channel_is_never_replaced(tmp_path):
    folder = spin_bands_copy(tmp_path)
    module = module_for("bands")
    mapping = {"gnu": [folder / "bands_dw.dat.gnu"]}  # deliberately the "wrong" one
    result = manual_result(module, folder, mapping)
    assert result.files["gnu"] == [folder / "bands_dw.dat.gnu"]
    assert "gnu_down" not in result.files or result.files["gnu_down"] != result.files["gnu"]


def test_the_fixed_magnetization_scf_is_detected_as_spin(tmp_path):
    folder = spin_bands_copy(tmp_path)
    shutil.copy(SPIN_FIXED / "ni.scf.out", folder / "ni.scf.out")
    result = detect_one(folder)
    assert names(result, "gnu_down") == ["bands_dw.dat.gnu"]
    assert any("duas energias de Fermi (↑/↓)" in w for w in result.warnings)


def test_gnu_files_are_up_and_down_after_copying_a_fixture_elsewhere(tmp_path):
    folder = copy_fixture("qe731_ni_spin_bands", tmp_path)
    up = read_gnu(folder / "bands_up.dat.gnu")
    down = read_gnu(folder / "bands_dw.dat.gnu")
    assert up.energies.shape == down.energies.shape == (14, 45)
    assert not np.allclose(up.energies, down.energies)  # exchange splitting
