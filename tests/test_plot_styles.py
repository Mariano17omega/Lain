"""Plot styles (spec 82): the YAML files the look of a new plot comes from, how they are checked, and
how a style reaches the parameters (``default_params``, the panel's "Estilo do gráfico")."""

import json
from pathlib import Path

import pytest

from qe_studio.core.calculations import REGISTRY
from qe_studio.core.calculations.bands.params import BandsParams
from qe_studio.core.calculations.bands_dos.params import BandsDosParams
from qe_studio.core.calculations.params import CommonParams
from qe_studio.core.calculations.pdos.params import (
    DEFAULT_ATOMOS_COLORS,
    DEFAULT_ORBITAL_COLORS,
    PdosParams,
)
from qe_studio.core.config import AppConfig, load_config
from qe_studio.core.plotting import styles
from qe_studio.core.plotting.plot_file import apply_stored, write_plot_file
from qe_studio.core.plotting.session import PlotSession
from qe_studio.core.plotting.styles import (
    DEFAULT_STYLE,
    STYLES_DIR,
    apply_style,
    load_styles,
    style_fields,
)
from qe_studio.core.sniff import SniffCache
from spin_helpers import SPIN_BANDS, detect_one
from style_helpers import ESCURO, install_styles, snapshot, style_folder
from test_bands_dos_render import combined
from test_plotting import render
from test_scf import load as load_scf
from test_scf import synthetic, write

from conftest import FIXTURES

ROOT = Path(__file__).resolve().parents[1]

# The look of a new plot before spec 82: the defaults of config.yaml then.
TODAY = {
    "figure_width": 6.0,
    "figure_height": 4.5,
    "line_width": 1.2,
    "background": "#ffffff",
    "valence_color": "#2563eb",
    "conduction_color": "#00d2ff",
    "fermi_color": "#f43f5e",
    "orbital_colors": {"s": "#fbbf24", "p": "#06b6d4", "d": "#a855f7", "f": "#ec4899"},
    "atomos_colors": {
        "Al": "#E41A1C",
        "C": "#377EB8",
        "H": "#4DAF4A",
        "Hg": "#FF7F00",
        "K": "#984EA3",
        "O": "#228B22",
        "Si": "#F781BF",
    },
}


def session_of(folder: Path) -> PlotSession:
    result = detect_one(folder)
    dataset = result.module.load(result, SniffCache().sniff)
    return PlotSession(result, dataset, result.module.default_params(AppConfig(), dataset))


def pick(session: PlotSession, name: str) -> None:
    """Choose style ``name`` as the panel does."""
    old, session.params.style = session.params.style, name
    session.param_changed("style", old)


# -- the files -----------------------------------------------------------------------------------
def test_the_package_default_style_is_the_look_of_today():
    loaded = load_styles(STYLES_DIR)
    assert loaded.warnings == ()
    default = loaded.styles[DEFAULT_STYLE]
    assert dict(default.params) == TODAY
    assert all(isinstance(default.params[k], float) for k in ("figure_width", "line_width"))
    for cls in (CommonParams, BandsParams, PdosParams, BandsDosParams):  # the code says the same
        code = cls()
        assert all(getattr(code, k) == v for k, v in TODAY.items() if hasattr(code, k)), cls
    assert TODAY["orbital_colors"] == DEFAULT_ORBITAL_COLORS
    assert TODAY["atomos_colors"] == DEFAULT_ATOMOS_COLORS


def test_a_style_gives_some_fields_and_takes_the_rest_from_the_default(tmp_path):
    loaded = load_styles(style_folder(tmp_path, escuro=ESCURO))
    assert loaded.warnings == ()
    values = loaded.values("escuro")
    assert (values["background"], values["line_width"], values["figure_width"]) == (
        "#111827",
        2.0,
        6.0,
    )
    assert values["conduction_color"] == TODAY["conduction_color"]
    # A map of colors is added to the default's, never replaces it whole.
    assert values["orbital_colors"] == {**TODAY["orbital_colors"], "s": "#f97316"}
    assert loaded.values(DEFAULT_STYLE) == TODAY
    assert loaded.values("sumido") == TODAY  # a style that does not exist gives nothing


