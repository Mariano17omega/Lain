"""What a click on a link of a rendered Markdown file does (spec 38 R1.4), without Qt.

The viewer shows files from synced cluster folders that the user did not write: only a web address
opens (in the browser) and an ``#anchor`` scrolls; a local file, a ``file:`` URL or anything else is
not followed. Headings carry no anchor name in Qt's Markdown import, so the anchors are the
GitHub-style slugs of the heading texts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal, NamedTuple
from urllib.parse import unquote, urlsplit

WEB_SCHEMES = ("http", "https")
_DROPPED = re.compile(r"[^\w\- ]", re.UNICODE)


class LinkAction(NamedTuple):
    """``target``: the URL to open, the anchor without ``#``, or the destination the message shows."""

    kind: Literal["open", "anchor", "blocked"]
    target: str


def link_action(href: str) -> LinkAction:
    """What ``href`` asks for: ``open`` (a web URL), ``anchor`` (a heading of this file) or ``blocked``."""
    href = href.strip()
    if href.startswith("#"):
        return LinkAction("anchor", unquote(href[1:]))
    try:
        parts = urlsplit(href)
    except ValueError:  # an unparsable address is no web address
        return LinkAction("blocked", href)
    if parts.scheme.lower() in WEB_SCHEMES and parts.netloc:
        return LinkAction("open", href)
    return LinkAction("blocked", href)


def heading_slug(title: str) -> str:
    """GitHub's anchor of a heading: lowercase, punctuation dropped, spaces as hyphens."""
    return _DROPPED.sub("", title.strip().lower()).replace(" ", "-")


def heading_slugs(titles: Iterable[str]) -> list[str]:
    """The slug of each heading in document order; a repeated one gets ``-1``, ``-2``… as on GitHub."""
    seen: dict[str, int] = {}
    slugs = []
    for title in titles:
        base = heading_slug(title)
        count = seen.get(base, 0)
        seen[base] = count + 1
        slugs.append(base if count == 0 else f"{base}-{count}")
    return slugs
