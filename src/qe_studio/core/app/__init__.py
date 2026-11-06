"""The program itself, without Qt and without QE (spec 78.5): what no feature owns.

- ``startup_language``: the language the program starts in (``ui.language``), read before any text
  loads.
- ``about``: the versions "Sobre o Lain" reports.
- ``colors``: WCAG contrast and the compositing of translucent theme colours.
- ``fontscale``: the font scale (``ui.font_scale``): pixel sizes and QSS text.
- ``logs``: the log file (the ``log:`` section): the only module that configures ``logging``.
"""