def test_the_combo_lists_the_default_first_then_the_others_by_label(tmp_path):
    folder = style_folder(
        tmp_path,
        escuro=ESCURO,
        b_claro="lain_style: 1\nname: Artigo\n",
        sem_nome="lain_style: 1\nparams: {}\n",
    )
    assert load_styles(folder).choices() == (
        (DEFAULT_STYLE, "Padrão"),
        ("b_claro", "Artigo"),
        ("escuro", "Escuro"),
        ("sem_nome", "sem_nome"),
    )


BAD = """\
lain_style: 1
params:
  figure_width: 7
  fermi_color: notacolor
  emin: -3.0
  line_width: 99
  legend_loc: middle
  legend_size: null
  show_legend: "yes"
  atomos_colors: {Fe: nope}
"""


def test_invalid_values_and_fields_a_style_may_not_give_are_dropped_with_a_warning(tmp_path):
    loaded = load_styles(style_folder(tmp_path, ruim=BAD))
    assert dict(loaded.styles["ruim"].params) == {"figure_width": 7.0, "legend_size": None}
    assert isinstance(loaded.styles["ruim"].params["figure_width"], float)
    assert list(loaded.warnings) == [
        "Estilo ruim.yaml: valor inválido em fermi_color ('notacolor'), ignorado.",
        "Estilo ruim.yaml: emin não é um campo de estilo e é ignorado.",
        "Estilo ruim.yaml: valor inválido em line_width (99), ignorado.",
        "Estilo ruim.yaml: valor inválido em legend_loc ('middle'), ignorado.",
        "Estilo ruim.yaml: valor inválido em show_legend ('yes'), ignorado.",
        "Estilo ruim.yaml: valor inválido em atomos_colors ({'Fe': 'nope'}), ignorado.",
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("orbital_colors", {"px": "#ff0000"}),  # s, p, d and f only
        ("orbital_colors", {"S": "#ff0000"}),
        ("atomos_colors", {" Al": "#ff0000"}),  # a label never has a space
        ("atomos_colors", {"Al 1": "#ff0000"}),
        ("atomos_colors", {"": "#ff0000"}),
    ],
)
def test_a_map_of_colors_with_a_key_no_plot_would_match_is_dropped(tmp_path, key, value):
    """The checks ``config.yaml`` made before spec 82: a color under such a key would never show."""
    text = f"lain_style: 1\nparams:\n  {key}: {json.dumps(value)}\n"
    loaded = load_styles(style_folder(tmp_path, ruim=text))
    assert dict(loaded.styles["ruim"].params) == {}
    assert list(loaded.warnings) == [
        f"Estilo ruim.yaml: valor inválido em {key} ({value!r}), ignorado."
    ]


def test_a_map_of_colors_with_good_keys_is_kept(tmp_path):
    text = "lain_style: 1\nparams:\n  orbital_colors: {d: red}\n  atomos_colors: {Fe1: blue}\n"
    loaded = load_styles(style_folder(tmp_path, bom=text))
    assert dict(loaded.styles["bom"].params) == {
        "orbital_colors": {"d": "red"},
        "atomos_colors": {"Fe1": "blue"},
    }
    assert loaded.warnings == ()


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("name: Sem versão\nparams: {background: black}\n", "falta “lain_style: 1”"),
        ("lain_style: 2\nparams: {}\n", "falta “lain_style: 1”"),
        ("- a\n- b\n", "falta “lain_style: 1”"),
        ("lain_style: 1\nparams: [background]\n", "“params” deve ser um mapeamento"),
        ("lain_style: 1\nparams: {background: [unclosed\n", "YAML inválido"),
    ],
)
def test_a_file_that_is_not_a_style_is_left_out_with_a_warning(tmp_path, text, fragment):
    loaded = load_styles(style_folder(tmp_path, outro=text))
    assert "outro" not in loaded.styles
    (warning,) = loaded.warnings
    assert warning.startswith("Estilo de gráfico outro.yaml ignorado:") and fragment in warning


