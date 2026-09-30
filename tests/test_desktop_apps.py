from pathlib import Path

import pytest

from qe_studio.core.desktop_apps import AppCatalog, DesktopApp, expand_exec, split_exec


def write_app(data_dir: Path, name: str, body: str) -> Path:
    path = data_dir / "applications" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# comment\n[Desktop Entry]\nType=Application\n" + body)
    return path


def write_list(folder: Path, body: str, name: str = "mimeapps.list") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body)


@pytest.fixture
def dirs(tmp_path):
    """(user data dir, system data dir, user config dir), all empty: no real system apps."""
    return tmp_path / "home", tmp_path / "system", tmp_path / "config"


def catalog(dirs, desktops=()) -> AppCatalog:
    home, system, config = dirs
    return AppCatalog([home, system], [config], list(desktops))


def names(apps) -> list[str]:
    return [app.name for app in apps]


def test_registered_programs_and_skipped_entries(dirs):
    home, system, _ = dirs
    write_app(system, "editor.desktop", "Name=Editor\nExec=editor %f\nMimeType=text/plain;\n")
    write_app(system, "viewer.desktop", "Name=Viewer\nExec=viewer %U\nMimeType=image/png;\n")
    write_app(system, "hidden.desktop", "Name=H\nExec=h\nNoDisplay=true\nMimeType=text/plain;\n")
    write_app(system, "gone.desktop", "Name=G\nExec=g\nHidden=true\nMimeType=text/plain;\n")
    write_app(
        system, "absent.desktop", "Name=A\nExec=a\nTryExec=/nonexistent/a\nMimeType=text/plain;\n"
    )
    write_app(system, "noexec.desktop", "Name=N\nMimeType=text/plain;\n")
    (system / "applications" / "link.desktop").write_text(
        "[Desktop Entry]\nType=Link\nName=L\nURL=https://example.org\n"
    )
    apps = catalog(dirs)
    assert names(apps.apps_for(["text/plain"])) == ["Editor"]
    assert names(apps.apps_for(["image/png", "text/plain"])) == ["Editor", "Viewer"]
    assert apps.apps_for(["application/x-nothing"]) == []


def test_user_entries_shadow_system_ones(dirs):
    home, system, _ = dirs
    write_app(home, "kate.desktop", "Name=Kate (mine)\nExec=kate %U\nMimeType=text/plain;\n")
    write_app(system, "kate.desktop", "Name=Kate\nExec=kate %U\nMimeType=text/plain;\n")
    write_app(home, "old.desktop", "Name=Old\nExec=old\nHidden=true\n")  # "deleted" by the user
    write_app(system, "old.desktop", "Name=Old\nExec=old %f\nMimeType=text/plain;\n")
    write_app(
        system, "kde/dolphin.desktop", "Name=Dolphin\nExec=dolphin %u\nMimeType=inode/directory;\n"
    )
    apps = catalog(dirs)
    assert names(apps.apps_for(["text/plain"])) == ["Kate (mine)"]
    assert [app.id for app in apps.apps_for(["inode/directory"])] == ["kde-dolphin.desktop"]


def test_portuguese_names(dirs):
    _, system, _ = dirs
    write_app(
        system, "a.desktop", "Name=Viewer\nName[pt_BR]=Visualizador\nName[pt]=Visor\nExec=a\n"
    )
    write_app(system, "b.desktop", "Name=Editor\nName[pt]=Editor de texto\nExec=b\n")
    apps = catalog(dirs)
    assert apps.apps["a.desktop"].name == "Visualizador"
    assert apps.apps["b.desktop"].name == "Editor de texto"


def test_default_program(dirs):
    home, system, config = dirs
    for name in ("alpha", "beta", "gamma"):
        write_app(system, f"{name}.desktop", f"Name={name}\nExec={name} %f\nMimeType=text/plain;\n")
    assert catalog(dirs).default_app(["text/plain"]).name == "alpha"  # first of the list
    write_list(config, "[Default Applications]\ntext/plain=missing.desktop;beta.desktop;\n")
    assert catalog(dirs).default_app(["text/plain"]).name == "beta"
    # A desktop-specific list wins over the generic one.
    write_list(config, "[Default Applications]\ntext/plain=gamma.desktop\n", "kde-mimeapps.list")
    assert catalog(dirs, ["kde"]).default_app(["text/plain"]).name == "gamma"
    assert catalog(dirs, ["gnome"]).default_app(["text/plain"]).name == "beta"
    # The most specific type first: markdown files use the text/plain default.
    assert catalog(dirs).default_app(["text/markdown", "text/plain"]).name == "beta"
    assert catalog(dirs).default_app(["image/png"]) is None


def test_added_and_removed_associations(dirs):
    home, system, config = dirs
    write_app(system, "editor.desktop", "Name=Editor\nExec=editor %f\nMimeType=text/plain;\n")
    write_app(system, "ide.desktop", "Name=IDE\nExec=ide %F\n")  # no MimeType of its own
    write_list(
        config,
        "[Added Associations]\ntext/plain=ide.desktop;\n"
        "[Removed Associations]\ntext/plain=editor.desktop;\n",
    )
    apps = catalog(dirs)
    assert names(apps.apps_for(["text/plain"])) == ["IDE"]
    assert apps.default_app(["text/plain"]).name == "IDE"


def app(exec_line: str, icon: str = "") -> DesktopApp:
    return DesktopApp("x.desktop", "Prog", exec_line, icon, frozenset(), Path("/apps/x.desktop"))


@pytest.mark.parametrize(
    ("exec_line", "expected"),
    [
        ("kate -b %U", ["kate", "-b", "file:///runs/si%20bands/scf.in"]),
        ("gedit %f", ["gedit", "/runs/si bands/scf.in"]),
        ("prog %F %d", ["prog", "/runs/si bands/scf.in"]),
        ("prog", ["prog", "/runs/si bands/scf.in"]),  # no file code: the path is appended
        ("prog %i %c %k 100%%", ["prog", "--icon", "ic", "Prog", "/apps/x.desktop", "100%",
                                 "/runs/si bands/scf.in"]),
        ('"/opt/My App/app" --file=%f', ["/opt/My App/app", "--file=/runs/si bands/scf.in"]),
        ('prog "a\\"b" "c\\\\\\\\d" %u', ["prog", 'a"b', "c\\d", "file:///runs/si%20bands/scf.in"]),
    ],
)  # fmt: skip
def test_expand_exec(exec_line, expected):
    assert expand_exec(app(exec_line, icon="ic"), Path("/runs/si bands/scf.in")) == expected


def test_expand_exec_without_icon_and_shell_characters():
    path = Path("/runs/$(rm -rf ~); x.in")
    assert expand_exec(app("prog %i %f"), path) == ["prog", str(path)]


def test_split_exec_escapes():
    # General escapes apply before quoting: an unquoted "\\s" is just a separator.
    assert split_exec("a\\sb  c\t d") == ["a", "b", "c", "d"]
    assert split_exec('"a b"\\s""') == ["a b", ""]
