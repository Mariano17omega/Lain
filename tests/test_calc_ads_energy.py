"""Spec 79 R2: the "Energia de adsorção" type gathers several SCFs in one folder, one script.

Each SCF is copied with the folder's unit (``outdir``, ``pseudo_dir``) and nothing else changed; the
script runs them in the list's order; two inputs that would share ``<outdir>/<prefix>.save`` block
"Criar", read in the texts as they will be written (a hand edit included).
"""

import dataclasses
import difflib

from qe_studio.core.calc_create.overrides import apply_overrides
from qe_studio.core.calc_create.scf_info import ScfInfo, read_scf, scf_info
from qe_studio.core.calc_create.types import ads_energy, by_id
from qe_studio.core.calc_create.types.ads_energy import SAME_PREFIX
from qe_studio.core.calc_create.writer import create_folder
from qe_studio.core.config import JobsConfig
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.viewer.qsub_lint import lint_script

from calc_helpers import AL_SCF, JOBS, SI_SCF, runs
from conftest import FIXTURES

NI_SCF = FIXTURES / "qe731_ni_spin_fixed" / "ni.scf.in"
TYPE = by_id("ads_energy")
PSEUDO = "/opt/pseudo"


def scfs() -> tuple[ScfInfo, ...]:
    return tuple(read_scf(path) for path in (SI_SCF, AL_SCF, NI_SCF))


def plan(listed: tuple[ScfInfo, ...], jobs: JobsConfig = JOBS, values=None, mode="padrao"):
    return TYPE.plan(listed[0], values or {}, jobs, mode, "", listed)


def changed(original: str, text: str) -> list[str]:
    """The lines of ``text`` that are not in ``original`` (added or changed)."""
    diff = difflib.ndiff(original.splitlines(), text.splitlines())
    return [line[2:].strip() for line in diff if line.startswith("+ ")]


def test_the_type():
    assert TYPE.label == "Energia de adsorção"
    assert TYPE.folder_prefix == "Ads_energy" and TYPE.script_name == "ads_energy.qsub"
    assert TYPE.multi_scf and TYPE.scf_label == "Inputs de SCF"
    assert not TYPE.writes_report


def test_the_files_follow_the_list():
    result = plan(scfs())
    assert result.ok, result.errors
    assert [planned.name for planned in result.files] == [
        "ads_energy.qsub",
        "scf_silicon.in",
        "scf_al.in",
        "scf_nifix.in",
    ]
    assert [planned.tab_label for planned in result.files[1:]] == [
        "SCF (scf_silicon.in)",
        "SCF (scf_al.in)",
        "SCF (scf_nifix.in)",
    ]


def test_each_input_is_its_scf_in_the_folder_unit():
    jobs = JobsConfig(pseudo_dir=PSEUDO)
    listed = scfs()
    result = plan(listed, jobs)
    assert result.ok, result.errors
    for scf, planned in zip(listed, result.files[1:], strict=True):
        assert planned.source == scf.text  # the preview compares with its own SCF
        made, original = InputEditor.from_text(planned.text), InputEditor.from_text(scf.text)
        assert made.get("control", "outdir") == "./tmp/"
        assert made.get("control", "pseudo_dir") == PSEUDO
        for namelist in ("control", "system", "electrons"):
            for key in original.keys(namelist):
                if key not in ("outdir", "pseudo_dir"):
                    assert made.get(namelist, key) == original.get(namelist, key), key
        for card in ("ATOMIC_SPECIES", "ATOMIC_POSITIONS", "K_POINTS", "CELL_PARAMETERS"):
            assert made.card_rows(card) == original.card_rows(card), card
        assert all(
            "outdir" in line or "pseudo_dir" in line for line in changed(scf.text, planned.text)
        )


def test_without_a_pseudo_dir_in_the_config_it_stays():
    listed = scfs()
    result = plan(listed)
    for scf, planned in zip(listed, result.files[1:], strict=True):
        assert [line for line in changed(scf.text, planned.text) if "outdir" not in line] == []


def test_the_script_runs_them_in_order():
    script = plan(scfs()).files[0]
    assert runs(script.text) == ["scf_silicon.in", "scf_al.in", "scf_nifix.in"]
    assert [issue for issue in lint_script(script.text) if issue.severity == "error"] == []


def test_the_order_is_the_list_s():
    si, al, ni = scfs()
    assert [planned.name for planned in plan((ni, si, al)).files[1:]] == [
        "scf_nifix.in",
        "scf_silicon.in",
        "scf_al.in",
    ]


def test_the_same_prefix_twice_blocks_until_one_is_changed_by_hand():
    si, al, __ = scfs()
    same = SAME_PREFIX.format(prefix="silicon")
    result = plan((si, al, si))
    names = [planned.name for planned in result.files[1:]]
    assert names == ["scf_silicon.in", "scf_al.in", "scf_silicon_2.in"]  # no name to fix
    assert result.errors == (same,) and dict(result.problems) == {}
    # Renaming the file does not separate the runs: they would share ./tmp/silicon.save.
    renamed = plan((si, al, si), values={"name:scf2": "scf_outro.in"}, mode="avancado")
    assert renamed.errors == (same,)
    # The prefix changed by hand in the preview (the advanced mode) does.
    scf2 = result.by_key("scf2")
    assert scf2 is not None
    typed = scf2.text.replace("prefix='silicon'", "prefix='silicon_b'")
    assert apply_overrides(result, {"scf2": typed}, TYPE).ok
    # And an edit that makes two prefixes the same blocks.
    scf1 = result.by_key("scf1")
    assert scf1 is not None
    collides = {"scf2": typed, "scf1": scf1.text.replace("prefix='al'", "prefix='silicon_b'")}
    edited = apply_overrides(result, collides, TYPE)
    assert edited.errors == (SAME_PREFIX.format(prefix="silicon_b"),)


