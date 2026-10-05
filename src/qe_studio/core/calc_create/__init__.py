"""Backend of "Criar cálculo" (spec 25): from an SCF input to a new folder with the inputs and the
cluster script of a calculation, never over existing files. Qt-free; the window is spec 26.

- ``scf_info``: what the SCF gives (``read_scf``, worker).
- ``types``: the ``REGISTRY`` of calculation types, their form fields and ``plan`` (the files).
- ``kpath``: ``K_POINTS`` cards, and the checks of a typed band path (``collapsed_segments``, ``distribute``).
- ``render``: the packaged Jinja2 templates (``resources/templates``).
- ``writer``: ``validate_target``, ``preview_name`` and ``create_folder`` (worker).

``jinja2`` is imported on first use only.
"""