def test_an_unreadable_file_is_left_out_with_a_warning(tmp_path):
    folder = style_folder(tmp_path)
    (folder / "binario.yaml").write_bytes(b"\xff\xfe\x00lain_style")
    loaded = load_styles(folder)
    assert "binario" not in loaded.styles
    (warning,) = loaded.warnings
    assert "binario.yaml ignorado: não foi possível ler o arquivo" in warning


def test_without_a_valid_default_file_the_code_defaults_hold(tmp_path):
    loaded = load_styles(style_folder(tmp_path, default=False, escuro=ESCURO))
    assert loaded.warnings == (
        "Estilo de gráfico padrao.yaml ausente ou inválido: usando os padrões do Lain.",
    )
    assert loaded.choices()[0] == (DEFAULT_STYLE, "Padrão")
    assert dict(loaded.own(DEFAULT_STYLE)) == {}
    styles.set_styles(loaded)
    params = BandsParams()
    apply_style(params, DEFAULT_STYLE)
    assert params == BandsParams()
    apply_style(params, "escuro")
    assert (params.background, params.conduction_color) == ("#111827", "#00d2ff")


def test_load_config_installs_the_styles_and_reports_their_warnings(tmp_path, monkeypatch):
    """Read with the config (at startup and on "Recarregar config.yaml", spec 82 R1.4)."""
    folder = style_folder(tmp_path, escuro=ESCURO, ruim=BAD)
    monkeypatch.setattr(styles, "STYLES_DIR", folder)
    loaded = load_config(ROOT / "config.example.yaml", environ={}, cwd=tmp_path)
    assert "Estilo ruim.yaml: emin não é um campo de estilo e é ignorado." in loaded.warnings
    assert [name for name, _label in styles.styles().choices()] == [DEFAULT_STYLE, "escuro", "ruim"]
    (folder / "novo.yaml").write_text("lain_style: 1\nname: Novo\n", encoding="utf-8")
    assert "novo" not in styles.styles().styles  # a new file waits for the next reload
    load_config(ROOT / "config.example.yaml", environ={}, cwd=tmp_path)
    assert "novo" in styles.styles().styles


# -- the parameters ------------------------------------------------------------------------------
def test_apply_style_gives_each_plot_the_fields_it_has(tmp_path):
    install_styles(tmp_path, escuro=ESCURO)
    bands, pdos, both = BandsParams(), PdosParams(), BandsDosParams()
    assert apply_style(bands, "escuro") == ["atomos_colors", "orbital_colors"]
    assert (bands.background, bands.line_width, bands.valence_color, bands.fermi_color) == (
        "#111827",
        2.0,
        "#facc15",
        "#22d3ee",
    )
    assert bands.conduction_color == "#00d2ff"  # from the default style
    assert apply_style(pdos, "escuro") == ["conduction_color", "valence_color"]
    assert pdos.orbital_colors == {**TODAY["orbital_colors"], "s": "#f97316"}
    assert pdos.fermi_color == "#22d3ee"
    assert apply_style(both, "escuro") == []
    assert (both.valence_color, both.orbital_colors["s"]) == ("#facc15", "#f97316")
    assert both.atomos_colors == TODAY["atomos_colors"]
    pdos.atomos_colors["Al"] = "#000000"  # the parameters own their maps
    assert styles.styles().values("escuro")["atomos_colors"]["Al"] == "#E41A1C"


