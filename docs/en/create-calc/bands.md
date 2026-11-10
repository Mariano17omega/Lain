# Bands

SCF, `pw.x` with `calculation='bands'` along a high-symmetry path, and `bands.x`.

- **Files**: the SCF, `bands.in` (pw.x), `bands_pp.in` for `bands.x` (or `bands_pp_up.in` / `bands_pp_dw.in` for a
  collinear-spin SCF — one per channel) and `bands.qsub`.
- **Fields**: **High-symmetry path** (labeled points; *Distribuir pelo comprimento* button; Lain warns about segments
  that collapse on `bands.x`'s x axis), **Band file** (`filband`, default `./band`; `./band_up`/`./band_dw` per
  channel). In Standard mode only the path is asked for: `nbnd` comes from the SCF.
- **Warnings**: segments that collapse on the x axis; two equal consecutive points in the path (`bands.x` leaves the
  `.gnu` empty); `tot_magnetization` in the SCF (QE's `bands.x` aborts with a constrained magnetization: the `pw.x`
  runs go through and the bands only come from the `pw.x` output). A `disk_io` of `nowf`, `minimal` or `none` is
  removed from the generated inputs, with a warning, because `bands.x` needs the `wfc*.dat` files.
- **Script**: pw.x SCF → pw.x bands → `bands.x` (one per channel).
- The result is detected as `BANDS` — see [bands](../plots/bands.md).

Code: `core/calc_create/types/bandas.py`, `core/calc_create/kpath.py`; templates `qe/bandas/bands_pp.in.j2`,
`qsub/bands.qsub.j2`.
