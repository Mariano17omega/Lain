"""Backend of "Criar cálculo" (spec 25): from an SCF input to a new folder with the inputs and the
cluster script of a calculation, never over existing files. Qt-free; the window is spec 26.

- ``scf_info``: what the SCF gives (``read_scf``, worker).
- ``types``: the ``REGISTRY`` of calculation types, their form fields and ``plan`` (the files).
- ``kpath``: band path (``suggest_path``, pymatgen, worker) and ``K_POINTS`` cards.
- ``render``: the packaged Jinja2 templates (``resources/templates``).
- ``writer``: ``validate_target``, ``preview_name`` and ``create_folder`` (worker).

``jinja2`` and ``pymatgen`` are imported on first use only.
"""
