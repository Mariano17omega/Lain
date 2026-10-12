"""Spec 38 R1: Markdown files open rendered in the text viewer, with a switch to the text."""

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QImage, QTextDocument, QTextFormat

from qe_studio.core.calc_create.types import by_id
from qe_studio.core.calc_create.writer import create_folder
from qe_studio.core.text_preview import MARKDOWN_RENDER_LIMIT

from calc_helpers import AL_PATH, JOBS, al
from viewer_helpers import CTRL, key, open_text

MARKDOWN = """# Resultados do Al

Texto com **negrito**, `codigo` e [o site](https://example.org/doc) e [outro](outro.md).

- item um
- [x] item feito

| a | b |
|---|---|
| 1 | 2 |

```
bloco de codigo
```

<script>alert(1)</script>

## Notas
"""
KEY = "viewer/markdown_rendered"


def write(tmp_path: Path, text: str = MARKDOWN, name: str = "LEIA.md") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


@pytest.fixture
def opened(qtbot, main_window, tmp_path, monkeypatch):
    """The viewer of ``LEIA.md``, with ``QDesktopServices.openUrl`` replaced by a recorder."""
    urls: list[str] = []

    def record(url):
        urls.append(url.toString())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(record))
    viewer = open_text(qtbot, main_window, write(tmp_path))
    viewer.opened_urls = urls
    return viewer


def focus(qtbot, window, widget) -> None:
    """Shortcuts need the focus inside an active window, which offscreen gives a moment after show."""
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=3000)
    widget.setFocus()


def fragments(document: QTextDocument):
    """(text, char format) of every fragment of ``document``."""
    out = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            out.append((it.fragment().text(), it.fragment().charFormat()))
            it += 1
        block = block.next()
    return out


def format_of(document: QTextDocument, text: str):
    return next(fmt for t, fmt in fragments(document) if t == text)


# -- what opens rendered -----------------------------------------------------------------------
def test_markdown_opens_rendered_and_plain_text_does_not(qtbot, main_window, tmp_path):
    md = open_text(qtbot, main_window, write(tmp_path))
    markdown = open_text(qtbot, main_window, write(tmp_path, name="LEIA.markdown"))
    txt = open_text(qtbot, main_window, write(tmp_path, name="notas.txt"))
    for viewer in (md, markdown):
        assert viewer.viewing_rendered
        assert viewer.stack.currentWidget() is viewer.markdown
        assert viewer.text_button.isVisibleTo(viewer) and viewer.rendered_button.isEnabled()
    assert not txt.viewing_rendered and txt.stack.currentWidget() is txt.editor
    assert not txt.text_button.isVisibleTo(txt) and not txt.rendered_button.isVisibleTo(txt)
    assert txt.markdown.source == ""


def test_structure_comes_out_and_the_marks_do_not(opened):
    view = opened.markdown
    html = view.document().toHtml()
    assert "<h1" in html and "<h2" in html and "<table" in html and "<ul" in html
    shown = view.toPlainText()
    assert "#" not in shown.replace("# ", "") and "**" not in shown and "`" not in shown
    assert "Resultados do Al" in shown and "negrito" in shown and "bloco de codigo" in shown
    fence = QTextFormat.Property.BlockCodeFence
    block = view.document().begin()
    while block.isValid() and block.text() != "bloco de codigo":
        block = block.next()
    assert block.isValid() and block.blockFormat().hasProperty(fence)


def test_raw_html_is_shown_as_text_not_interpreted(opened):
    document = opened.markdown.document()
    assert "<script>alert(1)</script>" in opened.markdown.toPlainText()
    assert "<script" not in document.toHtml() and "&lt;script" in document.toHtml()


# -- links -------------------------------------------------------------------------------------
def test_a_web_link_opens_in_the_browser(opened):
    opened.markdown.anchorClicked.emit(QUrl("https://example.org/doc"))
    assert opened.opened_urls == ["https://example.org/doc"]


def test_a_real_click_on_a_link_reaches_the_browser(qtbot, opened):
    view = opened.markdown
    cursor = view.document().find("o site")
    assert not cursor.isNull()
    cursor.setPosition(cursor.selectionStart() + 3)  # inside the link text
    qtbot.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=view.cursorRect(cursor).center()
    )
    assert opened.opened_urls == ["https://example.org/doc"]


