"""Stand-in for ``ssh`` in tests: drops options and the host, runs the remote command locally.

rsync calls ``<rsh> [-l user] host rsync --server ...``; ssh would join the command words
with spaces and hand them to the remote shell, which is what this does with ``sh -c``.
"""

import os
import sys

OPTIONS_WITH_VALUE = {"-p", "-o", "-i", "-l", "-F", "-J", "-b", "-c", "-D", "-E", "-L", "-R"}

args = sys.argv[1:]
i = 0
while i < len(args) and args[i].startswith("-"):
    i += 2 if args[i] in OPTIONS_WITH_VALUE else 1
host, command = args[i], args[i + 1 :]
if log := os.environ.get("FAKE_SSH_LOG"):
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(f"{host}\t{' '.join(command)}\n")
os.execvp("sh", ["sh", "-c", " ".join(command)])
