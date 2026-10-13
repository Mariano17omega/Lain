#!/usr/bin/env python3
"""Estágio 2 (010) — supercélula 2x1x1 (dobra o eixo 0, no plano) construída
inteiramente a partir da superfície (010) JÁ RELAXADA, emitida como sua
própria célula vc-relax (mesmo padrão do Estágio 1: só a célula no plano
relaxa, camada da base fixa). Rode depois que o vc-relax do Estágio 1
(generate_surface.py) tiver convergido.

Geometria e todo parâmetro físico/numérico (cutoffs, pseudopotenciais,
massas, k-mesh, ...) vêm de `scf-kaolinite-slab-010.in` (em scfs/) —
nada vem mais de scf-kaolinite.in aqui, que é Estágio 1 apenas. Depois que o
pw.x convergir o vc-relax, produza esse arquivo (mesmo estilo/namelists de
scf-kaolinite.in, mas com a geometria relaxada) e então rode este script.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from qe_slab_common import ROOT
from qe_slab_supercell import generate_supercell

# ---- parâmetros ajustáveis ----
SCF_DIR = ROOT / "scfs"
SLAB_REF = SCF_DIR / "scf-kaolinite-slab-010.in"   # superfície (010) já relaxada (Estágio 1)
VACUUM_MIN = 10.5      # Å
SUPERCELL_MULT = 2     # 2x1x1 — teto computacional rígido (CLAUDE.md)
BOND_SCALE = 1.15      # tolerância sobre soma dos raios covalentes (if_pos)
PURE_DIR = "surface_pure"
# --------------------------------

if __name__ == "__main__":
    generate_supercell(
        miller=(0, 1, 0),
        slab_ref=SLAB_REF,
        out_dir=ROOT / PURE_DIR / "010" / "supercell",
        vacuum_min=VACUUM_MIN,
        supercell_mult=SUPERCELL_MULT,
        bond_scale=BOND_SCALE,
    )
