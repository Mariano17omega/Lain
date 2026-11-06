"""Spec 85: a job's stdout log that only lists the job's machines is not an error."""

import pytest

from qe_studio.core.files.job_log import (
    JOB_STDOUT,
    clean_job_log,
    host_lines,
    job_cores,
    machines_of,
)
from qe_studio.core.sniff import HEAD_BYTES, FileKind, SniffCache

from conftest import FIXTURES

HOST = "ther02 32 physica.q@ther02 UNDEFINED\n"


def script(cores, name="job"):
    return f'#!/bin/bash\n#$ -N "{name}"\n#$ -pe physica {cores}\n#$ -cwd -j y -notify\n'


def put_scripts(folder, *texts):
    for number, text in enumerate(texts):
        (folder / f"run{number}.qsub").write_text(text)


@pytest.mark.parametrize(
    ("name", "text", "scripts", "clean"),
    [
        ("job.o1", HOST, [script(32)], True),
        ("job.o1", HOST * 2, [script(64)], True),
        ("job.o1", HOST * 4, [script(128)], True),
        ("job.o1", HOST, [script(16)], True),
        ("job.o1", HOST, [script(64)], False),  # the count
        ("job.o1", HOST * 2, [script(32)], False),  # the count
        ("job.o1", HOST * 2 + "Segmentation fault\n", [script(64)], False),
        ("job.o1", "Segmentation fault\n", [script(32)], False),  # the format
        ("job.o1", "node117 32 physica.q@node117 UNDEFINED\n", [script(32)], True),
        ("job.o1", "[mpiexec@ther02] error\n", [script(32)], False),  # has an ``@``, not the format
        ("job.o1", HOST, [], True),  # decision 2: only the format can be checked
        ("job.o1", "Segmentation fault\n", [], False),
        ("job.o1", HOST, [script(64, "other")], True),  # decision 2
        ("job.o1", HOST, [script(32), script(64)], True),  # decision 2: the scripts disagree
        ("job.e1", HOST, [script(32)], False),  # the stderr log never is
    ],
)
def test_the_verdict_of_a_log(tmp_path, name, text, scripts, clean):
    put_scripts(tmp_path, *scripts)
    assert clean_job_log(tmp_path / name, text) is clean


@pytest.mark.parametrize(
    ("cores", "machines"), [(32, 1), (64, 2), (128, 4), (16, 1), (48, 2), (33, 2)]
)
def test_the_machines_of_a_job_round_up(cores, machines):
    assert machines_of(cores) == machines


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        (HOST, 1),
        (HOST * 3, 3),
        (f"\n{HOST}\n  \n{HOST}", 2),  # blank lines are not machines
        (HOST.replace("\n", "\r\n"), 1),
        (f"  {HOST.rstrip()}  \n", 1),
        ("", None),
        ("   \n\n", None),  # only blanks stays an error, as an unknown content
        ("ther02 32 physica.q UNDEFINED\n", None),  # no ``@``
        ("ther02 x physica.q@ther02 UNDEFINED\n", None),  # not a number of slots
        ("ther02 32 physica.q@ther02\n", None),  # three columns
        ("ther02 32 physica.q@ther02 UNDEFINED extra\n", None),  # five columns
        ("ther02@host 32 physica.q UNDEFINED\n", None),  # the ``@`` of another column
    ],
)
def test_host_lines_counts_only_a_text_made_of_them(text, lines):
    assert host_lines(text) == lines


def test_the_cores_come_from_the_script_of_that_job(tmp_path):
    put_scripts(tmp_path, script(32, "a"), script(64, "b"))
    assert job_cores(tmp_path, "a") == 32
    assert job_cores(tmp_path, "b") == 64
    assert job_cores(tmp_path, "c") is None


def test_a_script_without_a_name_is_the_job_named_after_it(tmp_path):
    (tmp_path / "bands.qsub").write_text("#!/bin/bash\n#$ -pe physica 64\n")
    assert job_cores(tmp_path, "bands.qsub") == 64


@pytest.mark.parametrize("texts", [["#$ -N job\n"], ["#$ -N job\n#$ -pe physica 32-64\n"]])
def test_a_script_that_does_not_say_its_slots_gives_no_cores(tmp_path, texts):
    put_scripts(tmp_path, *texts)
    assert job_cores(tmp_path, "job") is None


@pytest.mark.parametrize(
    "texts",
    [[script(32), script(64)], [script(32), "#$ -N job\n"]],
    ids=["two_counts", "one_without_pe"],
)
def test_scripts_of_the_same_job_that_disagree_give_no_cores(tmp_path, texts):
    put_scripts(tmp_path, *texts)
    assert job_cores(tmp_path, "job") is None


def test_two_scripts_of_the_same_job_that_agree_give_the_cores(tmp_path):
    put_scripts(tmp_path, script(64), script(64))
    assert job_cores(tmp_path, "job") == 64


def test_only_a_qsub_of_the_folder_itself_counts(tmp_path):
    (tmp_path / "run.sh").write_text(script(32))
    (tmp_path / "inner").mkdir()
    (tmp_path / "inner" / "run.qsub").write_text(script(32))
    (tmp_path / "folder.qsub").mkdir()  # not a file
    assert job_cores(tmp_path, "job") is None
    (tmp_path / "RUN.QSUB").write_text(script(64))
    assert job_cores(tmp_path, "job") == 64


