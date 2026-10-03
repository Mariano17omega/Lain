"""Facts of a scanned output → the sections and rows of the summary (spec 12 R2).

Labels and values are Portuguese (user-facing); numbers keep QE's decimal point.
"""

from __future__ import annotations

from ..pw_output import PwOutput
from ..relax import RelaxData
from .model import Level, OutputSummary, SummaryIssue, SummaryRow, SummarySection
from .scan import Facts, Hit
from .text import clock_text, duration_text, normalize_number

RELAX_CALCULATIONS = ("relax", "vc-relax")
PW_PROGRAM = "PWSCF"


def _row(
    label: str,
    value: str,
    hit: Hit | None = None,
    level: Level | None = None,
    children: tuple[SummaryRow, ...] = (),
) -> SummaryRow:
    return SummaryRow(label, value, level, hit.line if hit else None, children)


def _group(hit: Hit | None, index: int = 0) -> str | None:
    return hit.groups[index] if hit else None


def build_summary(facts: Facts, pw: PwOutput | None, relax: RelaxData | None) -> OutputSummary:
    sections = [SummarySection("Geral", tuple(_general(facts)))]
    if facts.program == PW_PROGRAM:
        for title, rows in (
            ("Sistema", _system(facts, pw)),
            ("Resultados", _results(facts, pw, relax)),
        ):
            if rows:
                sections.append(SummarySection(title, tuple(rows)))
    sections.append(SummarySection("Avisos e erros", tuple(_issue_rows(facts.issues))))
    return OutputSummary(facts.program, tuple(sections), tuple(facts.issues))


# -- Geral --------------------------------------------------------------------------------------
def _general(facts: Facts) -> list[SummaryRow]:
    program = facts.hit("program", first=True)
    rows = [
        _row("Programa", f"{_group(program, 0)} {_group(program, 1)}" if program else "—", program),
        _state_row(facts),
    ]
    if program and program.groups[2]:
        rows.append(
            _row("Início", f"{program.groups[2]} {clock_text(program.groups[3] or '')}", program)
        )
    if ended := facts.hit("ended"):
        rows.append(
            _row("Término", f"{ended.groups[1]} {clock_text(ended.groups[0] or '')}", ended)
        )
    if timing := facts.hit("time"):
        rows.append(_row("Tempo (WALL)", duration_text(timing.groups[2] or ""), timing))
        rows.append(_row("Tempo (CPU)", duration_text(timing.groups[1] or ""), timing))
    rows += _parallel_rows(facts)
    rows += _memory_rows(facts)
    if written := facts.items.get("written"):
        names = dict.fromkeys(hit.groups[0] or "" for hit in written)
        children = tuple(
            _row("Arquivo", name, next(h for h in written if h.groups[0] == name)) for name in names
        )
        rows.append(_row("Arquivos escritos", str(len(names)), children=children))
    return rows


def _state_row(facts: Facts) -> SummaryRow:
    errors = [issue for issue in facts.issues if issue.level == "error"]
    if errors:
        return SummaryRow("Estado", "Erro", "error", errors[0].line)
    if done := facts.hit("job_done", first=True):
        return _row("Estado", "Concluído", done, "success")
    return SummaryRow("Estado", "Incompleto", "warning")


def _parallel_rows(facts: Facts) -> list[SummaryRow]:
    rows = []
    if serial := facts.hit("serial"):
        rows.append(_row("Paralelização", "Serial", serial))
    elif parallel := facts.hit("parallel"):
        flavor, count = parallel.groups
        rows.append(_row("Paralelização", f"{flavor}, {count} processadores", parallel))
    for key, label, suffix in (
        ("mpi", "Processos MPI", ""),
        ("threads", "Threads por processo MPI", ""),
        ("nodes", "Nós", ""),
        ("npool", "Divisão de k-pontos (npool)", ""),
        ("rg_division", "Divisão R & G (proc/nbgrp/npool/nimage)", ""),
    ):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]}{suffix}", hit))
    if gpu := facts.hit("gpu"):
        rows.append(_row("GPU", "Ativa", gpu))
    return rows


def _memory_rows(facts: Facts) -> list[SummaryRow]:
    rows = []
    for key, label, unit in (
        ("memory", "Memória disponível", " MiB"),
        ("ram_process", "RAM máx. estimada por processo", ""),
        ("ram_total", "RAM total estimada", ""),
    ):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]}{unit}", hit))
    return rows


# -- Sistema ------------------------------------------------------------------------------------
def _system(facts: Facts, pw: PwOutput | None) -> list[SummaryRow]:
    formula = "".join(
        f"{name}{count if count > 1 else ''}" for name, count in facts.species.items()
    )
    rows = [
        SummaryRow("Cálculo", (pw.calculation if pw else None) or "—"),
        SummaryRow("Fórmula", formula or "—"),
    ]
    for key, label, template, normalize in (
        ("nat", "Átomos na célula", "{}", False),
        ("ntyp", "Tipos atômicos", "{}", False),
        ("alat", "Parâmetro de rede (alat)", "{} a.u.", True),
        ("volume", "Volume da célula", "{} a.u.^3", True),
        ("nelec", "Elétrons", "{}", True),
        ("nbnd", "Estados de Kohn-Sham", "{}", False),
        ("ecutwfc", "Cutoff da função de onda", "{} Ry", True),
        ("ecutrho", "Cutoff da densidade de carga", "{} Ry", True),
        ("xc", "Funcional (XC)", "{}", False),
    ):
        if hit := facts.hit(key, first=True):
            value = hit.groups[0] or ""
            rows.append(
                _row(label, template.format(normalize_number(value) if normalize else value), hit)
            )
    if kpoints := facts.hit("kpoints", first=True):
        count, smearing, width = kpoints.groups
        rows.append(_row("k-pontos", count or "", kpoints))
        if smearing:
            rows.append(_row("Smearing", f"{smearing} (largura {width} Ry)", kpoints))
    if (spin := _spin(facts, pw)) is not None:
        rows.append(SummaryRow("Spin", spin))
    if facts.pseudos:
        children = tuple(
            SummaryRow(element, name, line=line)
            for _index, (element, name, line) in sorted(facts.pseudos.items())
        )
        rows.append(SummaryRow("Pseudopotenciais", str(len(children)), children=children))
    return rows


