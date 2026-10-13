"""Shared builders for tests."""

import math

import numpy as np

from viewer3d.core.structure import SourceInfo, SpeciesInfo, Structure


def h3chg_input():
    c = np.array([0.0, 0.000173, 2.176393])
    theta, bond = math.radians(70.0), 1.09
    hs = []
    for k in range(3):
        phi = math.radians(120 * k)
        hs.append(
            c
            + bond
            * np.array(
                [math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)]
            )
        )
    rows = ["Hg 0.0 -0.000323 -0.140002", "C 0.0 0.000173 2.176393"]
    rows += [f"H {x:.6f} {y:.6f} {z:.6f}" for x, y, z in hs]
    return (
        "&CONTROL\n/\n&SYSTEM\nibrav=14, celldm(1)=40.0, celldm(2)=1.0, celldm(3)=1.0,\n"
        "celldm(4)=0.0, celldm(5)=0.0, celldm(6)=0.0, nat=5, ntyp=3\n/\n"
        "ATOMIC_SPECIES\nHg 200.59 Hg.UPF\nC 12.011 C.UPF\nH 1.008 H.UPF\n"
        "ATOMIC_POSITIONS (angstrom)\n" + "\n".join(rows) + "\n"
    )


def make_structure(cell, frac, labels):
    """Structure straight from arrays (one species per distinct label)."""
    unique = list(dict.fromkeys(labels))
    species = tuple(SpeciesInfo(label, None, None, i + 1) for i, label in enumerate(unique))
    return Structure(
        np.asarray(cell, dtype=float),
        tuple(labels),
        np.asarray(frac, dtype=float),
        (None,) * len(labels),
        species,
        SourceInfo(nat=len(labels)),
    )