def test_picking_a_style_changes_the_look_and_keeps_the_rest(tmp_path):
    install_styles(tmp_path, escuro=ESCURO)
    session = session_of(FIXTURES / "al_bands")
    params = session.params
    params.emin, params.labels = -3.0, "L, G, X, U, G"
    params.line_width, params.conduction_color = 3.0, "#000000"  # the look, by hand
    pick(session, "escuro")
    assert (params.background, params.line_width, params.valence_color) == (
        "#111827",
        2.0,
        "#facc15",
    )
    assert params.conduction_color == "#00d2ff"  # the hand edit is undone: the default's
    assert (params.emin, params.labels) == (-3.0, "L, G, X, U, G")
    figure, _info = render(session.module, session.dataset, params, session.style)
    assert figure.get_facecolor()[:3] == pytest.approx((17 / 255, 24 / 255, 39 / 255))
    pick(session, DEFAULT_STYLE)
    assert all(
        getattr(params, name) == getattr(session.defaults, name)
        for name in style_fields()
        if hasattr(params, name)
    )
    assert (params.style, params.emin) == (DEFAULT_STYLE, -3.0)


def test_back_to_the_default_style_a_relaxation_keeps_its_taller_figure(tmp_path):
    install_styles(tmp_path, escuro=ESCURO, alto="lain_style: 1\nparams: {figure_height: 5}\n")
    session = session_of(FIXTURES / "si_relax")
    assert session.params.figure_height == pytest.approx(4.5 * 1.5)
    pick(session, "escuro")  # gives no height: the plot's own default stays
    assert session.params.figure_height == pytest.approx(4.5 * 1.5)
    assert session.params.background == "#111827"
    pick(session, "alto")
    assert (session.params.figure_height, session.params.background) == (5.0, "#ffffff")
    pick(session, "sumido")  # a style whose file is gone: nothing of its own
    assert session.params.figure_height == pytest.approx(4.5 * 1.5)
    pick(session, DEFAULT_STYLE)
    assert session.params == session.defaults


def test_a_plot_file_with_a_style_that_is_gone_keeps_its_name_and_values():
    session = session_of(FIXTURES / "al_bands")
    module, dataset = session.module, session.dataset
    schema = module.param_schema(dataset)
    params = module.default_params(AppConfig(), dataset)
    assert apply_stored(params, {"style": "sumido", "background": "#000000"}, schema) == []
    assert (params.style, params.background) == ("sumido", "#000000")
    assert apply_stored(params, {"style": 3}, schema) == ["style"]
    old = module.default_params(AppConfig(), dataset)  # a .plot from before spec 82: no style
    assert apply_stored(old, {"background": "#000000"}, schema) == []
    assert (old.style, old.background) == (DEFAULT_STYLE, "#000000")


def test_every_plot_offers_the_style_first_and_every_color_can_come_from_a_style(tmp_path):
    """The contract a plot module keeps (spec 82 R3.1): ``style_field()`` opens its "Estilo"
    section, and each color parameter declares ``metadata={"kind": "color"}``."""
    plots = []
    for folder in (
        FIXTURES / "al_bands",
        SPIN_BANDS,
        FIXTURES / "al_pdos_flat",
        FIXTURES / "si_relax",
    ):
        session = session_of(folder)
        plots.append((session.module, session.dataset))
    result, dataset, _params = load_scf(write(tmp_path, synthetic(3, spin=True)))
    plots.append((result.module, dataset))
    module, dataset, _params = combined()
    plots.append((module, dataset))
    for module, dataset in plots:
        schema = module.param_schema(dataset)
        assert [f.name for f in schema if f.section == "style"][0] == "style", module.kind
        colors = {f.name for f in schema if f.kind in ("color", "colors")}
        assert colors <= set(style_fields()), (module.kind, colors - set(style_fields()))
    assert {m.kind for m, _d in plots} == {m.kind for m in REGISTRY if m.plottable and m.plot_file}


def test_plotting_and_saving_never_write_the_style_folder(tmp_path):
    folder = install_styles(tmp_path, escuro=ESCURO)
    before = snapshot(folder)
    session = session_of(FIXTURES / "al_bands")
    pick(session, "escuro")
    session.params.fermi_color = "#000000"
    render(session.module, session.dataset, session.params)
    write_plot_file(tmp_path / "sim", "bands", session.params)
    assert snapshot(folder) == before
    assert snapshot(STYLES_DIR) == {"padrao.yaml": (STYLES_DIR / "padrao.yaml").read_bytes()}
