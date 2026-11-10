"""The reading side of L-05 and L-06 of the Lain × QE checklist (``Documentation/QE-73/07-lain-checklist.md``):
bands.x leaving an empty ``.gnu`` and a k path that the data does not match."""

import numpy as np

from qe_studio.core.calculations.bands.data import load_dataset
from qe_studio.core.detection import detect_folder
from qe_studio.core.qe.bands_x import parse_bandsx_output, path_coordinates
from qe_studio.core.sniff import FileKind, SniffCache, sniff

from conftest import FIXTURES, copy_fixture

SAME_K = "     Message from routine punch_plottable_bands:\n     two consecutive same k, exiting\n"


def detect(folder):
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    return result


# -- L-05 -----------------------------------------------------------------------------------------
def test_l05_the_x_axis_does_not_collapse_when_the_first_two_k_are_equal():
    k = np.array([[0, 0, 0], [0, 0, 0], [0.1, 0, 0], [0.2, 0, 0], [0.3, 0, 0]], dtype=float)
    # bands.x never gets here (it stops at the equal pair); before the fix typical = 0 and x stayed 0
    np.testing.assert_allclose(path_coordinates(k), [0, 0, 0.1, 0.2, 0.3])


def test_l05_the_rule_is_the_same_when_the_first_step_is_regular():
    k = np.array([[0, 0, 0], [0.1, 0, 0], [0.2, 0, 0], [5.0, 5.0, 0], [5.1, 5.0, 0]])
    np.testing.assert_allclose(path_coordinates(k), [0, 0.1, 0.2, 0.2, 0.3])


def test_l05_a_real_output_wrote_its_gnu():
    out = parse_bandsx_output((FIXTURES / "al_bands/bands.out").read_text())
    assert out.gnu_name == "bands.dat.gnu" and not out.gnu_skipped


def test_l05_the_infomsg_marks_the_gnu_as_skipped():
    text = (FIXTURES / "al_bands/bands.out").read_text()
    out = parse_bandsx_output(text.replace("Plottable bands", "Plottable").rstrip() + "\n" + SAME_K)
    assert out.gnu_skipped


def test_l05_a_filband_without_a_gnu_in_a_finished_run_is_skipped_too():
    lines = (FIXTURES / "al_bands/bands.out").read_text().splitlines()
    kept = [line for line in lines if "Plottable bands" not in line]
    out = parse_bandsx_output("\n".join(kept))
    assert out.filband_name == "bands.dat" and out.gnu_name is None and out.gnu_skipped


def test_l05_an_empty_gnu_is_unknown_and_detection_says_why(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    gnu = folder / "bands.dat.gnu"
    gnu.write_bytes(b"")
    out = folder / "bands.out"
    text = out.read_text().splitlines()
    out.write_text(
        "\n".join(line for line in text if "Plottable bands" not in line) + "\n" + SAME_K
    )
    assert sniff(gnu).kind is FileKind.UNKNOWN
    result = detect(folder)
    assert any(
        "não gravou o .gnu" in warning and "bands.out" in warning for warning in result.warnings
    )
    dataset = load_dataset(result, sniff)
    assert dataset.source == "filband"  # the plot falls back to the raw file, as before
    assert dataset.bands.n_kpoints == 91


# -- L-06 -----------------------------------------------------------------------------------------
def with_collinear_vertex(folder):
    """The Al path with a vertex in the middle of the straight Γ-X segment: bands.x does not mark it,
    and a weight changed so that the path no longer has the 91 points of the data."""
    path = folder / "al.band.in"
    text = path.read_text()
    text = text.replace("5\n", "6\n", 1)
    text = text.replace(
        "  00.000 0.000 00.000 30  !G\n",
        "  00.000 0.000 00.000 15  !G\n  -0.250 0.000 -0.250 16  !M\n",
    )
    path.write_text(text)


def test_l06_a_path_that_does_not_match_is_told_to_be_short_of_vertices(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    with_collinear_vertex(folder)
    (folder / "al.band.out").unlink()
    result = detect(folder)
    dataset = load_dataset(result, sniff)
    assert dataset.tick_source == "bands.x"
    assert len(dataset.ticks) == 5 and dataset.labels == [""] * 5  # the labels cannot be matched
    assert any("rótulos omitidos" in w and "5" in w and "6" in w for w in dataset.warnings)


def test_l06_a_path_that_matches_keeps_every_vertex_and_says_nothing(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    (folder / "al.band.out").unlink()
    dataset = load_dataset(detect(folder), sniff)
    assert dataset.tick_source == "entrada" and len(dataset.ticks) == 5
    assert not [w for w in dataset.warnings if "rótulos omitidos" in w]
