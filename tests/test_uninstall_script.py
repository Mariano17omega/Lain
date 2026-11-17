"""``uninstall.sh``: what it lists, what it deletes and, above all, what it leaves alone.

Runs with the fake ``git``, ``uv`` and ``ssh`` of ``install_helpers``, in a temp home: nothing real
is deleted, and the fake ssh edits a temp folder that stands for the cluster account.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from install_helpers import (
    EXAMPLE,
    FAKE_GIT,
    FAKE_UV,
    ROOT,
    SCRIPT,
    SYSTEM_PATH,
    executable,
    fake_bin,
    full_install,
    log_of,
    windows,
)

UNINSTALL = ROOT / "uninstall.sh"
QUESTION = "Delete everything listed above?"
KEY_QUESTION = "Rename this key, so that ssh asks for your password again?"
BACKUP_QUESTION = "Also delete these backups?"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="uninstall.sh needs bash")

PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI+new/key+body me@laptop\n"


def config_text(tmp_path: Path, **values: str) -> str:
    root = values.get("local_root", str(tmp_path / "home" / "sims"))
    data = values.get("data", "")
    auth = values.get("auth", "key")
    key = values.get("key_path", str(tmp_path / "home" / ".ssh" / "id_ed25519"))
    return (
        f'paths:\n  local_root: "{root}"\n  data: "{data}"\n'
        f'cluster:\n  host: "c.example"\n  port: 22\n  user: "alice"\n  auth: {auth}\n'
        f'  key_path: "{key}"\n'
    )


def checkout_at(path: Path, config: str | None) -> Path:
    (path / ".git").mkdir(parents=True)
    (path / "pyproject.toml").write_text('name = "lain"\nversion = "1.0.0"\n', encoding="utf-8")
    shutil.copyfile(EXAMPLE, path / "config.example.yaml")
    (path / "code.py").write_text("code\n", encoding="utf-8")
    if config is not None:
        (path / "config.yaml").write_text(config, encoding="utf-8")
    return path


def installed(tmp_path: Path, config: str | None = None) -> Path:
    """A whole installation in a temp home, with simulations; returns the checkout."""
    home = tmp_path / "home"
    checkout = checkout_at(home / "Lain", config or config_text(tmp_path))
    (checkout / "config.yaml.bak").write_text("older\n", encoding="utf-8")

    tool = home / ".local" / "share" / "uv" / "tools" / "lain"
    tool.mkdir(parents=True)
    bin_dir = home / ".local" / "bin"
    (tool / "uv-receipt.toml").write_text(
        f'[tool]\nrequirements = [{{ name = "lain", editable = "{checkout}" }}]\n'
        f'entrypoints = [\n    {{ name = "lain", install-path = "{bin_dir}/lain", from = "lain" }},\n]\n',
        encoding="utf-8",
    )

    share = home / ".local" / "share"
    (share / "applications").mkdir(parents=True)
    (share / "applications" / "lain.desktop").write_text(
        "[Desktop Entry]\nName=Lain\nExec=lain\n", encoding="utf-8"
    )
    icon = share / "icons" / "hicolor" / "48x48" / "apps" / "lain.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"png")

    settings = home / ".config" / "qe-studio"
    settings.mkdir(parents=True)
    (settings / "QE Studio.conf").write_text("[ui]\n", encoding="utf-8")
    data = share / "qe-studio"
    data.mkdir(parents=True)
    (data / "submitted_jobs.log").write_text("job\n", encoding="utf-8")
    cache = home / ".cache" / "qe-studio"
    cache.mkdir(parents=True)
    (cache / "askpass.sh").write_text("x\n", encoding="utf-8")

    sims = home / "sims" / "Si"
    (sims / ".lain").mkdir(parents=True)
    (sims / "plots").mkdir()
    (sims / "scf.out").write_text("simulation\n", encoding="utf-8")
    (sims / ".lain" / "grids.json").write_text("{}\n", encoding="utf-8")
    (sims / "plots" / "bands.plot").write_text("plot\n", encoding="utf-8")
    return checkout


def add_key(tmp_path: Path) -> Path:
    """The local key pair; returns its folder."""
    ssh = tmp_path / "home" / ".ssh"
    ssh.mkdir(parents=True, exist_ok=True)
    (ssh / "id_ed25519").write_text("private\n", encoding="utf-8")
    (ssh / "id_ed25519.pub").write_text(PUBLIC_KEY, encoding="utf-8")
    return ssh


def uninstall(tmp_path: Path, lines: list[str], **kw) -> subprocess.CompletedProcess[str]:
    if "script" not in kw:
        download = tmp_path / "download"
        download.mkdir()
        kw["script"] = download / "uninstall.sh"
        shutil.copyfile(UNINSTALL, kw["script"])
    return full_install(tmp_path, lines, **kw)


def assert_ok(result) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def simulations_intact(tmp_path: Path) -> bool:
    sims = tmp_path / "home" / "sims" / "Si"
    return (
        (sims / "scf.out").read_text(encoding="utf-8") == "simulation\n"
        and (sims / ".lain" / "grids.json").is_file()
        and (sims / "plots" / "bands.plot").is_file()
    )


def test_an_accepted_uninstall_deletes_lain_and_keeps_the_simulations(tmp_path):
    checkout = installed(tmp_path)
    result = uninstall(tmp_path, ["y"])
    assert_ok(result)
    home = tmp_path / "home"
    assert not checkout.exists()
    assert "tool uninstall lain" in log_of(tmp_path)
    assert not (home / ".local" / "share" / "uv" / "tools" / "lain").exists()
    assert not (home / ".local" / "share" / "applications" / "lain.desktop").exists()
    assert not list((home / ".local" / "share" / "icons").rglob("lain.png"))
    assert not (home / ".config" / "qe-studio").exists()
    assert not (home / ".local" / "share" / "qe-studio").exists()
    assert not (home / ".cache" / "qe-studio").exists()
    assert simulations_intact(tmp_path)
    assert result.stdout.isascii() and result.stderr.isascii()


def test_every_path_is_listed_before_the_question(tmp_path):
    checkout = installed(tmp_path)
    home = tmp_path / "home"
    result = uninstall(tmp_path, ["n"])
    asked = result.stdout.index(QUESTION)
    for path in (
        checkout,
        checkout / "config.yaml",
        checkout / "config.yaml.bak",
        home / ".local" / "share" / "uv" / "tools" / "lain",
        home / ".local" / "bin" / "lain",
        home / ".local" / "share" / "applications" / "lain.desktop",
        home / ".local" / "share" / "icons" / "hicolor" / "48x48" / "apps" / "lain.png",
        home / ".config" / "qe-studio",
        home / ".local" / "share" / "qe-studio",
        home / ".cache" / "qe-studio",
    ):
        assert result.stdout.find(str(path)) in range(asked), path
    # The simulations are named too, under what stays.
    assert str(home / "sims") in result.stdout[:asked]


@pytest.mark.parametrize("answer", ["n", ""])
def test_no_or_enter_changes_nothing(tmp_path, answer):
    checkout = installed(tmp_path)
    result = uninstall(tmp_path, [answer])
    assert_ok(result)
    assert "Nothing was changed." in result.stdout
    assert (checkout / "code.py").is_file()
    assert (tmp_path / "home" / ".config" / "qe-studio").is_dir()
    assert "tool uninstall lain" not in log_of_if_any(tmp_path)


def log_of_if_any(tmp_path: Path) -> list[str]:
    return log_of(tmp_path) if (tmp_path / "log.txt").exists() else []


def kept(tmp_path: Path, checkout: Path, result, reason: str) -> None:
    """The folder stayed, the reason was told, and the rest of the uninstall went on."""
    assert_ok(result)
    assert (checkout / "code.py").is_file()
    assert reason in result.stdout
    assert not (tmp_path / "home" / ".config" / "qe-studio").exists()
    assert "tool uninstall lain" in log_of(tmp_path)


def test_a_folder_holding_the_simulations_stays(tmp_path):
    root = tmp_path / "home" / "Lain" / "sims"
    checkout = installed(tmp_path, config_text(tmp_path, local_root=str(root)))
    root.mkdir()
    (root / "scf.out").write_text("simulation\n", encoding="utf-8")
    result = uninstall(tmp_path, ["y"])
    kept(tmp_path, checkout, result, "your simulations (paths.local_root) are inside it")
    assert (root / "scf.out").is_file()


def test_a_root_that_cannot_be_located_keeps_the_folder(tmp_path):
    checkout = installed(tmp_path, config_text(tmp_path, local_root="$SCRATCH/sims"))
    kept(tmp_path, checkout, uninstall(tmp_path, ["y"]), "relative or has a variable")


@pytest.mark.parametrize(
    "status",
    ["?? notes.txt", "!! my_run.log", " M src/changed.py", "?? results/"],
)
def test_files_of_the_user_keep_the_folder(tmp_path, status):
    checkout = installed(tmp_path)
    result = uninstall(tmp_path, ["y"], env={"FAKE_GIT_STATUS": status})
    kept(tmp_path, checkout, result, "files that are not part of the program")
    assert status[3:].rstrip("/") in result.stdout


def test_what_lain_and_its_tools_make_does_not_keep_the_folder(tmp_path):
    checkout = installed(tmp_path)
    status = "\n".join(
        [
            "!! config.yaml",
            "!! config.yaml.bak",
            "!! .venv/",
            "!! src/qe_studio/__pycache__/",
            "!! src/lain.egg-info/",
            "!! .pytest_cache/",
        ]
    )
    assert_ok(uninstall(tmp_path, ["y"], env={"FAKE_GIT_STATUS": status}))
    assert not checkout.exists()


def test_a_clone_of_another_repository_stays(tmp_path):
    checkout = installed(tmp_path)
    env = {"FAKE_ORIGIN": "git@github.com:someone/lain-dev.git"}
    kept(tmp_path, checkout, uninstall(tmp_path, ["y"], env=env), "a clone of another repository")


def test_a_folder_without_git_stays(tmp_path):
    checkout = installed(tmp_path)
    shutil.rmtree(checkout / ".git")
    kept(tmp_path, checkout, uninstall(tmp_path, ["y"]), "no way to tell your files")


def test_local_commits_keep_the_folder(tmp_path):
    checkout = installed(tmp_path)
    result = uninstall(tmp_path, ["y"], env={"FAKE_GIT_LOCAL_COMMIT": "abc1234"})
    kept(tmp_path, checkout, result, "local commits")


def test_a_data_folder_of_the_user_loses_only_lains_files(tmp_path):
    folder = tmp_path / "home" / "mine"
    installed(tmp_path, config_text(tmp_path, data=str(folder)))
    folder.mkdir()
    (folder / "settings.ini").write_text("[ui]\n", encoding="utf-8")
    (folder / "lain.log").write_text("log\n", encoding="utf-8")
    (folder / "lain.log.1").write_text("log\n", encoding="utf-8")
    (folder / "thesis.tex").write_text("mine\n", encoding="utf-8")
    assert_ok(uninstall(tmp_path, ["y"]))
    assert sorted(p.name for p in folder.iterdir()) == ["thesis.tex"]


def test_a_data_folder_with_only_lains_files_goes(tmp_path):
    folder = tmp_path / "home" / "lain-data"
    installed(tmp_path, config_text(tmp_path, data=str(folder)))
    folder.mkdir()
    (folder / "settings.ini").write_text("[ui]\n", encoding="utf-8")
    assert_ok(uninstall(tmp_path, ["y"]))
    assert not folder.exists()


def test_the_home_as_data_folder_is_not_deleted(tmp_path):
    installed(tmp_path, config_text(tmp_path, data="~"))
    home = tmp_path / "home"
    (home / "lain.log").write_text("log\n", encoding="utf-8")
    (home / "personal.txt").write_text("mine\n", encoding="utf-8")
    assert_ok(uninstall(tmp_path, ["y"]))
    assert (home / "personal.txt").is_file()
    assert not (home / "lain.log").exists()
    assert simulations_intact(tmp_path)


def test_a_folder_holding_the_simulations_is_not_deleted_as_settings(tmp_path):
    root = tmp_path / "home" / ".config" / "qe-studio" / "sims"
    installed(tmp_path, config_text(tmp_path, local_root=str(root)))
    root.mkdir()
    (root / "scf.out").write_text("simulation\n", encoding="utf-8")
    assert_ok(uninstall(tmp_path, ["y"]))
    assert (root / "scf.out").is_file()


def test_another_programs_menu_entry_stays(tmp_path):
    installed(tmp_path)
    share = tmp_path / "home" / ".local" / "share"
    desktop = share / "applications" / "lain.desktop"
    desktop.write_text("[Desktop Entry]\nExec=other-program\n", encoding="utf-8")
    assert_ok(uninstall(tmp_path, ["y"]))
    assert desktop.is_file()
    assert list((share / "icons").rglob("lain.png"))


def backup_at(tmp_path: Path, name: str = "lain-backup-0.9.0") -> Path:
    backup = checkout_at(tmp_path / "home" / name, "old\n")
    (backup / "config-backup").mkdir()
    return backup


def test_backups_stay_by_default(tmp_path):
    installed(tmp_path)
    backup = backup_at(tmp_path)
    result = uninstall(tmp_path, ["y", ""])
    assert_ok(result)
    assert BACKUP_QUESTION in result.stdout
    assert str(backup) in result.stdout
    assert (backup / "code.py").is_file()


def test_backups_go_when_asked(tmp_path):
    installed(tmp_path)
    backup = backup_at(tmp_path)
    status = "!! config.yaml\n?? config-backup/"
    assert_ok(uninstall(tmp_path, ["y", "y"], env={"FAKE_GIT_STATUS": status}))
    assert not backup.exists()


def test_a_backup_with_files_of_the_user_is_not_offered(tmp_path):
    installed(tmp_path)
    backup = backup_at(tmp_path)
    # Both folders report the file: the installation stays as well, and no backup is offered.
    result = uninstall(tmp_path, ["y"], env={"FAKE_GIT_STATUS": "?? notes.txt"})
    assert_ok(result)
    assert BACKUP_QUESTION not in result.stdout
    assert backup.is_dir()


def test_renaming_the_key_keeps_it_and_never_calls_ssh(tmp_path):
    installed(tmp_path)
    ssh = add_key(tmp_path)
    result = uninstall(tmp_path, ["y", "y"])
    assert_ok(result)
    assert not (ssh / "id_ed25519").exists()
    assert not (ssh / "id_ed25519.pub").exists()
    assert (ssh / "id_ed25519.lain-disabled").read_text(encoding="utf-8") == "private\n"
    assert (ssh / "id_ed25519.pub.lain-disabled").read_text(encoding="utf-8") == PUBLIC_KEY
    assert not any(line.startswith("ssh ") for line in log_of(tmp_path))
    # How to undo it, and how to check it.
    assert f"mv {ssh}/id_ed25519.lain-disabled {ssh}/id_ed25519" in result.stdout
    assert f"mv {ssh}/id_ed25519.pub.lain-disabled {ssh}/id_ed25519.pub" in result.stdout
    assert "ssh -p 22 alice@c.example" in result.stdout


def test_the_rename_is_explained_before_the_question(tmp_path):
    installed(tmp_path)
    ssh = add_key(tmp_path)
    result = uninstall(tmp_path, ["y", "n"])
    explained = result.stdout[: result.stdout.index(KEY_QUESTION)]
    for text in (
        "never connects to the cluster",
        "only renames the key on this computer",
        str(ssh / "id_ed25519.lain-disabled"),
        "Nothing is deleted",
        "Be sure you know your cluster password",
        "GitHub",
        "public key stays on the cluster",
        "another key of yours",
    ):
        assert text in explained, text


@pytest.mark.parametrize("answer", ["n", ""])
def test_a_declined_rename_leaves_the_key(tmp_path, answer):
    installed(tmp_path)
    ssh = add_key(tmp_path)
    assert_ok(uninstall(tmp_path, ["y", answer]))
    assert (ssh / "id_ed25519").read_text(encoding="utf-8") == "private\n"
    assert (ssh / "id_ed25519.pub").is_file()
    assert not list(ssh.glob("*.lain-disabled"))


def test_a_private_key_without_its_public_half_is_renamed(tmp_path):
    installed(tmp_path)
    ssh = add_key(tmp_path)
    (ssh / "id_ed25519.pub").unlink()
    assert_ok(uninstall(tmp_path, ["y", "y"]))
    assert (ssh / "id_ed25519.lain-disabled").is_file()


def test_an_earlier_rename_is_never_overwritten(tmp_path):
    installed(tmp_path)
    ssh = add_key(tmp_path)
    (ssh / "id_ed25519.lain-disabled").write_text("older\n", encoding="utf-8")
    assert_ok(uninstall(tmp_path, ["y", "y"]))
    assert (ssh / "id_ed25519.lain-disabled").read_text(encoding="utf-8") == "older\n"
    assert (ssh / "id_ed25519.lain-disabled_2").read_text(encoding="utf-8") == "private\n"


def test_the_key_leaves_ssh_agent(tmp_path):
    installed(tmp_path)
    ssh = add_key(tmp_path)
    executable(tmp_path / "bin" / "ssh-add", '#!/bin/sh\necho "ssh-add $*" >> "$FAKE_LOG"\n')
    assert_ok(uninstall(tmp_path, ["y", "y"]))
    assert f"ssh-add -d {ssh}/id_ed25519" in log_of(tmp_path)


def test_no_key_question_with_a_password_login(tmp_path):
    installed(tmp_path, config_text(tmp_path, auth="password"))
    add_key(tmp_path)
    result = uninstall(tmp_path, ["y"])
    assert_ok(result)
    assert KEY_QUESTION not in result.stdout


def test_no_key_question_without_a_key(tmp_path):
    installed(tmp_path)
    result = uninstall(tmp_path, ["y"])
    assert_ok(result)
    assert KEY_QUESTION not in result.stdout


def test_no_key_question_without_a_cluster(tmp_path):
    installed(tmp_path, config_text(tmp_path).replace('"c.example"', '""'))
    ssh = add_key(tmp_path)
    result = uninstall(tmp_path, ["y"])
    assert_ok(result)
    assert KEY_QUESTION not in result.stdout
    assert (ssh / "id_ed25519").is_file()


def test_no_command_can_reach_the_cluster():
    # The cluster is production: this script must have no way of touching it.
    for line in UNINSTALL.read_text(encoding="utf-8").splitlines():
        code = line.strip()
        if not code.startswith("#"):
            assert not re.match(r"(ssh|scp|sftp|rsync|ssh-copy-id)\b(?!-)", code), line


def test_without_uv_the_command_is_reported_and_the_rest_goes(tmp_path):
    checkout = installed(tmp_path)
    result = uninstall(tmp_path, ["y"], without=("uv",))
    assert_ok(result)
    assert "only uv can remove it" in result.stderr
    assert (tmp_path / "home" / ".local" / "share" / "uv" / "tools" / "lain").is_dir()
    assert not checkout.exists()


def test_nothing_installed_says_so(tmp_path):
    (tmp_path / "home").mkdir()
    result = uninstall(tmp_path, [""])
    assert_ok(result)
    assert "Nothing of Lain was found" in result.stdout


def test_it_runs_from_inside_the_folder_it_deletes(tmp_path):
    checkout = installed(tmp_path)
    shutil.copyfile(UNINSTALL, checkout / "uninstall.sh")
    result = uninstall(tmp_path, ["y"], script=checkout / "uninstall.sh", cwd=checkout)
    assert_ok(result)
    assert not checkout.exists()
    assert "the folder just deleted" in result.stdout


def test_windows_deletes_its_folders_and_registry_key(tmp_path):
    env = windows(tmp_path)
    profile = Path(env["USERPROFILE"])
    appdata, local = profile / "AppData" / "Roaming", profile / "AppData" / "Local"
    (appdata / "qe-studio").mkdir(parents=True)
    (local / "qe-studio").mkdir(parents=True)
    env.update({"APPDATA": str(appdata), "LOCALAPPDATA": str(local)})
    executable(
        tmp_path / "bin" / "reg",
        '#!/bin/sh\necho "reg $* conv=$MSYS2_ARG_CONV_EXCL" >> "$FAKE_LOG"\n',
    )
    config = config_text(tmp_path).replace(str(tmp_path / "home"), str(profile))
    (profile / "sims").mkdir()
    checkout = checkout_at(profile / "Lain", config)
    tools = tmp_path / "home" / ".local" / "share" / "uv" / "tools" / "lain"
    tools.mkdir(parents=True)
    (tools / "uv-receipt.toml").write_text(f'editable = "{checkout}"\n', encoding="utf-8")

    result = uninstall(tmp_path, ["y"], env=env)
    assert_ok(result)
    assert "Windows, Git Bash" in result.stdout
    assert "HKCU\\Software\\qe-studio" in result.stdout
    assert not (appdata / "qe-studio").exists()
    assert not (local / "qe-studio").exists()
    assert not checkout.exists()
    assert (profile / "sims").is_dir()
    # MSYS would otherwise rewrite /f as a path.
    assert any(
        line.startswith("reg delete HKCU\\Software\\qe-studio /f") and line.endswith("conv=*")
        for line in log_of(tmp_path)
    )


def test_enter_in_the_menu_deletes_nothing(tmp_path):
    pty = pytest.importorskip("pty")
    checkout = installed(tmp_path)
    bin_dir = fake_bin(tmp_path)
    executable(bin_dir / "git", FAKE_GIT)
    executable(bin_dir / "uv", FAKE_UV)
    master, slave = pty.openpty()
    process = subprocess.Popen(
        ["bash", str(UNINSTALL)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={
            "HOME": str(tmp_path / "home"),
            "PATH": f"{bin_dir}:{SYSTEM_PATH}",
            "LANG": "C.UTF-8",
            "TERM": "xterm-256color",
            "FAKE_LOG": str(tmp_path / "log.txt"),
            "FAKE_TOOLS_DIR": str(tmp_path / "home" / ".local" / "share" / "uv" / "tools"),
            "LAIN_DIR": str(checkout),
        },
        cwd=tmp_path,
        start_new_session=True,
    )
    output = ""
    try:
        deadline = time.monotonic() + 20
        answered = False
        while process.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                output += os.read(master, 65536).decode("utf-8", "replace")
            if not answered and "○ Yes" in output:  # the menu, starting on No
                time.sleep(0.05)
                os.write(master, b"\r")
                answered = True
        assert process.poll() == 0, output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
    assert "⣿" in output  # the portrait
    assert (checkout / "code.py").is_file()
    assert (tmp_path / "home" / ".config" / "qe-studio").is_dir()


# What the two scripts must have in common, since `curl | bash` gets only one file.
SHARED = (
    "say", "info", "ok", "retry", "warn", "die", "step", "section", "detect_ui", "hide_cursor",
    "show_cursor", "term_cols", "repeat", "panel", "read_answer", "prompt_start", "select_menu",
    "ask", "ask_yes_no", "detect_platform", "expand_home", "full_path_ok", "local_path", "on_path",
    "add_to_path", "has", "shell_quote", "unique_name", "get_key", "read_cluster_from", "is_lain_checkout", "script_checkout",
    "project_version", "repo_id", "same_repo", "user_config_dir", "system_data_dir", "data_folder",
)  # fmt: skip


def function_text(script: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?(?:\}}$|^\}}$)", script, re.M | re.S)
    assert match is not None, name
    return match.group(0)


@pytest.mark.parametrize("name", SHARED)
def test_the_shared_functions_are_the_same_in_both_scripts(name):
    install = SCRIPT.read_text(encoding="utf-8")
    remove = UNINSTALL.read_text(encoding="utf-8")
    assert function_text(install, name) == function_text(remove, name)


def test_the_portrait_is_the_same_in_both_scripts():
    pattern = re.compile(r"^PORTRAIT='.*?'$", re.M | re.S)
    install = pattern.search(SCRIPT.read_text(encoding="utf-8"))
    remove = pattern.search(UNINSTALL.read_text(encoding="utf-8"))
    assert install is not None and remove is not None
    assert install.group(0) == remove.group(0)


def test_help_and_syntax():
    help_run = subprocess.run(
        ["bash", str(UNINSTALL), "--help"], capture_output=True, text=True, timeout=30
    )
    assert help_run.returncode == 0
    assert "--plain" in help_run.stdout and help_run.stdout.isascii()
    assert subprocess.run(["bash", "-n", str(UNINSTALL)], timeout=30).returncode == 0
    assert UNINSTALL.read_bytes().count(b"\r") == 0
    assert os.access(UNINSTALL, os.X_OK)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck():
    result = subprocess.run(
        ["shellcheck", str(UNINSTALL)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout
