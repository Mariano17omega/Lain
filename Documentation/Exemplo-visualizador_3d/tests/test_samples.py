"""Every real input dropped into samples/ must open and render."""

import numpy as np
import pytest
from conftest import SAMPLES
from PyQt6.QtGui import QImage

from viewer3d.__main__ import main
from viewer3d.core.qe_input import read_structure
from viewer3d.core.structure import StructureError

FILES = sorted(p for p in SAMPLES.glob("*") if p.is_file() and not p.name.startswith("."))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_sample_reads_and_renders(path, tmp_path, qapp):
    result = read_structure(path)
    if isinstance(result, StructureError):
        # a known, Portuguese error is acceptable; the safety net is not
        assert result.message and not result.message.startswith("erro inesperado")
        return
    assert len(result) == result.source.nat
    out = tmp_path / "shot.png"
    assert main([str(path), "--screenshot", str(out), "--size", "640x480"]) == 0
    image = QImage(str(out))
    assert not image.isNull() and (image.width(), image.height()) == (640, 480)
    ptr = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = ptr.constBits()
    bits.setsize(ptr.sizeInBytes())
    pixels = np.frombuffer(bits, np.uint8).reshape(-1, 4)
    assert len(np.unique(pixels, axis=0)) > 20
