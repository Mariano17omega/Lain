"""The logic without widgets (CLAUDE.md, Architecture): testable without Qt, never imports ``ui``.

At the top only what every area uses: ``config`` and ``config_template`` (the settings), ``appdirs``
(the app's folders, atomic writes), ``tasks`` and ``cancel`` (background work), and the
identification by content, ``sniff`` and ``detection`` (PRD §3). The rest lives in an area
(spec 78.5):

- ``app``: the program itself (the language at start, "Sobre", colours, font scale).
- ``files``: the user's files and folders; ``project``: what ``<local_root>/.lain/`` keeps;
  ``search``: the command palette; ``viewer``: what the text viewer shows and checks.
- ``qe``: QE's formats; ``calculations``: the plot types (``REGISTRY``); ``plotting``: figures,
  sessions and export; ``analysis``: sums over results already computed.
- ``calc_create``: "Criar cálculo"; ``structure3d``: the structure in 3D.
- ``remote``: the cluster mode and its jobs; ``sync``: rsync and ssh.
"""
