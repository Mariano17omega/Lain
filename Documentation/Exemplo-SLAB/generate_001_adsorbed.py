#!/usr/bin/env python3
"""Estágio 3 — metilmercúrio adsorvido na supercélula 2x1x1 (001) JÁ RELAXADA
(scf-kaolinite-slab-001-2x1x1.in): Hg-down, ontop de cada átomo de O de
superfície listado em LABELS abaixo (rótulos de candidatos-001.md — gere o
relatório antes com `python generate_001_candidates.py`; aceita tanto o
rótulo representante de cada grupo simétrico quanto outro membro do mesmo
grupo, ver docstring de `qe_slab_candidates.frac_for_labels`). Antes de
posicionar a molécula, o H da hidroxila do O âncora é removido
(desprotonação — o Hg substitui o próton; só no (001), ver
REMOVE_ANCHOR_H). Emite uma entrada `relax` (célula fixa) por átomo de
LABELS em surface_with_methylmercury/001/<label>/. Rode depois que o
Estágio 2 tiver sido relaxado na supercélula."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from qe_slab_common import ROOT
from qe_slab_candidates import frac_for_labels
from qe_slab_adsorb import generate_adsorbed

# ---- parâmetros ajustáveis ----
SCF_DIR = ROOT / "scfs"
SLAB_2X1X1_REF = SCF_DIR / "scf-kaolinite-slab-001-2x1x1.in"   # supercélula (001) já relaxada (Estágio 2)
KAOLINITE_REF = SCF_DIR / "scf-kaolinite.in"    # template de coordenação p/ get_surface_sites
MOLECULE_REF = SCF_DIR / "scf-H3CHg.in"
VACUUM_MIN = 10.5       # Å
ADS_DISTANCE = 2.0      # Å — distância padrão de posicionamento de adsorbato (pymatgen)
ASF_HEIGHT = 1.5        # Å — janela de átomos de superfície p/ AdsorbateSiteFinder
HEIGHT_WINDOW = 1.5     # Å — janela de altura da enumeração de candidatos (mesmo valor)
H_CLEARANCE = 1.9       # Å — folga mínima Hg...H / CH3-slab (só reportada)
SITE_ATOM_TOL = 0.5     # Å — tolerância p/ casar site_atom com um átomo real do slab
BOND_SCALE = 1.15       # tolerância sobre soma dos raios covalentes (if_pos)
SITE_SYMBOLS = ("O",)   # espécies candidatas — Hg ancora em O (artigo)
REMOVE_ANCHOR_H = True  # remove o H da hidroxila do O âncora antes de adsorver
                        # (desprotonação: o Hg substitui o próton — só no (001))
ADS_DIR = "surface_with_methylmercury"

# Átomos de O a processar (rótulos = símbolo + índice 0-based do pymatgen;
# QE/VESTA numeram a partir de 1: "Atom 43 O42" no QE → índice 42 → label "O42")
LABELS = ("O42", "O49")
# --------------------------------

if __name__ == "__main__":
    if not SLAB_2X1X1_REF.exists():
        sys.exit(f"referência ausente: {SLAB_2X1X1_REF.name} — relaxe a "
                 "supercélula 2x1x1 (001) do Estágio 2 no QE e salve o scf "
                 "com a geometria relaxada nesse caminho antes de rodar.")

    try:
        fracs = frac_for_labels(
            (0, 0, 1),
            slab_2x1x1_ref=SLAB_2X1X1_REF,
            labels=LABELS,
            height_window=HEIGHT_WINDOW,
            site_symbols=SITE_SYMBOLS,
        )
    except ValueError as err:
        sys.exit(str(err))

    for label, frac in zip(LABELS, fracs):
        generate_adsorbed(
            miller=(0, 0, 1),
            slab_2x1x1_ref=SLAB_2X1X1_REF,
            kaolinite_ref=KAOLINITE_REF,
            molecule_ref=MOLECULE_REF,
            vacuum_min=VACUUM_MIN,
            ads_distance=ADS_DISTANCE,
            asf_height=ASF_HEIGHT,
            h_clearance=H_CLEARANCE,
            site_atom_tol=SITE_ATOM_TOL,
            bond_scale=BOND_SCALE,
            out_dir=ROOT / ADS_DIR / "001",
            site_atom=frac,
            site_label=label,
            remove_anchor_h=REMOVE_ANCHOR_H,
        )
