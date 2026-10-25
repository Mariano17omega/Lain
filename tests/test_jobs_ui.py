"""The cluster's jobs on the top bar (spec 64 R4–R6): what the indicator says, the queue popup and
its session cache, when queries run, the LED and closing. ``fetch_jobs`` is a fake
(``jobs_helpers.FakeFetch``); the real ssh path is ``test_cluster_jobs_ssh.py``."""

import time

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QInputDialog

from qe_studio.core.cluster_jobs import JobsFailure
from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.sync.monitor import ConnectionState
from qe_studio.ui import shutdown
from qe_studio.ui.theme.scale import scaled
from qe_studio.ui.widgets.jobs_popup import CANCEL, EMPTY, FAILURE, LOADING, TABLE, WIDTH

from jobs_helpers import EMPTY as EMPTY_LISTING
from jobs_helpers import QSTATUS_ALL, USER, FakeFetch, cluster_window, snapshot, with_mine

REFUSED = JobsFailure("Autenticação recusada pelo cluster.", auth=True)
OFFLINE = JobsFailure("Cluster inacessível (tempo de conexão esgotado).", connection=True)
MISSING = JobsFailure("O comando qstatus -a não foi encontrado no cluster.", missing=True)


@pytest.fixture
def make(window_factory, demo_project, monkeypatch, qtbot):
    """``make(fetch, **cluster)``: a window with a cluster, after the first answer (unless the
    fetch holds or no query can start)."""

    def build(fetch=None, wait=True, **cluster):
        fetch = fetch or FakeFetch()
        window = cluster_window(window_factory, demo_project, monkeypatch, fetch, **cluster)
        if wait:
            qtbot.waitUntil(lambda: window.jobs.result is not None, timeout=5000)
        return window, fetch

    return build


def text(window) -> str:
    return window.jobs.indicator.full_text()


def answer(qtbot, window, fetch, result) -> None:
    """``Atualizar`` with ``fetch`` answering ``result``."""
    fetch.result = result
    with qtbot.waitSignal(window.jobs.fetched, timeout=5000):
        window.jobs.refresh()


def app_state(state) -> None:
    app = QGuiApplication.instance()
    assert isinstance(app, QGuiApplication)
    app.applicationStateChanged.emit(state)


# -- the indicator (R4) -------------------------------------------------------------------------
def test_hidden_without_a_cluster(main_window):
    assert not main_window.jobs.enabled
    assert main_window.jobs.indicator.isHidden()


def test_hidden_without_a_command(make):
    window, fetch = make(wait=False, jobs_command="")
    assert window.jobs.indicator.isHidden() and fetch.calls == []


def test_the_indicator_is_left_of_the_led(make):
    window, _fetch = make()
    bar = window.top_bar
    layout = bar.layout()
    assert layout is not None
    order = [
        layout.indexOf(widget)
        for widget in (bar.breadcrumb, bar.plot_file, window.jobs.indicator, bar.led)
    ]
    assert order == sorted(order) and order[3] == order[2] + 1
    separator = layout.itemAt(order[3] + 1)
    assert separator is not None and separator.widget().objectName() == "topSeparator"
    assert window.jobs.indicator.isVisible()


def test_querying_until_the_first_answer(qtbot, make):
    fetch = FakeFetch()
    fetch.hold()
    window, _ = make(fetch, wait=False)
    qtbot.waitUntil(lambda: fetch.calls == [None], timeout=5000)
    assert text(window) == "Consultando jobs…"
    fetch.release()
    qtbot.waitUntil(lambda: window.jobs.result is not None, timeout=5000)
    assert text(window) == "Nenhum job em execução"


def test_no_job_of_the_user(make):
    window, _ = make()
    assert text(window) == "Nenhum job em execução"  # the listing has jobs of others only
    tip = window.jobs.indicator.toolTip()
    assert tip.startswith("Seus jobs: 0 em execução, 0 na fila · atualizado às ")
    assert not window.jobs.rotation.isActive()


def test_one_running_job_and_the_tooltip(make):
    window, _ = make(FakeFetch(snapshot(with_mine("Bands-kao-b", waiting=2))))
    assert text(window) == "Executando: Bands-kao-b"
    assert "1 em execução, 2 na fila" in window.jobs.indicator.toolTip()
    assert not window.jobs.rotation.isActive()


