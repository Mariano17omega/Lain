#!/usr/bin/env python3
"""Estágio 3 — metilmercúrio adsorvido na supercélula 2x1x1 (010) JÁ RELAXADA
(scf-kaolinite-slab-010-2x1x1.in): Hg-down, ontop de cada átomo de O de
superfície não-equivalente (candidatos de qe_slab_candidates, os mesmos de
candidatos-010.md). Emite uma entrada `relax` (célula fixa) por candidato
em surface_with_methylmercury/010/<label>/. Rode depois que o Estágio 2 tiver
sido relaxado na supercélula."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from qe_slab_common import ROOT
from qe_slab_adsorb import generate_adsorbed_candidates

# ---- parâmetros ajustáveis ----
SCF_DIR = ROOT / "scfs"
SLAB_2X1X1_REF = SCF_DIR / "scf-kaolinite-slab-010-2x1x1.in"   # supercélula (010) já relaxada (Estágio 2)
KAOLINITE_REF = SCF_DIR / "scf-kaolinite.in"    # template de coordenação p/ get_surface_sites
MOLECULE_REF = SCF_DIR / "scf-H3CHg.in"
VACUUM_MIN = 10.5       # Å
ADS_DISTANCE = 2.0      # Å — distância padrão de posicionamento de adsorbato (pymatgen)
ASF_HEIGHT = 1.5        # Å — janela de átomos de superfície p/ AdsorbateSiteFinder
HEIGHT_WINDOW = 1.5     # Å — janela de altura da enumeração de candidatos (mesmo valor)
SYMPREC = 1e-3          # Å — tolerância spglib p/ agrupar átomos equivalentes
H_CLEARANCE = 1.9       # Å — folga mínima Hg...H / CH3-slab (só reportada)
SITE_ATOM_TOL = 0.5     # Å — tolerância p/ casar site_atom com um átomo real do slab
BOND_SCALE = 1.15       # tolerância sobre soma dos raios covalentes (if_pos)
SITE_SYMBOLS = ("O",)   # espécies candidatas — Hg ancora em O (artigo)
ADS_DIR = "surface_with_methylmercury"
# --------------------------------

if __name__ == "__main__":
    if not SLAB_2X1X1_REF.exists():
        sys.exit(f"referência ausente: {SLAB_2X1X1_REF.name} — relaxe a "
                 "supercélula 2x1x1 (010) do Estágio 2 no QE e salve o scf "
                 "com a geometria relaxada nesse caminho antes de rodar.")
    generate_adsorbed_candidates(
        miller=(0, 1, 0),
        slab_2x1x1_ref=SLAB_2X1X1_REF,
        kaolinite_ref=KAOLINITE_REF,
        molecule_ref=MOLECULE_REF,
        vacuum_min=VACUUM_MIN,
        ads_distance=ADS_DISTANCE,
        asf_height=ASF_HEIGHT,
        height_window=HEIGHT_WINDOW,
        symprec=SYMPREC,
        h_clearance=H_CLEARANCE,
        site_atom_tol=SITE_ATOM_TOL,
        bond_scale=BOND_SCALE,
        site_symbols=SITE_SYMBOLS,
        out_dir=ROOT / ADS_DIR / "010",
    )
