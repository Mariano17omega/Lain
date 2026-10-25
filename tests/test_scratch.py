"""The names of the scratch copy of a remote plot (spec 66 R1) and the request that fills it (R3.1):
pure, nothing synced here (``test_scratch_pull.py`` runs rsync)."""

from dataclasses import replace
from pathlib import Path

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.plotting.export import plots_dir, table_path, target_paths
from qe_studio.core.plotting.names import plots_folder
from qe_studio.core.plotting.plot_file import plot_file_path
from qe_studio.core.plotting.saved import was_plotted
from qe_studio.core.scratch import is_scratch, scratch_of
from qe_studio.core.structure3d.image_file import save_png
from qe_studio.core.sync.request import (
    PLOT_PROJECT,
    PLOT_ROOT,
    SyncRefusal,
    SyncRequest,
    prepare_scratch,
    sync_scope,
)
from qe_studio.core.sync.rsync import Endpoint


def test_scratch_names():
    mirror = Path("/data/ilita/Bands")
    assert scratch_of(mirror) == Path("/data/ilita/Bands/tmp_remote")
    assert is_scratch(scratch_of(mirror))
    assert not is_scratch(mirror) and not is_scratch(Path("/data/tmp_remote_old"))
    assert not is_scratch(Path("/data/tmp_remote/orbitals"))


def test_plots_folder():
    assert plots_folder(Path("/data/Bands")) == Path("/data/Bands/plots")
    assert plots_folder(Path("/data/Bands/tmp_remote")) == Path(
        "/data/Bands/tmp_remote/plots_remote"
    )


def test_exports_and_settings_of_a_copy_go_to_plots_remote(tmp_path):
    copy = tmp_path / "Bands" / "tmp_remote"
    remote_plots = copy / "plots_remote"
    assert plots_dir(copy) == remote_plots
    assert plot_file_path(copy, "bands") == remote_plots / "bands.plot"
    assert target_paths(copy, "Bands-tmp_remote-bands", ["png"]) == [
        remote_plots / "Bands-tmp_remote-bands.png"
    ]
    assert table_path(copy, "x") == remote_plots / "x.csv"
    copy.mkdir(parents=True)
    assert save_png(copy, "scf-3d", b"png") == remote_plots / "scf-3d.png"


def test_a_plain_folder_keeps_plots(tmp_path):
    folder = tmp_path / "Bands"
    assert plots_dir(folder) == folder / "plots"
    assert plot_file_path(folder, "bands") == folder / "plots" / "bands.plot"


def test_was_plotted_looks_in_plots_remote(tmp_path):
    copy = tmp_path / "Bands" / "tmp_remote"
    (copy / "plots").mkdir(parents=True)
    (copy / "plots" / "bands.plot").write_text("lain_plot: 1\n", encoding="utf-8")
    assert not was_plotted(copy)  # a plots/ copied from the cluster is not a plot of the copy
    (copy / "plots_remote").mkdir()
    (copy / "plots_remote" / "Bands-tmp_remote-bands.png").write_bytes(b"png")
    assert was_plotted(copy) and was_plotted(copy, "bands")
    assert not was_plotted(tmp_path / "Bands")  # the mirror's own plots/ is empty


# -- the request (R3.1) and its scope ----------------------------------------------------------
def config(tmp_path: Path, **cluster):
    return parse_config(
        {
            "paths": {"local_root": str(tmp_path), "remote_root": "/scratch/me"},
            "cluster": {"host": "hpc.example", "user": "me", **cluster},
        }
    )


def test_the_copy_is_of_the_mirror_cluster_side(tmp_path):
    mirror = tmp_path / "ilita" / "Bands"  # need not exist
    request = prepare_scratch(config(tmp_path), mirror)
    assert isinstance(request, SyncRequest)
    assert request.folder == mirror / "tmp_remote"
    assert request.endpoint == Endpoint("/scratch/me/ilita/Bands", "hpc.example", "me")
    assert not request.needs_password


@pytest.mark.parametrize(
    "relative, message", [("", PLOT_ROOT), ("ilita", PLOT_PROJECT)], ids=["root", "project"]
)
def test_root_and_project_are_refused(tmp_path, relative, message):
    request = prepare_scratch(config(tmp_path), tmp_path / relative)
    assert request == SyncRefusal("warning", message)


def test_without_a_cluster_nothing_is_copied(tmp_path):
    request = prepare_scratch(
        parse_config({"paths": {"local_root": str(tmp_path)}}), tmp_path / "a/b"
    )
    assert isinstance(request, SyncRefusal) and request.level == "info"


def test_the_scope_of_a_copy(tmp_path):
    scope = replace(sync_scope(config(tmp_path), tmp_path / "ilita" / "Bands"), scratch=True)
    assert scope.title == "Baixando para plotar: ilita/Bands (e subpastas)"
    assert scope.local_text == "ilita/Bands/tmp_remote"
    assert scope.remote == "me@hpc.example:/scratch/me/ilita/Bands/"
    assert scope.confirm_text == "Baixar"
