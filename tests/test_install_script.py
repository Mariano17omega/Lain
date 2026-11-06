"""``install.sh``, the installer for Linux and for Windows (Git Bash).

Most tests run ``--config-only``: the answers go on stdin, into a copy of ``config.example.yaml``,
and Lain's own loader reads the result. The full install runs only with fake ``git``, ``uv`` and
``ssh`` on a PATH without the real ones: nothing is installed, cloned or contacted, and the fake
ssh runs a remote command in a temp folder that stands for the cluster account.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from qe_studio.core.config import AppConfig, load_config

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install.sh"
EXAMPLE = ROOT / "config.example.yaml"
SYSTEM_PATH = "/usr/bin:/bin"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="install.sh needs bash")

Answer = str | list[str]  # a list: the wrong answers first, the accepted one last


def answers(
    *,
    local_root: Answer = "",
    create: Answer | None = "",  # None: not asked (the folder exists, or it is not created)
    remote_root: Answer = "",
    xcrysden: Answer = "",
    data: Answer = "",
    host: Answer = "cluster.example",
    port: Answer = "",
    user: Answer = "alice",
    auth: Answer = "",
    key_path: Answer | None = "",  # None: not asked (auth password)
    email: Answer = "alice@mail.example",
) -> list[str]:
    """The lines install.sh reads, in the order it asks; "" takes the default."""
    lines: list[str] = []
    for value in (local_root, create, remote_root, xcrysden, data, host, port, user, auth):
        if value is not None:
            lines += value if isinstance(value, list) else [value]
    for value in (key_path, email):
        if value is not None:
            lines += value if isinstance(value, list) else [value]
    return lines


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


def run_install(
    tmp_path: Path, lines: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    checkout = tmp_path / "lain"
    checkout.mkdir(exist_ok=True)
    if not (checkout / "config.example.yaml").exists():
        shutil.copyfile(EXAMPLE, checkout / "config.example.yaml")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    full_env = {"HOME": str(home), "PATH": f"{fake_bin(tmp_path)}:{SYSTEM_PATH}", **(env or {})}
    return subprocess.run(
        ["bash", str(SCRIPT), "--config-only", str(checkout)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        env=full_env,
        cwd=tmp_path,
        timeout=30,
    )


def config_of(tmp_path: Path) -> AppConfig:
    return load_config(tmp_path / "lain" / "config.yaml", environ={}, cwd=tmp_path).config


def assert_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_defaults_are_the_lucci_folders(tmp_path):
    result = run_install(tmp_path, answers())
    assert_ok(result)
    config = config_of(tmp_path)
    assert config.paths.local_root == Path("~/Documentos/LUCCI").expanduser()
    assert config.paths.remote_root == "~/LUCCI"
    assert config.paths.xcrysden_path is None
    assert config.paths.data is None
    assert (config.cluster.host, config.cluster.port, config.cluster.user) == (
        "cluster.example",
        22,
        "alice",
    )
    assert config.cluster.auth == "key"
    assert config.cluster.key_path == Path("~/.ssh/id_ed25519").expanduser()
    assert config.jobs.myemail == "alice@mail.example"
    # The folder was created where Lain will look for it (the HOME the script ran with).
    assert (tmp_path / "home" / "Documentos" / "LUCCI").is_dir()
    # English only.
    assert result.stdout.isascii() and result.stderr.isascii()


def test_the_default_folder_is_in_the_documents_folder(tmp_path):
    executable(tmp_path / "bin" / "xdg-user-dir", '#!/bin/sh\nprintf "%s\\n" "$HOME/Documents"\n')
    result = run_install(tmp_path, answers())
    assert_ok(result)
    assert "[~/Documents/LUCCI]" in result.stdout
    assert config_of(tmp_path).paths.local_root == Path("~/Documents/LUCCI").expanduser()
    assert (tmp_path / "home" / "Documents" / "LUCCI").is_dir()


def test_relative_and_variable_paths_are_asked_again(tmp_path):
    # Lain reads a relative path from the folder it runs in, and expands $HOME itself.
    local = tmp_path / "sims"
    local.mkdir()
    key = tmp_path / "id"
    lines = answers(
        local_root=["sims", "$HOME/sims", "~other/sims", str(local)],
        create=None,
        key_path=["keys/id", str(key)],
    )
    result = run_install(tmp_path, lines)
    assert_ok(result)
    assert result.stdout.count("Give the full path") == 4
    config = config_of(tmp_path)
    assert config.paths.local_root == local
    assert config.cluster.key_path == key
    assert not (tmp_path / "$HOME").exists()


def test_only_the_answered_keys_change(tmp_path):
    assert_ok(run_install(tmp_path, answers()))
    example = EXAMPLE.read_text(encoding="utf-8").splitlines()
    written = (tmp_path / "lain" / "config.yaml").read_text(encoding="utf-8").splitlines()
    comment = next(i for i, line in enumerate(example) if line.startswith("  # myemail:"))
    assert written[comment + 1] == '  myemail: "alice@mail.example"'
    del written[comment + 1]
    changed = {
        old.split(":")[0].strip() for old, new in zip(example, written, strict=True) if old != new
    }
    assert changed == {"local_root", "remote_root", "host", "user", "key_path"}


def test_xcrysden_comes_from_xcrysden_topdir(tmp_path):
    install = tmp_path / "xcrysden-1.6.2"
    executable(install / "xcrysden")
    result = run_install(tmp_path, answers(), env={"XCRYSDEN_TOPDIR": str(install)})
    assert_ok(result)
    assert config_of(tmp_path).paths.xcrysden_path == str(install)


def test_xcrysden_comes_from_path(tmp_path):
    script = executable(tmp_path / "bin" / "xcrysden")
    assert_ok(run_install(tmp_path, answers()))
    assert config_of(tmp_path).paths.xcrysden_path == str(script)


@pytest.mark.skipif(
    shutil.which("xcrysden", path=SYSTEM_PATH) is not None, reason="XCrySDen is installed"
)
def test_a_typed_xcrysden_path_is_checked(tmp_path):
    no_program = tmp_path / "empty"
    no_program.mkdir()
    install = tmp_path / "xc"
    executable(install / "xcrysden")
    # "xc" is there, but relative to this run's folder only.
    lines = answers(xcrysden=[str(tmp_path / "nowhere"), str(no_program), "xc", str(install)])
    result = run_install(tmp_path, lines)
    assert_ok(result)
    assert result.stdout.count("There is no executable 'xcrysden'") == 2
    assert result.stdout.count("Give the full path") == 1
    assert "type 'none' to leave it blank" in result.stdout
    assert config_of(tmp_path).paths.xcrysden_path == str(install)


@pytest.mark.skipif(
    shutil.which("xcrysden", path=SYSTEM_PATH) is not None, reason="XCrySDen is installed"
)
def test_enter_leaves_xcrysden_blank(tmp_path):
    result = run_install(tmp_path, answers(xcrysden=[str(tmp_path / "nowhere"), ""]))
    assert_ok(result)
    assert "stays disabled" in result.stderr
    assert config_of(tmp_path).paths.xcrysden_path is None


def test_paths_keep_spaces_quotes_and_backslashes(tmp_path):
    local = tmp_path / 'my runs "x" \\ y'
    local.mkdir()
    lines = answers(
        local_root=str(local),
        create=None,
        remote_root='~/runs with space/"q"',
        data="lain data",
        key_path=str(tmp_path / "keys" / "id x"),
    )
    assert_ok(run_install(tmp_path, lines))
    config = config_of(tmp_path)
    assert config.paths.local_root == local
    assert config.paths.remote_root == '~/runs with space/"q"'
    assert config.paths.data == tmp_path / "lain" / "lain data"  # relative to config.yaml
    assert config.cluster.key_path == tmp_path / "keys" / "id x"


def test_wrong_answers_are_asked_again(tmp_path):
    lines = answers(
        create="n",
        host=["", "bad host", "-oProxyCommand=x", "user@host", "ok.example"],
        port=["0", "70000", "x", "02222"],
        user=["", "a b", "bob"],
        auth=["kerberos", "PASSWORD"],
        key_path=None,
        email=["no-at", "a b@c.d", 'x"y@z', "bob@mail.example"],
    )
    result = run_install(tmp_path, lines)
    assert_ok(result)
    config = config_of(tmp_path)
    assert config.cluster.host == "ok.example"
    assert config.cluster.port == 2222
    assert config.cluster.user == "bob"
    assert config.cluster.auth == "password"
    assert "QE_STUDIO_SSH_PASSWORD" in result.stdout
    assert config.jobs.myemail == "bob@mail.example"
    assert not (tmp_path / "home" / "Documentos" / "LUCCI").exists()  # "n": not created


def test_an_existing_config_is_kept_unless_asked(tmp_path):
    checkout = tmp_path / "lain"
    checkout.mkdir()
    config = checkout / "config.yaml"
    config.write_bytes(b"paths:\n  local_root: /old\n")

    result = run_install(tmp_path, ["n"])
    assert_ok(result)
    assert config.read_bytes() == b"paths:\n  local_root: /old\n"
    assert sorted(p.name for p in checkout.iterdir()) == ["config.example.yaml", "config.yaml"]

    assert_ok(run_install(tmp_path, ["y", *answers()]))
    assert (checkout / "config.yaml.bak").read_bytes() == b"paths:\n  local_root: /old\n"
    assert config_of(tmp_path).cluster.host == "cluster.example"

    assert_ok(run_install(tmp_path, ["y", *answers(create=None, host="second.example")]))
    assert (checkout / "config.yaml.bak_2").read_bytes() != config.read_bytes()
    assert config_of(tmp_path).cluster.host == "second.example"


def test_the_input_ending_stops_without_writing(tmp_path):
    result = run_install(tmp_path, answers()[:4])
    assert result.returncode == 1
    assert "the input ended" in result.stderr
    assert sorted(p.name for p in (tmp_path / "lain").iterdir()) == ["config.example.yaml"]


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


def test_windows_paths_are_written_as_windows_reads_them(tmp_path):
    env = windows(tmp_path)
    lines = answers(
        local_root="/c/Users/me/runs",
        create="n",  # /c/Users/me/runs does not exist here, and is not created
        data="D:\\lain data",
    )
    result = run_install(tmp_path, lines, env=env)
    assert_ok(result)
    assert "Windows, Git Bash" in result.stdout
    text = (tmp_path / "lain" / "config.yaml").read_text(encoding="utf-8")
    assert '  local_root: "C:/Users/me/runs"\n' in text
    assert '  data: "D:/lain data"\n' in text
    assert '  remote_root: "~/LUCCI"\n' in text  # the cluster's path is never converted
    assert '  key_path: "~/.ssh/id_ed25519"\n' in text  # a ~ stays for Lain to expand


def test_windows_takes_documents_and_drive_letters(tmp_path):
    # "Documentos" is only the name Explorer shows: the folder is Documents.
    env = windows(tmp_path)
    # Drive-letter answers pass the full-path check (C:\no\xcrysden then has no program).
    lines = answers(create="n", xcrysden=["C:\\no\\xcrysden", "none"], key_path="C:\\Users\\me\\id")
    result = run_install(tmp_path, lines, env=env)
    assert_ok(result)
    assert "Give the full path" not in result.stdout
    text = (tmp_path / "lain" / "config.yaml").read_text(encoding="utf-8")
    assert '  local_root: "~/Documents/LUCCI"\n' in text
    assert '  key_path: "C:/Users/me/id"\n' in text


def test_a_crlf_example_keeps_its_endings(tmp_path):
    checkout = tmp_path / "lain"
    checkout.mkdir()
    crlf = EXAMPLE.read_bytes().replace(b"\n", b"\r\n")
    (checkout / "config.example.yaml").write_bytes(crlf)
    assert_ok(run_install(tmp_path, answers()))
    written = (checkout / "config.yaml").read_bytes()
    assert written.count(b"\n") == written.count(b"\r\n")
    config = config_of(tmp_path)
    assert config.cluster.user == "alice"
    assert config.jobs.myemail == "alice@mail.example"


def test_a_piped_script_without_a_terminal_says_how_to_run_it(tmp_path):
    result = subprocess.run(
        ["bash", "-s", "--", "--config-only", str(tmp_path)],
        input=SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "PATH": SYSTEM_PATH},
        timeout=30,
        start_new_session=True,  # no controlling terminal, so /dev/tty cannot open
    )
    assert result.returncode == 1
    assert "there is no terminal" in result.stderr
    assert "bash install.sh" in result.stderr


# --- the full install, with fakes ------------------------------------------------------------------

# The real programs install.sh (and the fakes below) run; nothing else of the system is on PATH, so
# the real git, uv, ssh, ssh-copy-id, rsync, curl and xcrysden are out of reach.
SYSTEM_TOOLS = (
    "bash", "sh", "awk", "sed", "mktemp", "cp", "mv", "rm", "mkdir", "cat", "grep", "ls",
    "dirname", "uname", "chmod",
)  # fmt: skip

# git: "clone -- URL DIR" makes a Lain checkout; "-C DIR pull" fails when FAKE_GIT_PULL_FAILS is set.
FAKE_GIT = r"""#!/bin/sh
case $1 in
    clone)
        echo "clone $3" >> "$FAKE_LOG"
        mkdir -p "$4/.git"
        printf 'name = "lain"\n' > "$4/pyproject.toml"
        cp "$LAIN_EXAMPLE" "$4/config.example.yaml" ;;
    -C)
        echo "pull $2" >> "$FAKE_LOG"
        if [ -n "$FAKE_GIT_PULL_FAILS" ]; then
            echo "fatal: Not possible to fast-forward, aborting." >&2
            exit 1
        fi ;;
