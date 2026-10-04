"""A PDOS folder with several atoms, for the atom-selection tests (spec 21).

``al_pdos_flat`` has one atom. ``pdos_folder`` copies it into the PRD layout with one set of
projection files per atom (atom ``n`` is the fixture's projections times ``n``, so the sum of any
subset tells which atoms were drawn) and a site list of that many atoms in both pw.x outputs.
"""

import re
import shutil
from pathlib import Path

from qe_studio.core.qe import projwfc

from conftest import FIXTURES

SOURCE = FIXTURES / "al_pdos_flat"
SITE_LINE = re.compile(r"^ +1 +Al +tau\(\s*1\).*$", re.M)


def site_list(species: tuple[str, ...]) -> str:
    return "\n".join(
        f"{i:9d}{name:>10}     tau({i:4d}) = ({0.25 * (i - 1):12.7f}{0.0:12.7f}{0.0:12.7f}  )"
        for i, name in enumerate(species, start=1)
    )


def scaled(path: Path, factor: float) -> str:
    """The projection file with every column but the energy times ``factor``."""
    header, *rows = path.read_text().splitlines()
    out = [header]
    for row in rows:
        energy, *values = row.split()
        out.append(f"{energy:>8}  " + "  ".join(f"{float(v) * factor:.6E}" for v in values))
    return "\n".join(out) + "\n"


def pdos_folder(root: Path, species: tuple[str, ...] = ("Al", "Al"), name: str = "pdos") -> Path:
    folder = root / name
    (folder / "orbitals").mkdir(parents=True)
    for old, new in (("al.scf.out", "scf.out"), ("al.nscf.out", "nscf.out")):
        text = SITE_LINE.sub(lambda _m: site_list(species), (SOURCE / old).read_text(), count=1)
        (folder / new).write_text(text)
    shutil.copy(SOURCE / "al.projwfc.out", folder / "projwfc.out")
    shutil.copy(SOURCE / "pdos.dat.pdos_tot", folder / "pdos.dat.pdos_tot")
    for path in SOURCE.glob("*pdos_atm*"):
        meta = projwfc.parse_atm_name(path.name)
        assert meta is not None
        for atom, element in enumerate(species, start=1):
            target = f"pdos.dat.pdos_atm#{atom}({element})_wfc#{meta.wfc}({meta.l})"
            (folder / "orbitals" / target).write_text(scaled(path, atom))
    return folder
