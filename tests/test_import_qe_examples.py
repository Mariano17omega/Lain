"""``scripts/import_qe_examples.py``: how a ``run_example`` is read, and that the corpus is its work."""

import filecmp
import importlib.util
import sys
from pathlib import Path

import pytest

from reference_helpers import needs_reference

from conftest import QE_EXAMPLES

ROOT = Path(__file__).parents[1]


def load_importer():
    spec = importlib.util.spec_from_file_location(
        "import_qe_examples", ROOT / "scripts" / "import_qe_examples.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


importer = load_importer()


def extract(text: str):
    return importer.extract_script(text)


def test_reads_a_heredoc_and_the_run_that_uses_it():
    found = extract("cat > a.in << EOF\n&control\n/\nEOF\n$PW_COMMAND < a.in > a.out\n")
    assert found.inputs == {"a.in": "&control\n/\n"}
    assert [(r.command, r.input, r.output) for r in found.runs] == [("PW_COMMAND", "a.in", "a.out")]


def test_reads_the_redirection_after_the_delimiter():
    assert extract("cat <<EOF > b.in\nx\nEOF\n").inputs == {"b.in": "x\n"}


def test_replaces_the_folders_with_placeholders():
    text = "cat > a.in << EOF\npseudo_dir='$PSEUDO_DIR/'\noutdir='$TMP_DIR/'\nEOF\n"
    assert extract(text).inputs["a.in"] == (
        "pseudo_dir='/home/seu_usuario/PSEUDO/'\noutdir='/home/seu_usuario/tmp/'\n"
    )


def test_a_quoted_delimiter_expands_nothing():
    text = "cat > a.in << 'EOF'\n$PSEUDO_DIR\nEOF\n"
    assert extract(text).inputs["a.in"] == "$PSEUDO_DIR\n"


def test_expands_a_loop_in_names_and_bodies():
    text = (
        "for d in david cg ; do\n"
        "cat > s.$d.in << EOF\nsolver='$d'\nEOF\n"
        "$PW_COMMAND < s.$d.in > s.$d.out\n"
        "done\n"
    )
    found = extract(text)
    assert found.inputs == {"s.david.in": "solver='david'\n", "s.cg.in": "solver='cg'\n"}
    assert [r.output for r in found.runs] == ["s.david.out", "s.cg.out"]


def test_do_on_its_own_line_and_a_quoted_list():
    text = 'LIST="1 2"\nfor n in $LIST\ndo\ncat > n$n.in << EOF\nEOF\ndone\n'
    assert sorted(extract(text).inputs) == ["n1.in", "n2.in"]


def test_a_nested_loop():
    text = "for a in 1 2 ; do\nfor b in x y ; do\ncat > $a$b.in << EOF\nEOF\ndone\ndone\n"
    assert sorted(extract(text).inputs) == ["1x.in", "1y.in", "2x.in", "2y.in"]


def test_a_run_sees_the_input_as_it_was_then():
    """A script that rewrites one input in a loop: each run read its own version."""
    text = "for n in 1 2 ; do\ncat > a.in << EOF\nn=$n\nEOF\n$PW_COMMAND < a.in > a$n.out\ndone\n"
    assert [(r.output, r.text) for r in extract(text).runs] == [
        ("a1.out", "n=1\n"),
        ("a2.out", "n=2\n"),
    ]


def test_echo_and_comments_are_no_runs():
    text = '$ECHO "running $PW_COMMAND < a.in > a.out"\n# $PW_COMMAND < a.in > a.out\n'
    assert extract(text).runs == []


@pytest.mark.parametrize(
    ("source", "landed"),
    [
        ("PW/examples/example01/reference/a.out", "PW/example01/a.out"),
        ("PP/examples/ACF_example/reference_pbe/a.out", "PP/ACF_example/reference_pbe/a.out"),
        ("test-suite/pw_scf/benchmark.out.git.inp=scf.in", "test-suite/pw_scf/scf.out"),
        ("test-suite/pw_w/benchmark.out.git.inp=a-1.in.args=1", "test-suite/pw_w/a-1.out"),
    ],
)
def test_where_a_file_lands(source, landed):
    assert importer.destination(source).as_posix() == landed


@pytest.mark.parametrize(
    ("version", "supported"),
    [("7.1", True), ("7.3.1", True), ("7.0", False), ("6.8", False), (None, False)],
)
def test_support_follows_the_version(version, supported):
    assert importer.is_supported(version) is supported


def test_refuses_a_target_with_files(tmp_path, capsys):
    (tmp_path / "source").mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "kept").write_text("x")
    args = ["--source", str(tmp_path / "source"), "--target", str(target)]
    assert importer.main(args) == 1
    assert (target / "kept").read_text() == "x"
    assert "not empty" in capsys.readouterr().out


def test_says_when_the_sources_are_missing(tmp_path, capsys):
    assert importer.main(["--source", str(tmp_path / "gone"), "--target", str(tmp_path)]) == 1
    assert "not found" in capsys.readouterr().out


@needs_reference
def test_the_corpus_is_what_the_importer_writes(tmp_path):
    importer.build(importer.SOURCE, tmp_path)

    def tree(root: Path) -> set[str]:
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}

    assert tree(tmp_path) == tree(QE_EXAMPLES)
    names = sorted(tree(QE_EXAMPLES))
    _same, different, errors = filecmp.cmpfiles(tmp_path, QE_EXAMPLES, names, shallow=False)
    assert not different and not errors


@needs_reference
def test_the_selection_covers_every_combination_of_the_sources():
    """Each (calculation, variation) the QE sources hold has a case in the corpus."""
    every = importer.combinations(importer.catalog(importer.SOURCE))
    chosen = importer.combinations(importer.selected(importer.SOURCE))
    assert every - chosen == set()


@needs_reference
def test_the_lists_name_real_runs():
    known = {case.relative_output(importer.SOURCE) for case in importer.catalog(importer.SOURCE)}
    chosen = {*importer.COVERAGE, *importer.POST_PROCESSING, *importer.KNOWN_LIMITS}
    assert chosen - known == set()
    assert all((importer.SOURCE / name).is_file() for name in importer.DATA_FILES)
