"""Moving to the cluster's trash (spec 84 R1): the target's name, what is refused, the exact line, and
the checks of the folder of the items and of each folder deleted (its subfolders too), when planned
and again before ``mv``. ``list_remote``, ``list_outputs``, ``fetch_jobs`` and ``run_action`` are
fakes: no network; the log of submitted jobs is in the test's data folder."""

from datetime import datetime

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote import trash as trash_module
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.cluster_jobs import JobsFailure
from qe_studio.core.remote.listing import NO_ACCESS, RemoteFailure
from qe_studio.core.remote.submit_log import record
from qe_studio.core.remote.trash import (
    IN_TRASH,
    ONE_FOLDER,
    ROOT,
    TrashBlocked,
    TrashDone,
    TrashPlan,
    plan_trash,
    run_trash,
    trash_blocked,
    trash_command,
    trash_target,
)
from qe_studio.core.remote.trash_dir import TRASH_DIR, TRASH_EXCLUDE, in_trash
from qe_studio.core.sync.command import CommandResult

from action_helpers import FakeAction
from jobs_helpers import EMPTY, USER, FakeFetch, snapshot, with_mine
from remote_helpers import FakeListing, FakeOutputs, entries

REMOTE_ROOT = "/home/u/runs"
PROJECT = f"{REMOTE_ROOT}/projeto"
PDOS = f"{PROJECT}/PDOS"
NOW = datetime(2026, 10, 30, 14, 2, 11)
STAMP = "2026-10-30_14-02-11"
ACCOUNT = f"{USER}@hpc.example"


def config(**cluster):
    settings = {"host": "hpc.example", "user": USER, **cluster}
    return parse_config({"paths": {"remote_root": REMOTE_ROOT}, "cluster": settings})


# -- the names -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("path", "is_dir", "target"),
    [
        (PDOS, True, f"trash/projeto/PDOS_{STAMP}"),
        (f"{PROJECT}/scf.in", False, f"trash/projeto/scf_{STAMP}.in"),
        (f"{PROJECT}/README", False, f"trash/projeto/README_{STAMP}"),
        (f"{PROJECT}/a.tar.gz", False, f"trash/projeto/a.tar_{STAMP}.gz"),
        (f"{PROJECT}/Al.v2", True, f"trash/projeto/Al.v2_{STAMP}"),  # a folder keeps its dots
        (PROJECT, True, f"trash/projeto_{STAMP}"),
    ],
)
def test_the_target_keeps_the_path_and_takes_the_date(path, is_dir, target):
    assert trash_target(REMOTE_ROOT, path, is_dir, NOW) == target


def test_the_trash_folder_is_named_once():
    assert TRASH_EXCLUDE == "/" + TRASH_DIR + "/" == "/trash/"  # anchored: the root's only
    assert in_trash(REMOTE_ROOT, f"{REMOTE_ROOT}/trash")
    assert in_trash(REMOTE_ROOT, f"{REMOTE_ROOT}/trash/projeto/PDOS_{STAMP}")
    assert not in_trash(REMOTE_ROOT, f"{REMOTE_ROOT}/trash2")
    assert not in_trash(REMOTE_ROOT, f"{PROJECT}/trash")  # only the root's
    assert not in_trash("", "/trash")


# -- what is refused -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("items", "reason"),
    [
        ([(REMOTE_ROOT, True)], ROOT),
        ([(f"{REMOTE_ROOT}/trash", True)], IN_TRASH),
        ([(f"{REMOTE_ROOT}/trash/projeto/PDOS_{STAMP}", True)], IN_TRASH),
        ([(f"{REMOTE_ROOT}/trash/x.out", False)], IN_TRASH),
        ([(PDOS, True), (f"{REMOTE_ROOT}/outro/a.in", False)], ONE_FOLDER),
    ],
)
def test_blocked(items, reason):
    assert trash_blocked(config(), items) == reason


def test_a_name_unfit_for_a_command_and_a_folder_outside_the_root_are_refused():
    unsafe = trash_blocked(config(), [(f"{PROJECT}/meu run", True)])
    assert unsafe.startswith("Nome não suportado") and "meu run" in unsafe
    assert "-rf" in trash_blocked(config(), [(f"{PROJECT}/-rf", False)])
    outside = trash_blocked(config(), [("/etc/passwd", False)])
    assert "não está em paths.remote_root" in outside
    assert trash_blocked(config(), [(PDOS, True), (f"{PROJECT}/scf.in", False)]) == ""


