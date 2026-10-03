"""Output summary extractor (spec 12 R1, R2): no Qt."""

from __future__ import annotations

import pytest

from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.qe.summary import OutputSummary, summarize, summarize_lines, to_text
from qe_studio.core.qe.summary.text import (
    clock_text,
    duration_text,
    format_duration,
    normalize_number,
    parse_qe_time,
)

from conftest import FIXTURES, copy_fixture

AL_SCF = FIXTURES / "al_bands" / "al.scf.out"
BANDS_X = FIXTURES / "al_bands" / "bands.out"
VC_RELAX = FIXTURES / "kao_vc_relax" / "vc-relax.out"
SI_RELAX = FIXTURES / "si_relax" / "si.rel.out"
NI_SCF = FIXTURES / "qe731_ni_spin_bands" / "ni.scf.out"


def rows(summary: OutputSummary, title: str) -> dict:
    (section,) = [s for s in summary.sections if s.title == title]
    return {row.label: row for row in section.rows}


def titles(summary: OutputSummary) -> list[str]:
    return [section.title for section in summary.sections]


def from_text(text: str) -> OutputSummary:
    return summarize_lines(text.splitlines(keepends=True), parse_pw_output(text))


HEAD = "     Program PWSCF v.7.3.1 starts on  3Jan2025 at  6:59:51 \n\n"
ERROR_BLOCK = (
    " %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n"
    "     Error in routine cdiaghg (3):\n"
    "     S matrix not positive definite\n"
    " %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n"
)


# -- acceptance: real fixtures ----------------------------------------------------------------
def test_scf_output():
    summary = summarize(AL_SCF)
    assert summary.program == "PWSCF"
    assert titles(summary) == ["Geral", "Sistema", "Resultados", "Avisos e erros"]
    general, system, results = (rows(summary, t) for t in ("Geral", "Sistema", "Resultados"))
    assert general["Programa"].value == "PWSCF 7.3.1"
    assert (general["Estado"].value, general["Estado"].level) == ("Concluído", "success")
    assert general["Tempo (WALL)"].value == "1.90 s"
    assert general["Tempo (CPU)"].value == "1.88 s"
    assert general["Paralelização"].value == "Serial"
    assert general["Início"].value == "3Jan2025 6:59:51"
    assert general["Término"].value == "3Jan2025 6:59:53"
    assert system["Cálculo"].value == "scf"
    assert system["Fórmula"].value == "Al"
    assert system["Cutoff da função de onda"].value == "100.0 Ry"
    assert system["Cutoff da densidade de carga"].value == "143.0 Ry"
    assert system["Funcional (XC)"].value == "PBE"
    assert system["k-pontos"].value == "47"
    assert "Gaussian" in system["Smearing"].value and "0.0100" in system["Smearing"].value
    assert system["Spin"].value == "não polarizado"
    assert results["Energia total"].value == "-5.03855495 Ry"
    assert results["Energia de Fermi"].value == "8.0584 eV"
    assert (results["SCF"].value, results["SCF"].level) == ("Convergiu em 4 iterações", "success")
    messages = [(issue.routine, issue.message) for issue in summary.issues]
    assert ("set_cutoff", "ecutrho < 4*ecutwfc, are you sure?") in messages
    assert all(issue.level == "warning" for issue in summary.issues)


def test_rows_know_their_line():
    summary = summarize(AL_SCF)
    lines = AL_SCF.read_text().splitlines()
    energy = rows(summary, "Resultados")["Energia total"]
    assert energy.line is not None and lines[energy.line - 1].startswith("!")
    warning = next(issue for issue in summary.issues if issue.routine == "set_cutoff")
    assert warning.line is not None and "Message from routine set_cutoff" in lines[warning.line - 1]


