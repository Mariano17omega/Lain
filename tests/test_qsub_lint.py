"""Spec 38 R2.2, R2.5: the write checks of a ``.qsub`` script, without Qt."""

import pytest

from fragment_helpers import SMALL
from qe_studio.core.calc_create.types import REGISTRY
from qe_studio.core.files.job_script import job_name, pe_slots
from qe_studio.core.viewer import qsub_lint
from qe_studio.core.viewer.qsub_lint import SGE_OPTIONS, lint_script
from reference_helpers import REFERENCE, needs_reference

from calc_helpers import AL_PATH, JOBS, al, from_text
from surface_helpers import MOLECULE, SUPERCELL_001, read

HEAD = "#!/bin/bash\n"


def found(text: str) -> list[tuple[int, int, int, str]]:
    return [(i.line, i.col_start, i.col_end, i.severity) for i in lint_script(text)]


def messages(text: str) -> list[str]:
    return [i.message for i in lint_script(text)]


def generated_scripts():
    """The script of each type "Criar cálculo" makes (spec 25 R2), every one of ``REGISTRY``."""
    for calc_type in REGISTRY:
        scf, values = al(), {}
        if calc_type.id == "bandas":
            values = {"kpath": AL_PATH}
        elif calc_type.id == "charge_diff":
            scf, values = from_text(SMALL), {"atoms": (5, 6)}
        elif calc_type.id == "adsorption":  # a surface and a molecule (spec 42)
            scf, values = read(SUPERCELL_001), {"molecule": read(MOLECULE), "site": (43,)}
        plan = calc_type.plan(scf, values, JOBS, "avancado")
        assert not plan.errors, (calc_type.id, plan.errors)
        yield calc_type.id, plan.files[0].text


# -- what must be clean ------------------------------------------------------------------------
@needs_reference
def test_the_reference_scripts_have_no_problem():
    scripts = sorted(REFERENCE.glob("*.qsub"))
    assert len(scripts) == 6
    for path in scripts:
        assert lint_script(path.read_text()) == [], path.name


def test_every_generated_script_has_no_problem():
    scripts = dict(generated_scripts())
    assert len(scripts) == len(REGISTRY) == 11
    for type_id, text in scripts.items():
        assert lint_script(text) == [], type_id


def test_empty_text_has_no_problem():
    assert lint_script("") == [] and lint_script("  \n\n") == []


def test_a_bare_directive_and_a_comment_with_a_quote_are_fine():
    text = HEAD + "#$\n# it's fine, don't worry\necho ok # it's\nexit 0\n"
    assert found(text) == []


# -- one example per rule ----------------------------------------------------------------------
def test_crlf_is_one_error_on_the_first_line_with_a_carriage_return():
    text = "#!/bin/bash\r\necho a\r\necho b\r\n"
    # the span is the text of the line: the editor drops the \r, so a span on it shows nothing
    assert found(text) == [(1, 0, 11, "error")]
    assert "CRLF" in messages(text)[0]
    # the rest is read as if the \r were not there: no second problem
    assert found("#!/bin/bash\necho a\r\nif true; then\r\n  :\r\nfi\r\n") == [(2, 0, 6, "error")]


def test_an_unclosed_quote_is_an_error_at_the_line_where_it_opened():
    assert found(HEAD + 'echo "abc\nexit 0\n') == [(2, 5, 9, "error")]
    assert found(HEAD + "echo 'abc\nexit 0\n") == [(2, 5, 9, "error")]
    assert "Aspas '" in messages(HEAD + "echo 'abc\n")[0]


def test_a_string_on_two_lines_is_valid():
    assert found(HEAD + 'echo "a\nb" > out\nexit 0\n') == []


def test_a_quote_escaped_or_inside_the_other_kind_does_not_open():
    assert found(HEAD + 'echo "it\'s" \\" "x"\nexit 0\n') == []
    assert found(HEAD + "echo 'say \"hi\"' ok\n") == []


def test_brace_that_is_never_closed():
    assert found(HEAD + "echo ${VAR\n") == [(2, 5, 10, "error")]
    assert found(HEAD + 'echo "${VAR"\n') == [(2, 6, 12, "error")]
    assert found(HEAD + "echo '${VAR'\n") == []  # single quotes: not an expansion
    assert found(HEAD + "echo ${A:-${B}}\n") == []
    assert found(HEAD + "echo ${A\necho ${B}\n") == [(2, 5, 8, "error")]  # } closes the second


def test_an_apostrophe_in_a_brace_inside_double_quotes_is_not_a_quote():
    # bash outside POSIX mode rejects it, ``sh`` accepts it: not wrong without ambiguity
    assert found(HEAD + 'echo "${X:-it\'s}"\necho ok\n') == []


