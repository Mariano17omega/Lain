# Text and input viewer

Text files open in tabs with line numbers.

- **Search** `Ctrl+F` (`F3` / `Shift+F3` next/previous), **Ir à linha…** (go to line) `Ctrl+L`.
- Colored QE outputs (energies, errors, warnings, convergence).
- Files > 4 MB show the first 1 MB and last 2 MB with real line numbers; the banner offers **Abrir no editor
  externo** (open in external editor) and **Carregar tudo** (load all, up to 64 MB).
- Tab menu (or middle click): **Fechar** (`Ctrl+W`), *others / to the right / all*, **Copiar caminho**,
  **Revelar no explorador**.
- Job files (`job.o<id>`, `.qsub`, `.slurm`, `.pbs`) open **read-only**; Markdown is rendered.

## QE inputs

Syntax colors and a check of how they are **written**: unclosed quote, namelist without `/`, line without `=`,
unbalanced parenthesis, malformed logical/number, misspelled namelist or card, bad card option. In a pw.x input, also
of what they **mean**, from the text alone: `ecutrho` not above `ecutwfc` (pw.x stops) or below 4 × `ecutwfc`; a US/PAW
pseudopotential (by its name) with `ecutrho` ≤ 4 × and below 300 Ry; `smearing` without `degauss`; `nspin = 2` without
a starting magnetization; `relax`/`md` without `&IONS` and `vc-relax`/`vc-md` without `&CELL`; `nat` different from the
rows of `ATOMIC_POSITIONS`; an `automatic` mesh with 1 point along an axis with no vacuum, shorter than 15 Å. An error
(red) is what makes pw.x stop or compute something else; a warning, what runs but probably gives a poor result.
Problems are underlined, marked in the margin and counted in a banner (**Ir ao primeiro**, `F8` / `Shift+F8`). A strip of chips shows `calculation`, cutoffs, the `K_POINTS` grid etc. (click jumps to the line).

**Comparar com…** (compare with) opens a tab listing the parameters that differ (`1d-8` = `1.0e-8`) or the two files
side by side.

## Summary

Every QE output (pw.x, bands.x, projwfc.x…) has **Resumo**: state (`Concluído`/`Incompleto`/`Erro`), WALL/CPU time,
parallelization, memory, system, results (energies, Fermi/HOMO-LUMO and gap, magnetization, pressure, forces, SCF and
BFGS progress) and warnings/errors — read from the file, never saved. **Copiar**, **Atualizar**, and a double click
opens the output at the source line.

For a projwfc.x output, **Resultados** (results) holds the *spilling* (the fraction of the occupied charge the atomic
basis leaves out; yellow above 5 %) and the **Löwdin charges** of each atom, per orbital (s, p, d, f), with ↑, ↓ and
the polarization (↑−↓) when the run has spin. If projwfc.x wrote them to another file (`filowdin`) or ran with
`pawproj`, the row says they are not in the output.

Code: `ui/widgets/viewer/`, `core/viewer/`, `core/qe/input_lexer.py`, `input_lint.py`, `input_semantics.py`, `input_diff.py`,
`core/qe/summary/`, `core/qe/lowdin.py`.
