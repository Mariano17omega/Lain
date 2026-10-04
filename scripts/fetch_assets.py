"""Download the fonts and icons vendored in src/qe_studio/ui/resources.

One-off maintenance script: the downloaded files are committed, so the app never
needs network access. Re-run it to refresh the assets or add new icon names.

    uv run python scripts/fetch_assets.py
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

RESOURCES = Path(__file__).resolve().parents[1] / "src" / "qe_studio" / "ui" / "resources"

INTER_ZIP = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
INTER_FILES = {
    "extras/ttf/Inter-Regular.ttf": "Inter-Regular.ttf",
    "extras/ttf/Inter-Medium.ttf": "Inter-Medium.ttf",
    "extras/ttf/Inter-SemiBold.ttf": "Inter-SemiBold.ttf",
    "extras/ttf/Inter-Bold.ttf": "Inter-Bold.ttf",
    "LICENSE.txt": "Inter-LICENSE.txt",
}

JBMONO_ZIP = (
    "https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip"
)
JBMONO_FILES = {
    "fonts/ttf/JetBrainsMono-Regular.ttf": "JetBrainsMono-Regular.ttf",
    "fonts/ttf/JetBrainsMono-Medium.ttf": "JetBrainsMono-Medium.ttf",
    "fonts/ttf/JetBrainsMono-SemiBold.ttf": "JetBrainsMono-SemiBold.ttf",
    "fonts/ttf/JetBrainsMono-Bold.ttf": "JetBrainsMono-Bold.ttf",
    "OFL.txt": "JetBrainsMono-LICENSE.txt",
}

ICON_URL = (
    "https://raw.githubusercontent.com/google/material-design-icons/master/"
    "symbols/web/{name}/materialsymbolsoutlined/{name}_24px.svg"
)
ICON_LICENSE_URL = "https://raw.githubusercontent.com/google/material-design-icons/master/LICENSE"
ICONS = [
    # activity bar / top bar
    "account_tree",
    "grid_view",
    "bolt",
    "monitoring",
    "sync",
    "tune",
    "dark_mode",
    "light_mode",
    "contrast",
    "person",
    # file types
    "folder",
    "folder_open",
    "drive_folder_upload",
    "description",
    "terminal",
    "analytics",
    "image",
    "polyline",
    "picture_as_pdf",
    "draft",
    "bar_chart",
    "table_chart",
    "data_object",
    "assignment_late",
    # explorer / grid toolbars
    "chevron_right",
    "expand_more",
    "filter_alt",
    "refresh",
    "unfold_less",
    "view_list",
    "sort",
    # plot toolbar
    "home",
    "arrow_back",
    "arrow_forward",
    "pan_tool",
    "zoom_in",
    "download",
    "restart_alt",
    # status and misc
    "check_circle",
    "warning",
    "error",
    "info",
    "close",
    "code",
    "bubble_chart",
    "difference",  # input comparison tab (spec 11)
    "summarize",  # output summary tab (spec 12)
    "open_in_new",
    "cloud_done",
    "cloud_off",
    "save",
    "edit",
    "add",
    "remove",
    "star",  # favorites (spec 16)
    "history",  # recent folders (spec 16)
]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def extract(zip_url: str, members: dict[str, str], dest: Path) -> None:
    archive = zipfile.ZipFile(io.BytesIO(fetch(zip_url)))
    names = archive.namelist()
    for member, target in members.items():
        match = next((n for n in names if n.endswith(member)), None)
        if match is None:
            raise SystemExit(f"{member} not found in {zip_url}")
        (dest / target).write_bytes(archive.read(match))
        print(f"font  {target}")


def main() -> int:
    fonts = RESOURCES / "fonts"
    icons = RESOURCES / "icons"
    fonts.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    extract(INTER_ZIP, INTER_FILES, fonts)
    extract(JBMONO_ZIP, JBMONO_FILES, fonts)

    failed = []
    for name in ICONS:
        try:
            (icons / f"{name}.svg").write_bytes(fetch(ICON_URL.format(name=name)))
            print(f"icon  {name}")
        except OSError as exc:
            failed.append(f"{name}: {exc}")
    (icons / "LICENSE.txt").write_bytes(fetch(ICON_LICENSE_URL))

    if failed:
        print("failed icons:", *failed, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
