"""The English catalog is split in one gettext domain per area of the code (``lain_<domain>.po``).

The domain of a message follows the files that use it (``scripts/i18n.py:domain_of``); the runtime
chains the ``.mo`` files (``qe_studio.i18n.load``), so ``_()`` stays a single function.
"""

from __future__ import annotations

import gettext
from pathlib import Path

import pytest

from i18n_helpers import script
from qe_studio import i18n
from qe_studio.i18n import DOMAINS, domain_name

tool = script()


@pytest.fixture(scope="module")
def updated():
    return tool.update(tool.extract(), "en")


def catalog(*entries):
    """An English catalog of ``(msgid, msgstr, file, …)``."""
    result = tool.new_catalog("en")
    for msgid, string, *files in entries:
        result.add(msgid, string, locations=[(name, 1) for name in files])
    return result


def by_domain(entries):
    return tool.split(catalog(*entries), "en")


# -- which domain holds a message --------------------------------------------------------------
@pytest.mark.parametrize(
    ("filename", "area"),
    [
        ("core/calc_create/types/slab.py", "calc_create"),
        ("core/plotting/grid.py", "calculations"),
        ("core/remote/trash.py", "sync"),
        ("ui/cluster/sync_coordinator.py", "sync"),
        ("ui/widgets/structure3d/panel.py", "structure3d"),
        ("ui/dialogs/atoms.py", "ui"),
        ("ui/actions.py", "ui"),
        ("core/config.py", "core"),
        ("i18n.py", "core"),
    ],
)
def test_the_area_follows_the_file(filename, area):
    assert tool.area_of(filename) == area


def test_a_message_of_one_area_goes_to_its_domain():
    parts = by_domain([("Abrir", "Open", "core/sync/rsync.py", "ui/cluster/sync_coordinator.py")])
    assert list(parts) == ["sync"]


def test_a_message_used_by_two_areas_goes_to_common():
    parts = by_domain([("Cancelar", "Cancel", "core/sync/rsync.py", "ui/dialogs/atoms.py")])
    assert list(parts) == ["common"]


def test_a_message_with_no_file_goes_to_core():
    assert list(by_domain([("Abrir", "Open")])) == ["core"]


def test_every_domain_name_is_known_and_unique():
    assert len(set(DOMAINS)) == len(DOMAINS)
    assert {tool.area_of(p) for p in ("ui/x.py", "core/x.py")} <= set(DOMAINS)
    assert {area for _prefix, area in tool.AREAS} | {tool.COMMON, tool.FALLBACK_AREA} <= set(
        DOMAINS
    )


# -- split and merge -----------------------------------------------------------------------------
def test_split_then_merge_gives_the_catalog_back(updated):
    parts = tool.split(updated, "en")
    merged = tool.merge(list(parts.values()), "en")
    assert len(tool.messages(merged)) == len(tool.messages(updated))
    ids = [tool.sources(m) for part in parts.values() for m in tool.messages(part)]
    assert len(ids) == len(set(ids)), "a message is in two domains"


def test_each_domain_file_is_what_update_would_write(updated):
    parts = tool.split(updated, "en")
    assert tool.domains_on_disk("en") == list(parts), "run `uv run python scripts/i18n.py update`"
    for domain, part in parts.items():
        on_disk = tool.read_catalog(tool.po_path("en", domain), "en")
        assert sorted(map(tool.signature, tool.messages(on_disk))) == sorted(
            map(tool.signature, tool.messages(part))
        ), domain


def test_no_stale_catalog_file_is_left():
    folder = tool.po_path("en", DOMAINS[0]).parent
    expected = {f"{domain_name(domain)}{ext}" for domain in DOMAINS for ext in (".po", ".mo")}
    assert {path.name for path in folder.iterdir()} <= expected


def test_write_domains_drops_the_file_of_an_emptied_domain(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "LOCALE", tmp_path)
    full = catalog(
        ("Abrir", "Open", "core/sync/rsync.py"), ("Fechar", "Close", "ui/dialogs/atoms.py")
    )
    tool.write_domains("en", full)
    assert tool.po_path("en", "sync").exists() and tool.po_path("en", "ui").exists()
    tool.compile_language("en")
    assert tool.mo_path("en", "ui").exists()
    tool.write_domains("en", catalog(("Abrir", "Open", "core/sync/rsync.py")))
    assert tool.po_path("en", "sync").exists()
    assert not tool.po_path("en", "ui").exists() and not tool.mo_path("en", "ui").exists()