def _spin(facts: Facts, pw: PwOutput | None) -> str | None:
    if facts.hit("spin_orbit"):
        return "spin-órbita"
    if pw is None:
        return None
    if pw.noncollinear:
        return "não colinear"
    return "colinear (nspin=2)" if pw.spin_polarized else "não polarizado"


# -- Resultados ---------------------------------------------------------------------------------
def _results(facts: Facts, pw: PwOutput | None, relax: RelaxData | None) -> list[SummaryRow]:
    is_relax = pw is not None and pw.calculation in RELAX_CALCULATIONS
    rows = _energy_rows(facts, is_relax)
    rows += _fermi_rows(facts, pw)
    for key, label in (("mag_total", "Magnetização total"), ("mag_abs", "Magnetização absoluta")):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]} Bohr mag/cell", hit))
    if pressure := facts.hit("pressure"):
        stress = tuple(
            SummaryRow(f"σ {axis}", "  ".join(row))
            for axis, row in zip("xyz", facts.stress, strict=False)
        )
        rows.append(_row("Pressão", f"{pressure.groups[0]} kbar", pressure, children=stress))
    if force := facts.hit("force"):
        rows.append(_row("Força total", f"{force.groups[0]} Ry/Bohr", force))
    if scf := _scf_row(facts):
        rows.append(scf)
    if is_relax:
        rows += _relax_rows(facts, relax)
    return rows


def _energy_rows(facts: Facts, is_relax: bool) -> list[SummaryRow]:
    first, last = facts.first.get("etot"), facts.last.get("etot")
    rows = []
    if first and last and is_relax and first.line != last.line:
        rows.append(_row("E inicial", f"{first.groups[0]} Ry", first))
        rows.append(_row("E final", f"{last.groups[0]} Ry", last))
    elif last:
        rows.append(_row("Energia total", f"{last.groups[0]} Ry", last))
    for key, label in (
        ("final_energy", "Energia final (BFGS)"),
        ("final_enthalpy", "Entalpia final"),
    ):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]} Ry", hit))
    return rows


def _fermi_rows(facts: Facts, pw: PwOutput | None) -> list[SummaryRow]:
    if pw is None or pw.fermi is None:
        return []

    def row(label: str, value: str) -> SummaryRow:
        return SummaryRow(label, value, line=facts.fermi_line)

    if pw.fermi_kind == "spin_fermi" and pw.fermi_up_down:
        up, down = pw.fermi_up_down
        return [row("Energia de Fermi (↑ / ↓)", f"{up:.4f} / {down:.4f} eV")]
    if pw.fermi_kind == "homo_lumo" and pw.lumo is not None:
        return [
            row("HOMO", f"{pw.fermi:.4f} eV"),
            row("LUMO", f"{pw.lumo:.4f} eV"),
            row("Gap", f"{pw.lumo - pw.fermi:.4f} eV"),
        ]
    if pw.fermi_kind == "homo":
        return [row("HOMO", f"{pw.fermi:.4f} eV")]
    return [row("Energia de Fermi", f"{pw.fermi:.4f} eV")]


def _scf_row(facts: Facts) -> SummaryRow | None:
    count, line = facts.scf_iterations, facts.scf_line
    if facts.scf_status == "converged":
        return SummaryRow("SCF", f"Convergiu em {count} iterações", "success", line)
    if facts.scf_status == "not_converged":
        return SummaryRow("SCF", f"Não convergiu ({count} iterações)", "warning", line)
    if count:
        return SummaryRow("SCF", f"Em andamento ({count} iterações)", None, line)
    return None  # nscf / bands: no SCF cycle


def _relax_rows(facts: Facts, relax: RelaxData | None) -> list[SummaryRow]:
    rows = []
    if relax is not None:
        rows.append(SummaryRow("Passos BFGS", str(len(relax.steps))))
    if end := facts.hit("bfgs_end"):
        outcome, cycles, steps = end.groups
        detail = f"{cycles} ciclos SCF, {steps} passos BFGS"
        if outcome == "converged":
            rows.append(_row("BFGS", f"Convergiu ({detail})", end, "success"))
        else:
            rows.append(_row("BFGS", f"Falhou ({detail})", end, "warning"))
    else:
        done = facts.hit("job_done") is not None
        rows.append(
            SummaryRow(
                "BFGS",
                "Sem convergência registrada" if done else "Em andamento",
                "warning" if done else None,
            )
        )
    start, new = facts.first.get("volume"), facts.last.get("new_volume")
    if start and new:
        before, after = normalize_number(start.groups[0] or ""), new.groups[0]
        rows.append(_row("Volume (inicial → final)", f"{before} → {after} a.u.^3", new))
    return rows


# -- Avisos e erros -----------------------------------------------------------------------------
def _issue_rows(issues: list[SummaryIssue]) -> list[SummaryRow]:
    if not issues:
        return [SummaryRow("Mensagens", "Nenhum aviso ou erro", "success")]
    rows = []
    for issue in issues:
        label = f"Erro em {issue.routine}" if issue.level == "error" else issue.routine
        value = issue.message + (f" (×{issue.count})" if issue.count > 1 else "")
        rows.append(SummaryRow(label, value, issue.level, issue.line))
    return rows
