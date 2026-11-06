"""The worker side of the 3D window's "Print" (spec 46 R5): PNG-encode the picture the GUI thread drew and
write it under ``plots/``. Encoding takes 150 to 210 ms for a 1920 × 1560 view, so it runs in a task."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage

from ....core.structure3d.image_file import save_png
from ....i18n import _


def save_view(image: QImage, folder: str | Path, stem: str) -> Path:
    """``image`` as ``<folder>/plots/<stem>.png`` (never over a file that exists); returns the path.

    Raises ``OSError`` when the image cannot be encoded or the folder is gone."""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    encoded = image.save(buffer, "PNG")
    buffer.close()
    if not encoded:
        raise OSError(_("não foi possível codificar a imagem em PNG"))
    return save_png(folder, stem, bytes(data.data()))
