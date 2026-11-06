"""The PyQt6 app (CLAUDE.md, Architecture): widgets, layout, dialogs and signal wiring, never the
disk.

At the top only the start (``app``), the composition root (``main_window``), the window's actions
(``actions``) and the closing (``shutdown``). A controller lives in an area, and its widgets in the
area of the same name of ``widgets`` (spec 78.5):

- ``shell``: the window's shell (identity, language, layout, focus, help, command palette).
- ``files``: the local files; ``plot``: plots, export and the Grids; ``cluster``: the cluster mode,
  its queue and the sync; ``tools``: the tools of the context menu with a window of their own.
- ``widgets``: the widgets; ``dialogs``: the dialogs; ``theme``: QSS, tokens and the font scale;
  ``resources``: fonts, icons, stylesheets and themes.
"""
