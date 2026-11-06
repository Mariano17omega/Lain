"""Spec 80 R1, R2: ``fingerprint.md`` says what a new calculation is and where its SCFs came from."""

import builtins
import dataclasses
from datetime import datetime
from pathlib import Path

import pytest

from qe_studio import __version__
from qe_studio.core.calc_create.fingerprint import (
    FINGERPRINT_NAME,
    Source,
    fingerprint_text,
    real_paths,
    shown_path,
    sources,
)
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.calc_create.writer import CreateError, create_folder, files_to_write
from test_calc_ads_energy import NI_SCF, scfs

from calc_helpers import AL_PATH, AL_SCF, JOBS, SI_SCF, al
from surface_helpers import MOLECULE, SUPERCELL_001, read

BANDAS = by_id("bandas")
ADSORPTION = by_id("adsorption")
ADS_ENERGY = by_id("ads_energy")
WHEN = datetime(2026, 10, 31, 14, 5, 9)


def test_a_path_inside_the_root_is_relative_and_one_outside_absolute(tmp_path):
    root = tmp_path / "root"
    inside = root / "proj" / "0_Relax" / "scf.in"
    outside = tmp_path / "elsewhere" / "scf.in"
    assert shown_path(inside, root) == "proj/0_Relax/scf.in"
    assert shown_path(outside, root) == str(outside.resolve())
    assert shown_path(root, root) == "."
    assert shown_path(inside, root, resolve=False) == "proj/0_Relax/scf.in"
    assert shown_path(outside, root, resolve=False) == str(outside)


