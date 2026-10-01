"""The calculation-module contract (spec 8): a new module is one class, with no code in ``ui/``."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PyQt6.QtGui import QImage, QPainter

from qe_studio.core.calculations import REGISTRY, describe_plottable
from qe_studio.core.calculations.base import (
    AxesLimits,
    CalculationModule,
    DetectionResult,
    FileRole,
)
from qe_studio.core.calculations.params import (
    COMMON_FIELDS,
    CommonParams,
    ParamField,
    RenderInfo,
    apply_common_config,
    ordered_sections,
)
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.plotting.draw import finish, new_axes
from qe_studio.core.plotting.export import export_figure
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.sniff import SniffCache
from qe_studio.ui.painting import paint_badge
from qe_studio.ui.plot_session import PlotSession
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.param_widgets import Section
from qe_studio.ui.widgets.plot_view import PlotView

UI_DIR = Path(__file__).parent.parent / "src" / "qe_studio" / "ui"


@dataclass
class DummyData:
    folder: Path
    values: list[float]
    warnings: list[str] = field(default_factory=list)


@dataclass
class DummyParams(CommonParams):
    color: str = "#ff0000"
    ymin: float | None = None
    ymax: float | None = None


class DummyModule(CalculationModule[DummyData, DummyParams]):
    kind = "dummy"
    badge = "DUMMY"
    display_name = "Cálculo de teste"
    plottable = True
    view_fields = ("ymin", "ymax")
    sections = (("Teste", None),)
    roles = (
        FileRole(
            "data",
            "Dados",
            lambda s: s.path.suffix == ".dummy",
            ("*.dummy",),
            required=True,
            anchor=True,
        ),
    )

    def load(self, result: DetectionResult) -> DummyData:
        path = result.file("data")
        assert path is not None
        values = [float(line) for line in path.read_text().split()]
        return DummyData(result.folder, values)

    def default_params(self, config: AppConfig, dataset: DummyData) -> DummyParams:
        params = DummyParams()
        apply_common_config(params, config)
        return params

    def param_schema(self, dataset: DummyData) -> list[ParamField]:
        return [
            ParamField("color", "Cor", "Teste", "color"),
            ParamField("ymin", "y mín", "Teste", "float", optional=True, minimum=-1e6),
            ParamField("ymax", "y máx", "Teste", "float", optional=True, minimum=-1e6),
            *COMMON_FIELDS,
        ]

    def apply_limits(self, params: DummyParams, axes_limits: AxesLimits) -> None:
        params.ymin, params.ymax = axes_limits[0][1]

    def render(self, figure, dataset, params, style) -> RenderInfo:
        ax = new_axes(figure, style)
        ax.plot(dataset.values, color=params.color)
        if params.ymin is not None and params.ymax is not None:
            ax.set_ylim(params.ymin, params.ymax)
        finish(figure, ax, params)
        return RenderInfo(ax.get_xlim(), ax.get_ylim(), "dummy ok")


DUMMY = DummyModule()


@pytest.fixture
def dummy_folder(tmp_path) -> Path:
    folder = tmp_path / "dummy_sim"
    folder.mkdir()
    (folder / "a.dummy").write_text("1 4 2 8 5")
    return folder


def detect_dummy(folder: Path) -> DetectionResult:
    (result,) = detect_folder(folder, sniff=SniffCache().sniff, modules=(DUMMY,))
    return result


def test_dummy_is_detected_loaded_plotted_saved_and_exported(dummy_folder):
    result = detect_dummy(dummy_folder)
    assert result.kind == "dummy" and result.plottable and result.badge_token is None
    dataset = DUMMY.load_cached(result)
    assert dataset.values == [1, 4, 2, 8, 5]
    params = DUMMY.default_params(AppConfig(), dataset)
    session = PlotSession(result, dataset, params)

    params.color = "#00ff00"
    assert write_plot_file(dummy_folder, "dummy", params) == dummy_folder / "dummy.plot"
    stored, warnings = read_plot_file(dummy_folder, "dummy")
    stored["color"] = "nope"  # a hand-edited file: dropped, the default stays
    fresh = DUMMY.default_params(AppConfig(), dataset)
    assert apply_stored(fresh, {**stored}, DUMMY.param_schema(dataset)) == ["color"]
    assert warnings == [] and fresh.color == "#ff0000" and fresh.title == params.title

    session.apply_limits([((0.0, 4.0), (-1.0, 9.0))])
    assert (params.ymin, params.ymax) == (-1.0, 9.0)
    session.reset_view()
    assert (params.ymin, params.ymax) == (None, None)

    written = export_figure(
        DUMMY, dataset, params, session.style, dummy_folder, DUMMY.export_stem(params)
    )
    assert sorted(p.name for p in written) == ["dummy.pdf", "dummy.png", "dummy.svg"]


def test_dummy_flows_through_the_window(qtbot, main_window, dummy_folder):
    window = main_window
    result = detect_dummy(dummy_folder)
    dataset = DUMMY.load_cached(result)
    window._on_loaded(result, dataset, (None, []), False)

    view = window.current_plot()
    assert isinstance(view, PlotView) and view.session.module is DUMMY
    titles = [s.title for s in window.params.body.findChildren(Section)]
    assert titles == ["Arquivos", "Estilo", "Legenda", "Figura", "Teste", "Exportar"]

    with qtbot.waitSignal(window.params.changed):
        window.params.set_param("color", "#00ff00")
    assert view.session.params.color == "#00ff00"
    view.figure.axes[0].set_ylim(-1.0, 9.0)  # toolbar zoom reaches the module's hook
    view._on_release()
    assert (view.session.params.ymin, view.session.params.ymax) == (-1.0, 9.0)
    view._reset()
    assert view.session.params.ymin is None

    window._flush_plot_files()
    stored, _ = read_plot_file(dummy_folder, "dummy")
    assert stored["color"] == "#00ff00"
    assert [p.name for p in window.export_plot()] == ["dummy.png", "dummy.svg", "dummy.pdf"]


def test_no_file_of_the_ui_knows_the_dummy_module():
    offenders = [
        path.name
        for path in UI_DIR.rglob("*")
        if path.is_file() and b"dummy" in path.read_bytes().lower()
    ]
    assert offenders == []


def test_ui_does_not_branch_on_plot_kinds():
    for path in UI_DIR.rglob("*.py"):
        text = path.read_text()
        for kind in ("bands", "pdos", "relax"):
            assert f'kind == "{kind}"' not in text, path.name


@pytest.mark.parametrize(
    "folder, kind", [("01_relax", "relax"), ("03_bands", "bands"), ("04_pdos", "pdos")]
)
def test_every_schema_field_belongs_to_a_section(demo_project, folder, kind):
    results = detect_folder(demo_project / folder, sniff=SniffCache().sniff)
    result = next(r for r in results if r.kind == kind)
    module = result.module
    sections = {s.name for s in ordered_sections(module)}
    schema = module.param_schema(module.load(result))
    assert {f.section for f in schema} <= sections
    assert all(f.kind != "series" or f.colors for f in schema)


def test_sections_are_ordered_from_the_module_declarations():
    names = [s.name for s in ordered_sections(DUMMY)]
    assert names == ["Energia", "Eixo X", "Estilo", "Legenda", "Figura", "Teste", "Exportar"]
    pdos = [s.name for s in ordered_sections(next(m for m in REGISTRY if m.kind == "pdos"))]
    assert pdos.index("Projeções") == pdos.index("Legenda") - 1

    class Unknown(DummyModule):
        sections = (("Antes", "Figura"), ("Perdida", "não existe"))

    # an unknown anchor puts the section just before the export one, which stays last
    assert [s.name for s in ordered_sections(Unknown())] == [
        "Energia",
        "Eixo X",
        "Estilo",
        "Legenda",
        "Antes",
        "Figura",
        "Perdida",
        "Exportar",
    ]


def test_base_hooks_have_neutral_defaults(dummy_folder):
    dataset = DUMMY.load(detect_dummy(dummy_folder))
    params = DummyParams()
    assert DUMMY.format_coordinates(1.23456, 2.0, 0, dataset, params) == "x = 1.235 · y = 2"
    assert DUMMY.series_colors(dataset, params, None) == {}  # type: ignore[arg-type]
    assert DUMMY.default_labels(dataset) == []
    DUMMY.legacy_params(params, dataset.folder, None)  # type: ignore[arg-type]  # no-op
    assert params == DummyParams()


def test_the_message_for_manual_mapping_names_every_plottable_module():
    assert describe_plottable() == (
        "estrutura de bandas, densidade de estados projetada ou otimização estrutural"
    )
    assert describe_plottable((DUMMY,)) == "cálculo de teste"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_badge_token_is_themed(theme):
    manager = ThemeManager(theme)
    tokens = {m.badge_token for m in REGISTRY if m.badge_token} | {"other"}
    for token in tokens:
        for part in ("bg", "fg", "border"):
            assert manager.has_color(f"badge_{token}_{part}"), (theme, token, part)
    assert not manager.has_color("badge_dummy_bg")  # unthemed tokens fall back to "other"


@pytest.mark.parametrize("token", [None, "bands", "not_in_the_theme"])
def test_paint_badge_uses_the_token_or_the_generic_colours(qtbot, token):
    theme = ThemeManager("dark")
    image = QImage(80, 20, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    left = paint_badge(painter, 78, 10, "ANY", theme, token)
    painter.end()
    assert left < 78 and image.pixelColor(int(left) + 4, 10).alpha() > 0