@pytest.mark.parametrize("target", ["outro.md", "file:///etc/passwd", "/home/x.md", "ftp://h/x"])
def test_any_other_link_is_not_opened_and_the_footer_says_so(qtbot, main_window, opened, target):
    opened.markdown.anchorClicked.emit(QUrl(target))
    assert opened.opened_urls == []
    assert main_window.status.message.text() == f"Link não aberto: {target}"


def test_an_anchor_scrolls_to_its_heading(qtbot, main_window, tmp_path):
    text = "# Topo\n\n" + "paragrafo\n\n" * 200 + "## Fim do Arquivo\n\nfim\n"
    viewer = open_text(qtbot, main_window, write(tmp_path, text))
    viewer.resize(600, 300)
    view = viewer.markdown
    assert view.verticalScrollBar().value() == 0
    view.anchorClicked.emit(QUrl("#fim-do-arquivo"))
    assert view.verticalScrollBar().value() > 0
    assert view.textCursor().block().text() == "Fim do Arquivo"
    assert not view.scroll_to_heading("nao-existe")


def test_images_resolve_in_the_files_folder_and_nothing_is_fetched(qtbot, main_window, tmp_path):
    picture = tmp_path / "pic.png"
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(0xFF0000)
    assert image.save(str(picture))
    viewer = open_text(qtbot, main_window, write(tmp_path, "![p](pic.png)\n"))
    resource = QTextDocument.ResourceType.ImageResource.value
    view = viewer.markdown
    assert view.loadResource(resource, QUrl("pic.png"))
    assert view.loadResource(resource, QUrl("https://example.org/a.png")) is None
    assert view.loadResource(resource, QUrl(picture.as_uri())) is None
    assert view.loadResource(resource, QUrl(str(picture))) is None


# -- the switch --------------------------------------------------------------------------------
def test_switching_shows_the_original_text_with_line_numbers(opened):
    opened.text_button.click()
    assert not opened.viewing_rendered and opened.stack.currentWidget() is opened.editor
    assert opened.editor.toPlainText() == MARKDOWN
    assert opened.editor.number_at(0) == 1 and opened.editor.number_at(4) == 5
    assert opened.line_button.isVisibleTo(opened) and opened.text_button.isChecked()
    opened.rendered_button.click()
    assert opened.viewing_rendered and not opened.line_button.isVisibleTo(opened)
    assert opened.rendered_button.isChecked() and not opened.text_button.isChecked()


def test_the_choice_is_the_programs_and_is_remembered(qtbot, window_factory, tmp_path):
    window = window_factory()
    path = write(tmp_path)
    viewer = open_text(qtbot, window, path)
    assert viewer.viewing_rendered and window.settings.value(KEY, True, type=bool) is True
    viewer.text_button.click()
    assert window.settings.value(KEY, True, type=bool) is False
    other = open_text(qtbot, window, write(tmp_path, name="OUTRO.md"))
    assert not other.viewing_rendered  # opened after the click
    window.close()

    restarted = window_factory()  # the same settings file: the app started again
    again = open_text(qtbot, restarted, path)
    assert not again.viewing_rendered and again.text_button.isChecked()
    again.rendered_button.click()
    assert restarted.settings.value(KEY, True, type=bool) is True


def test_a_click_in_one_tab_changes_the_other_open_tabs(qtbot, main_window, tmp_path):
    first = open_text(qtbot, main_window, write(tmp_path))
    second = open_text(qtbot, main_window, write(tmp_path, name="OUTRO.md"))
    assert first.viewing_rendered and second.viewing_rendered
    second.text_button.click()
    assert not first.viewing_rendered and not second.viewing_rendered
    first.rendered_button.click()
    assert first.viewing_rendered and second.viewing_rendered


def test_find_in_the_rendered_view_shows_the_text_and_opens_the_search(qtbot, main_window, opened):
    focus(qtbot, main_window, opened.markdown)
    key(qtbot, opened.markdown, "F", CTRL)
    assert not opened.viewing_rendered and not opened.search.isHidden()
    assert opened.text_button.isChecked()
    assert main_window.settings.value(KEY, True, type=bool) is True  # this tab only: not the choice
    opened.rendered_button.click()
    assert opened.viewing_rendered and opened.search.isHidden()


