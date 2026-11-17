"""What the tests of ``install.sh`` share: its full run with fake ``git``, ``uv`` and ``ssh``.

The fakes stand on a PATH without the real programs: nothing is installed, cloned or contacted, and
the fake ssh runs a remote command in a temp folder that stands for the cluster account.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install.sh"
EXAMPLE = ROOT / "config.example.yaml"
SYSTEM_PATH = "/usr/bin:/bin"


def executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


# xdg-user-dir with no Documents folder set: it prints the home folder.
NO_DOCUMENTS = '#!/bin/sh\nprintf "%s\\n" "$HOME"\n'


def fake_bin(tmp_path: Path) -> Path:
    """``tmp_path/bin``, first on PATH, with an ``xdg-user-dir`` unless the test wrote its own."""
    bin_dir = tmp_path / "bin"
    if not (bin_dir / "xdg-user-dir").exists():
        executable(bin_dir / "xdg-user-dir", NO_DOCUMENTS)
    return bin_dir


# The real programs install.sh (and the fakes below) run; nothing else of the system is on PATH, so
# the real git, uv, ssh, ssh-copy-id, rsync, curl and xcrysden are out of reach.
SYSTEM_TOOLS = (
    "bash", "sh", "awk", "sed", "mktemp", "cp", "mv", "rm", "mkdir", "cat", "grep", "ls",
    "dirname", "uname", "chmod", "rmdir", "cut", "tr",
)  # fmt: skip

FAKE_UNAME = "#!/bin/sh\necho MINGW64_NT-10.0-19045\n"
# cygpath as Git Bash has it, for the drive-letter forms the script uses: -m gives C:/x, -u gives /c/x.
FAKE_CYGPATH = r"""#!/bin/sh
mode=$1
path=$2
case $mode in
    -m)
        case $path in
            /[a-z]/*) drive=$(printf %s "$path" | cut -c2 | tr a-z A-Z)
                      printf '%s:%s\n' "$drive" "$(printf %s "$path" | cut -c3-)" ;;
            *) printf '%s\n' "$path" | tr '\\' / ;;
        esac ;;
    -u)
        case $path in
            [A-Za-z]:*) drive=$(printf %s "$path" | cut -c1 | tr A-Z a-z)
                        printf '/%s%s\n' "$drive" "$(printf %s "$path" | cut -c3- | tr '\\' /)" ;;
            *) printf '%s\n' "$path" ;;
        esac ;;
esac
"""


def windows(tmp_path: Path) -> dict[str, str]:
    """Git Bash, faked: its uname and cygpath on PATH; returns the env with USERPROFILE."""
    executable(tmp_path / "bin" / "uname", FAKE_UNAME)
    executable(tmp_path / "bin" / "cygpath", FAKE_CYGPATH)
    profile = tmp_path / "profile"
    profile.mkdir()
    return {"USERPROFILE": str(profile)}


# git: "clone -- URL DIR" makes a Lain checkout of version FAKE_REMOTE_VERSION (none when unset), or
# fails with FAKE_GIT_CLONE_FAILS; "-C DIR pull" fails with FAKE_GIT_PULL_FAILS; "-C DIR remote"
# answers FAKE_ORIGIN (the public repository when unset); "-C DIR status" prints FAKE_GIT_STATUS, or
# a changed file with FAKE_GIT_DIRTY; "-C DIR log" prints FAKE_GIT_LOCAL_COMMIT.
FAKE_GIT = r"""#!/bin/sh
case $1 in
    clone)
        echo "clone $3" >> "$FAKE_LOG"
        if [ -n "$FAKE_GIT_CLONE_FAILS" ]; then
            echo "fatal: unable to access the repository" >&2
            exit 128
        fi
        mkdir -p "$4/.git"
        printf 'name = "lain"\n' > "$4/pyproject.toml"
        if [ -n "$FAKE_REMOTE_VERSION" ]; then
            printf 'version = "%s"\n' "$FAKE_REMOTE_VERSION" >> "$4/pyproject.toml"
        fi
        cp "$LAIN_EXAMPLE" "$4/config.example.yaml" ;;
    -C)
        case $3 in
            remote) echo "${FAKE_ORIGIN:-https://github.com/Mariano17omega/Lain.git}" ;;
            status)
                if [ -n "$FAKE_GIT_DIRTY" ]; then echo " M src/changed.py"; fi
                if [ -n "$FAKE_GIT_STATUS" ]; then printf '%s\n' "$FAKE_GIT_STATUS"; fi ;;
            log) if [ -n "$FAKE_GIT_LOCAL_COMMIT" ]; then echo "$FAKE_GIT_LOCAL_COMMIT"; fi ;;
            *)
                echo "pull $2" >> "$FAKE_LOG"
                if [ -n "$FAKE_GIT_PULL_FAILS" ]; then
                    echo "fatal: Not possible to fast-forward, aborting." >&2
                    exit 1
                fi ;;
        esac ;;
esac
"""

# uv: "tool install" puts a lain command in FAKE_TOOL_BIN, which "tool dir --bin" names; "tool dir"
# names FAKE_TOOLS_DIR, of which "tool uninstall" deletes the tool.
FAKE_UV = r"""#!/bin/sh
case "$1 $2" in
    "--version "*) echo "uv 0.0.0 (fake)" ;;
    "tool install")
        echo "tool install $3 $4 $5" >> "$FAKE_LOG"
        mkdir -p "$FAKE_TOOL_BIN"
        printf '#!/bin/sh\n' > "$FAKE_TOOL_BIN/lain"
        chmod +x "$FAKE_TOOL_BIN/lain" ;;
    "tool dir")
        if [ "$3" = "--bin" ]; then echo "$FAKE_TOOL_BIN"; else echo "$FAKE_TOOLS_DIR"; fi ;;
    "tool uninstall")
        echo "tool uninstall $3" >> "$FAKE_LOG"
        rm -rf "$FAKE_TOOLS_DIR/$3" ;;
    "tool update-shell") echo "update-shell" >> "$FAKE_LOG" ;;
    *) echo "unexpected: uv $*" >> "$FAKE_LOG"; exit 1 ;;
esac
"""

# ssh: the remote command (the last argument) runs here, with the cluster account's home faked by
# FAKE_REMOTE_HOME. Nothing is contacted.
FAKE_SSH = r"""#!/bin/sh
echo "ssh $*" >> "$FAKE_LOG"
for last in "$@"; do :; done
cd "$FAKE_REMOTE_HOME" && HOME=$FAKE_REMOTE_HOME exec sh -c "$last"
"""


def full_install(
    tmp_path: Path,
    lines: list[str],
    *,
    on_path: Sequence[Path] = (),
    env: dict[str, str] | None = None,
    script: Path | None = None,
    cwd: Path | None = None,
    without: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    """install.sh with no option: ``script``, or a downloaded copy (outside any checkout).
    ``without``: the fakes left out, as a program this computer does not have."""
    if script is None:
        download = tmp_path / "download"
        download.mkdir()
        script = download / "install.sh"
        shutil.copyfile(SCRIPT, script)
    bin_dir = fake_bin(tmp_path)
    for name, fake in (("git", FAKE_GIT), ("uv", FAKE_UV), ("ssh", FAKE_SSH)):
        if name not in without:
            executable(bin_dir / name, fake)
    system = tmp_path / "sysbin"
    system.mkdir()
    for tool in SYSTEM_TOOLS:
        found = shutil.which(tool, path=SYSTEM_PATH)
        assert found is not None, tool
        (system / tool).symlink_to(found)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (tmp_path / "cluster").mkdir(exist_ok=True)
    full_env = {
        "HOME": str(home),
        "PATH": ":".join(str(p) for p in (*on_path, bin_dir, system)),
        "FAKE_LOG": str(tmp_path / "log.txt"),
        "FAKE_TOOL_BIN": str(home / ".local" / "bin"),
        "FAKE_TOOLS_DIR": str(home / ".local" / "share" / "uv" / "tools"),
        "FAKE_REMOTE_HOME": str(tmp_path / "cluster"),
        "LAIN_EXAMPLE": str(EXAMPLE),
        **(env or {}),
    }
    return subprocess.run(
        ["bash", str(script)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        env=full_env,
        cwd=cwd or tmp_path,
        timeout=30,
    )


def log_of(tmp_path: Path) -> list[str]:
    return (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()