@pytest.mark.parametrize(
    "script, line, columns, word",
    [
        ("if true; then\n  echo a\n", 2, (0, 2), "if"),
        ("echo a\nfi\n", 3, (0, 2), "fi"),
        ("for i in 1 2; do\n  echo $i\n", 2, (0, 3), "for"),
        ("while true; do\n  break\n", 2, (0, 5), "while"),
        ("until false; do\n  break\n", 2, (0, 5), "until"),
        ("echo a\ndone\n", 3, (0, 4), "done"),
        ("case $x in\n  a) echo;;\n", 2, (0, 4), "case"),
        ("echo a\nesac\n", 3, (0, 4), "esac"),
        ("echo a\ndo\n", 3, (0, 2), "do"),
    ],
)
def test_blocks_without_their_pair(script, line, columns, word):
    issues = lint_script(HEAD + script)
    assert [(i.line, i.col_start, i.col_end, i.severity) for i in issues] == [
        (line, *columns, "error")
    ]
    assert f"{word} " in issues[0].message or issues[0].message.startswith(word)


def test_blocks_that_are_balanced():
    text = HEAD + (
        "if [ -f x ]; then\n"
        "  for i in 1 2 3; do\n"
        '    echo "$i"\n'
        "  done\n"
        "elif true; then\n"
        "  while read l; do echo $l; done < in\n"
        "else\n"
        "  case $y in a|b) echo ok;; *) echo no;; esac\n"
        "fi\n"
    )
    assert found(text) == []


def test_a_keyword_that_is_an_argument_or_quoted_is_not_a_keyword():
    text = HEAD + 'echo if fi done esac\nFOO=if\n"if" x\n\\fi y\nls case\n'
    assert found(text) == []


def test_a_case_pattern_named_like_a_keyword_is_a_pattern():
    assert found(HEAD + "case $x in\n  fi) echo a;;\n  if) echo b;;\nesac\n") == []


def test_backslash_followed_by_a_space_breaks_the_continuation():
    assert found(HEAD + "echo a \\ \n  b\n") == [(2, 7, 9, "warning")]
    assert found(HEAD + "echo a \\\n  b\n") == []
    assert found(HEAD + "# a comment \\ \necho b\n") == []
    assert found(HEAD + "echo 'a \\ '\n") == []  # single quotes: literal


def test_a_continued_line_keeps_the_command_position():
    assert found(HEAD + "if true \\\n  ; then\n  :\nfi\n") == []
    assert found(HEAD + "echo a \\\n  fi\n") == []  # an argument, not a closer


# Each one is valid for ``bash -O extglob -n``.
VALID_NESTING = [
    # a word after a substitution, an array, a redirection
    "echo $(date) done\n",
    "echo job $(hostname) for step 1\n",
    "states=(done running)\n",
    "states=(done\n  fi # it's\n  running)\n",
    "echo hi &> done\n",
    "echo hi &>> done\n",
    "echo hi >& done\n",
    "> done\n",
    "diff <(echo done) <(echo fi) done\n",
    "ls @(done|fi).txt\n",
    "[[ $x =~ (done|fi) ]]\n",
    # a case inside a substitution or a subshell
    'nk=$(case "$sys" in\n a) echo 4 ;;\nesac)\n',
    "(case $x in a) echo ;; esac)\n",
    # arithmetic
    "if true; then\n  n=$(( 1 << k ))\nfi\n",
    "for i in 1 2; do\n  m=$((m<<i))\ndone\n",
    "if ((1<<k)) then :; fi\n",
    "for (( i=0; i<3; i++ )); do :; done\n",
    "for ((i=0;i<3;i++)) do :; done\n",
    "y=$(((1+2)*3))\n",
    "echo $((16#ff))\n",
    "echo $((1); (2))\n",
    # quotes inside a substitution inside quotes
    'x="$(echo "it\'s")"\n',
    'y="$(sed "s/\'//g" f)"\n',
    'x="a `echo "b"` c"\n',
    # patterns of a case
    "case $x in\n  for|while) echo ;;\nesac\n",
    "case $x in\n  do|done) echo ;;\nesac\n",
    "case $x in\n  (fi|done) echo;;\nesac\n",
    "case a in a|esac) echo ok;; esac\n",
    "case esac in (esac) echo ok;; esac\n",
    "case a in a) echo;& b) echo;;& c) echo;; esac\n",
    "case a in a) echo; esac\n",
    # backticks
    "x=`for f in a b; do echo $f; done`\n",
    "x=`while read l; do echo $l; done < f`\n",
    "x=`echo a # b`; echo c\n",
    # heredoc delimiters
    "cat <<!\nit's a body\n!\n",
    "cat <<1\nit's\n1\n",
    "cat <<$E\nit's\n$E\n",
    'cat <<E"O"F\nit\'s\nEOF\n',
    "cat <<\\EOF\nit's\nEOF\n",
    "cat <<''\nit's\n\necho ok\n",
    "x=$(cat <<EOF\nit's\nEOF\n)\n",
    # ${…} over several lines, with quotes inside
    'echo "${X:-\ndefault}"\n',
    "echo ${X:-\ndefault}\n",
    'echo ${X:-"}"}\n',
    'echo "${X:-"it\'s"}"\n',
    # comments, functions, subshells, closers in a row
    "x=$(echo a # it's )\n)\n",
    "f() { if a; then b; fi; }\n",
    "f () for i in a; do b; done\n",
    "while (true) do :; done\n",
    "if (true) then if true; then :; fi; fi\n",
    "for a in 1; do for b in 2; do :; done done\n",
    "if a; then if b; then c; fi fi\n",
    "while a; do case b in c) :;; esac done\n",
]


