#!/usr/bin/env python3
"""Busca de sítios de superfície não-equivalentes na supercélula 2x1x1 (001)
JÁ RELAXADA (scf-kaolinite-slab-001-2x1x1.in). Escreve candidatos-001.md com
label, coordenada fracionária e vizinhos de cada átomo de superfície
simetricamente distinto — coordenadas prontas para `site_atom=(...)` em
generate_001_adsorbed.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from qe_slab_candidates import generate_candidates
from qe_slab_common import ROOT

# ---- parâmetros ajustáveis ----
SCF_DIR = ROOT / "scfs"
SLAB_2X1X1_REF = SCF_DIR / "scf-kaolinite-slab-001-2x1x1.in"   # supercélula (001) já relaxada (Estágio 2)
HEIGHT_WINDOW = 1.5  # Å — janela de átomos de superfície ao longo de +z (mesmo valor do ASF_HEIGHT do Estágio 3;
                     # get_surface_sites() não é usável aqui, ver docstring de qe_slab_candidates.py)
SYMPREC = 1e-3       # Å — tolerância spglib p/ agrupar átomos simetricamente equivalentes
BOND_SCALE = 1.15    # tolerância sobre soma dos raios covalentes (mesmo valor dos outros estágios)
SITE_SYMBOLS = ("O",)  # espécies candidatas — Hg ancora em O (H de hidroxila não é sítio)
OUT_PATH = ROOT / "candidatos-001.md"
# --------------------------------

if __name__ == "__main__":
    generate_candidates(
        miller=(0, 0, 1),
        slab_2x1x1_ref=SLAB_2X1X1_REF,
        height_window=HEIGHT_WINDOW,
        symprec=SYMPREC,
        bond_scale=BOND_SCALE,
        site_symbols=SITE_SYMBOLS,
        out_path=OUT_PATH,
    )
