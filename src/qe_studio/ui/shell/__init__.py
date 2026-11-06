"""The window's shell (spec 78.5): who the app is, an exception nobody caught, the language,
and the parts of the window that no feature owns.

- ``app_identity``: names, window icon and ``.desktop`` association.
- ``excepthook``: what the app does with an exception nobody caught (spec 27-5 R3).
- ``qt_log``: Qt's own messages in the log (spec 90 R7.2).
- ``language_install``: the language at startup and Qt's own texts in it (spec end).
- ``restart_notice``: the settings "Recarregar config.yaml" applies only after a restart.
- ``layout_controller``: which panels show, their widths and the window state (QSettings).
- ``focus_controller``: the tab order and the Ctrl+1..4 jumps (spec 19 R4).
- ``footer_path``: the path on the right of the status bar.
- ``first_run``: the first run and a missing project folder (spec 18 R5).
- ``busy``: the status bar spinner (spec 15 R2).
- ``help_controller``: the "Ajuda" menu (spec 18 R1).
- ``palette_controller``: the command palette's rows and what choosing one does (spec 18 R2).
"""