def test_another_outdir_does_not_separate_the_same_prefix():
    """``<prefix>.EXIT`` is looked for in the working folder, whatever the ``outdir``: cancelling would
    stop only the first run, and the second would go on (spec 70)."""
    si, al, __ = scfs()
    result = plan((si, al, si))
    scf2 = result.by_key("scf2")
    assert scf2 is not None
    editor = InputEditor.from_text(scf2.text)
    editor.set("control", "outdir", "'./tmp_b/'")
    edited = apply_overrides(result, {"scf2": editor.text()}, TYPE)
    assert edited.errors == (SAME_PREFIX.format(prefix="silicon"),)


def test_prefixes_with_the_same_file_name_get_their_own_names():
    """``Al O`` and ``Al_O`` are two runs (two ``.save``), but one file name: the second takes
    ``_2``, nothing blocks."""
    si = read_scf(SI_SCF)
    one = scf_info(si.text.replace("prefix='silicon'", "prefix='Al O'"), SI_SCF)
    two = scf_info(si.text.replace("prefix='silicon'", "prefix='Al_O'"), AL_SCF)
    result = plan((one, two))
    assert result.ok, result.errors
    assert [planned.name for planned in result.files[1:]] == ["scf_Al_O.in", "scf_Al_O_2.in"]


def test_the_prefix_of_a_run():
    assert ads_energy.prefix_of("&control\n  prefix='al'\n  outdir='./tmp/'\n/\n") == "al"
    assert ads_energy.prefix_of("&control\n/\n") == "pwscf"  # pw.x's default


def test_a_keystroke_reads_only_the_text_typed(monkeypatch):
    """``text_errors`` runs on every keystroke in a preview, with every input of the list."""
    listed = scfs()
    result = plan(listed)
    reads = []
    original = InputEditor.from_text
    ads_energy.prefix_of.cache_clear()
    TYPE.text_errors(result.files)

    def counted(text):
        reads.append(text)
        return original(text)

    monkeypatch.setattr(InputEditor, "from_text", counted)
    scf0 = result.by_key("scf0")
    assert scf0 is not None
    typed = scf0.text + "! typed\n"
    edited = apply_overrides(result, {"scf0": typed}, TYPE)
    assert edited.ok and reads == [typed]


def test_without_a_list_it_plans_the_scf_alone():
    """``plan`` never refuses: the two-SCF minimum is step 1's (spec 79 R1.2)."""
    si = read_scf(SI_SCF)
    result = TYPE.plan(si, {}, JOBS)
    assert [planned.name for planned in result.files] == ["ads_energy.qsub", "scf_silicon.in"]


def test_the_description_says_where_the_scfs_came_from():
    listed = scfs()
    assert TYPE.default_notes(listed) == (f"SCFs de origem:\n- {SI_SCF}\n- {AL_SCF}\n- {NI_SCF}\n")
    assert TYPE.default_notes(()) == ""
    assert by_id("scf").default_notes(listed) == ""


def test_the_description_names_an_scf_of_the_project_from_its_root():
    """No path of this machine goes to the cluster for an SCF inside the project (``fingerprint.md``
    does the same); one outside stays absolute."""
    root = FIXTURES.parent
    assert TYPE.default_notes(scfs(), root) == (
        "SCFs de origem:\n- fixtures/si_bands/si.scf.in\n- fixtures/al_bands/al.scf.in\n"
        "- fixtures/qe731_ni_spin_fixed/ni.scf.in\n"
    )
    assert TYPE.default_notes(scfs()[:1], FIXTURES / "al_bands") == f"SCFs de origem:\n- {SI_SCF}\n"


def test_the_description_says_a_project_reached_through_a_link_from_its_root(tmp_path):
    """The window resolves the paths in a worker (``real_paths``) and hands them here: no path of this
    machine goes to the cluster for an SCF of a project whose root is a link."""
    real = tmp_path / "real"
    link = tmp_path / "link"
    scf = real / "proj" / "al.scf.in"
    info = dataclasses.replace(read_scf(AL_SCF), path=scf)
    assert TYPE.default_notes((info,), link) == f"SCFs de origem:\n- {scf}\n"  # until they arrive
    assert TYPE.default_notes((info,), link, {link: real}) == "SCFs de origem:\n- proj/al.scf.in\n"
    assert by_id("scf").default_notes((info,), link, {link: real}) == ""


def test_create_folder_writes_them(tmp_path):
    result = plan(scfs())
    created = create_folder(tmp_path, TYPE, "", result, TYPE.default_notes(scfs()))
    assert created.folder == tmp_path / "Ads_energy"
    assert sorted(path.name for path in created.folder.iterdir()) == [
        "ads_energy.qsub",
        "descricao.md",
        "scf_al.in",
        "scf_nifix.in",
        "scf_silicon.in",
    ]
    assert (created.folder / "scf_al.in").read_text() == result.file("scf_al.in").text
