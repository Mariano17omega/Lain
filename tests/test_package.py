from importlib.resources import files

import qe_studio


def test_version():
    assert qe_studio.__version__


def test_vendored_assets_present():
    resources = files("qe_studio.ui.resources")
    fonts = {p.name for p in resources.joinpath("fonts").iterdir()}
    assert {"Inter-Regular.ttf", "JetBrainsMono-Regular.ttf"} <= fonts
    assert resources.joinpath("icons", "account_tree.svg").is_file()
