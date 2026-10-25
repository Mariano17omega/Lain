"""Shared pieces of the tests of the commands that change the cluster (specs 69 and 70): fakes of
``run_action`` and of the ``run_command`` it calls, and the toasts a window shows. No network."""

from __future__ import annotations

from qe_studio.core.sync.command import CommandResult


class FakeAction:
    """``run_action`` of ``core/remote``: the commands it was given, and ``result`` for each."""

    def __init__(self, result=None):
        self.result = CommandResult(0, "", "") if result is None else result
        self.commands: list[str] = []

    def __call__(self, _config, command, password=None):
        self.commands.append(command)
        return self.result


class FakeCommand:
    """``run_command`` of ``core/remote/actions.py``: every argv, and ``result``."""

    def __init__(self, result=None):
        self.result = CommandResult(0, "", "") if result is None else result
        self.argvs: list[list[str]] = []

    def __call__(self, argv, env, timeout_s):
        self.argvs.append(argv)
        return self.result


def toasts(window) -> list[tuple[str, str]]:
    """(text, level) of the toast shown and of those waiting their turn."""
    toast = window.toast
    shown = [toast.current, *toast._queue] if toast.current else list(toast._queue)
    return [(notice.text, notice.level) for notice in shown]
