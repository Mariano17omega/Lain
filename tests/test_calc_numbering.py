"""Spec 51 R1: the number in front of a new calculation's folder, for every type."""

import pytest

from fragment_helpers import SMALL
from qe_studio.core.calc_create.numbering import next_number
from qe_studio.core.calc_create.preview import target_text
from qe_studio.core.calc_create.types import REGISTRY, by_id
from qe_studio.core.calc_create.writer import create_folder, folder_name, preview_name

from calc_helpers import AL_PATH, JOBS, al, from_text
from surface_helpers import BULK, read

BANDAS = by_id("bandas")


def folders(parent, *names):
    for name in names:
        (parent / name).mkdir()
    return parent


def numbered_place(tmp_path):
    return folders(tmp_path, "0_Relax", "1_Bands")


def plan_of(type_id: str):
    """A plan with no errors for ``type_id`` (one type of each family)."""
    values = {"bandas": {"kpath": AL_PATH}, "charge_diff": {"atoms": (5, 6)}}.get(type_id, {})
    scf = {"charge_diff": lambda: from_text(SMALL), "slab": lambda: read(BULK)}.get(type_id, al)()
    plan = by_id(type_id).plan(scf, values, JOBS)
    assert plan.ok, plan.errors
    return plan


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ((), 0),
        (("0_Relax", "1_Bands", "2_PDOS"), 3),  # every type counts, PDOS too
        (("0_Relax", "1_Bands", "Notas"), 2),  # no number: not counted
        (("0_a", "5_b"), 6),  # the largest, not the count: gaps are not reused
        (("12_a", "2_b"), 13),  # decimal, no digit limit
        (("03_bands",), 4),  # leading zeros are read as the number
        ((".3_x", "3", "3.old", "plots"), 0),  # hidden, no "_", no number
    ],
)
def test_next_number(tmp_path, names, expected):
    assert next_number(folders(tmp_path, *names)) == expected


def test_files_and_missing_places_do_not_count(tmp_path):
    (tmp_path / "7_x.txt").write_text("")
    (tmp_path / "8_dados").write_text("")
    assert next_number(tmp_path) == 0
    assert next_number(tmp_path / "sumiu") == 0


@pytest.mark.parametrize("calc_type", REGISTRY, ids=lambda t: t.id)
def test_every_type_takes_the_number(tmp_path, calc_type):
    prefix = calc_type.folder_prefix
    assert folder_name(calc_type, "Al", 4) == f"4_{prefix}_Al"
    assert folder_name(calc_type, "", 4) == f"4_{prefix}"
    assert folder_name(calc_type, "Al") == f"{prefix}_Al"  # unnumbered: as before
    place = numbered_place(tmp_path)
    assert preview_name(place, calc_type, "Al", numbered=True) == f"2_{prefix}_Al"
    assert preview_name(place, calc_type, "Al") == f"{prefix}_Al"


def test_create_numbers_each_new_folder(tmp_path):
    place = numbered_place(tmp_path)
    plan = plan_of("bandas")
    first = create_folder(place, BANDAS, "Al", plan, numbered=True)
    assert first.folder == place / "2_Bands_Al" and first.renamed_from is None
    second = create_folder(place, BANDAS, "Al", plan, numbered=True)
    assert second.folder.name == "3_Bands_Al"
    assert create_folder(place, BANDAS, "Al", plan).folder.name == "Bands_Al"  # the default


def test_a_numbered_name_that_is_taken_gets_the_suffix(tmp_path):
    place = numbered_place(tmp_path)
    (place / "2_Bands_Al").write_text("")  # a file: no number for the next folder, but in the way
    assert target_text(place, BANDAS, "Al", numbered=True) == (
        "Será criada: 2_Bands_Al_1 — já existe 2_Bands_Al"
    )
    created = create_folder(place, BANDAS, "Al", plan_of("bandas"), numbered=True)
    assert (created.folder.name, created.renamed_from) == ("2_Bands_Al_1", "2_Bands_Al")


@pytest.mark.parametrize("type_id", ["scf", "pdos", "charge_diff", "slab"])
def test_create_numbers_every_family(tmp_path, type_id):
    calc_type = by_id(type_id)
    place = numbered_place(tmp_path)
    created = create_folder(place, calc_type, "Al", plan_of(type_id), numbered=True)
    assert created.folder.name == f"2_{calc_type.folder_prefix}_Al"
    assert created.files and all(path.parent == created.folder for path in created.files)


def test_the_numbers_go_across_types(tmp_path):
    names = [
        create_folder(tmp_path, by_id(type_id), "", plan_of(type_id), numbered=True).folder.name
        for type_id in ("relax", "bandas", "pdos")
    ]
    assert names == ["0_Relax", "1_Bands", "2_PDOS"]
    assert next_number(tmp_path) == 3
