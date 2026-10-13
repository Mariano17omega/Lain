#!/usr/bin/env python3
"""Estágio 1 — superfícies puras de caulinita (001) e (010) construídas
aumentando só a altura da caixa de simulação: a célula bulk de
scf-kaolinite.in com o vetor de rede fora do plano multiplicado por um
escalar (ainda sem supercélula). Cada superfície é uma célula vc-relax de
34 átomos cujo vácuo reservado já comporta a molécula de metilmercúrio
(ideia.md §3). Escreve surface_pure/001/ e surface_pure/010/.

Rode isso primeiro; relaxe as duas entradas com pw.x, depois produza
scf-kaolinite-slab-001.in / -010.in em scfs/ (mesmo estilo de
scf-kaolinite.in, mas com a geometria relaxada) e rode
generate_001_supercell.py / generate_010_supercell.py para a supercélula
2x1x1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from qe_slab_common import ROOT
from qe_slab_surface import generate_surface

# ---- parâmetros ajustáveis ----
SCF_DIR = ROOT / "scfs"
KAOLINITE_REF = SCF_DIR / "scf-kaolinite.in"
MOLECULE_REF = SCF_DIR / "scf-H3CHg.in"
VACUUM_MIN = 10.5      # Å — mínimo de vácuo (teste de convergência de caixa do H3CHg, ideia.md)
ADS_DISTANCE = 2.0     # Å — distância padrão de posicionamento de adsorbato (pymatgen), tornada explícita
BOND_SCALE = 1.15      # tolerância sobre soma dos raios covalentes (cura de O-H, poliedros de borda, if_pos)
PURE_DIR = "surface_pure"
# --------------------------------

if __name__ == "__main__":
    for miller in [(0, 0, 1), (0, 1, 0)]:
        mstr = "".join(str(x) for x in miller)
        generate_surface(
            miller=miller,
            kaolinite_ref=KAOLINITE_REF,
            molecule_ref=MOLECULE_REF,
            vacuum_min=VACUUM_MIN,
            ads_distance=ADS_DISTANCE,
            bond_scale=BOND_SCALE,
            out_dir=ROOT / PURE_DIR / mstr,
        )
