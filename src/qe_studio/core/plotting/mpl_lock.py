"""One lock around every use of matplotlib's global state (spec 15 R3).

``rcParams`` is global: a ``rc_context`` in the export worker would leak into a render on the GUI
thread and the other way round, and matplotlib is not thread-safe anyway. Every block that enters
``rc_context`` or builds, renders or saves a figure holds ``MPL_LOCK``: ``PlotSession.render``, the
preview canvas's ``draw`` and ``export_figure``. The GUI thread never blocks on it: ``PlotView``
tries it without blocking and renders again a moment later.
"""

from __future__ import annotations

import threading

MPL_LOCK = threading.RLock()
