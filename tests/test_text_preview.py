"""What the text viewer shows of a file, read without Qt (spec 15 R5: ``core/text_preview``)."""

from pathlib import Path

from qe_studio.core.text_preview import read_preview

from conftest import FIXTURES

AL_SCF = FIXTURES / "al_bands" / "al.scf.out"
BROKEN = """&control
    calculation = 'scf',
    prefix = 'si
/
&system
    ecutwfc = 25
    conv_thr = 1.0e
/
&electrons
/
ATOMIC_SPECIES
 Si  28.086  Si.pz-rrkj.UPF
"""


def write(tmp_path: Path, text: str, name: str = "run.in") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_large_file_shows_head_and_tail(tmp_path):
    big = tmp_path / "big.out"
    big.write_bytes(b"HEAD\n" + b"x" * (5 * 1024 * 1024) + b"\nTAIL JOB DONE.\n")
    loaded = read_preview(big)
    text = loaded.text
    assert text.startswith("HEAD") and text.rstrip().endswith("JOB DONE.")
    assert "trecho omitido" in text and "Arquivo grande" in loaded.banner
    assert (loaded.level, loaded.truncated) == ("warning", True)
    log = tmp_path / "job.o9"
    big.rename(log)
    job = read_preview(log)
    assert job.banner.startswith("O job registrou mensagens de erro. Arquivo grande")
    assert job.level == "error" and job.highlight


def test_omitted_lines_count_what_the_marker_hides(tmp_path):
    lines = [f"line {n}\n" for n in range(1, 400_001)]
    path = tmp_path / "long.out"
    path.write_text("".join(lines))
    preview = read_preview(path)
    assert preview.truncated and preview.omitted_lines > 0
    line_map = preview.line_map
    last_head = line_map.number(line_map.marker_start - 1)
    first_tail = line_map.number(line_map.tail_block)
    assert first_tail - last_head - 1 == preview.omitted_lines
    whole = read_preview(write(tmp_path, "a\nb\n", "small.out"))
    assert not whole.truncated and whole.omitted_lines == 0


def test_loader_marks_outputs(tmp_path):
    assert read_preview(AL_SCF).highlight
    assert not read_preview(write(tmp_path, "just text\n", "a.txt")).highlight


def test_loader_returns_the_lint_with_the_text(tmp_path):
    loaded = read_preview(write(tmp_path, BROKEN))
    assert loaded.is_input and loaded.input_doc is not None
    assert [i.line for i in loaded.input_doc.issues] == [3, 7]
    plain = read_preview(write(tmp_path, "just text\n", "a.txt"))
    assert not plain.is_input and plain.input_doc is None


def test_empty_and_written_job_logs(tmp_path):
    empty = read_preview(write(tmp_path, "", "job.o1"))
    assert (empty.banner, empty.level) == ("Arquivo vazio: o job não registrou erros.", "success")
    errors = read_preview(write(tmp_path, "segfault\n", "job.e1"))
    assert (errors.banner, errors.level) == ("O job registrou mensagens de erro.", "error")
