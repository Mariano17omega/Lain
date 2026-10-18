"""Facts of a scanned output → the sections and rows of the summary (spec 12 R2).

Labels and values are Portuguese (user-facing); numbers keep QE's decimal point.
"""

from __future__ import annotations

from ....i18n import _, ngettext
from ..pw_output import PwOutput
from ..relax import RelaxData
from ..structure import format_formula
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


def build_summary(
    facts: Facts, pw: PwOutput | None, relax: RelaxData | None, mesh: str | None = None
) -> OutputSummary:
    """``mesh``: the k-point mesh of the input next to the output (``mesh.k_mesh_of``), if any."""
    sections = [SummarySection(_("Geral"), tuple(_general(facts)))]
    if facts.program == PW_PROGRAM:
        for title, rows in (
            (_("Sistema"), _system(facts, pw, mesh)),
            (_("Resultados"), _results(facts, pw, relax)),
        ):
            if rows:
                sections.append(SummarySection(title, tuple(rows)))
    sections.append(SummarySection(_("Avisos e erros"), tuple(_issue_rows(facts.issues))))
    return OutputSummary(facts.program, tuple(sections), tuple(facts.issues))


# -- Geral --------------------------------------------------------------------------------------
def _general(facts: Facts) -> list[SummaryRow]:
    program = facts.hit("program", first=True)
    rows = [
        _row(
            _("Programa"), f"{_group(program, 0)} {_group(program, 1)}" if program else "—", program
        ),
        _state_row(facts),
    ]
    if program and program.groups[2]:
        rows.append(
            _row(_("Início"), f"{program.groups[2]} {clock_text(program.groups[3] or '')}", program)
        )
    if ended := facts.hit("ended"):
        rows.append(
            _row(_("Término"), f"{ended.groups[1]} {clock_text(ended.groups[0] or '')}", ended)
        )
    if timing := facts.hit("time"):
        rows.append(_row(_("Tempo (WALL)"), duration_text(timing.groups[2] or ""), timing))
        rows.append(_row(_("Tempo (CPU)"), duration_text(timing.groups[1] or ""), timing))
    rows += _parallel_rows(facts)
    rows += _memory_rows(facts)
    if written := facts.items.get("written"):
        names = dict.fromkeys(hit.groups[0] or "" for hit in written)
        children = tuple(
            _row(_("Arquivo"), name, next(h for h in written if h.groups[0] == name))
            for name in names
        )
        rows.append(_row(_("Arquivos escritos"), str(len(names)), children=children))
    return rows


def _state_row(facts: Facts) -> SummaryRow:
    errors = [issue for issue in facts.issues if issue.level == "error"]
    if errors:
        return SummaryRow(_("Estado"), _("Erro"), "error", errors[0].line)
    if done := facts.hit("job_done", first=True):
        return _row(_("Estado"), _("Concluído"), done, "success")
    return SummaryRow(_("Estado"), _("Incompleto"), "warning")


def _parallel_rows(facts: Facts) -> list[SummaryRow]:
    rows = []
    if serial := facts.hit("serial"):
        rows.append(_row(_("Paralelização"), _("Serial"), serial))
    elif parallel := facts.hit("parallel"):
        flavor, count = parallel.groups
        rows.append(
            _row(
                _("Paralelização"),
                _("{flavor}, {count} processadores").format(flavor=flavor, count=count),
                parallel,
            )
        )
    for key, label, suffix in (
        ("mpi", _("Processos MPI"), ""),
        ("threads", _("Threads por processo MPI"), ""),
        ("nodes", _("Nós"), ""),
        ("npool", _("Divisão de k-pontos (npool)"), ""),
        ("rg_division", _("Divisão R & G (proc/nbgrp/npool/nimage)"), ""),
    ):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]}{suffix}", hit))
    if gpu := facts.hit("gpu"):
        rows.append(_row(_("GPU"), _("Ativa"), gpu))
    return rows


