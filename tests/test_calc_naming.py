"""Spec 77 R1: the site and the inherited suffix in the name of a new calculation's folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from qe_studio.core.calc_create.naming import inherited_suffix, site_tag
from qe_studio.core.calc_create.types import REGISTRY, by_id
from qe_studio.core.calc_create.writer import (
    CreateError,
    create_folder,
    folder_name,
    preview_name,
    validate_target,
)
from test_calc_adsorption import mono, plan

from calc_helpers import JOBS, al

ADSORPTION, BANDAS = by_id("adsorption"), by_id("bandas")


def test_the_site_is_the_last_part_of_the_name():
    assert folder_name(ADSORPTION, "", 1, tag="O11") == "1_Adsorption_O11"
    assert folder_name(ADSORPTION, "teste", 1, tag="O11") == "1_Adsorption_teste_O11"
    assert folder_name(BANDAS, "", 2, inherited="teste_O11") == "2_Bands_teste_O11"
    assert folder_name(ADSORPTION, "x", 1, "Al", "O43-O46") == "1_Adsorption_x_Al_O43-O46"
    assert folder_name(ADSORPTION, "", tag="O43") == "Adsorption_O43"


@pytest.mark.parametrize("calc_type", REGISTRY, ids=lambda t: t.id)
def test_without_the_new_parts_every_name_is_todays(calc_type):
    prefix = calc_type.folder_prefix
    assert folder_name(calc_type, "Al") == f"{prefix}_Al"
    assert folder_name(calc_type, "", 3) == f"3_{prefix}"
    assert folder_name(calc_type, " Al ", 3, "", "") == f"3_{prefix}_Al"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("proj/1_Adsorption_teste_O11/scf.in", "teste_O11"),
        ("proj/0_Relax_Al/scf.in", "Al"),
        ("proj/Bands_Al_1/scf.in", "Al_1"),
        ("proj/3_vc-relax_x/scf.in", "x"),  # case does not matter
        ("proj/2_Bands/scf.in", ""),
        ("proj/SCF/scf.in", ""),
        ("proj/Notas/scf.in", ""),
        ("scf.in", ""),
    ],
)
def test_the_suffix_is_what_follows_the_number_and_the_type(path, expected):
    assert inherited_suffix(Path(path)) == expected


def test_no_scf_inherits_nothing():
    assert inherited_suffix(None) == ""


def test_the_longest_type_prefix_wins():
    assert inherited_suffix(Path("Diff_Charge_ilita/scf.in")) == "ilita"
    assert inherited_suffix(Path("Charge_ilita/scf.in")) == "ilita"


def test_the_site_tag():
    assert site_tag([("O", 43)]) == "O43"
    assert site_tag([("O", 46), ("O", 43)]) == "O43-O46"
    assert site_tag([("O1_x", 9)]) == "O1x9"  # only letters and digits of a label
    assert site_tag([]) == ""


def test_the_folder_is_made_with_the_tag(tmp_path):
    made = create_folder(tmp_path, ADSORPTION, "", mono(), tag="O43")
    assert made.folder.name == "Adsorption_O43"
    assert preview_name(tmp_path, ADSORPTION, "", tag="O43") == "Adsorption_O43_1"  # taken: last
    again = create_folder(tmp_path, ADSORPTION, "", mono(), tag="O43")
    assert again.folder.name == "Adsorption_O43_1" and again.renamed_from == "Adsorption_O43"


def test_the_numbered_name_has_every_part(tmp_path):
    (tmp_path / "0_Relax").mkdir()
    made = create_folder(
        tmp_path, ADSORPTION, "x", mono(), numbered=True, inherited="teste_O11", tag="O43"
    )
    assert made.folder.name == "1_Adsorption_x_teste_O11_O43"


@pytest.mark.parametrize(("inherited", "tag"), [("a b", ""), ("é", ""), ("", "O 43"), ("", "a/b")])
def test_a_bad_part_is_an_error_before_anything_is_made(tmp_path, inherited, tag):
    assert validate_target(tmp_path, "", inherited, tag)
    with pytest.raises(CreateError):
        create_folder(
            tmp_path, BANDAS, "", BANDAS.plan(al(), {}, JOBS), inherited=inherited, tag=tag
        )
    assert list(tmp_path.iterdir()) == []


def test_the_plan_offers_the_site():
    assert mono(43).folder_tag == "O43"
    assert plan(site=(45, 42), remove_h=True, mode="bidentado").folder_tag == "O42-O45"
    assert plan(site=()).folder_tag == ""  # no site: nothing built
    assert BANDAS.plan(al(), {}, JOBS).folder_tag == ""