esac
"""

# uv: "tool install" puts a lain command in FAKE_TOOL_BIN, which "tool dir --bin" names.
FAKE_UV = r"""#!/bin/sh
case "$1 $2" in
    "--version "*) echo "uv 0.0.0 (fake)" ;;
    "tool install")
        echo "tool install $3 $4 $5" >> "$FAKE_LOG"
        mkdir -p "$FAKE_TOOL_BIN"
        printf '#!/bin/sh\n' > "$FAKE_TOOL_BIN/lain"
        chmod +x "$FAKE_TOOL_BIN/lain" ;;
    "tool dir") echo "$FAKE_TOOL_BIN" ;;
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
    tmp_path: Path, lines: list[str], *, on_path: list[Path] = (), env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """install.sh with no option, run from a downloaded copy (outside any checkout)."""
    download = tmp_path / "download"
    download.mkdir()
    shutil.copyfile(SCRIPT, download / "install.sh")
    bin_dir = fake_bin(tmp_path)
    executable(bin_dir / "git", FAKE_GIT)
    executable(bin_dir / "uv", FAKE_UV)
    executable(bin_dir / "ssh", FAKE_SSH)
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
        "FAKE_REMOTE_HOME": str(tmp_path / "cluster"),
        "LAIN_EXAMPLE": str(EXAMPLE),
        **(env or {}),
    }
    return subprocess.run(
        ["bash", str(download / "install.sh")],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        env=full_env,
        cwd=tmp_path,
        timeout=30,
    )