def _memory_rows(facts: Facts) -> list[SummaryRow]:
    rows = []
    for key, label, unit in (
        ("memory", _("Memória disponível"), " MiB"),
        ("ram_process", _("RAM máx. estimada por processo"), ""),
        ("ram_total", _("RAM total estimada"), ""),
    ):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]}{unit}", hit))
    return rows


# -- Sistema ------------------------------------------------------------------------------------
def _system(facts: Facts, pw: PwOutput | None, mesh: str | None) -> list[SummaryRow]:
    rows = [
        SummaryRow(_("Cálculo"), (pw.calculation if pw else None) or "—"),
        SummaryRow(_("Fórmula"), format_formula(facts.species) or "—"),
    ]
    for key, label, template, normalize in (
        ("nat", _("Átomos na célula"), "{}", False),
        ("ntyp", _("Tipos atômicos"), "{}", False),
        ("alat", _("Parâmetro de rede (alat)"), "{} a.u.", True),
        ("volume", _("Volume da célula"), "{} a.u.^3", True),
        ("nelec", _("Elétrons"), "{}", True),
        ("nbnd", _("Estados de Kohn-Sham"), "{}", False),
        ("ecutwfc", _("Cutoff da função de onda"), "{} Ry", True),
        ("ecutrho", _("Cutoff da densidade de carga"), "{} Ry", True),
        ("xc", _("Funcional (XC)"), "{}", False),
    ):
        if hit := facts.hit(key, first=True):
            value = hit.groups[0] or ""
            rows.append(
                _row(label, template.format(normalize_number(value) if normalize else value), hit)
            )
    rows += _kpoint_rows(facts, mesh)
    if (spin := _spin(facts, pw)) is not None:
        rows.append(SummaryRow("Spin", spin))
    if facts.pseudos:
        children = tuple(
            SummaryRow(element, name, line=line)
            for _index, (element, name, line) in sorted(facts.pseudos.items())
        )
        rows.append(SummaryRow(_("Pseudopotenciais"), str(len(children)), children=children))
    return rows


def _kpoint_rows(facts: Facts, mesh: str | None) -> list[SummaryRow]:
    """The irreducible count pw.x prints, the mesh the input asked for (another file: no line), then
    the smearing, which the same output line carries."""
    kpoints = facts.hit("kpoints", first=True)
    rows = []
    if kpoints:
        rows.append(_row(_("k-pontos irredutíveis"), kpoints.groups[0] or "", kpoints))
    if mesh:
        rows.append(SummaryRow(_("Malha k"), mesh))
    if kpoints and kpoints.groups[1]:
        _count, smearing, width = kpoints.groups
        rows.append(
            _row(
                "Smearing",
                _("{smearing} (largura {width} Ry)").format(smearing=smearing, width=width),
                kpoints,
            )
        )
    return rows


def _spin(facts: Facts, pw: PwOutput | None) -> str | None:
    if facts.hit("spin_orbit"):
        return _("spin-órbita")
    if pw is None:
        return None
    if pw.noncollinear:
        return _("não colinear")
    return _("colinear (nspin=2)") if pw.spin_polarized else _("não polarizado")


# -- Resultados ---------------------------------------------------------------------------------
def _results(facts: Facts, pw: PwOutput | None, relax: RelaxData | None) -> list[SummaryRow]:
    is_relax = pw is not None and pw.calculation in RELAX_CALCULATIONS
    rows = _energy_rows(facts, is_relax)
    rows += _fermi_rows(facts, pw)
    for key, label in (
        ("mag_total", _("Magnetização total")),
        ("mag_abs", _("Magnetização absoluta")),
    ):
        if hit := facts.hit(key):
            rows.append(_row(label, f"{hit.groups[0]} Bohr mag/cell", hit))
    if pressure := facts.hit("pressure"):
        stress = tuple(
            SummaryRow(f"σ {axis}", "  ".join(row))
            for axis, row in zip("xyz", facts.stress, strict=False)
        )
        rows.append(_row(_("Pressão"), f"{pressure.groups[0]} kbar", pressure, children=stress))
    if force := facts.hit("force"):
        rows.append(_row(_("Força total"), f"{force.groups[0]} Ry/Bohr", force))
    if scf := _scf_row(facts):
        rows.append(scf)
    if is_relax:
        rows += _relax_rows(facts, relax)
    return rows