def test_the_name_rotates_among_the_running_jobs(make):
    window, _ = make(FakeFetch(snapshot(with_mine("Bands-kao-b", "PDS-B"))), jobs_rotate_seconds=7)
    jobs = window.jobs
    assert text(window) == "Executando: Bands-kao-b"
    assert jobs.rotation.isActive() and jobs.rotation.interval() == 7000
    seen = []
    for _ in range(3):
        jobs.rotate()  # the timer, by hand
        seen.append(text(window))
    assert seen == ["Executando: PDS-B", "Executando: Bands-kao-b", "Executando: PDS-B"]
    # The jobs of other owners never show, however long it turns.
    assert not any(name in t for t in seen for name in ("hBN+Sm-1", "Nd2Fe14B-4f-129"))


def test_a_long_name_is_elided_on_the_right(make):
    name = "Bands-" + "x" * 80
    window, _ = make(FakeFetch(snapshot(with_mine(name))))
    indicator = window.jobs.indicator
    assert indicator.full_text() == f"Executando: {name}"
    assert indicator.text().endswith("…") and indicator.text().startswith("Executando: Bands-")
    assert indicator.sizeHint().width() <= indicator.maximumWidth()


def test_a_failure_says_unavailable_and_why(make):
    window, _ = make(FakeFetch(OFFLINE))
    assert text(window) == "Jobs indisponíveis"
    assert window.jobs.indicator.toolTip() == OFFLINE.message


def test_a_password_is_asked_only_by_a_click(qtbot, make, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    asked = []
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: asked.append(1) or ("s3cret", True))
    )
    window, fetch = make(wait=False, auth="password", password_env="LAIN_NO_PW")
    qtbot.wait(100)
    assert text(window) == "Jobs: informe a senha"
    assert fetch.calls == [] and asked == []  # nothing on its own, no dialog
    window.jobs.poll()
    assert fetch.calls == [] and asked == []
    with qtbot.waitSignal(window.jobs.fetched, timeout=5000):
        window.jobs.indicator.click()
    assert asked == [1] and fetch.calls == ["s3cret"]
    assert window.sync.session_password(ask=False) == "s3cret"  # the sync's, for the session
    assert text(window) == "Nenhum job em execução"
    window.jobs.popup.hide()