def test_vc_relax_output():
    summary = summarize(VC_RELAX)
    general, system, results = (rows(summary, t) for t in ("Geral", "Sistema", "Resultados"))
    pseudos = system["Pseudopotenciais"]
    assert pseudos.value == "4"
    assert [child.label for child in pseudos.children] == ["Al", "H", "O", "Si"]  # no repeats
    assert pseudos.children[0].value == "Al.pbe-nl-kjpaw_psl.1.0.0.UPF"
    assert system["Cálculo"].value == "vc-relax"
    assert system["Átomos na célula"].value == "34"
    assert results["Força total"].value == "0.000433 Ry/Bohr"  # the last one
    assert results["Pressão"].value == "0.08 kbar"
    assert [child.value for child in results["Pressão"].children][0] == "0.11  0.01  0.07"
    assert results["Passos BFGS"].value != "0"
    assert results["BFGS"].value.startswith("Convergiu") and results["BFGS"].level == "success"
    assert results["Entalpia final"].value == "-1107.4641917963 Ry"
    assert results["E inicial"].value != results["E final"].value
    assert results["Volume (inicial → final)"].value == "2218.2317 → 2253.94778 a.u.^3"
    assert general["Paralelização"].value == "MPI, 64 processadores"
    assert general["Divisão de k-pontos (npool)"].value == "8"
    assert general["RAM máx. estimada por processo"].value == "103.84 MB"  # printed twice: last
    assert general["Tempo (WALL)"].value == "1h 15min 00s"
    assert "HOMO" in results  # fixed occupations: no Fermi energy


def test_relax_final_energy():
    results = rows(summarize(SI_RELAX), "Resultados")
    assert results["Energia final (BFGS)"].value == "-15.8682760727 Ry"
    assert results["BFGS"].level == "success"
    assert "Pressão" not in results  # a fixed-cell relax prints no stress


def test_bands_x_output_has_only_general_and_messages():
    summary = summarize(BANDS_X)
    assert summary.program == "BANDS"
    assert titles(summary) == ["Geral", "Avisos e erros"]
    general = rows(summary, "Geral")
    assert general["Estado"].value == "Concluído"
    assert general["Início"].value == "3Jan2025 7:00:07"  # QE pads the clock with spaces
    assert [child.value for child in general["Arquivos escritos"].children] == [
        "bands.dat.gnu",
        "bands.dat",
    ]
    assert rows(summary, "Avisos e erros")["Mensagens"].value == "Nenhum aviso ou erro"


def test_spin_polarized_output_reports_the_last_magnetization():
    results = rows(summarize(NI_SCF), "Resultados")
    assert results["Magnetização total"].value == "0.71 Bohr mag/cell"
    assert results["Magnetização absoluta"].value == "0.81 Bohr mag/cell"
    assert rows(summarize(NI_SCF), "Sistema")["Spin"].value == "colinear (nspin=2)"


# -- truncated, errors, odd inputs ------------------------------------------------------------
def test_truncated_output_is_incomplete(tmp_path):
    out = copy_fixture("al_bands", tmp_path) / "al.scf.out"
    lines = out.read_text().splitlines(keepends=True)
    out.write_text("".join(lines[:300]))
    summary = summarize(out)
    state = rows(summary, "Geral")["Estado"]
    assert (state.value, state.level) == ("Incompleto", "warning")
    results = rows(summary, "Resultados")
    assert "Energia total" not in results  # the "!" line is at 390
    assert results["SCF"].value.startswith("Em andamento")


def test_error_block_sets_the_state_and_lists_the_routine():
    summary = from_text(HEAD + "     some line\n" + ERROR_BLOCK + "     Program stopped\n")
    state = rows(summary, "Geral")["Estado"]
    assert (state.value, state.level) == ("Erro", "error")
    (issue,) = summary.issues
    assert (issue.level, issue.routine, issue.message) == (
        "error",
        "cdiaghg",
        "S matrix not positive definite",
    )
    row = rows(summary, "Avisos e erros")["Erro em cdiaghg"]
    assert (row.value, row.level) == ("S matrix not positive definite", "error")
    assert row.line == 4  # the opening bar


def test_error_block_still_open_at_the_end_of_a_cut_file():
    summary = from_text(HEAD + ERROR_BLOCK.rsplit("\n", 2)[0] + "\n")
    assert [issue.routine for issue in summary.issues] == ["cdiaghg"]
    assert rows(summary, "Geral")["Estado"].value == "Erro"


def test_bar_without_a_message_is_not_an_issue():
    summary = from_text(HEAD + " %%%%%%%%%%%%%%%%\n")
    assert summary.issues == ()
    assert rows(summary, "Geral")["Estado"].value == "Incompleto"