# -- the command -----------------------------------------------------------------------------------
def test_the_line_is_exact():
    items = [(PDOS, True), (f"{PROJECT}/scf.in", False)]
    assert trash_command(config(), items, NOW) == (
        f"cd {REMOTE_ROOT} && mkdir -p trash/projeto"
        f" && test ! -e trash/projeto/PDOS_{STAMP} && mv projeto/PDOS trash/projeto/PDOS_{STAMP}"
        f" && test ! -e trash/projeto/scf_{STAMP}.in && mv projeto/scf.in trash/projeto/scf_{STAMP}.in"
    )


def test_the_root_is_quoted_and_an_item_of_the_root_goes_to_trash_itself():
    cfg = parse_config(
        {"paths": {"remote_root": "/home/u/my runs"}, "cluster": {"host": "h", "user": "u"}}
    )
    assert trash_command(cfg, [("/home/u/my runs/proj", True)], NOW) == (
        f"cd '/home/u/my runs' && mkdir -p trash && test ! -e trash/proj_{STAMP}"
        f" && mv proj trash/proj_{STAMP}"
    )


def test_a_root_in_the_home_is_left_to_the_shell():
    cfg = parse_config({"paths": {"remote_root": "~/runs"}, "cluster": {"host": "h", "user": "u"}})
    assert trash_command(cfg, [("~/runs/projeto/PDOS", True)], NOW) == (
        f"cd ~/runs && mkdir -p trash/projeto && test ! -e trash/projeto/PDOS_{STAMP}"
        f" && mv projeto/PDOS trash/projeto/PDOS_{STAMP}"
    )


def test_the_command_refuses_what_is_blocked():
    with pytest.raises(ValueError, match="Nome não suportado"):
        trash_command(config(), [(f"{PROJECT}/a;rm -rf ~", False)], NOW)
    with pytest.raises(ValueError, match="lixeira"):
        trash_command(config(), [(f"{REMOTE_ROOT}/trash/x", True)], NOW)


# -- the checks ------------------------------------------------------------------------------------
@pytest.fixture
def outputs():
    """``list_outputs``, walking the folders of the ``fakes`` listing."""
    return FakeOutputs(FakeListing())


@pytest.fixture
def fakes(monkeypatch, outputs):
    """``(listing, fetch, run)``: ``projeto`` holds ``PDOS`` and ``scf.in``; ``PDOS`` holds a PDOS
    output; the queue has no job of the user; ``mv`` succeeds."""
    listing = FakeListing(
        {
            PROJECT: entries("PDOS", files=("scf.in", "scf.out")),
            PDOS: entries("orbitals", files=("al.pdos_tot",)),
        }
    )
    outputs.listing = listing
    fetch, run = FakeFetch(snapshot(EMPTY)), FakeAction()
    monkeypatch.setattr(trash_module, "list_remote", listing)
    monkeypatch.setattr(trash_module, "list_outputs", outputs)
    monkeypatch.setattr(trash_module, "fetch_jobs", fetch)
    monkeypatch.setattr(trash_module, "run_action", run)
    return listing, fetch, run


def test_the_plan_lists_again_and_asks_the_queue(fakes):
    listing, fetch, run = fakes
    plan = plan_trash(config(), [(PDOS, True), (f"{PROJECT}/scf.in", False)], now=NOW)
    assert isinstance(plan, TrashPlan), plan
    assert plan.remote_dir == PROJECT
    assert plan.moves == (
        ("projeto/PDOS", f"trash/projeto/PDOS_{STAMP}"),
        ("projeto/scf.in", f"trash/projeto/scf_{STAMP}.in"),
    )
    assert plan.line == trash_command(config(), plan.items, NOW)
    assert listing.calls == [PROJECT]  # the folder of the items
    assert len(fetch.calls) == 1
    assert run.commands == []  # planning changes nothing


def test_while_a_job_of_the_user_runs_each_folder_deleted_is_listed_whole(fakes, outputs):
    _listing, fetch, _run = fakes
    fetch.result = snapshot(with_mine("Elsewhere"))  # running in no folder of these
    plan = plan_trash(config(), [(PDOS, True), (f"{PROJECT}/scf.in", False)], now=NOW)
    assert isinstance(plan, TrashPlan), plan
    assert outputs.calls == [PDOS]  # not the file