@pytest.mark.parametrize("script", VALID_NESTING)
def test_valid_nesting_has_no_problem(script):
    assert found(HEAD + script) == []


@pytest.mark.parametrize(
    "script, issues",
    [
        ("echo $(x); done\n", [(2, 11, 15)]),  # a real stray done, after a substitution
        ("x=$(if a; then b)\n", [(2, 4, 6)]),  # the block must end inside its own level
        ("x=`if a; then b`\n", [(2, 3, 5)]),
        ("(for i in 1; do b)\n", [(2, 1, 4)]),
        ('x=$(echo "abc\n', [(2, 9, 13)]),  # an open quote, inside an open substitution
        ("case a in a) echo;;\nfor\nesac\nesac\n", [(5, 0, 4)]),  # for is a pattern; 2nd esac stray
    ],
)
def test_real_errors_are_still_reported_through_the_nesting(script, issues):
    assert found(HEAD + script) == [(*issue, "error") for issue in issues]


def test_a_line_of_a_heredoc_inside_arithmetic_stays_arithmetic():
    """The ``fi`` after ``<< k`` must still be seen: ``k`` is an operand, not a delimiter."""
    assert found(HEAD + "n=$(( 1 << k ))\nfi\n") == [(3, 0, 2, "error")]


def test_a_failure_of_the_checker_is_logged_with_the_script(monkeypatch, caplog):
    def broken(_text):
        raise RuntimeError("boom")

    monkeypatch.setattr(qsub_lint, "_lint", broken)
    assert lint_script("x", "/runs/job.qsub") == []
    assert caplog.records[-1].getMessage() == "file: cannot check /runs/job.qsub"


def test_unknown_option_of_a_directive_is_a_warning():
    assert found(HEAD + "#$ -zz\n") == [(2, 3, 6, "warning")]
    assert "-zz" in messages(HEAD + "#$ -zz\n")[0]
    assert found(HEAD + '#$ -N "x" -pe physica 8 -cwd -wd /tmp -qq 1\n') == [(2, 38, 41, "warning")]


def test_the_known_options_and_negative_values_raise_no_warning():
    options = "-N job -cwd -j y -hold_jid 12 -binding linear:2 -S /bin/bash -V"
    assert found(HEAD + f"#$ {options}\n") == []
    assert found(HEAD + "#$ -hard -l h_vmem=2G -tc 10 -p -5\n") == []
    assert {"hard", "soft", "tc", "notify", "shell"} <= SGE_OPTIONS
    assert found(HEAD + "#$ -jsv /a -display b:0 -xd c -clearp\n") == []


def test_pe_needs_the_environment_and_the_slots():
    assert found(HEAD + "#$ -pe physica 64\n") == []
    assert found(HEAD + "#$ -pe physica 4-8 -cwd\n") == []
    assert found(HEAD + "#$ -pe physica\n") == [(2, 3, 6, "error")]
    assert found(HEAD + "#$ -pe\n") == [(2, 3, 6, "error")]
    assert found(HEAD + "#$ -pe physica -cwd\n") == [(2, 3, 6, "error")]


def test_n_needs_a_name():
    assert found(HEAD + '#$ -N "BD010o1"\n') == []
    assert found(HEAD + "#$ -N\n") == [(2, 3, 5, "error")]
    assert found(HEAD + '#$ -N ""\n') == [(2, 3, 5, "error")]
    assert found(HEAD + "#$ -N -cwd\n") == [(2, 3, 5, "error")]


def test_a_directive_is_read_wherever_it_stands():
    """SGE scans the whole file for ``#$``: a heredoc does not hide it."""
    text = HEAD + "cat > x << EOF\n#$ -zz\nEOF\n"
    assert found(text) == [(3, 3, 6, "warning")]


