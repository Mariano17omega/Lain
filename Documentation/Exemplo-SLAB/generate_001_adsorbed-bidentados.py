#!/usr/bin/env python3
"""Estágio 3 (BIDENTADO) — metilmercúrio adsorvido na supercélula 2x1x1 (001)
JÁ RELAXADA (scf-kaolinite-slab-001-2x1x1.in), no caso em que o único Hg faz
PONTE entre DOIS átomos de O de superfície (complexação bidentada do artigo,
distinta do monodentado de generate_001_adsorbed.py, que põe o Hg ontop de um
único O).

As duplas de O são definidas em PAIRS abaixo (sem argumento de terminal).
Cada rótulo é resolvido via `qe_slab_candidates.frac_for_labels` contra a
janela de superfície de `candidatos-001.md` (gere o relatório antes com
`python generate_001_candidates.py`) — aceita tanto o rótulo representante de
cada grupo simétrico (ex.: 'O42', a linha do relatório) quanto outro membro
do mesmo grupo (ex.: 'O43', coluna "índices equivalentes" de O42). O script
resolve os rótulos às coordenadas e posiciona o H3CHg (Hg-down) acima do PONTO
MÉDIO dos dois O SEM remover nenhum átomo da superfície (REMOVE_ANCHOR_H=False
— bidentado: o Hg faz ponte entre os dois O, não substitui prótons). Emite uma
entrada `relax` (célula fixa) por dupla em
surface_with_methylmercury/001/O<i>-O<j>/. Rode depois que o Estágio 2 tiver
sido relaxado na supercélula.

Uso:
    python generate_001_adsorbed-bidentados.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from qe_slab_common import ROOT
from qe_slab_candidates import frac_for_labels
from qe_slab_adsorb import generate_adsorbed_bidentate

# ---- parâmetros ajustáveis ----
SCF_DIR = ROOT / "scfs"
SLAB_2X1X1_REF = SCF_DIR / "scf-kaolinite-slab-001-2x1x1.in"   # supercélula (001) já relaxada (Estágio 2)
KAOLINITE_REF = SCF_DIR / "scf-kaolinite.in"    # template de coordenação p/ get_surface_sites
MOLECULE_REF = SCF_DIR / "scf-H3CHg.in"
VACUUM_MIN = 10.0       # Å — mínimo de vácuo (verificação de leitura; a caixa NÃO é modificada)
ADS_DISTANCE = 2.0      # Å — distância padrão de posicionamento de adsorbato (pymatgen)
ASF_HEIGHT = 1.5        # Å — janela de átomos de superfície p/ AdsorbateSiteFinder
HEIGHT_WINDOW = 1.5     # Å — janela de altura da enumeração de candidatos (= candidatos-001.md)
SITE_ATOM_TOL = 0.5     # Å — tolerância p/ casar cada O pedido com um átomo real do slab
BOND_SCALE = 1.15       # tolerância sobre soma dos raios covalentes (if_pos / hidroxila)
H_CLEARANCE = 1.9       # Å — folga mínima Hg...H / CH3-slab (só reportada)
SITE_SYMBOLS = ("O",)   # espécies candidatas — Hg ancora em O (= candidatos-001.md)
REMOVE_ANCHOR_H = True # bidentado: Remove dois átomo H da superfície;
                        # o Hg faz ponte acima do ponto médio dos dois O
ADS_DIR = "surface_with_methylmercury"

# Duplas de O (rótulos = símbolo + índice 0-based do pymatgen;
# QE/VESTA numeram a partir de 1: "Atom N" no QE → label O(N-1) no script)
# QE Atom43-Atom50 → O42-O49 | QE Atom43-Atom46 → O42-O45
# QE Atom46-Atom44 → O45-O43 | QE Atom44-Atom50 → O43-O49
PAIRS = [
    ("O42", "O49"),
    ("O42", "O45"),
    ("O45", "O43"),
    ("O43", "O49"),
]
# --------------------------------

if __name__ == "__main__":
    if not SLAB_2X1X1_REF.exists():
        sys.exit(f"referência ausente: {SLAB_2X1X1_REF.name} — relaxe a "
                 "supercélula 2x1x1 (001) do Estágio 2 no QE e salve o scf "
                 "com a geometria relaxada nesse caminho antes de rodar.")

    for lab1, lab2 in PAIRS:
        print(f"== dupla {lab1}-{lab2} ==")
        try:
            frac1, frac2 = frac_for_labels(
                (0, 0, 1),
                slab_2x1x1_ref=SLAB_2X1X1_REF,
                labels=(lab1, lab2),
                height_window=HEIGHT_WINDOW,
                site_symbols=SITE_SYMBOLS,
            )
        except ValueError as err:
            sys.exit(str(err))

        generate_adsorbed_bidentate(
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
            site_atom_1=tuple(frac1),
            site_atom_2=tuple(frac2),
            label=None,             # dir automático O<i>-O<j> (índices dos O casados)
            remove_anchor_h=REMOVE_ANCHOR_H,
        )
