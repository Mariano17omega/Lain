"""The image tab reads and decodes its file in a worker (CLAUDE.md: the GUI thread never reads files)
and scales the picture when its size changes, not at every paint."""

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from qe_studio.ui.widgets.shell.workspace import ImageViewer

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
    '<rect width="40" height="20" fill="red"/></svg>'
)


def png(path, width=40, height=20):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("blue"))
    assert image.save(str(path))
    return path


def shown(qtbot, path) -> ImageViewer:
    viewer = ImageViewer(path)
    qtbot.addWidget(viewer)
    return viewer


def test_a_png_is_read_after_the_constructor_not_in_it(qtbot, tmp_path):
    viewer = shown(qtbot, png(tmp_path / "a.png"))
    assert viewer.natural_size.isEmpty()  # the worker has not called back: no read on this thread
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.natural_size == QSize(40, 20) and viewer.svg is None


def test_an_svg_is_read_in_the_worker_and_rendered_here(qtbot, tmp_path):
    path = tmp_path / "a.svg"
    path.write_text(SVG)
    viewer = shown(qtbot, path)
    assert viewer.natural_size.isEmpty()
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.natural_size == QSize(40, 20) and viewer.image is None


@pytest.mark.parametrize("name", ["gone.png", "gone.svg"])
def test_a_file_that_cannot_be_read_stays_blank(qtbot, tmp_path, name):
    viewer = shown(qtbot, tmp_path / name)
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.natural_size.isEmpty()
    viewer.grab()  # a blank paint, no error


def test_a_file_that_is_not_an_image_stays_blank(qtbot, tmp_path):
    path = tmp_path / "text.png"
    path.write_text("not a picture")
    viewer = shown(qtbot, path)
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    assert viewer.natural_size.isEmpty()


def test_the_picture_is_scaled_once_per_size_not_per_paint(qtbot, tmp_path):
    viewer = shown(qtbot, png(tmp_path / "big.png", 400, 200))
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    viewer.resize(116, 200)  # 84 x 168 of room: the picture is drawn at 84 x 42
    viewer.grab()
    first = viewer._scaled
    assert first is not None and first[0] == QSize(84, 42)
    viewer.grab()
    assert viewer._scaled is first  # the same pixmap: no new scaling
    viewer.resize(216, 200)
    viewer.grab()
    assert viewer._scaled is not None and viewer._scaled is not first
    assert viewer._scaled[0] == QSize(184, 92)


def test_a_cancelled_read_calls_nothing_back(qtbot, tmp_path):
    viewer = shown(qtbot, png(tmp_path / "a.png"))
    viewer.cancel_load()
    qtbot.wait(200)
    assert viewer.natural_size.isEmpty()