def log_of(tmp_path: Path) -> list[str]:
    return (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()


def test_a_full_install_clones_configures_and_installs(tmp_path):
    lines = ["", *answers(), "n", "n"]  # ~/Lain; config; no key to create; no menu entry
    result = full_install(tmp_path, lines)
    assert_ok(result)
    checkout = tmp_path / "home" / "Lain"
    config = load_config(checkout / "config.yaml", environ={}, cwd=tmp_path).config
    assert config.cluster.host == "cluster.example"
    assert (tmp_path / "home" / "Documentos" / "LUCCI").is_dir()
    log = log_of(tmp_path)
    assert log[0] == "clone https://github.com/Mariano17omega/Lain.git"
    assert f"tool install --editable --force {checkout}" in log
    # lain is in ~/.local/bin, which this script put on its own PATH but the user's PATH lacks.
    assert "update-shell" in log
    assert "open a new terminal first" in result.stdout
    # Without ssh-copy-id, the command left to run is the fallback, not one that does not exist.
    assert "ssh-copy-id" not in result.stdout
    assert "'umask 077; mkdir -p ~/.ssh" in result.stdout
    assert "-o IdentitiesOnly=yes" in result.stdout
    assert result.stdout.isascii() and result.stderr.isascii()


def test_a_failed_git_pull_goes_on(tmp_path):
    checkout = tmp_path / "home" / "Lain"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('name = "lain"\n', encoding="utf-8")
    shutil.copyfile(EXAMPLE, checkout / "config.example.yaml")
    tool_bin = tmp_path / "home" / ".local" / "bin"
    lines = ["", "", *answers(), "n", "n"]  # ~/Lain; update it; config; no key; no menu entry
    result = full_install(tmp_path, lines, on_path=[tool_bin], env={"FAKE_GIT_PULL_FAILS": "1"})
    assert_ok(result)
    assert "git pull failed: going on" in result.stderr
    assert (checkout / "config.yaml").is_file()
    log = log_of(tmp_path)
    assert f"pull {checkout}" in log
    assert "clone" not in " ".join(log)
    # ~/.local/bin was already on the user's PATH: nothing to add, no new terminal needed.
    assert "update-shell" not in log
    assert "open a new terminal" not in result.stdout


def test_a_key_copied_without_ssh_copy_id_gets_a_line_of_its_own(tmp_path):
    key = tmp_path / "keys" / "id"
    key.parent.mkdir()
    key.write_text("private\n", encoding="utf-8")
    (tmp_path / "keys" / "id.pub").write_text("ssh-ed25519 AAAAnew me@laptop\n", encoding="utf-8")
    authorized = tmp_path / "cluster" / ".ssh" / "authorized_keys"
    authorized.parent.mkdir(parents=True)
    authorized.write_bytes(b"ssh-ed25519 AAAAold old@desk")  # no newline at the end
    lines = ["", *answers(key_path=str(key)), "y", "n", "n"]  # copy the key; no test; no menu
    result = full_install(tmp_path, lines)
    assert_ok(result)
    keys = [line for line in authorized.read_text(encoding="utf-8").splitlines() if line]
    assert keys == ["ssh-ed25519 AAAAold old@desk", "ssh-ed25519 AAAAnew me@laptop"]
    assert any(
        line.startswith("ssh -p 22 alice@cluster.example umask 077;") for line in log_of(tmp_path)
    )


def test_help_and_syntax():
    help_run = subprocess.run(
        ["bash", str(SCRIPT), "--help"], capture_output=True, text=True, timeout=30
    )
    assert help_run.returncode == 0
    assert "--config-only" in help_run.stdout and help_run.stdout.isascii()
    assert subprocess.run(["bash", "-n", str(SCRIPT)], timeout=30).returncode == 0
    assert SCRIPT.read_bytes().count(b"\r") == 0  # LF only (.gitattributes keeps it on Windows)
    assert os.access(SCRIPT, os.X_OK)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck():
    result = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout
