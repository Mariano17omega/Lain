"""``install.sh`` over an installation: the offer of a newer version and what it keeps.

Runs with the fake ``git``, ``uv`` and ``ssh`` of ``install_helpers``: the "repository" is what the
fake ``git clone`` writes, of the version the test gives it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from install_helpers import EXAMPLE, SCRIPT, executable, full_install, log_of

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="install.sh needs bash")

CONFIG = 'paths:\n  data: ""\ncluster:\n  host: "c.example"\n  user: "alice"\n  auth: key\n'
OFFER = "is available"
FOLDER = ""  # Enter: the default install folder, ~/Lain


def installed(tmp_path: Path, version: str = "1.0.0", config: str = CONFIG) -> Path:
    """A Lain of ``version`` in ``~/Lain``, cloned from the public repository, with a config.yaml."""
    checkout = tmp_path / "home" / "Lain"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        f'name = "lain"\nversion = "{version}"\n', encoding="utf-8"
    )
    shutil.copyfile(EXAMPLE, checkout / "config.example.yaml")
    (checkout / "config.yaml").write_text(config, encoding="utf-8")
    (checkout / "old_code.py").write_text("old\n", encoding="utf-8")
    return checkout


def update(
    tmp_path: Path, lines: list[str], remote: str = "1.1.0", env: dict[str, str] | None = None, **kw
):
    tool_bin = tmp_path / "home" / ".local" / "bin"
    return full_install(
        tmp_path,
        lines,
        on_path=[tool_bin],
        env={"FAKE_REMOTE_VERSION": remote, **(env or {})},
        **kw,
    )


def assert_ok(result) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def no_temp_left(tmp_path: Path) -> bool:
    return not list((tmp_path / "home").glob(".lain-update.*"))


def version_of(checkout: Path) -> str:
    return (checkout / "pyproject.toml").read_text(encoding="utf-8")


def test_an_accepted_update_keeps_a_backup_and_the_configuration(tmp_path):
    checkout = installed(tmp_path)
    (checkout / "config.yaml.bak").write_text("older\n", encoding="utf-8")
    # Only these two answers: one more question would end the input and fail the run.
    result = update(tmp_path, [FOLDER, "y"])
    assert_ok(result)
    backup = tmp_path / "home" / "lain-backup-1.0.0"

    assert 'version = "1.1.0"' in version_of(checkout)
    assert not (checkout / "old_code.py").exists()
    assert (checkout / "config.yaml").read_text(encoding="utf-8") == CONFIG
    assert (checkout / "config.yaml.bak").read_text(encoding="utf-8") == "older\n"

    assert 'version = "1.0.0"' in version_of(backup)
    assert (backup / "old_code.py").is_file()
    assert (backup / "config.yaml").read_text(encoding="utf-8") == CONFIG
    saved = backup / "config-backup"
    assert (saved / "config.yaml").read_text(encoding="utf-8") == CONFIG
    assert (saved / "config.yaml.bak").read_text(encoding="utf-8") == "older\n"

    assert f"tool install --editable --force {checkout}" in log_of(tmp_path)
    assert "Your configuration was kept." in result.stdout
    assert "1.0.0 -> 1.1.0" in result.stdout
    assert no_temp_left(tmp_path)


def test_settings_and_data_outside_are_copied_and_stay(tmp_path):
    installed(tmp_path)
    settings = tmp_path / "home" / ".config" / "qe-studio"
    settings.mkdir(parents=True)
    (settings / "QE Studio.conf").write_text("[ui]\n", encoding="utf-8")
    data = tmp_path / "home" / ".local" / "share" / "qe-studio"
    data.mkdir(parents=True)
    (data / "submitted_jobs.log").write_text("job\n", encoding="utf-8")
    (data / "lain.lock").write_text("123\n", encoding="utf-8")

    result = update(tmp_path, [FOLDER, "y"])
    assert_ok(result)
    assert "Lain seems to be open" in result.stderr
    saved = tmp_path / "home" / "lain-backup-1.0.0" / "config-backup"
    assert (saved / "settings" / "QE Studio.conf").read_text(encoding="utf-8") == "[ui]\n"
    assert (saved / "data" / "submitted_jobs.log").read_text(encoding="utf-8") == "job\n"
    assert not (saved / "data" / "lain.lock").exists()
    assert (settings / "QE Studio.conf").is_file()  # copied, not moved
    assert (data / "submitted_jobs.log").is_file()


def test_a_data_folder_inside_the_installation_goes_to_both(tmp_path):
    checkout = installed(tmp_path, config=CONFIG.replace('data: ""', 'data: "data"'))
    (checkout / "data").mkdir()
    (checkout / "data" / "settings.ini").write_text("[ui]\n", encoding="utf-8")
    assert_ok(update(tmp_path, [FOLDER, "y"]))
    backup = tmp_path / "home" / "lain-backup-1.0.0"
    assert (checkout / "data" / "settings.ini").read_text(encoding="utf-8") == "[ui]\n"
    assert (backup / "config-backup" / "data" / "settings.ini").is_file()
    assert (backup / "data" / "settings.ini").is_file()


def test_a_data_folder_holding_the_installation_is_not_copied(tmp_path):
    # paths.data: "~" holds ~/Lain itself: copying it would copy the whole home folder.
    checkout = installed(tmp_path, config=CONFIG.replace('data: ""', 'data: "~"'))
    result = update(tmp_path, [FOLDER, "y"])
    assert_ok(result)
    assert "holds the whole installation" in result.stderr
    assert 'version = "1.1.0"' in version_of(checkout)
    assert not (tmp_path / "home" / "lain-backup-1.0.0" / "config-backup" / "data").exists()


def test_a_declined_update_changes_nothing(tmp_path):
    checkout = installed(tmp_path)
    # No git pull question after a "no": then keep config.yaml, no key, no menu.
    result = update(tmp_path, [FOLDER, "n", "n", "n", "n"])
    assert_ok(result)
    assert OFFER in result.stdout
    assert 'version = "1.0.0"' in version_of(checkout)
    assert (checkout / "old_code.py").is_file()
    assert not (tmp_path / "home" / "lain-backup-1.0.0").exists()
    assert no_temp_left(tmp_path)
    assert not any(line.startswith("pull") for line in log_of(tmp_path))


@pytest.mark.parametrize(
    ("local", "remote"), [("1.0.0", "1.0.0"), ("1.0.10", "1.0.9"), ("2.0.0", "1.9.9")]
)
def test_no_offer_without_a_later_version(tmp_path, local, remote):
    checkout = installed(tmp_path, version=local)
    # The questions of a run with no update: the git pull, then keep config.yaml, no key, no menu.
    result = update(tmp_path, [FOLDER, "n", "n", "n", "n"], remote=remote)
    assert_ok(result)
    assert OFFER not in result.stdout
    assert f"up to date (version {local})" in result.stdout
    assert f'version = "{local}"' in version_of(checkout)
    assert no_temp_left(tmp_path)


def test_versions_compare_by_number(tmp_path):
    installed(tmp_path, version="1.0.9")
    result = update(tmp_path, [FOLDER, "y"], remote="1.0.10")
    assert_ok(result)
    assert (tmp_path / "home" / "lain-backup-1.0.9").is_dir()


def test_a_failed_download_goes_on_with_the_installed_version(tmp_path):
    checkout = installed(tmp_path)
    lines = [FOLDER, "n", "n", "n", "n"]
    result = update(tmp_path, lines, env={"FAKE_GIT_CLONE_FAILS": "1"})
    assert_ok(result)
    assert "could not look for updates" in result.stderr
    assert (checkout / "old_code.py").is_file()
    assert no_temp_left(tmp_path)


def test_a_clone_of_another_repository_is_never_replaced(tmp_path):
    checkout = installed(tmp_path)
    origin = "git@github.com:someone/lain-dev.git"
    result = update(tmp_path, [FOLDER, "n", "n", "n", "n"], env={"FAKE_ORIGIN": origin})
    assert_ok(result)
    assert OFFER not in result.stdout
    assert not any(line.startswith("clone") for line in log_of(tmp_path))
    assert (checkout / "old_code.py").is_file()


def test_an_ssh_origin_of_the_same_repository_counts(tmp_path):
    installed(tmp_path)
    origin = "git@github.com:Mariano17omega/Lain.git"
    assert_ok(update(tmp_path, [FOLDER, "y"], env={"FAKE_ORIGIN": origin}))
    assert (tmp_path / "home" / "lain-backup-1.0.0").is_dir()


def test_an_existing_backup_is_never_overwritten(tmp_path):
    installed(tmp_path)
    earlier = tmp_path / "home" / "lain-backup-1.0.0"
    earlier.mkdir()
    (earlier / "mine.txt").write_text("keep\n", encoding="utf-8")
    assert_ok(update(tmp_path, [FOLDER, "y"]))
    assert (earlier / "mine.txt").read_text(encoding="utf-8") == "keep\n"
    assert (tmp_path / "home" / "lain-backup-1.0.0_2" / "old_code.py").is_file()


def test_uncommitted_changes_are_told_before_asking(tmp_path):
    installed(tmp_path)
    result = update(tmp_path, [FOLDER, "n", "n", "n", "n"], env={"FAKE_GIT_DIRTY": "1"})
    assert_ok(result)
    assert "uncommitted changes" in result.stderr


def test_a_failed_swap_restores_the_installation(tmp_path):
    checkout = installed(tmp_path)
    real_mv = shutil.which("mv", path="/usr/bin:/bin")
    # The rename of the new version into place fails; every other mv works.
    executable(
        tmp_path / "bin" / "mv",
        f'#!/bin/sh\ncase "$*" in *.lain-update.*/new*) exit 1 ;; esac\nexec {real_mv} "$@"\n',
    )
    result = update(tmp_path, [FOLDER, "y"])
    assert result.returncode == 1
    assert "could not put the new version" in result.stderr
    assert 'version = "1.0.0"' in version_of(checkout)
    assert (checkout / "config.yaml").read_text(encoding="utf-8") == CONFIG
    assert not (checkout / "config-backup").exists()
    assert not (tmp_path / "home" / "lain-backup-1.0.0").exists()
    assert no_temp_left(tmp_path)


def test_it_updates_from_inside_the_installation(tmp_path):
    checkout = installed(tmp_path)
    shutil.copyfile(SCRIPT, checkout / "install.sh")
    result = update(tmp_path, ["y"], script=checkout / "install.sh", cwd=checkout)
    assert_ok(result)
    assert 'version = "1.1.0"' in version_of(checkout)
    assert (tmp_path / "home" / "lain-backup-1.0.0" / "install.sh").is_file()
    assert "still in the old folder" in result.stdout
