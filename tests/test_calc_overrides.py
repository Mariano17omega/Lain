"""Spec 39 R2.2: the files edited by hand in "Criar cálculo" (``core/calc_create/overrides``, Qt-free)."""

from qe_studio.core.calc_create.overrides import (
    apply_overrides,
    edit_issues,
    edits_in_force,
    is_edit,
    normalized,
)
from qe_studio.core.calc_create.types import CalcPlan, PlannedFile

SCRIPT = PlannedFile("pdos.qsub", "qsub", "#!/bin/bash\necho ok\n", "pdos.qsub", "script")
SCF = PlannedFile(
    "scf_al.in", "pw_input", "&control\n  calculation = 'scf'\n/\n", "scf_al.in", "scf"
)
PLAN = CalcPlan((SCRIPT, SCF), notes=("uma nota",), errors=("um erro",), problems={"np": "x"})


def test_normalized_ends_with_one_newline():
    assert normalized("a\nb") == "a\nb\n"
    assert normalized("a\r\nb\r\n") == "a\nb\n"
    assert normalized("a\n") == "a\n"
    assert normalized("") == ""


def test_a_text_equal_to_the_generated_one_is_no_edit():
    assert not is_edit(SCF.text, SCF.text)
    assert not is_edit(SCF.text.rstrip("\n"), SCF.text)  # the final newline aside
    assert not is_edit(SCF.text.replace("\n", "\r\n"), SCF.text)  # and the line ends
    assert is_edit(SCF.text + "! nota\n", SCF.text)


def test_the_typed_text_replaces_the_file_of_its_key():
    typed = "&control\n  calculation = 'scf'\n  verbosity = 'high'\n/"
    plan = apply_overrides(PLAN, {"scf": typed})
    scf = plan.by_key("scf")
    assert scf is not None and scf.text == typed + "\n"
    assert scf.name == SCF.name and scf.kind == SCF.kind and scf.tab_label == SCF.tab_label
    assert plan.by_key("script") == SCRIPT  # untouched
    # What the fields say stays the fields'.
    assert (plan.notes, plan.errors, dict(plan.problems)) == (PLAN.notes, PLAN.errors, {"np": "x"})


def test_unknown_keys_and_unchanged_texts_are_ignored():
    assert apply_overrides(PLAN, {}) is PLAN
    assert apply_overrides(PLAN, {"nscf": "&control\n/\n"}) is PLAN
    assert apply_overrides(PLAN, {"scf": SCF.text.rstrip()}) is PLAN
    assert edits_in_force(PLAN, {"nscf": "x", "scf": SCF.text, "script": "#!/bin/sh\n"}) == {
        "script": "#!/bin/sh\n"
    }


def test_a_renamed_file_keeps_its_edit():
    renamed = CalcPlan((SCRIPT, PlannedFile("scf_teste.in", "pw_input", SCF.text, "x", "scf")))
    scf = apply_overrides(renamed, {"scf": "&control\n/\n"}).by_key("scf")
    assert scf is not None and (scf.name, scf.text) == ("scf_teste.in", "&control\n/\n")


def test_issues_of_an_input_and_of_a_script():
    broken = "&control\n  calculation 'scf'\n/\n"  # no "="
    issues = edit_issues("pw_input", broken)
    assert [issue.line for issue in issues] == [2]
    assert edit_issues("pw_input", SCF.text) == []
    assert edit_issues("qsub", "#!/bin/bash\nif true; then\n  echo ok\n") != []  # no "fi"
    assert edit_issues("qsub", SCRIPT.text) == []
