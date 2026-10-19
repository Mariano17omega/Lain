"""Spec 58 R3.3: a real pull and a real upload in English and in Portuguese, through the SSH server
of ``tests/ssh_server.py``.

The language is chosen once per process, so each run is a process of its own
(``tests/i18n_sync_run.py``) talking to the server that lives here. The texts are the same ones the
window shows, but nothing here depends on them to decide what is copied: the files, the left-alone
files and the failure of a password are compared between the languages, and the password is looked
for in everything the runs printed, logged or reported.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ssh_server import PASSWORD

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "i18n_sync_run.py"
RUN_TIMEOUT_S = 50
WRONG_PASSWORD = "wrong-lain-pw"
CLUSTER_COPY = "the copy the cluster already has\n"

pytestmark = pytest.mark.skipif(
    shutil.which("rsync") is None or shutil.which("ssh") is None, reason="rsync and ssh required"
)


def run_sync_in(language, step, folder, config, work, password=None) -> tuple[dict, str]:
    """``(result, raw)`` of one run of the runner: its JSON and everything it printed."""
    work.mkdir(parents=True, exist_ok=True)
    config_file = work / f"config-{language}-{step}.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    command = [sys.executable, str(RUNNER), "--language", language, "--config", str(config_file)]
    command += ["--step", step, "--folder", str(folder)]
    if password is not None:
        command += ["--password", password]
    done = subprocess.run(
        command, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, cwd=ROOT, check=False
    )
    assert done.returncode == 0, f"the run failed ({done.returncode}):\n{done.stderr[-3000:]}"
    return json.loads(done.stdout.strip().splitlines()[-1]), done.stdout + done.stderr


def configured(server, remote_root, local_root, **cluster) -> dict:
    data = server.config_data(**cluster)
    data["paths"] = {"local_root": str(local_root), "remote_root": str(remote_root)}
    return data


def files_under(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def test_sync_in_english_end_to_end(ssh_server, demo_project, tmp_path):
    """A pull and an upload of the demo project end with the same files copied in ``en`` and in
    ``pt_BR``, and the upload leaves alone the file the cluster already has."""
    server, cluster = ssh_server
    outcomes: dict[str, dict] = {}
    for language in ("pt_BR", "en"):
        remote_root, local_root = cluster / language, tmp_path / language / "local"
        shutil.copytree(demo_project, remote_root / "project")
        config = configured(server, remote_root, local_root)
        work = tmp_path / language
        pulled, _raw = run_sync_in(language, "pull", local_root / "project", config, work)

        # The cluster has one file of the calculation in another version and lacks two others.
        remote_bands = remote_root / "project" / "03_bands"
        (remote_bands / "bands.in").write_text(CLUSTER_COPY, encoding="utf-8")
        (remote_bands / "bands_pp.out").unlink()
        (remote_bands / "bands.dat.gnu").unlink()
        before = {name: (remote_bands / name).read_bytes() for name in files_under(remote_bands)}
        pushed, _raw = run_sync_in(
            language, "push", local_root / "project" / "03_bands", config, work
        )

        assert pulled["status"] == "done" and pushed["status"] == "done", (pulled, pushed)
        assert (remote_bands / "bands.in").read_text(encoding="utf-8") == CLUSTER_COPY
        after = {name: (remote_bands / name).read_bytes() for name in files_under(remote_bands)}
        assert {name: after[name] for name in before} == before  # nothing there was changed
        outcomes[language] = {"pull": pulled, "push": pushed}

    pt, en = outcomes["pt_BR"], outcomes["en"]
    expected = {
        path.relative_to(demo_project).as_posix()
        for path in demo_project.rglob("*")
        if path.is_file()
    }
    assert set(pt["pull"]["transferred"]) == set(en["pull"]["transferred"]) == expected
    for result in ("transferred", "existing"):
        assert en["push"][result] == pt["push"][result]
    assert en["push"]["transferred"] == ["bands.dat.gnu", "bands_pp.out"]
    assert en["push"]["existing"] == ["bands.in"]  # the dry run lists the files that differ
    rows = {
        language: [line for line in out["push"]["preview"] if line.startswith("row: ")]
        for language, out in outcomes.items()
    }
    assert [row.split(" | ")[0] for row in rows["en"]] == [
        row.split(" | ")[0] for row in rows["pt_BR"]
    ]

    # What the preview of the upload promised about the file the cluster had, in each language.
    en_preview, pt_preview = en["push"]["preview"], pt["push"]["preview"]
    assert "row: bands.in | will not be changed" in en_preview
    assert "row: bands.in | não será alterado" in pt_preview
    assert (
        "section: Already on the cluster, will not be changed (1) | will not be changed"
        in en_preview
    )
    assert any(line.startswith("section: To upload (2 · ") for line in en_preview)
    assert en_preview[0].startswith("summary: 2 files to upload (")
    assert en_preview[0].endswith("1 already on the cluster (will not be changed)")
    assert pt_preview[0].endswith("1 já existe no cluster (não será alterado)")
    # The report: the same two sentences the toast shows.
    assert en["push"]["message"].splitlines() == [
        "2 files uploaded.",
        "1 already existed on the cluster and was not changed.",
    ]
    assert en["pull"]["headline"].endswith("files downloaded.")
    assert pt["pull"]["headline"].endswith("arquivos baixados.")


def test_the_password_never_shows_in_english(ssh_server, demo_project, tmp_path):
    """A pull with a password and one with a wrong password, in English: the secret travels in the
    environment of ssh only, never in the output, the log or a report; a refusal is told by the flag."""
    server, cluster = ssh_server
    shutil.copytree(demo_project / "03_bands", cluster / "project" / "03_bands")
    config = configured(server, cluster, tmp_path / "local", auth="password")
    wrong_config = configured(server, cluster, tmp_path / "local-wrong", auth="password")

    accepted, raw = run_sync_in(
        "en", "pull", tmp_path / "local" / "project", config, tmp_path, PASSWORD
    )
    assert accepted["status"] == "done" and accepted["transferred"], accepted
    assert (tmp_path / "local" / "project" / "03_bands" / "scf.out").is_file()

    refused, raw_refused = run_sync_in(
        "en", "pull", tmp_path / "local-wrong" / "project", wrong_config, tmp_path, WRONG_PASSWORD
    )
    assert refused["status"] == "failed" and refused["auth_failed"] is True
    assert (
        refused["error"]
        == "Authentication refused by the cluster (check the user, key or password)."
    )
    assert refused["message"].startswith("Sync failed: Authentication refused")
    assert not (tmp_path / "local-wrong").exists()  # nothing created

    for secret, result, printed in (
        (PASSWORD, accepted, raw),
        (WRONG_PASSWORD, refused, raw_refused),
    ):
        assert any("rsync" in line for line in result["log"])  # the log was heard, and it is clean
        assert secret not in printed and secret not in json.dumps(result, ensure_ascii=False)
