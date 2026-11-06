# SCF convergence

Plotted from **one** `pw.x` output file. It is the fallback module: valid only when no other type was detected in the
folder. It opens through **Plotar** in the output's context menu or the **Plotar SCF** button in the top bar
(preview, not saved).

Up to three stacked panels sharing the iteration axis:

- **Estimated accuracy** against `conv_thr` (threshold line);
- **Energy**: |ΔE| between iterations or total E (**Energia como**); needs ≥ 2 iterations;
- **Magnetization** (spin runs only).

Controls: log/linear **scale**, show each panel and the threshold, iteration window (`xmin`/`xmax`), colors. If the
SCF did not converge, the plot says "convergência NÃO atingida" (convergence NOT reached).

Code: `core/calculations/scf.py`.
