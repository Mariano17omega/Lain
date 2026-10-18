"""Spec 50 R2: the run error of a folder (a CRASH file, a job stdout log with content)."""

import pytest

from qe_studio.core.file_kinds import is_job_log, is_job_stdout
from qe_studio.core.run_errors import RunError, run_error
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES


def put(folder, name, text=""):
    (folder / name).write_text(text)


def test_a_clean_folder_has_no_error(tmp_path):
    put(tmp_path, "scf.in", "&control\n/")
    put(tmp_path, "scf.out", "JOB DONE.")
    assert run_error(tmp_path) is None


@pytest.mark.parametrize("text", ["", "forrtl: severe\n"])
def test_a_crash_file_counts_whatever_its_size(tmp_path, text):
    put(tmp_path, "CRASH", text)
    assert run_error(tmp_path) == RunError("crash", "CRASH")


def test_an_empty_job_log_is_no_error_one_with_content_is(tmp_path):
    put(tmp_path, "job.o123")
    assert run_error(tmp_path) is None
    put(tmp_path, "job.o123", "x")
    assert run_error(tmp_path) == RunError("job_log", "job.o123")


def test_the_stderr_log_does_not_count(tmp_path):
    put(tmp_path, "job.e123", "mpirun: warning")
    assert run_error(tmp_path) is None


def test_a_job_array_log_counts(tmp_path):
    put(tmp_path, "job.o123.1", "boom")
    assert run_error(tmp_path) == RunError("job_log", "job.o123.1")


def test_crash_wins_over_a_job_log(tmp_path):
    put(tmp_path, "job.o1", "boom")
    put(tmp_path, "CRASH")
    assert run_error(tmp_path) == RunError("crash", "CRASH")


def test_of_several_logs_the_first_by_name_with_content_is_named(tmp_path):
    put(tmp_path, "job.o10", "b")
    put(tmp_path, "job.o02", "")
    put(tmp_path, "job.o03", "a")
    assert run_error(tmp_path) == RunError("job_log", "job.o03")


def test_only_the_folder_itself_is_read(tmp_path):
    inner = tmp_path / "inner"
    inner.mkdir()
    put(inner, "CRASH")
    put(inner, "job.o1", "boom")
    assert run_error(tmp_path) is None


def test_a_directory_is_not_a_crash_file_nor_a_log(tmp_path):
    (tmp_path / "CRASH").mkdir()
    (tmp_path / "job.o9").mkdir()
    assert run_error(tmp_path) is None


def test_a_missing_folder_or_a_file_is_no_error(tmp_path):
    assert run_error(tmp_path / "nao_existe") is None
    put(tmp_path, "file.txt", "x")
    assert run_error(tmp_path / "file.txt") is None


def test_a_log_holding_a_finished_qe_output_is_no_error(tmp_path):
    """A job without ``> scf.out`` prints pw.x into its log: finished, its grid row reads OK."""
    text = (FIXTURES / "al_bands" / "al.scf.out").read_text(encoding="utf-8")
    put(tmp_path, "job.o1", text)
    assert run_error(tmp_path, SniffCache().sniff) is None
    assert run_error(tmp_path) == RunError("job_log", "job.o1")  # no sniff: any content counts


def test_a_log_holding_a_truncated_qe_output_or_plain_text_is_an_error(tmp_path):
    text = (FIXTURES / "al_bands" / "al.scf.out").read_text(encoding="utf-8")
    put(tmp_path, "job.o1", text[: text.index("JOB DONE")])  # killed at the walltime
    put(tmp_path, "job.o2", "Segmentation fault\n")
    assert run_error(tmp_path, SniffCache().sniff) == RunError("job_log", "job.o1")
    (tmp_path / "job.o1").unlink()
    assert run_error(tmp_path, SniffCache().sniff) == RunError("job_log", "job.o2")


def test_a_broken_link_named_like_a_log_is_skipped(tmp_path):
    (tmp_path / "job.o5").symlink_to(tmp_path / "nowhere")
    put(tmp_path, "job.o6", "boom")
    assert run_error(tmp_path) == RunError("job_log", "job.o6")


def test_the_tooltip_names_the_file(tmp_path):
    assert RunError("crash", "CRASH").tooltip == "Erro de simulação: arquivo CRASH"
    assert RunError("job_log", "job.o7").tooltip == "Erro de simulação: job.o7 não está vazio"


@pytest.mark.parametrize(
    ("name", "stdout"),
    [
        ("job.o123", True),
        ("JOB.O123", True),
        ("job.o123.4", True),
        ("job.o123-4", True),
        ("job.e123", False),
        ("job.out", False),
        ("o123", False),
        ("job.o", False),
    ],
)
def test_job_stdout_is_the_o_half_of_the_job_log(tmp_path, name, stdout):
    assert is_job_stdout(tmp_path / name) is stdout


def test_the_stderr_half_stays_a_job_log_for_the_file_panels(tmp_path):
    assert is_job_log(tmp_path / "job.e123") and not is_job_stdout(tmp_path / "job.e123")