def test_moving_runs_the_line_after_checking_again(fakes):
    listing, fetch, run = fakes
    plan = plan_trash(config(), [(PDOS, True)], now=NOW)
    assert isinstance(plan, TrashPlan)
    assert run_trash(config(), plan) == TrashDone(plan.moves)
    assert run.commands == [plan.line]
    assert listing.calls == [PROJECT, PROJECT] and len(fetch.calls) == 2


def test_an_item_gone_blocks(fakes):
    listing, _fetch, run = fakes
    plan = plan_trash(config(), [(f"{PROJECT}/nada.in", False)], now=NOW)
    assert isinstance(plan, TrashBlocked) and "nada.in" in plan.message
    listing.folders[PROJECT] = entries(files=("scf.in",))  # PDOS went away meanwhile
    assert isinstance(plan_trash(config(), [(PDOS, True)], now=NOW), TrashBlocked)
    assert run.commands == []


def test_a_running_job_in_the_folder_of_the_items_blocks_even_a_file(fakes):
    listing, fetch, run = fakes
    listing.folders[PROJECT] = entries("PDOS", "tmp", files=("scf.in", "Al-scf.o24000"))
    fetch.result = snapshot(with_mine("Al-scf"))
    for item in [(f"{PROJECT}/scf.in", False), (f"{PROJECT}/tmp", True)]:
        plan = plan_trash(config(), [item], now=NOW)
        assert plan == TrashBlocked(
            "Há um job seu em execução em projeto (24000): cancele-o antes de apagar."
        )
    assert run.commands == []


def test_a_running_job_in_a_folder_deleted_blocks(fakes):
    listing, fetch, _run = fakes
    listing.folders[PDOS] = entries(files=("al.pdos_tot", "PDOS-Al.o24000"))
    fetch.result = snapshot(with_mine("PDOS-Al"))
    plan = plan_trash(config(), [(PDOS, True)], now=NOW)
    assert plan == TrashBlocked(
        "Há um job seu em execução em projeto/PDOS (24000): cancele-o antes de apagar."
    )


def test_a_running_job_deep_in_a_folder_deleted_blocks(fakes):
    """A job submitted outside Lain, running in a subfolder of the project deleted: its output is
    found below, and the message names its folder."""
    listing, fetch, run = fakes
    listing.folders[REMOTE_ROOT] = entries("projeto")
    listing.folders[f"{PDOS}/orbitals"] = entries(files=("w.dat", "PDOS-Al.o24000"))
    fetch.result = snapshot(with_mine("PDOS-Al"))
    for item in (PROJECT, PDOS):
        plan = plan_trash(config(), [(item, True)], now=NOW)
        assert plan == TrashBlocked(
            "Há um job seu em execução em projeto/PDOS/orbitals (24000): cancele-o antes de apagar."
        )
    assert run.commands == []


def test_an_output_of_a_job_that_ended_does_not_block(fakes):
    listing, fetch, _run = fakes
    listing.folders[f"{PDOS}/orbitals"] = entries(files=("PDOS-Al.o23999",))  # an old run
    fetch.result = snapshot(with_mine("PDOS-Al"))  # the same name, another ID
    assert isinstance(plan_trash(config(), [(PDOS, True)], now=NOW), TrashPlan)


def test_a_job_lain_submitted_below_a_folder_deleted_blocks_while_in_the_queue(fakes):
    listing, fetch, _run = fakes
    listing.folders[REMOTE_ROOT] = entries("projeto")
    record(ACCOUNT, "25000", "Queued-0", f"{PDOS}/orbitals", "pdos.qsub")
    fetch.result = snapshot(with_mine(waiting=1))
    plan = plan_trash(config(), [(PROJECT, True)], now=NOW)
    assert plan == TrashBlocked(
        "O job 25000 (Queued-0), que o Lain submeteu de projeto/PDOS/orbitals, ainda está na fila: "
        "cancele-o pela fila antes de apagar."
    )
    fetch.result = snapshot(EMPTY)  # it ended
    assert isinstance(plan_trash(config(), [(PROJECT, True)], now=NOW), TrashPlan)


def test_a_job_lain_submitted_from_the_folder_of_the_items_blocks(fakes):
    _listing, fetch, _run = fakes
    record(ACCOUNT, "24000", "Al-scf", PROJECT, "scf.qsub")
    record("outro@hpc.example", "24000", "Al-scf", PDOS, "scf.qsub")  # another account's
    fetch.result = snapshot(with_mine("Al-scf"))
    plan = plan_trash(config(), [(f"{PROJECT}/scf.out", False)], now=NOW)
    assert isinstance(plan, TrashBlocked) and "está em execução" in plan.message


