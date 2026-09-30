"""``tests/fixtures`` holds real QE outputs shared by every test: nothing may write into it."""

import shutil
import subprocess

import pytest

from conftest import FIXTURES


def git(*args: str) -> list[str]:
    return subprocess.run(
        ["git", *args], cwd=FIXTURES, capture_output=True, text=True, check=True
    ).stdout.splitlines()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_fixtures_are_untouched():
    """Runs last (see conftest), so it also sees what this run's tests wrote, besides leftovers
    of earlier runs or of the app pointed at the fixtures (an export into ``plots/``)."""
    try:
        git("rev-parse", "--is-inside-work-tree")
    except subprocess.CalledProcessError:
        pytest.skip("not a git checkout")
    # No --exclude-standard: files matched by .gitignore (e.g. *.log) count too.
    untracked = git("ls-files", "--others", "--", ".")
    modified = git("diff", "--name-only", "--relative", "--", ".")
    assert not untracked and not modified, (
        "tests/fixtures was changed (copy fixtures with copy_fixture before writing; "
        f"git add a new fixture on purpose): untracked={untracked} modified={modified}"
    )