def _energy_rows(facts: Facts, is_relax: bool) -> list[SummaryRow]:
    first, last = facts.first.get("etot"), facts.last.get("etot")
    rows = []
    if first and last and is_relax and first.line != last.line:
        rows.append(_row(_("E inicial"), f"{first.groups[0]} Ry", first))
        rows.append(_row(_("E final"), f"{last.groups[0]} Ry", last))
    elif last:
        rows.append(_row(_("Energia total"), f"{last.groups[0]} Ry", last))
    for key, label in (
        ("final_energy", _("Energia final (BFGS)")),
        ("final_enthalpy", _("Entalpia final")),
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
        return [row(_("Energia de Fermi (↑ / ↓)"), f"{up:.4f} / {down:.4f} eV")]
    if pw.fermi_kind == "homo_lumo" and pw.lumo is not None:
        return [
            row("HOMO", f"{pw.fermi:.4f} eV"),
            row("LUMO", f"{pw.lumo:.4f} eV"),
            row("Gap", f"{pw.lumo - pw.fermi:.4f} eV"),
        ]
    if pw.fermi_kind == "homo":
        return [row("HOMO", f"{pw.fermi:.4f} eV")]
    return [row(_("Energia de Fermi"), f"{pw.fermi:.4f} eV")]


def _scf_row(facts: Facts) -> SummaryRow | None:
    count, line = facts.scf_iterations, facts.scf_line
    if facts.scf_status == "converged":
        text = ngettext(
            "Convergiu em {count} iteração", "Convergiu em {count} iterações", count
        ).format(count=count)
        return SummaryRow("SCF", text, "success", line)
    if facts.scf_status == "not_converged":
        text = ngettext(
            "Não convergiu ({count} iteração)", "Não convergiu ({count} iterações)", count
        ).format(count=count)
        return SummaryRow("SCF", text, "warning", line)
    if count:
        text = ngettext(
            "Em andamento ({count} iteração)", "Em andamento ({count} iterações)", count
        ).format(count=count)
        return SummaryRow("SCF", text, None, line)
    return None  # nscf / bands: no SCF cycle


def _relax_rows(facts: Facts, relax: RelaxData | None) -> list[SummaryRow]:
    rows = []
    if relax is not None:
        rows.append(SummaryRow(_("Passos BFGS"), str(len(relax.steps))))
    if end := facts.hit("bfgs_end"):
        outcome, cycles, steps = end.groups
        detail = _("{cycles} ciclos SCF, {steps} passos BFGS").format(cycles=cycles, steps=steps)
        if outcome == "converged":
            rows.append(
                _row("BFGS", _("Convergiu ({detail})").format(detail=detail), end, "success")
            )
        else:
            rows.append(_row("BFGS", _("Falhou ({detail})").format(detail=detail), end, "warning"))
    else:
        done = facts.hit("job_done") is not None
        rows.append(
            SummaryRow(
                "BFGS",
                _("Sem convergência registrada") if done else _("Em andamento"),
                "warning" if done else None,
            )
        )
    start, new = facts.first.get("volume"), facts.last.get("new_volume")
    if start and new:
        before, after = normalize_number(start.groups[0] or ""), new.groups[0]
        rows.append(_row(_("Volume (inicial → final)"), f"{before} → {after} a.u.^3", new))
    return rows


# -- Avisos e erros -----------------------------------------------------------------------------
def _issue_rows(issues: list[SummaryIssue]) -> list[SummaryRow]:
    if not issues:
        return [SummaryRow(_("Mensagens"), _("Nenhum aviso ou erro"), "success")]
    rows = []
    for issue in issues:
        label = (
            _("Erro em {routine}").format(routine=issue.routine)
            if issue.level == "error"
            else issue.routine
        )
        value = issue.message + (f" (×{issue.count})" if issue.count > 1 else "")
        rows.append(SummaryRow(label, value, issue.level, issue.line))
    return rows
