"""The user's files and folders, without widgets (spec 78.5): what a file is, the rules of a
folder, and what is done with them.

- ``file_kinds``: how a file opens and the state it reports (``viewer_kind``, ``status_label``).
- ``job_log``: whether a job's stdout log only lists the job's machines (spec 85).
- ``run_errors``: whether a folder holds the trace of a failed run (spec 50).
- ``paths``: the folder rules of the file panels: hidden folders, order of names, entry counts.
- ``filtering``: what the quick filter accepts (spec 16 R3).
- ``navigation``: the back/forward history and the breadcrumb's arithmetic (spec 16).
- ``file_ops``: the operations of the context menu, never over an existing file.
- ``unique_names``: names that never overwrite (``_1``, ``_2``…, spec 24).
- ``desktop_apps``: the installed programs that open a MIME type ("Abrir com").
- ``xcrysden``: opening a pw.x file with XCrySDen (spec 45).
"""