def test_next_match_key_in_the_rendered_view_also_opens_the_search(qtbot, main_window, opened):
    focus(qtbot, main_window, opened.markdown)
    key(qtbot, opened.markdown, "F3")
    assert not opened.viewing_rendered and not opened.search.isHidden()


# -- theme -------------------------------------------------------------------------------------
def test_links_code_and_tables_follow_the_theme(qtbot, main_window, opened):
    theme = main_window.theme
    document = opened.markdown.document()

    def check():
        assert format_of(document, "o site").foreground().color() == theme.color("accent")
        code = format_of(document, "codigo")
        assert code.foreground().color() == theme.color("text_secondary")
        assert code.background().color() == theme.color("card")
        assert code.fontFamilies() == ["JetBrains Mono"]
        block = document.begin()
        while block.text() != "bloco de codigo":
            block = block.next()
        assert block.blockFormat().background().color() == theme.color("card")
        table = document.rootFrame().childFrames()[0]
        assert table.format().borderBrush().color() == theme.color("border")

    check()
    dark = theme.color("accent").name()
    main_window.toggle_theme()  # dark → light
    assert theme.color("accent").name() != dark
    check()


def test_the_scroll_position_survives_a_theme_change(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, "paragrafo\n\n" * 400))
    viewer.resize(600, 300)
    bar = viewer.markdown.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    assert before > 0
    main_window.toggle_theme()
    assert bar.value() == before


# -- limits ------------------------------------------------------------------------------------
def test_a_file_over_the_limit_opens_as_text_with_a_banner(qtbot, main_window, tmp_path):
    line = "texto de um markdown grande, linha de relleno para passar do limite\n"
    text = line * (2 * 1024 * 1024 // len(line))
    assert MARKDOWN_RENDER_LIMIT < len(text) < 4 * 1024 * 1024
    viewer = open_text(qtbot, main_window, write(tmp_path, text))
    assert not viewer.viewing_rendered and viewer.stack.currentWidget() is viewer.editor
    assert "Markdown grande" in viewer.banner.text() and viewer.banner.isVisibleTo(viewer)
    assert not viewer.rendered_button.isEnabled() and "1 MB" in viewer.rendered_button.toolTip()
    assert viewer.markdown.source == ""  # never parsed
    assert viewer.editor.toPlainText().startswith("texto de um markdown")


def test_a_file_truncated_by_the_reader_is_not_rendered_either(qtbot, main_window, tmp_path):
    line = "linha de um markdown enorme para o leitor cortar\n"
    text = line * (5 * 1024 * 1024 // len(line))
    viewer = open_text(qtbot, main_window, write(tmp_path, text))
    assert not viewer.viewing_rendered and not viewer.rendered_button.isEnabled()
    assert "Arquivo grande" in viewer.banner.text()


def test_the_description_of_a_new_calculation_opens_rendered(qtbot, main_window, tmp_path):
    bands = by_id("bandas")
    plan = bands.plan(al(), {"kpath": AL_PATH}, JOBS)
    created = create_folder(
        tmp_path, bands, "Al", plan, "# Bandas do Al\n\n- 12 pontos por segmento\n"
    )
    viewer = open_text(qtbot, main_window, created.folder / "descricao.md")
    assert viewer.viewing_rendered
    assert "<h1" in viewer.markdown.document().toHtml()


def test_a_reload_renders_again(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, "# Um\n"))
    assert "Um" in viewer.markdown.toPlainText()
    (tmp_path / "LEIA.md").write_text("# Dois\n")
    viewer._start_load(full=True)
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.viewing_rendered and "Dois" in viewer.markdown.toPlainText()


def test_cursor_keys_move_the_rendered_view(qtbot, main_window, tmp_path):
    viewer = open_text(qtbot, main_window, write(tmp_path, "paragrafo\n\n" * 300))
    viewer.resize(600, 300)
    bar = viewer.markdown.verticalScrollBar()
    viewer.go_end()
    assert bar.value() == bar.maximum() > 0
    viewer.go_start()
    assert bar.value() == 0
    viewer.ask_line()  # no line numbers here: nothing opens (a dialog would block the test)
