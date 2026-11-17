"""Every "Criar cálculo" type planned from real SCF inputs, without a window."""

import pytest

from qe_studio.core.calc_create.scf_info import scf_info
from qe_studio.core.calc_create.types import REGISTRY
from qe_studio.core.qe.input_lint import lint
from qe_studio.core.sniff import FileKind

from calc_helpers import JOBS
from qe_examples_helpers import PW, params, select

SCF_CASES = select(PW, ["scf"])
TYPES = [pytest.param(calc_type, id=calc_type.id) for calc_type in REGISTRY]


@pytest.mark.parametrize("case", params(SCF_CASES))
def test_scf_info_reads_the_input(case):
    info = scf_info(case.input_text, case.input_path)
    assert info.crystal is not None


@pytest.mark.parametrize("calc_type", TYPES)
@pytest.mark.parametrize("case", params(SCF_CASES))
def test_plan_is_made_or_refused_with_a_reason(case, calc_type):
    info = scf_info(case.input_text, case.input_path)
    refused = calc_type.check_scf(info)
    if refused:
        assert refused.strip()
        return
    plan = calc_type.plan(info, {}, JOBS)
    if not plan.ok:
        assert all(error.strip() for error in plan.errors)
        return
    assert plan.files
    for planned in plan.files:
        if planned.kind is FileKind.PW_IN:
            errors = [issue for issue in lint(planned.text).issues if issue.severity == "error"]
            assert errors == [], planned.name
