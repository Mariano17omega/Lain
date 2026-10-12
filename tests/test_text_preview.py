"""What the text viewer shows of a file, read without Qt (spec 15 R5: ``core/text_preview``)."""

from pathlib import Path

from qe_studio.core.text_preview import MARKDOWN_RENDER_LIMIT, read_preview

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


# -- Markdown and scripts (spec 38) ------------------------------------------------------------
def test_markdown_is_renderable_up_to_the_limit(tmp_path):
    small = read_preview(write(tmp_path, "# Titulo\n\ntexto\n", "LEIA.md"))
    assert small.is_markdown and small.renderable and small.banner == ""
    assert not small.is_input and not small.is_script and small.issues == []
    assert read_preview(write(tmp_path, "# T\n", "LEIA.markdown")).renderable
    plain = read_preview(write(tmp_path, "# T\n", "notas.txt"))
    assert not plain.is_markdown and not plain.renderable


def test_markdown_over_the_limit_says_it_is_shown_as_text(tmp_path):
    text = "x" * (MARKDOWN_RENDER_LIMIT + 1)
    big = read_preview(write(tmp_path, text, "grande.md"))
    assert big.is_markdown and not big.renderable and not big.truncated
    assert big.banner.startswith("Markdown grande (1.0 MB): exibido como texto")
    assert len(big.text) == len(text)  # the text is whole, only not rendered
    just = read_preview(write(tmp_path, "x" * MARKDOWN_RENDER_LIMIT, "justo.md"))
    assert just.renderable and just.banner == ""


def test_markdown_cut_by_the_reader_keeps_its_own_banner_and_is_not_rendered(tmp_path):
    path = tmp_path / "enorme.md"
    path.write_bytes(b"# Cabeca\n" + b"x" * (5 * 1024 * 1024) + b"\n# Cauda\n")
    loaded = read_preview(path)
    assert loaded.truncated and not loaded.renderable
    assert loaded.banner.startswith("Arquivo grande") and "Markdown grande" not in loaded.banner


def test_markdown_that_looks_like_an_input_is_still_markdown(tmp_path):
    loaded = read_preview(write(tmp_path, "&control\n  calculation = 'scf'\n/\n", "nota.md"))
    assert loaded.is_markdown and not loaded.is_input and loaded.input_doc is None


def test_qsub_is_a_script_with_its_issues_and_never_an_input(tmp_path):
    clean = read_preview(write(tmp_path, "#!/bin/bash\necho ok\n", "job.qsub"))
    assert clean.is_script and clean.issues == [] and not clean.is_input and not clean.highlight
    broken = read_preview(write(tmp_path, "#!/bin/bash\nif true; then\n", "job.qsub"))
    assert [(i.line, i.severity) for i in broken.issues] == [(2, "error")]
    heredoc = "#!/bin/bash\ncat > a.in << EOF\n&control\n  calculation = 'scf'\n/\nEOF\n"
    assert not read_preview(write(tmp_path, heredoc, "job.qsub")).is_input


def test_big_script_is_not_checked_and_says_so(tmp_path):
    from qe_studio.core.sniff import INPUT_READ_LIMIT

    line = "echo ok  # linha de enchimento do script\n"
    text = '#!/bin/bash\necho "aberta\n' + line * (INPUT_READ_LIMIT // len(line) + 5)
    loaded = read_preview(write(tmp_path, text, "grande.qsub"))
    assert loaded.is_script and loaded.issues == []
    assert loaded.banner.startswith("Script grande (") and "não foi verificada" in loaded.banner
