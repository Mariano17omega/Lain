"""The log of the jobs Lain submitted (spec 71 R3): a table that reads in a text editor, written
whole, read back line by line; in the test's own data folder (``XDG_DATA_HOME``)."""

import pytest

from qe_studio.core.appdirs import data_dir
from qe_studio.core.remote.submit_log import (
    HEADER,
    Logged,
    log_path,
    logged_here,
    read_log,
    record,
)

ACCOUNT = "usuario@hpc.example"
BANDS = "/home/u/runs/ilita/Bands"


def test_the_log_lives_in_the_data_folder():
    assert log_path() == data_dir() / "submitted_jobs.log"
    assert read_log() == []  # none yet


def test_a_job_is_one_line_under_the_header():
    first = record(ACCOUNT, "24123", "Bands-kao-b", BANDS, "bands.qsub")
    second = record(ACCOUNT, "24124", "PDS-B", f"{BANDS}/../PDOS", "pdos.qsub")
    lines = log_path().read_text(encoding="utf-8").splitlines()
    assert lines[0] == HEADER == "# date_utc\taccount\tjob_id\tname\tremote_dir\tscript"
    assert lines[1].split("\t") == [
        first.date_utc,
        ACCOUNT,
        "24123",
        "Bands-kao-b",
        BANDS,
        "bands.qsub",
    ]
    assert first.date_utc.endswith("Z") and len(first.date_utc) == len("2026-10-26T14:03:12Z")
    assert read_log() == [first, second]


def test_a_line_that_cannot_be_read_is_skipped(tmp_path):
    path = tmp_path / "log"
    path.write_text(
        f"{HEADER}\n"
        "garbage\n"
        "2026-10-26T14:03:12Z\tusuario@h\t1\tname\t/x\n"  # a field short
        "2026-10-26T14:03:12Z\tusuario@h\t\tname\t/x\ts.qsub\n"  # an empty field
        "2026-10-26T14:03:12Z\tusuario@h\t2\tok\t/x\ts.qsub",  # no final newline
        encoding="utf-8",
    )
    assert read_log(path) == [
        Logged("2026-10-26T14:03:12Z", "usuario@h", "2", "ok", "/x", "s.qsub")
    ]
    record("usuario@h", "3", "next", "/x", "s.qsub", path)
    assert [entry.job_id for entry in read_log(path)] == ["2", "3"]  # appended on its own line


def test_a_file_without_the_header_gets_it(tmp_path):
    path = tmp_path / "log"
    path.write_text("2026-10-26T14:03:12Z\tusuario@h\t2\tok\t/x\ts.qsub\n", encoding="utf-8")
    record("usuario@h", "3", "next", "/x", "s.qsub", path)
    assert path.read_text(encoding="utf-8").startswith(HEADER + "\n2026-10-26T14:03:12Z")


def test_a_log_that_cannot_be_read_counts_as_empty(tmp_path):
    folder = tmp_path / "log"
    folder.mkdir()  # reading a folder fails with an OSError
    assert read_log(folder) == []


@pytest.mark.parametrize("field", ["a\tb", "a\nb", ""])
def test_a_field_that_would_break_the_table_is_refused(tmp_path, field):
    with pytest.raises(ValueError):
        record(ACCOUNT, "1", field, BANDS, "bands.qsub", tmp_path / "log")
    assert not (tmp_path / "log").exists()


def test_the_jobs_of_one_account_and_folder():
    record(ACCOUNT, "1", "a", BANDS, "bands.qsub")
    record(ACCOUNT, "2", "b", f"{BANDS}/", "bands.qsub")  # the same folder
    record(ACCOUNT, "3", "c", "/home/u/runs/other", "x.qsub")
    record("outro@hpc.example", "4", "d", BANDS, "bands.qsub")
    assert logged_here(read_log(), ACCOUNT, BANDS) == {("1", "a"), ("2", "b")}