def test_a_queue_that_cannot_be_read_blocks(fakes):
    _listing, fetch, run = fakes
    fetch.result = JobsFailure("qstatus terminou com código 1.")
    plan = plan_trash(config(), [(f"{PROJECT}/scf.in", False)], now=NOW)
    assert isinstance(plan, ActionFailure)
    assert plan.message.startswith("Não foi possível conferir se roda um job aqui: qstatus")
    assert plan.message.endswith("Nada foi movido.")
    assert run.commands == []


def test_a_folder_that_cannot_be_listed_blocks(fakes):
    listing, fetch, _run = fakes
    fetch.result = snapshot(with_mine("Elsewhere"))  # a job runs: the folder must be looked in
    listing.folders[PDOS] = RemoteFailure(NO_ACCESS)
    assert plan_trash(config(), [(PDOS, True)], now=NOW) == ActionFailure(NO_ACCESS)


def test_a_subfolder_that_cannot_be_read_blocks_and_is_named(fakes):
    """A job of the user runs and the walk could not look there: it could be that job's folder."""
    listing, fetch, run = fakes
    fetch.result = snapshot(with_mine("Elsewhere"))
    listing.folders[f"{PDOS}/orbitals"] = RemoteFailure(NO_ACCESS)
    plan = plan_trash(config(), [(PDOS, True)], now=NOW)
    assert isinstance(plan, TrashBlocked)
    assert "projeto/PDOS/orbitals" in plan.message and REMOTE_ROOT not in plan.message
    assert run.commands == []


def test_a_job_found_in_what_could_be_read_is_named_first(fakes):
    listing, fetch, _run = fakes
    listing.folders[PDOS] = entries("orbitals", "locked", files=("PDOS-Al.o24000",))
    listing.folders[f"{PDOS}/locked"] = RemoteFailure(NO_ACCESS)
    fetch.result = snapshot(with_mine("PDOS-Al"))
    plan = plan_trash(config(), [(PDOS, True)], now=NOW)
    assert isinstance(plan, TrashBlocked) and "24000" in plan.message
    assert "locked" not in plan.message


def test_a_job_that_starts_while_the_dialog_is_open_blocks_the_move(fakes):
    listing, fetch, run = fakes
    plan = plan_trash(config(), [(PDOS, True)], now=NOW)
    assert isinstance(plan, TrashPlan)
    listing.folders[PDOS] = entries(files=("al.pdos_tot", "PDOS-Al.o24000"))
    fetch.result = snapshot(with_mine("PDOS-Al"))
    assert isinstance(run_trash(config(), plan), TrashBlocked)
    assert run.commands == []


def test_a_target_that_exists_stops_the_rest(fakes, monkeypatch):
    listing, _fetch, run = fakes
    items = [(PDOS, True), (f"{PROJECT}/scf.in", False)]
    plan = plan_trash(config(), items, now=NOW)
    assert isinstance(plan, TrashPlan)
    run.result = CommandResult(1, "", "")  # the second ``test ! -e``
    real = listing.folders[PROJECT]

    def after_the_first_move(config, remote_dir, password=None):
        if run.commands and remote_dir == PROJECT:
            return entries(files=("scf.in", "scf.out"))
        if remote_dir == f"{REMOTE_ROOT}/trash/projeto":
            return entries(f"PDOS_{STAMP}", files=(f"scf_{STAMP}.in",))
        return real if remote_dir == PROJECT else listing(config, remote_dir, password)

    monkeypatch.setattr(trash_module, "list_remote", after_the_first_move)
    done = run_trash(config(), plan)
    assert isinstance(done, TrashDone)
    assert done.moved == (("projeto/PDOS", f"trash/projeto/PDOS_{STAMP}"),)
    assert done.failure is not None
    assert done.failure.message == (
        f"Já existe trash/projeto/scf_{STAMP}.in no cluster: nada foi sobrescrito."
    )


def test_a_failure_before_any_move_is_the_answer(fakes):
    _listing, _fetch, run = fakes
    plan = plan_trash(config(), [(PDOS, True)], now=NOW)
    assert isinstance(plan, TrashPlan)
    run.result = CommandResult(1, "", "mkdir: cannot create directory 'trash': Permission denied\n")
    answer = run_trash(config(), plan)
    assert isinstance(answer, ActionFailure)
    assert answer.message == (
        "mv terminou com código 1: mkdir: cannot create directory 'trash': Permission denied"
    )