def test_a_password_dialog_cancelled_opens_nothing(qtbot, make, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    window, fetch = make(wait=False, auth="password", password_env="LAIN_NO_PW")
    window.jobs.indicator.click()
    assert fetch.calls == [] and not window.jobs.popup.isVisible()


def test_a_password_in_the_environment_needs_no_click(make, monkeypatch):
    monkeypatch.setenv("LAIN_PW", "from-env")
    window, fetch = make(auth="password", password_env="LAIN_PW")
    assert fetch.calls == [None]  # child_env reads it from the config itself
    assert text(window) == "Nenhum job em execução"


# -- the popup (R5) ---------------------------------------------------------------------------
def open_popup(qtbot, window):
    window.jobs.indicator.click()
    popup = window.jobs.popup
    qtbot.waitUntil(popup.isVisible, timeout=2000)
    return popup


def test_the_popup_shows_both_sections_and_the_columns(qtbot, make):
    window, _ = make(FakeFetch(snapshot(with_mine("Bands-kao-b"))))
    popup = open_popup(qtbot, window)
    assert popup.page() == TABLE
    tree = popup.tree
    header = tree.headerItem()
    assert header is not None
    assert [header.text(c) for c in range(4)] == ["Nome", "Dono", "Envio / início", "Núcleos"]
    running, waiting = tree.topLevelItem(0), tree.topLevelItem(1)
    assert running is not None and waiting is not None
    assert (running.text(0), waiting.text(0)) == ("Em execução (4)", "Na fila (2)")
    first = running.child(0)
    assert first is not None
    assert [first.text(c) for c in range(4)] == [
        "Nd2Fe14B-4f-129",
        "usuario_a",
        "10/15 17:53",
        "32",
    ]
    assert first.toolTip(0) == "job-ID 23538 · physica.q · 10/15/2026 17:53:02"
    queued = waiting.child(0)
    assert queued is not None and queued.text(2) == "10/15 18:05" and queued.text(3) == "32"
    assert queued.toolTip(0) == "job-ID 23542 · 10/15/2026 18:05:21"  # waiting: no queue yet
    mine = running.child(3)
    assert mine is not None and mine.text(1) == USER
    accent = window.theme.color("accent_text")
    assert mine.font(0).bold() and mine.foreground(0).color() == accent
    assert not first.font(0).bold() and first.foreground(0).color() != accent
    assert popup.updated.text().startswith("Atualizado às ")


def test_the_two_sections_are_bars_of_their_own_colour(qtbot, make):
    window, _ = make()
    popup = open_popup(qtbot, window)
    running, waiting = popup.tree.topLevelItem(0), popup.tree.topLevelItem(1)
    assert running is not None and waiting is not None
    color = window.theme.color
    for item, bar in ((running, "job_running"), (waiting, "job_queued")):
        assert item.background(0).color() == color(f"{bar}_bg")
        assert item.foreground(0).color() == color(f"{bar}_fg")
        assert item.font(0).bold() and item.isFirstColumnSpanned()
    assert running.background(0).color() != waiting.background(0).color()
    assert popup.tree.indentation() > 0  # the jobs sit inside their bar


def test_the_popup_shows_the_cache_and_refresh_asks_again(qtbot, make):
    window, fetch = make()
    popup = open_popup(qtbot, window)
    assert fetch.calls == [None]  # the cache is fresh: nothing asked
    popup.hide()
    popup = open_popup(qtbot, window)
    assert fetch.calls == [None] and popup.page() == TABLE
    with qtbot.waitSignal(window.jobs.fetched, timeout=5000):
        popup.refresh_button.click()
    assert fetch.calls == [None, None]


def test_an_old_cache_is_shown_and_asked_again(qtbot, make):
    window, fetch = make()
    jobs = window.jobs
    jobs._clock = lambda: time.monotonic() + 301  # the poll interval went by
    with qtbot.waitSignal(jobs.fetched, timeout=5000):
        popup = open_popup(qtbot, window)
        assert popup.page() == TABLE  # the cache at once, while the query runs
    assert fetch.calls == [None, None]


def test_esc_closes_the_popup(qtbot, make):
    window, _ = make()
    popup = open_popup(qtbot, window)
    qtbot.keyClick(popup, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not popup.isVisible(), timeout=2000)


def test_only_the_users_waiting_jobs_have_a_cancel_button(qtbot, make):
    """Spec 70 R5: none in "Em execução", none on the jobs of others."""
    window, _ = make(FakeFetch(snapshot(with_mine("Bands-kao-b", waiting=2))))
    popup = open_popup(qtbot, window)
    tree = popup.tree
    header = tree.headerItem()
    assert header is not None and tree.columnCount() == 5 and header.text(CANCEL) == ""
    running, waiting = tree.topLevelItem(0), tree.topLevelItem(1)
    assert running is not None and waiting is not None
    widgets = [
        tree.itemWidget(section.child(i), CANCEL)
        for section in (running, waiting)
        for i in range(section.childCount())
    ]
    assert widgets == [None] * 6 + popup.cancel_buttons  # 4 running, 2 of usuario_a, then theirs
    assert [button.job.job_id for button in popup.cancel_buttons] == ["25000", "25001"]
    assert popup.cancel_buttons[0].toolTip() == "Cancelar o job 25000 (qdel)"
    assert all(button.isEnabled() for button in popup.cancel_buttons)
    assert popup.width() == scaled(WIDTH)


def test_no_waiting_job_of_the_user_no_button(qtbot, make):
    window, _ = make(FakeFetch(snapshot(with_mine("Bands-kao-b"))))
    assert open_popup(qtbot, window).cancel_buttons == []


def test_the_popup_before_the_first_answer(qtbot, make):
    fetch = FakeFetch()
    fetch.hold()
    window, _ = make(fetch, wait=False)
    qtbot.waitUntil(lambda: fetch.calls == [None], timeout=5000)
    popup = open_popup(qtbot, window)
    assert popup.page() == LOADING and not popup.refresh_button.isEnabled()
    fetch.release()
    qtbot.waitUntil(lambda: popup.page() == TABLE, timeout=5000)
    assert popup.refresh_button.isEnabled()


def test_an_empty_cluster(qtbot, make):
    window, _ = make(FakeFetch(snapshot(EMPTY_LISTING)))
    assert text(window) == "Nenhum job em execução"
    popup = open_popup(qtbot, window)
    assert popup.page() == EMPTY and popup.empty.text() == "Nenhum job no cluster."


def test_a_failure_and_try_again(qtbot, make):
    window, fetch = make(FakeFetch(OFFLINE))
    popup = open_popup(qtbot, window)
    assert popup.page() == FAILURE and popup.failure.text() == OFFLINE.message
    fetch.result = snapshot()
    with qtbot.waitSignal(window.jobs.fetched, timeout=5000):
        popup.retry_button.click()
    assert popup.page() == TABLE and text(window) == "Nenhum job em execução"


# -- when to ask, the LED and closing (R6) ----------------------------------------------------
def test_an_inactive_window_does_not_ask(qtbot, make):
    window, fetch = make(jobs_poll_seconds=60)
    jobs = window.jobs
    assert jobs.poll_timer.isActive() and jobs.poll_timer.interval() == 60_000
    app_state(Qt.ApplicationState.ApplicationInactive)
    assert not jobs.poll_timer.isActive()
    app_state(Qt.ApplicationState.ApplicationActive)  # back soon: the cache is fresh
    assert jobs.poll_timer.isActive() and fetch.calls == [None]
    app_state(Qt.ApplicationState.ApplicationInactive)
    jobs._clock = lambda: time.monotonic() + 61
    with qtbot.waitSignal(jobs.fetched, timeout=5000):
        app_state(Qt.ApplicationState.ApplicationActive)  # back after the interval: it asks
    assert fetch.calls == [None, None]


def test_the_answers_feed_the_led(qtbot, make):
    window, fetch = make(reachable=False)
    monitor = window.sync.monitor
    qtbot.waitUntil(lambda: not monitor._probing, timeout=5000)
    monitor.report(False)
    answer(qtbot, window, fetch, snapshot())
    assert monitor.state is ConnectionState.ONLINE
    answer(qtbot, window, fetch, OFFLINE)
    assert monitor.state is ConnectionState.OFFLINE
    answer(qtbot, window, fetch, REFUSED)  # the cluster answered: the LED stays as it was
    assert monitor.state is ConnectionState.OFFLINE
    answer(qtbot, window, fetch, MISSING)  # it answered, the command is missing: reachable
    assert monitor.state is ConnectionState.ONLINE
    assert window.top_bar.led.state == "online"


@pytest.mark.parametrize("failure", [REFUSED, MISSING])
def test_a_refused_login_or_a_missing_command_stops_the_polls(qtbot, make, failure):
    window, fetch = make(FakeFetch(failure))
    jobs = window.jobs
    window.sync._session_password = "typed"
    assert jobs.paused
    jobs._clock = lambda: time.monotonic() + 10_000
    jobs.poll()  # the timer
    app_state(Qt.ApplicationState.ApplicationActive)
    qtbot.wait(100)
    assert fetch.calls == [None]
    answer(qtbot, window, fetch, snapshot())  # "Atualizar" asks again
    assert fetch.calls == [None, None] and not jobs.paused


def test_a_refused_login_forgets_the_password_of_the_session(qtbot, make, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    window, fetch = make(wait=False, auth="password", password_env="LAIN_NO_PW")
    window.sync._session_password = "wrong"
    answer(qtbot, window, fetch, REFUSED)
    assert window.sync.session_password(ask=False) is None
    assert text(window) == "Jobs: informe a senha"
    assert REFUSED.message in window.jobs.indicator.toolTip()


def test_reloading_the_config_starts_over(qtbot, make, demo_project):
    window, fetch = make(FakeFetch(REFUSED))
    jobs = window.jobs
    assert jobs.paused and jobs.result is not None
    fetch.result = snapshot(QSTATUS_ALL)
    fetch.hold()
    window.use_session_root(demo_project)  # goes through _apply_loaded, as a reload does
    assert jobs.result is None and not jobs.paused
    assert text(window) == "Consultando jobs…"
    qtbot.waitUntil(lambda: len(fetch.calls) == 2, timeout=5000)
    fetch.release()
    qtbot.waitUntil(lambda: jobs.result is not None, timeout=5000)
    assert text(window) == "Nenhum job em execução"


def test_a_config_without_a_cluster_hides_the_indicator(make, demo_project):
    window, _ = make()
    config = parse_config({"paths": {"local_root": str(demo_project)}})
    window._apply_loaded(LoadedConfig(config, None))
    assert window.jobs.indicator.isHidden() and not window.jobs.poll_timer.isActive()


def test_closing_does_not_wait_for_a_hung_query(qtbot, make):
    fetch = FakeFetch()
    fetch.hold()  # never released: only the cancellation ends it
    window, _ = make(fetch, wait=False)
    qtbot.waitUntil(lambda: fetch.calls == [None], timeout=5000)
    window.close()
    report = window.shutdown_report
    assert report is not None and "cancelar" in report.ok
    assert report.elapsed_ms < shutdown.TOTAL_MS
    assert fetch.exited.wait(1.0)  # the worker saw the cancellation
    assert not window.jobs.poll_timer.isActive()
