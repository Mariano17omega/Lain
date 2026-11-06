"""What the text viewer shows and checks (specs 10, 11 and 38), without Qt.

- ``textfile``: a file's text, whole or head + tail when it is large (worker).
- ``text_preview``: what the viewer shows of a file: the text or its ends, the banner, the checks of
  a QE input or a ``.qsub`` script.
- ``qsub_lint``: the write checks of an SGE job script.
- ``markdown_links``: what a click on a link of a rendered Markdown file does.
"""
