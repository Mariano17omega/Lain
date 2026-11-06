"""The user's cluster scripts in ``Documentation/``, which only the development repository has.

The public repository gets release snapshots without ``Documentation/``: a test that reads these
scripts carries ``needs_reference`` and is skipped there, while the development checkout runs it."""

from pathlib import Path

import pytest

REFERENCE = Path(__file__).parents[1] / "Documentation" / "Referencia_de_scripts_QSUB"
needs_reference = pytest.mark.skipif(
    not REFERENCE.is_dir(), reason="Documentation/ is only in the development repository"
)
