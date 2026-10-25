"""Commands that change the cluster (spec 69 R1): names from the cluster checked and quoted, the
failures of a run classified. No network."""

import shlex

import pytest
from hypothesis import given
from hypothesis import strategies as st

from qe_studio.core.config import parse_config
from qe_studio.core.remote.actions import (
    SAFE_NAME,
    ActionFailure,
    checked_dir,
    checked_name,
    classify_failure,
)
from qe_studio.core.remote.submit import submit_line
from qe_studio.core.sync.command import CommandResult

ROOT = "/home/u/runs"


def config(root: str = ROOT, **cluster):
    settings = {"host": "hpc.example", "user": "u", **cluster}
    return parse_config({"paths": {"remote_root": root}, "cluster": settings})


@pytest.mark.parametrize("name", ["scf.qsub", "1_Bands_Al", "hBN+Sm-1", "vc-relax.qsub", "a.b"])
def test_safe_names_pass(name):
    assert checked_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["-x.qsub", ".oculto", "a b.qsub", "a;b", "$(id)", "a`b", "a'b", "a\nb", "a\n", "", "..", "é"],
)
def test_unsafe_names_are_refused(name):
    with pytest.raises(ValueError, match="Nome não suportado"):
        checked_name(name)


def test_a_folder_under_the_root_is_quoted_part_by_part():
    assert checked_dir(config(), f"{ROOT}/ilita/Bands") == f"{ROOT}/ilita/Bands"
    assert checked_dir(config(), ROOT) == ROOT
    assert checked_dir(config("/home/u/my runs"), "/home/u/my runs/ilita") == (
        "'/home/u/my runs'/ilita"
    )


@pytest.mark.parametrize(
    "folder", [f"{ROOT}/../x", "/home/u/other", "/home/u/runsx/a", f"{ROOT}/a b", f"{ROOT}/$(id)"]
)
def test_a_folder_outside_the_root_or_unsafe_is_refused(folder):
    with pytest.raises(ValueError):
        checked_dir(config(), folder)


def test_no_remote_root_refuses_every_folder():
    with pytest.raises(ValueError):
        checked_dir(config(""), "/home/u/runs")


@given(
    folders=st.lists(st.from_regex(SAFE_NAME, fullmatch=True), max_size=3),
    script=st.from_regex(SAFE_NAME, fullmatch=True),
    root=st.sampled_from([ROOT, "/home/u/my runs", "/scratch/a'b", "/x/$HOME"]),
)
def test_the_submission_line_never_breaks(folders, script, root):
    folder = "/".join([root, *folders])
    line = submit_line(config(root), folder, script)
    assert shlex.split(line) == [
        *("cd", folder, "&&", "chmod", "a+x", script, "&&", "qsub", script),
    ]


def result(code, stderr="", stdout="", timed_out=False):
    return CommandResult(code, stdout, stderr, timed_out)


def test_failures_are_classified():
    setting = "cluster.submit_command"
    timed = classify_failure(result(None, timed_out=True), "qsub", setting)
    assert timed.connection and "qsub" in timed.message
    auth = classify_failure(result(255, "u@h: Permission denied (publickey)."), "qsub", setting)
    assert auth.auth and not auth.connection
    missing = classify_failure(result(127, "bash: qsub: command not found"), "qsub", setting)
    assert missing == ActionFailure(
        "O comando qsub não foi encontrado no cluster (cluster.submit_command).", missing=True
    )
    gone = classify_failure(
        result(255, "ssh: connect to host h port 22: No route"), "qsub", setting
    )
    assert gone.connection
    other = classify_failure(result(1, "warning\nUnable to read script file\n"), "qsub", setting)
    assert other == ActionFailure("qsub terminou com código 1: Unable to read script file")
    assert classify_failure(result(2), "qsub", setting).message == "qsub terminou com código 2."
    # The command's own "Permission denied" (spec 70: a folder the user cannot write) is no login
    # refused: the password stays.
    denied = classify_failure(
        result(1, "touch: cannot touch 'a/x.EXIT': Permission denied"), "touch"
    )
    assert denied == ActionFailure(
        "touch terminou com código 1: touch: cannot touch 'a/x.EXIT': Permission denied"
    )
