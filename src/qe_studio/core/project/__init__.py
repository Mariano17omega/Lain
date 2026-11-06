"""What Lain keeps per project and per folder, in ``<local_root>/.lain/`` (spec 48), without Qt.

- ``project_data``: where the root's settings live, the one module that names the folder.
- ``projects``: the projects, the first-level folders of ``paths.local_root`` (spec 31).
- ``folder_memory``: the user's decisions per simulation folder (file mappings, k-point labels).
- ``grid_store``: the saved grids of plots (spec 23).
- ``nav_store``: the favorite and recent folders (spec 16 R4).
- ``compounds``: the compounds and the atom selection remembered for each (spec 21).
"""
