"""The calculation-module contract (spec 8): a new module is one class, with no code in ``ui/``."""

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from matplotlib.figure import Figure
from PyQt6.QtGui import QImage, QPainter

from qe_studio.core.calculations import REGISTRY, describe_plottable, module_for_file
from qe_studio.core.calculations.base import (
    AxesLimits,
    CalculationModule,
    DetectionResult,
    FileRole,
    SniffFn,
    Stores,
)
from qe_studio.core.calculations.params import (
    COMMON_FIELDS,
    CommonParams,
    ParamField,
    RenderInfo,
    apply_common_config,
    ordered_sections,
)
from qe_studio.core.compounds import AtomChoices, Compound, CompoundStore
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder, plottable_modules
from qe_studio.core.plotting.draw import finish, new_axes
from qe_studio.core.plotting.export import export_figure
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.session import PlotSession, build_session
from qe_studio.core.qe.structure import Site
from qe_studio.core.sniff import SniffCache, sniff
from qe_studio.ui.dialogs.atoms import AtomsAnswer
from qe_studio.ui.painting import paint_badge
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
    pick: list[int] | None = field(default=None, metadata={"store": "dummy"})  # a user store's


STORE_KEY = "dummy"


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

    def load(self, result: DetectionResult, sniff: SniffFn) -> DummyData:
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
            ParamField("pick", "Pontos", "Teste", "atoms"),
            *COMMON_FIELDS,
        ]

    def atoms_of(self, dataset: DummyData) -> AtomChoices:
        sites = tuple(Site(i, "X", float(i), 0.0, 0.0) for i in range(1, len(dataset.values) + 1))
        return AtomChoices(sites, Compound(STORE_KEY, f"X{len(sites)}"))

    def stored_params(self, dataset: DummyData, stores: Stores) -> dict:
        picked = stores.compounds.selection(STORE_KEY)
        return {} if picked is None else {"pick": picked}

    def save_stored(self, dataset: DummyData, params: DummyParams, name: str, stores: Stores):
        stores.compounds.save(STORE_KEY, "X", params.pick)

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
    dataset = DUMMY.load_cached(result, sniff)
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
    dataset = DUMMY.load_cached(result, sniff)
    window.plot_workflow.show_loaded(result, dataset, (None, []))

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

    window.plot_settings.flush_now()
    stored, _ = read_plot_file(dummy_folder, "dummy")
    assert stored["color"] == "#00ff00"
    with qtbot.waitSignal(window.export_finished, timeout=10_000) as blocker:
        assert window.export_plot()
    assert [p.name for p in blocker.args[0]] == ["dummy.png", "dummy.svg", "dummy.pdf"]


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
        for kind in ("bands", "pdos", "relax", "scf", "bands_dos", "grid"):
            assert f'kind == "{kind}"' not in text, path.name


@pytest.mark.parametrize(
    "folder, kind", [("01_relax", "relax"), ("03_bands", "bands"), ("04_pdos", "pdos")]
)
def test_every_schema_field_belongs_to_a_section(demo_project, folder, kind):
    results = detect_folder(demo_project / folder, sniff=SniffCache().sniff)
    result = next(r for r in results if r.kind == kind)
    module = result.module
    sections = {s.name for s in ordered_sections(module)}
    schema = module.param_schema(module.load(result, sniff))
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


def test_a_module_plots_its_folder_unless_it_says_otherwise(dummy_folder):
    result = detect_dummy(dummy_folder)
    assert result.plot_target == dummy_folder and DUMMY.single_file_role is None
    session = PlotSession(result, DUMMY.load(result, sniff), DummyParams())
    assert session.key == f"plot:dummy:{dummy_folder}"
    assert session.title == "Cálculo de teste · dummy_sim"
    assert module_for_file(SniffCache().sniff(dummy_folder / "a.dummy"), (DUMMY,)) is None


def test_base_hooks_have_neutral_defaults(dummy_folder):
    dataset = DUMMY.load(detect_dummy(dummy_folder), sniff)
    params = DummyParams()
    assert DUMMY.format_coordinates(1.23456, 2.0, 0, dataset, params) == "x = 1.235 · y = 2"
    assert DUMMY.series_colors(dataset, params, None) == {}  # type: ignore[arg-type]
    assert DUMMY.default_labels(dataset) == []
    DUMMY.legacy_params(params, dataset.folder, None)  # type: ignore[arg-type]  # no-op
    assert params == DummyParams()
    # Spec 23: its parameters live in a .plot, it can be a grid cell, its axes are its own.
    assert DUMMY.plot_file and DUMMY.grid_cell
    assert DUMMY.axes_routes(Figure(), dataset) is None
    assert (
        not DUMMY.render_in_worker
    )  # spec 27-8: only a figure too slow for the GUI thread is drawn off it


def test_a_named_figure_keys_its_tab_by_name_and_shows_its_parts(dummy_folder, tmp_path):
    """A figure of other plots that belongs to no folder (a grid, spec 23)."""
    part = detect_dummy(dummy_folder)
    result = DetectionResult(DUMMY, tmp_path, parts=(part,), plot_name="mine")
    assert result.plot_id == "mine" and result.targets == (dummy_folder,)
    session = PlotSession(result, DUMMY.load(part, sniff), DummyParams())
    assert session.key == "plot:dummy:mine" and session.composite
    assert session.paths == (dummy_folder,) and session.ref.path == dummy_folder
    nested = DetectionResult(DUMMY, tmp_path, parts=(result, part))
    assert nested.targets == (dummy_folder, dummy_folder)


