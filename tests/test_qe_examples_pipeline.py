"""Real run folders from detection to the drawn figure, and the Summary of every real output.

``EXPECTED`` says what each folder gives. ``not_plottable``: the folder lacks a file the plot needs
(the QE examples do not keep every data file). ``refused``: a relax run that prints no step the
reader knows (FCP), a limit held here on purpose. Damped dynamics is read since spec 101.
"""

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from qe_studio.core.calculations.base import LoadError
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.plotting.style import DARK
from qe_studio.core.qe.summary import summarize
from qe_studio.core.sniff import SniffCache

from conftest import QE_EXAMPLES
from qe_examples_helpers import CASES, RISM_GAP, params

RENDERED, NOT_PLOTTABLE, REFUSED = "rendered", "not_plottable", "refused"
EXPECTED = {
    "PP/BGW_example/references": {"scf": RENDERED},
    "PP/ForceTheorem_example": {"pdos": NOT_PLOTTABLE},
    "PP/MolDos_example": {"bands": RENDERED, "pdos": NOT_PLOTTABLE},
    "PP/WannierHam_example": {"calc": NOT_PLOTTABLE},
    "PP/WorkFct_example": {"calc": NOT_PLOTTABLE},
    "PP/dipole_example": {"scf": RENDERED},
    "PP/example01": {"bands": RENDERED},
    "PP/example02": {"pdos": RENDERED},
    "PP/example04": {"bands": NOT_PLOTTABLE, "pdos": NOT_PLOTTABLE},
    "PP/example06": {"bands": RENDERED},
    "PP/exx_scf_bands_example": {"bands": NOT_PLOTTABLE},
    "PP/fermisurf_example": {"pdos": RENDERED},
    "PW/ESM_example": {"relax": REFUSED},
    "PW/Extffield_example": {"calc": NOT_PLOTTABLE},
    "PW/RISM_example": {"scf": RENDERED},
    "PW/VCSexample": {"relax": RENDERED},
    "PW/cluster_example": {"relax": RENDERED},
    "PW/example01": {"bands": NOT_PLOTTABLE},
    "PW/example02": {"relax": RENDERED},
    "PW/example03": {"calc": NOT_PLOTTABLE},
    "PW/example04": {"calc": NOT_PLOTTABLE},
    "PW/example06": {"relax": RENDERED},
    "PW/example11": {"bands": NOT_PLOTTABLE},
    "PW/example14": {"scf": RENDERED},
    "PW/gatefield": {"bands": NOT_PLOTTABLE, "relax": RENDERED},
    "PW/vdwDF_example": {"relax": RENDERED},
    "test-suite/pw_cluster": {"scf": RENDERED},
    "test-suite/pw_lda+U": {"scf": RENDERED},
    "test-suite/pw_scf": {"scf": RENDERED},
    "test-suite/pw_twochem": {"relax": RENDERED},
    "test-suite/pw_vc-relax": {"relax": RENDERED},
    "test-suite/pw_vdw": {"relax": RENDERED},
    "test-suite/pw_workflow_exx_nscf": {"scf": RENDERED},
    "test-suite/pw_workflow_vc-relax_dos": {"relax": RENDERED},
    "test-suite/pw_workflow_vc-relax_scf": {"relax": RENDERED},
}
GAPS = {"PW/RISM_example": RISM_GAP}
FOLDERS = [
    pytest.param(
        folder,
        id=folder,
        marks=[pytest.mark.xfail(strict=True, reason=GAPS[folder])] if folder in GAPS else [],
    )
    for folder in sorted(EXPECTED)
]


def outcome(result, cache) -> str:
    if not result.plottable:
        return NOT_PLOTTABLE
    try:
        dataset = result.module.load(result, cache.sniff)
    except LoadError:
        return REFUSED
    figure = Figure()
    FigureCanvasAgg(figure)
    result.module.render(figure, dataset, result.module.default_params(AppConfig(), dataset), DARK)
    figure.canvas.draw()
    assert figure.axes, "a plot without axes"
    return RENDERED


def test_every_folder_is_in_the_table():
    folders = {str(case.output_path.parent.relative_to(QE_EXAMPLES)) for case in CASES}
    assert folders == set(EXPECTED)


@pytest.mark.parametrize("folder", FOLDERS)
def test_folder_gives_what_is_expected(folder):
    cache = SniffCache()
    results = detect_folder(QE_EXAMPLES / folder, sniff=cache.sniff)
    assert {result.kind: outcome(result, cache) for result in results} == EXPECTED[folder]


@pytest.mark.parametrize("case", params(CASES))
def test_summary_reads_every_output(case):
    summary = summarize(case.output_path)
    assert summary.sections
    assert all(section.title for section in summary.sections)
