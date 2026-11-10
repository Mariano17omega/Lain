"""The pull and the push over rsync and ssh (PRD §5, spec 27). Only ``_process``, ``controller``
and ``monitor`` use Qt.

- ``rsync``: the command lines, environments and output parsers; ``ssh_command`` is the one
  builder of ssh options; ``mux``: one ssh connection for many commands (spec 72);
  ``remote_path``: each side of a sync as an argument; ``rsync_errors``: what a failure said;
  ``partial``: the temporaries a killed rsync leaves.
- ``planner`` and ``push_plan``: the plans, from rsync's dry run; ``preview`` and ``report``: what
  the window shows before and after; ``request``: whether a sync can start, and from where.
- ``_process``: one rsync run in a ``QProcess``; ``controller``: the pull; ``push``: the push.
- ``command``: one command on the cluster other than rsync; ``monitor``: the reachability LED;
  ``askpass``: the ``SSH_ASKPASS`` helper.
"""
