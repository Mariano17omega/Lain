"""The cluster mode, its queue and the sync (PRD §5, specs 64–72).

- ``remote_controller``: the cluster's folders and files in the panels, on a red background
  (spec 65).
- ``remote_plot``: plotting a cluster folder through its ``tmp_remote/`` copy (spec 66).
- ``sync_coordinator``: pull and push from the window: password, preview, report.
- ``jobs_controller``: the jobs on the top bar and the queue popup (spec 64).
- ``job_actions``: "Submeter…" on a ``.qsub`` (spec 69); ``job_cancel``: "Cancelar simulação…"
  (spec 70).

Their widgets are in ``ui/widgets/cluster``.
"""