def test_a_file_saying_the_same_is_not_rewritten(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "LOCALE", tmp_path)
    entries = [("Abrir", "Open", "core/sync/rsync.py")]
    tool.write_domains("en", catalog(*entries))
    target = tool.po_path("en", "sync")
    marked = "# marker\n" + target.read_text(encoding="utf-8")
    target.write_text(marked, encoding="utf-8")
    tool.write_domains("en", catalog(*entries))
    assert target.read_text(encoding="utf-8") == marked


def test_a_moved_message_keeps_its_translation(tmp_path, monkeypatch):
    """A message that changed area is found by its text in the merged catalog."""
    monkeypatch.setattr(tool, "LOCALE", tmp_path)
    tool.write_domains("en", catalog(("Abrir", "Open", "core/sync/rsync.py")))
    moved = tool.new_catalog()
    moved.add("Abrir", locations=[("ui/dialogs/atoms.py", 1)])
    merged = tool.update(moved, "en")
    assert [tool.forms(m) for m in tool.messages(merged)] == [("Open",)]
    assert list(tool.split(merged, "en")) == ["ui"]


# -- the runtime ---------------------------------------------------------------------------------
def write_mo(folder: Path, domain: str, entries: list[tuple[str, str]]) -> None:
    source = tool.new_catalog("en")
    for msgid, msgstr in entries:
        source.add(msgid, msgstr, locations=[("ui/x.py", 1)])
    target = folder / "en" / "LC_MESSAGES" / f"{domain_name(domain)}.mo"
    assert tool.compile_catalog(source, target) == []


def test_install_chains_the_domains(tmp_path, monkeypatch):
    write_mo(tmp_path, "common", [("Abrir", "Open")])
    write_mo(tmp_path, "sync", [("Enviar", "Upload")])
    write_mo(tmp_path, "core", [("Fechar", "Close")])
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)
    i18n.install("en")
    try:
        assert [i18n._(text) for text in ("Abrir", "Enviar", "Fechar", "Outro")] == [
            "Open",
            "Upload",
            "Close",
            "Outro",  # in no catalog: the source message
        ]
    finally:
        i18n.install(i18n.SOURCE_LANGUAGE)


def test_install_chains_the_plurals(tmp_path, monkeypatch):
    source = tool.new_catalog("en")
    source.add(
        ("{n} pasta", "{n} pastas"), ("{n} folder", "{n} folders"), locations=[("ui/x.py", 1)]
    )
    target = tmp_path / "en" / "LC_MESSAGES" / f"{domain_name('viewer')}.mo"
    assert tool.compile_catalog(source, target) == []
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)
    i18n.install("en")
    try:
        assert i18n.ngettext("{n} pasta", "{n} pastas", 1) == "{n} folder"
        assert i18n.ngettext("{n} pasta", "{n} pastas", 3) == "{n} folders"
        assert i18n.ngettext("{n} outra", "{n} outras", 3) == "{n} outras"
    finally:
        i18n.install(i18n.SOURCE_LANGUAGE)


def test_a_missing_catalog_shows_the_source_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)
    i18n.install("en")
    try:
        assert i18n._("Abrir") == "Abrir"
    finally:
        i18n.install(i18n.SOURCE_LANGUAGE)


def test_the_source_language_loads_no_catalog():
    chained = i18n.load(i18n.SOURCE_LANGUAGE)
    assert chained.gettext("Abrir pasta") == "Abrir pasta"


def test_the_committed_catalogs_translate_every_area():
    """``install("en")`` over the real ``.mo`` files: one message of each domain."""
    translation = i18n.load("en")
    assert isinstance(translation, gettext.NullTranslations)
    for domain in tool.domains_on_disk("en"):
        part = tool.read_catalog(tool.po_path("en", domain), "en")
        message = next(m for m in tool.messages(part) if isinstance(m.id, str) and m.string)
        assert translation.gettext(message.id) == message.string, domain


def test_the_script_runs_per_area(capsys):
    assert tool.main(["check", "--area", "sync"]) == 0
    assert "en:" in capsys.readouterr().out