def test_missing_shebang_is_a_warning_on_the_first_line():
    assert found("echo hi\n") == [(1, 0, 7, "warning")]
    assert found("\necho hi\n") == [(1, 0, 0, "warning")]
    assert found("#!/usr/bin/env bash\necho hi\n") == []


# -- heredocs ----------------------------------------------------------------------------------
def test_a_heredoc_body_is_not_shell():
    text = HEAD + "cat > a.in << EOF\n&X\n  prefix = 'al\n  s = \"${x\nif\nEOF\necho ok\n"
    assert found(text) == []
    quoted = HEAD + "cat << 'END' > a\n  don't ${\nEND\ncat <<-DONE\n\tit's\n\tDONE\n"
    assert found(quoted) == []


def test_the_text_after_a_heredoc_is_checked_again():
    text = HEAD + 'cat << EOF\nx\nEOF\necho "open\n'
    assert found(text) == [(5, 5, 10, "error")]


def test_a_here_string_is_not_a_heredoc():
    assert found(HEAD + "cat <<< word\nif\n") == [(3, 0, 2, "error")]


def test_a_delimiter_with_trailing_text_does_not_close_the_heredoc():
    # bash needs the delimiter alone on its line: the body goes on (and nothing in it is checked)
    assert found(HEAD + "cat << EOF\nEOF x\nif\n") == []


# -- the result --------------------------------------------------------------------------------
def test_issues_are_sorted_and_fit_their_line():
    text = 'echo "a\nif true\n${B\nfi\nfi\n#$ -zz\n'
    issues = lint_script(text)
    assert len(issues) >= 3
    assert issues == sorted(issues, key=lambda i: (i.line, i.col_start))
    lines = text.split("\n")
    for issue in issues:
        assert 1 <= issue.line <= len(lines)
        assert 0 <= issue.col_start <= issue.col_end <= len(lines[issue.line - 1])


# -- the job name (spec 71 R3) ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("script", "name"),
    [
        ('#!/bin/bash\n#$ -N "BD010o1"\n#$ -cwd\n', "BD010o1"),
        ("#!/bin/bash\n#$ -N scf-al -pe physica 64\n", "scf-al"),
        ("#!/bin/bash\n#$ -N 'first'\n#$ -N second\n", "second"),  # the last one counts
        ("#!/bin/bash\n#$ -cwd # -N comment\n", "run.qsub"),
        ("#!/bin/bash\n#$ -N\n#$ -N -cwd\n", "run.qsub"),  # no value: SGE's default
        ("#!/bin/bash\n# $ -N spaced\necho -N x\n", "run.qsub"),  # not directives
        ("", "run.qsub"),
    ],
)
def test_the_job_name_is_the_last_n_or_the_script_name(script, name):
    assert job_name(script, "run.qsub") == name


@needs_reference
def test_the_reference_scripts_name_their_jobs():
    path = REFERENCE / "bands.qsub"
    assert job_name(path.read_text(), path.name) == "BD010o1"


# -- the slots of a job (spec 85 R1) ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("script", "slots"),
    [
        ('#!/bin/bash\n#$ -N "Bands-kao"\n#$ -pe physica 32\n#$ -cwd -j y -notify\n', 32),
        ("#$ -N scf-al -pe physica 64 -cwd\n", 64),  # in the middle of a line with other options
        ("#$-pe physica 128\n", 128),
        ('#$ -pe "physica" "64"\n', 64),
        ("#$ -pe physica 64 # the whole node\n", 64),
        ("#$ -pe physica 32\n#$ -pe physica 64\n", 64),  # the last one counts
        ("#$ -pe physica 32\n#$ -pe physica 32-64\n", None),  # also when it says nothing
        ("#$ -pe physica 32-64\n", None),  # a range
        ("#$ -pe physica\n", None),
        ("#$ -pe\n", None),
        ("#$ -pe physica -cwd\n", None),
        ("#$ -cwd # -pe physica 64\n", None),  # a comment
        ("#!/bin/bash\n# $ -pe physica 64\necho -pe physica 64\n", None),  # not directives
        ("#!/bin/bash\n#$ -N job\n", None),
        ("", None),
    ],
)
def test_the_slots_are_those_of_the_last_pe(script, slots):
    assert pe_slots(script) == slots


def test_the_slots_are_read_with_crlf_line_ends():
    assert pe_slots("#!/bin/bash\r\n#$ -pe physica 64\r\n") == 64


@pytest.mark.parametrize("separator", ["\f", "\x85", " ", "\v", "\x1c"])
def test_only_a_newline_ends_a_directive_line(separator):
    assert job_name(f"# note{separator}#$ -N fake\n", "run.qsub") == "run.qsub"
    assert pe_slots(f"#$ -pe mpi 8 {separator}#$ -pe mpi 16\n") == 8