def test_a_folder_that_cannot_be_read_gives_no_cores(tmp_path):
    assert job_cores(tmp_path / "nao_existe", "job") is None


def test_a_script_with_a_bad_encoding_is_still_read(tmp_path):
    (tmp_path / "run.qsub").write_bytes(b"# caf\xe9\n" + script(64).encode())
    assert job_cores(tmp_path, "job") == 64


@pytest.mark.parametrize(
    ("name", "job"),
    [
        ("Bands-kao-001-p.o24000", "Bands-kao-001-p"),
        ("job.o123.4", "job"),
        ("job.o123-4", "job"),
        ("JOB.O123", "JOB"),
        ("run.qsub.o7", "run.qsub"),
    ],
)
def test_the_name_of_the_job_comes_from_the_log(name, job):
    match = JOB_STDOUT.match(name)
    assert match is not None and match["name"] == job


def test_the_log_of_a_job_array_is_judged_by_its_job(tmp_path):
    put_scripts(tmp_path, script(32))
    assert clean_job_log(tmp_path / "job.o1.3", HOST)
    assert not clean_job_log(tmp_path / "job.o1.3", HOST * 2)


def test_a_name_that_is_no_stdout_log_is_never_clean(tmp_path):
    put_scripts(tmp_path, script(32))
    assert not clean_job_log(tmp_path / "hosts.txt", HOST)


# -- in the sniff (R2) ------------------------------------------------------------------------------
def test_the_sniff_keeps_the_verdict_of_a_clean_log(tmp_path):
    put_scripts(tmp_path, script(32))
    (tmp_path / "job.o1").write_text(HOST)
    found = SniffCache().sniff(tmp_path / "job.o1")
    assert found.clean_job_log and found.kind is FileKind.UNKNOWN


def test_the_sniff_says_no_for_a_log_that_is_not_clean(tmp_path):
    put_scripts(tmp_path, script(64))
    (tmp_path / "count.o1").write_text(HOST)
    (tmp_path / "job.o1").write_text(HOST)
    (tmp_path / "empty.o1").write_text("")
    cache = SniffCache()
    assert not cache.sniff(tmp_path / "job.o1").clean_job_log
    assert cache.sniff(tmp_path / "count.o1").clean_job_log  # another job: no script says its cores
    assert not cache.sniff(tmp_path / "empty.o1").clean_job_log


def test_a_finished_qe_output_in_a_log_stays_a_qe_output(tmp_path):
    (tmp_path / "job.o1").write_bytes((FIXTURES / "al_bands" / "al.scf.out").read_bytes())
    found = SniffCache().sniff(tmp_path / "job.o1")
    assert found.kind is FileKind.PW_OUT and found.job_done is True
    assert not found.clean_job_log


def test_a_qe_output_after_the_machines_stays_a_qe_output(tmp_path):
    """A job without ``> scf.out``: the machines first, then what pw.x prints."""
    text = (FIXTURES / "al_bands" / "al.scf.out").read_text(encoding="utf-8")
    put_scripts(tmp_path, script(32))
    (tmp_path / "done.o1").write_text(HOST + text)
    (tmp_path / "job.o2").write_text(HOST + text[: text.index("JOB DONE")])
    cache = SniffCache()
    done, cut = cache.sniff(tmp_path / "done.o1"), cache.sniff(tmp_path / "job.o2")
    assert done.kind is FileKind.PW_OUT and done.job_done is True and not done.clean_job_log
    assert cut.kind is FileKind.PW_OUT and cut.job_done is False and not cut.clean_job_log


def test_a_log_bigger_than_the_head_is_not_clean(tmp_path):
    """Only the head is read: an error right after it must not pass for a log of machines. The head
    ends at the end of a line here, so it is all hostfile lines and only the size can tell."""
    machines = HOST * (HEAD_BYTES // len(HOST))
    head = "x" * (HEAD_BYTES - len(machines)) + machines  # a longer name in the first line
    assert len(head) == HEAD_BYTES
    (tmp_path / "whole.o1").write_text(head)
    (tmp_path / "bigger.o2").write_text(head + "Segmentation fault\n")
    cache = SniffCache()
    assert cache.sniff(tmp_path / "whole.o1").clean_job_log
    assert not cache.sniff(tmp_path / "bigger.o2").clean_job_log


def test_a_later_edit_of_the_script_counts_only_after_the_cache_forgets(tmp_path):
    """R2.2: the verdict is cached by the (mtime, size) of the log."""
    put_scripts(tmp_path, script(32))
    (tmp_path / "job.o1").write_text(HOST)
    cache = SniffCache()
    assert cache.sniff(tmp_path / "job.o1").clean_job_log
    put_scripts(tmp_path, script(64))
    assert cache.sniff(tmp_path / "job.o1").clean_job_log
    cache.invalidate(tmp_path)
    assert not cache.sniff(tmp_path / "job.o1").clean_job_log