def test_a_link_out_of_the_root_is_shown_where_it_leads(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "real.in"
    target.write_text("x")
    (root / "link.in").symlink_to(target)
    assert shown_path(root / "link.in", root) == str(target.resolve())


def test_real_paths_follow_links_as_shown_path_does(tmp_path):
    """What the "Arquivos" preview gets from a worker: with it, ``shown_path`` without the disk says
    what it says with the disk."""
    real = tmp_path / "real"
    (real / "proj").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    scf = real / "proj" / "scf.in"
    found = real_paths([link, scf, tmp_path / "missing.in"])
    assert found == {
        link: real.resolve(),
        scf: scf.resolve(),
        tmp_path / "missing.in": (tmp_path / "missing.in").resolve(),
    }
    assert (
        shown_path(found[scf], found[link], resolve=False) == shown_path(scf, link) == "proj/scf.in"
    )


def test_a_loop_of_links_stops_neither_the_preview_nor_the_writer(tmp_path, monkeypatch):
    def loop(self, strict=False):
        raise RuntimeError("Symlink loop")

    monkeypatch.setattr(Path, "resolve", loop)
    scf = tmp_path / "root" / "scf.in"
    assert real_paths([scf]) == {scf: scf}
    assert shown_path(scf, tmp_path / "root") == "scf.in"


def test_a_type_of_one_scf_lists_it_with_step_1s_label():
    found = sources(BANDAS, al(), (), {})
    assert found == [Source("Input de SCF", AL_SCF)]
    assert sources(ADSORPTION, read(SUPERCELL_001), (), {}) == [
        Source("SCF da superfície", SUPERCELL_001)
    ]


def test_the_molecule_on_a_surface_lists_both_scfs():
    fields = ADSORPTION.fields(read(SUPERCELL_001), JOBS, "", ())
    found = sources(ADSORPTION, read(SUPERCELL_001), fields, {"molecule": read(MOLECULE)})
    assert [source.path for source in found] == [SUPERCELL_001, MOLECULE]
    assert found[0].label == "SCF da superfície"
    assert found[1].label == next(f.label for f in fields if f.id == "molecule")
    assert len({source.label for source in found}) == 2


def test_an_empty_scf_field_and_an_scf_without_path_are_left_out():
    fields = ADSORPTION.fields(read(SUPERCELL_001), JOBS, "", ())
    assert len(sources(ADSORPTION, read(SUPERCELL_001), fields, {"molecule": None})) == 1
    assert sources(BANDAS, dataclasses.replace(al(), path=None), (), {}) == []


def test_the_adsorption_energy_lists_every_scf_and_no_base():
    listed = scfs()
    found = sources(ADS_ENERGY, listed[0], (), {}, listed)
    assert [source.label for source in found] == ["SCF 1", "SCF 2", "SCF 3"]
    assert [source.path for source in found] == [SI_SCF, AL_SCF, NI_SCF]


def test_the_text_has_the_type_the_folder_the_date_and_the_version(tmp_path):
    found = [Source("Input de SCF", tmp_path / "proj" / "scf.in"), Source("Outro", SI_SCF)]
    text = fingerprint_text(BANDAS, "2_Bands_Al", found, tmp_path, WHEN)
    lines = text.splitlines()
    assert lines[0] == "# Fingerprint do cálculo" and text.endswith("\n")
    assert "| Tipo de cálculo | Bandas (`bandas`) |" in lines
    assert "| Pasta | `2_Bands_Al` |" in lines
    assert "| Criado em | 2026-10-31 14:05:09 |" in lines
    assert f"| Lain | {__version__} |" in lines
    assert "| Input de SCF | `proj/scf.in` |" in lines
    assert f"| Outro | `{SI_SCF.resolve()}` |" in lines
    rows = [line for line in lines if line.startswith("|")]
    assert all(line.count("|") == 3 for line in rows)


def test_a_bar_in_a_path_does_not_break_the_table(tmp_path):
    found = [Source("SCF", tmp_path / "a|b" / "scf.in")]
    text = fingerprint_text(BANDAS, "Bands", found, tmp_path, WHEN)
    assert "| SCF | `a\\|b/scf.in` |" in text.splitlines()


def test_a_backtick_in_a_path_keeps_the_code_span(tmp_path):
    found = [Source("SCF", tmp_path / "a`b" / "scf.in")]
    text = fingerprint_text(BANDAS, "Bands", found, tmp_path, WHEN)
    assert "| SCF | ``a`b/scf.in`` |" in text.splitlines()


# -- the file in the new folder (R2) -----------------------------------------------------------------
def bands_plan():
    plan = BANDAS.plan(al(), {"kpath": AL_PATH}, JOBS)
    assert plan.ok
    return plan


def test_files_to_write_adds_it_only_when_asked():
    plan = bands_plan()
    assert [f.name for f in files_to_write(plan, "")] == [f.name for f in plan.files]
    with_it = files_to_write(plan, "nota", "texto")
    assert [f.name for f in with_it][-2:] == ["descricao.md", FINGERPRINT_NAME]
    assert with_it[-1].kind == "notes" and with_it[-1].text == "texto"


def test_the_folder_gets_the_file_with_its_final_name(tmp_path):
    (tmp_path / "0_Relax").mkdir()
    (tmp_path / "1_Bands").mkdir()
    (tmp_path / "2_Bands_Al").mkdir()  # the name asked for is taken
    found = (Source("Input de SCF", tmp_path / "proj" / "scf.in"),)
    created = create_folder(
        tmp_path, BANDAS, "Al", bands_plan(), numbered=True, fingerprint=found, root=tmp_path
    )
    assert created.folder.name == "3_Bands_Al"  # 0, 1 and 2 are taken: the next number
    text = (created.folder / FINGERPRINT_NAME).read_text()
    assert "| Pasta | `3_Bands_Al` |" in text and "| Input de SCF | `proj/scf.in` |" in text
    assert created.files[-1] == created.folder / FINGERPRINT_NAME


def test_a_taken_name_is_the_one_the_file_says(tmp_path):
    found = (Source("Input de SCF", AL_SCF),)
    create_folder(tmp_path, BANDAS, "Al", bands_plan())
    created = create_folder(tmp_path, BANDAS, "Al", bands_plan(), fingerprint=found)
    assert created.folder.name == "Bands_Al_1"
    assert "| Pasta | `Bands_Al_1` |" in (created.folder / FINGERPRINT_NAME).read_text()


def test_without_it_the_folder_holds_what_it_always_did(tmp_path):
    plan = bands_plan()
    plain = create_folder(tmp_path, BANDAS, "A", plan, "nota")
    unset = create_folder(tmp_path, BANDAS, "B", plan, "nota", fingerprint=None)
    for created in (plain, unset):
        assert sorted(p.name for p in created.folder.iterdir()) == sorted(
            [*(f.name for f in plan.files), "descricao.md"]
        )


def test_the_root_defaults_to_the_place(tmp_path):
    found = (Source("SCF", tmp_path / "x" / "scf.in"),)
    created = create_folder(tmp_path, BANDAS, "Al", bands_plan(), fingerprint=found)
    assert "`x/scf.in`" in (created.folder / FINGERPRINT_NAME).read_text()


def test_a_failed_write_removes_the_fingerprint_too(tmp_path, monkeypatch):
    real_open = builtins.open

    def failing(path, mode="r", *args, **kwargs):
        if mode == "x" and Path(path).name == FINGERPRINT_NAME:
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", failing)
    with pytest.raises(CreateError, match=f"Não foi possível gravar {FINGERPRINT_NAME}"):
        create_folder(tmp_path, BANDAS, "Al", bands_plan(), fingerprint=(Source("SCF", AL_SCF),))
    assert list(tmp_path.iterdir()) == []
