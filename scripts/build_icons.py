"""Render the app icon (``ui/resources/app/lain.svg``) to the PNG sizes the desktop needs.

Maintenance script: the PNGs are committed, so neither the app nor ``install_desktop.py`` needs
to render anything. Re-run it after editing the SVG.

    uv run python scripts/build_icons.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402

APP_RESOURCES = (
    Path(__file__).resolve().parents[1] / "src" / "qe_studio" / "ui" / "resources" / "app"
)
SIZES = (16, 32, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return image


def main() -> int:
    _app = QGuiApplication(sys.argv[:1])
    svg = APP_RESOURCES / "lain.svg"
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        print(f"invalid SVG: {svg}", file=sys.stderr)
        return 1
    for size in SIZES:
        target = APP_RESOURCES / f"lain-{size}.png"
        if not render(renderer, size).save(str(target), "PNG"):
            print(f"could not write {target}", file=sys.stderr)
            return 1
        print(f"wrote {target.relative_to(APP_RESOURCES.parents[4])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