def test_a_module_without_plot_file_keeps_every_edit_in_its_store(dummy_folder, tmp_path):
    class Stored(DummyModule):
        plot_file = False
        saved: list = []

        def save_stored(self, dataset, params, name, stores):
            self.saved.append(name)

    module = Stored()
    result = detect_dummy(dummy_folder)
    result.module = module
    session = PlotSession(result, module.load(result, sniff), DummyParams())
    session.params.ymin = 3.0
    assert session.persist("ymin", None)  # type: ignore[arg-type]
    assert module.saved == ["ymin"] and session.defaults.ymin == 3.0


def test_a_module_that_is_not_selectable_is_never_offered_for_mapping(dummy_folder):
    class Combined(DummyModule):
        selectable = False
        roles = tuple(dataclasses.replace(r, anchor=False) for r in DummyModule.roles)

    combined = Combined()
    assert DUMMY.selectable and plottable_modules((DUMMY, combined)) == [DUMMY]
    assert describe_plottable((DUMMY, combined)) == "cálculo de teste"
    # Without an anchor role it is never detected; it is plotted from results built for it.
    assert detect_folder(dummy_folder, sniff=SniffCache().sniff, modules=(combined,)) == []
    part = detect_dummy(dummy_folder)
    result = DetectionResult(combined, dummy_folder, files=dict(part.files), parts=(part, part))
    assert result.plot_id == f"{dummy_folder}|{dummy_folder}" and part.plot_id == str(dummy_folder)
    session = PlotSession(result, DUMMY.load(part, sniff), DummyParams())
    assert session.key == f"plot:dummy:{dummy_folder}|{dummy_folder}" and session.composite
    assert session.paths == (dummy_folder, dummy_folder)


def test_the_message_for_manual_mapping_names_every_plottable_module():
    assert describe_plottable() == (
        "estrutura de bandas, densidade de estados projetada, otimização estrutural "
        "ou convergência scf"
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


def test_every_module_describes_its_badge():
    for module in REGISTRY:
        assert module.description, module.kind
        tip = module.badge_tooltip()
        assert tip.splitlines() == [module.display_name, module.description]


def test_a_module_without_description_tips_its_name_only():
    assert DUMMY.badge_tooltip() == DUMMY.display_name


# -- parameters kept in a user store (spec 21) ----------------------------------------------------
def test_a_store_backed_parameter_never_reaches_the_plot_file(dummy_folder, tmp_path):
    dataset = DUMMY.load(detect_dummy(dummy_folder), sniff)
    params = DUMMY.default_params(AppConfig(), dataset)
    params.pick = [2, 3]
    folder = tmp_path / "sim"
    folder.mkdir()
    write_plot_file(folder, "dummy", params)
    stored, _warnings = read_plot_file(folder, "dummy")
    assert stored is not None and "pick" not in stored
    fresh = DUMMY.default_params(AppConfig(), dataset)
    assert apply_stored(fresh, {"pick": [1], "color": "#00ff00"}, DUMMY.param_schema(dataset)) == []
    assert fresh.pick is None and fresh.color == "#00ff00"


def test_the_session_takes_store_values_over_the_defaults(dummy_folder, tmp_path):
    result = detect_dummy(dummy_folder)
    dataset = DUMMY.load(result, sniff)
    stores = Stores(CompoundStore(tmp_path / "compounds.json"))
    memory = None  # never read: there is no legacy data for it to hold

    def build(open_session=None):
        return build_session(
            result, dataset, AppConfig(), (None, []), memory, open_session, stores
        )[0]  # type: ignore[arg-type]

    assert build().params.pick is None
    stores.compounds.save(STORE_KEY, "X5", [1, 5])
    session = build()
    assert session.params.pick == [1, 5] and session.defaults.pick == [1, 5] and not session.edited

    session.params.pick = [2]
    assert session.persist("pick", stores) is True
    assert stores.compounds.selection(STORE_KEY) == [2] and not session.edited
    session.params.color = "#00ff00"
    assert session.persist("color", stores) is False and session.edited


def test_the_window_offers_and_saves_a_store_backed_parameter(
    qtbot, main_window, dummy_folder, monkeypatch
):
    from PyQt6.QtWidgets import QPushButton

    window = main_window
    window.compounds.save(STORE_KEY, "X5", [2, 3])
    result = detect_dummy(dummy_folder)
    window.plot_workflow.show_loaded(result, DUMMY.load_cached(result, sniff), (None, []))
    session = window.current_plot().session
    assert session.params.pick == [2, 3]

    seen = []

    def ask(parent, choices, selected):
        seen.append((len(choices.sites), selected))
        return AtomsAnswer([4])

    monkeypatch.setattr("qe_studio.ui.widgets.params_body.ask_atoms", ask)
    (button,) = [b for b in window.params.body.findChildren(QPushButton) if b.text() == "Átomos…"]
    button.click()
    assert seen == [(5, [2, 3])] and session.params.pick == [4]
    assert window.compounds.selection(STORE_KEY) == [4]
    window.plot_settings.flush_now()
    assert not (dummy_folder / "dummy.plot").exists()  # not a plot edit


def test_modules_without_atoms_have_neutral_hooks(dummy_folder):
    from qe_studio.core.calculations.base import CalculationModule as Base

    module = DummyModule()
    dataset = module.load(detect_dummy(dummy_folder), sniff)
    stores = Stores(CompoundStore())
    assert Base.atoms_of(module, dataset) is None
    assert Base.stored_params(module, dataset, stores) == {}
    assert Base.save_stored(module, dataset, DummyParams(), "pick", stores) is None
    bands = next(m for m in REGISTRY if m.kind == "bands")
    assert bands.atoms_of(None) is None and bands.stored_params(None, stores) == {}  # type: ignore[arg-type]
