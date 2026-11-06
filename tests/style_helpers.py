"""Plot styles of a test (spec 82): a folder with the package's ``padrao.yaml`` and the styles a test
writes, made the styles in use (``tests/conftest.py`` puts the package's back after each test)."""

from __future__ import annotations

import shutil
from pathlib import Path

from qe_studio.core.plotting import styles

# A dark style that gives a few fields: the rest comes from padrao.yaml.
ESCURO = """\
lain_style: 1
name: Escuro
params:
  background: "#111827"
  line_width: 2.0
  valence_color: "#facc15"
  fermi_color: "#22d3ee"
  orbital_colors: {s: "#f97316"}
"""


def style_folder(tmp_path: Path, default: bool = True, **texts: str) -> Path:
    """``<tmp_path>/plot_styles`` with the package's default style (unless ``default`` is False)
    and one ``<name>.yaml`` per keyword."""
    folder = tmp_path / "plot_styles"
    folder.mkdir(exist_ok=True)
    if default:
        shutil.copyfile(styles.STYLES_DIR / "padrao.yaml", folder / "padrao.yaml")
    for name, text in texts.items():
        (folder / f"{name}.yaml").write_text(text, encoding="utf-8")
    return folder


def install_styles(tmp_path: Path, **texts: str) -> Path:
    """``style_folder`` made the styles in use; its folder."""
    folder = style_folder(tmp_path, **texts)
    styles.set_styles(styles.load_styles(folder))
    return folder


def snapshot(folder: Path) -> dict[str, bytes]:
    """The bytes of every file of ``folder``: a style folder Lain must never write."""
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}
