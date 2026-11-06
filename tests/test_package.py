from importlib.resources import files

import qe_studio


def test_version():
    assert qe_studio.__version__


def test_vendored_assets_present():
    resources = files("qe_studio.ui.resources")
    fonts = {p.name for p in resources.joinpath("fonts").iterdir()}
    assert {"Inter-Regular.ttf", "JetBrainsMono-Regular.ttf"} <= fonts
    assert resources.joinpath("icons", "account_tree.svg").is_file()


def test_app_icon_files_ship_with_the_package():
    app = files("qe_studio.ui.resources").joinpath("app")
    assert app.joinpath("lain.svg").is_file()
    for size in (16, 32, 48, 64, 128, 256):
        assert app.joinpath(f"lain-{size}.png").is_file()