def test_repeated_warnings_are_folded():
    message = "     Message from routine setup:\n     no reason to have ecutrho>4*ecutwfc\n"
    summary = from_text(HEAD + message + "\n" + message + message)
    (issue,) = summary.issues
    assert issue.count == 3
    assert rows(summary, "Avisos e erros")["setup"].value.endswith("(×3)")


def test_warning_message_may_follow_a_blank_line():
    summary = from_text(HEAD + "     Message from routine setup :\n\n     the message\n")
    assert [(i.routine, i.message) for i in summary.issues] == [("setup", "the message")]


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ("     Noncollinear calculation without spin-orbit\n", "não colinear"),
        ("     Noncollinear calculation with spin-orbit\n", "spin-órbita"),
        ("     Starting magnetic structure\n", "colinear (nspin=2)"),
    ],
)
def test_spin_kinds(extra, expected):
    assert rows(from_text(HEAD + extra), "Sistema")["Spin"].value == expected


def test_noncollinear_magnetization_keeps_the_three_components():
    text = HEAD + "     total magnetization       =     0.00     0.00     1.50 Bohr mag/cell\n"
    assert rows(from_text(text), "Resultados")["Magnetização total"].value.startswith("0.00")


def test_parallel_and_gpu_lines_of_recent_versions():
    text = (
        HEAD
        + "     Parallel version (MPI & OpenMP), running on     128 processor cores\n"
        + "     Number of MPI processes:                64\n"
        + "     Threads/MPI process:                     2\n"
        + "     GPU acceleration is ACTIVE.\n"
    )
    general = rows(from_text(text), "Geral")
    assert general["Paralelização"].value == "MPI & OpenMP, 128 processadores"
    assert general["Processos MPI"].value == "64"
    assert general["Threads por processo MPI"].value == "2"
    assert general["GPU"].value == "Ativa"


def test_routine_timing_lines_are_not_the_total_time():
    text = HEAD + "     init_run     :      0.04s CPU      0.04s WALL (       1 calls)\n"
    assert "Tempo (WALL)" not in rows(from_text(text), "Geral")


def test_empty_text_has_a_state_and_no_exception():
    summary = from_text("")
    assert summary.program is None
    assert titles(summary) == ["Geral", "Avisos e erros"]
    assert rows(summary, "Geral")["Programa"].value == "—"
    assert rows(summary, "Geral")["Estado"].value == "Incompleto"


def test_summarize_creates_no_file(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    before = sorted(p.name for p in folder.iterdir())
    summarize(folder / "al.scf.out")
    assert sorted(p.name for p in folder.iterdir()) == before


def test_unreadable_path_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        summarize(tmp_path / "missing.out")


# -- plain text and formatting ----------------------------------------------------------------
def test_to_text_has_one_block_per_section():
    text = to_text(summarize(AL_SCF))
    blocks = text.strip().split("\n\n")
    assert [block.splitlines()[0] for block in blocks] == [
        "GERAL",
        "SISTEMA",
        "RESULTADOS",
        "AVISOS E ERROS",
    ]
    assert "WALL" in text and "Concluído" in text
    assert "  Al  " in text  # the pseudopotential child is indented under its parent


@pytest.mark.parametrize(
    ("field", "seconds"),
    [
        ("1.88s", 1.88),
        ("1h10m", 4200),
        ("3h 4m", 11040),
        ("38m32.15s", 2312.15),
        ("40m 7.94s", 2407.94),
    ],
)
def test_parse_qe_time(field, seconds):
    assert parse_qe_time(field) == pytest.approx(seconds)


def test_parse_qe_time_of_garbage():
    assert parse_qe_time("n/a") is None
    assert duration_text("n/a") == "n/a"


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (1.9, "1.90 s"),
        (59.99, "59.99 s"),
        (59.996, "1min 00s"),
        (125, "2min 05s"),
        (3725, "1h 02min 05s"),
        (4500.4, "1h 15min 00s"),
    ],
)
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text


def test_number_and_clock_text():
    assert normalize_number("100.0000") == "100.0"
    assert normalize_number("0.0100") == "0.01"
    assert normalize_number("144.00") == "144.0"
    assert normalize_number("34") == "34"
    assert normalize_number("1.0E-05") == "1.0E-05"
    assert clock_text(" 7: 0: 9") == "7:00:09"
    assert clock_text("odd") == "odd"
