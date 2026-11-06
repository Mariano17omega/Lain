"""The Quantum ESPRESSO input documentation the "Ajuda" menu links to (spec 73).

The addresses are constants, not settings, and nothing is downloaded or stored: the menu only hands
the URL to the system. No Qt.
"""

from __future__ import annotations

from typing import NamedTuple

DOCS_BASE = "https://www.quantum-espresso.org/Doc"


class QeDoc(NamedTuple):
    id: str
    program: str
    url: str


QE_DOCS: tuple[QeDoc, ...] = (
    QeDoc("pw", "pw.x", f"{DOCS_BASE}/INPUT_PW.html"),
    QeDoc("bands", "bands.x", f"{DOCS_BASE}/INPUT_BANDS.html"),
    QeDoc("projwfc", "projwfc.x", f"{DOCS_BASE}/INPUT_PROJWFC.html"),
)


def doc_for(doc_id: str) -> QeDoc:
    """The documentation page with this id (``KeyError`` when there is none)."""
    for doc in QE_DOCS:
        if doc.id == doc_id:
            return doc
    raise KeyError(doc_id)
