import os
import pathlib
import re
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt

###############################################################################
# Configuração
###############################################################################
BASE = pathlib.Path(__file__).resolve().parent
BANDS_DIR = BASE / 'bands-010-mehg-O2'            # band.gnu, points.txt, scf.out
PDOS_DIR = BASE / 'DOS-surface_MeHg'           # scf.out, orbitals/
ORB_DIR = PDOS_DIR / 'orbitals'
OUT_PATH = BASE / 'bands_pdos_ilita-010_mehg-O2.png'

# Deslocamento da legenda (fração do painel PDOS): dx > 0 direita, dy > 0 cima
LEGEND_DX, LEGEND_DY = 0.0, 0.1

def read_fermi(scf_path):
    """Última E_Fermi (eV) do scf.out."""
    with open(scf_path, errors='ignore') as fh:
        return [float(m.group(1)) for line in fh
                if (m := re.search(r'the Fermi energy is\s+([-\d.]+)\s+ev', line, re.I))][-1]

# Cada conjunto é deslocado pelo seu próprio E_Fermi
FermiEnergy = read_fermi(BANDS_DIR / 'scf.out')   # bandas
FermiPdos = read_fermi(PDOS_DIR / 'scf.out')      # PDOS
print(f'E_Fermi bandas = {FermiEnergy:.4f} eV   E_Fermi PDOS = {FermiPdos:.4f} eV')

# energias plotadas = E - E_Fermi (eV)
E_min, E_max = -2.0, 8.0       # janela de energia (eixo Y compartilhado)

# Rótulos dos pontos de alta simetria (mesmo caminho de plot_bandas.ipynb)
labels =  ['Y',r'$\Gamma$','Z', r'$\Gamma$', 'T2'] 

# ── Mapeamento fixo átomo → cor ──────────────────────────────────────────────
# (mesmo esquema de 2_DOS-surface_Pure/plot_pdos-no_HCHg.py)
ATOM_COLORS = {
    'Al': '#E41A1C',
    'C':  '#377EB8',
    'H':  '#4DAF4A',
    'Hg': '#FF7F00',
    'K':  '#984EA3',
    'O':  '#228B22',
    'Si': '#F781BF',
}

COLORS_FALLBACK = [
    '#000000',
    '#00CED1',
    '#FFD700',
    '#8B0000',
    '#1E90FF',
    '#228B22',
    '#FF4500',
    '#9400D3',
    '#8FBC8F',
    '#708090',
    '#DC143C',
    '#20B2AA',
    '#DAA520',
]

###############################################################################
# 1. Carregar bandas  (band.gnu: col0 = x no caminho, col1 = E em eV)
###############################################################################
eixo = np.loadtxt(BANDS_DIR / 'points.txt')          # posições-x dos pontos de simetria
z = np.loadtxt(BANDS_DIR / 'band.gnu')

x = np.unique(z[:, 0])                                # x únicos ao longo do caminho
bndl = len(z[z[:, 0] == x[1]])                        # número de bandas

bands = [np.zeros([len(x), 2]) for _ in range(bndl)]
for i in range(len(x)):
    sel = z[z[:, 0] == x[i]]                          # energias para um dado x
    for j in range(bndl):
        bands[j][i][0] = x[i]
        bands[j][i][1] = sel[j][1] - FermiEnergy

# Gap de energia: maior intervalo sem estados dentro da janela visível.
# (Robusto: identifica o topo da valência e o fundo da condução sem hardcode.)
allE = np.sort(z[:, 1] - FermiEnergy)
win = allE[(allE > E_min) & (allE < E_max)]
ig = int(np.argmax(np.diff(win)))
vbm, cbm = win[ig], win[ig + 1]
gap = cbm - vbm
xv = z[np.argmin(np.abs(z[:, 1] - FermiEnergy - vbm)), 0]   # k do VBM
xc = z[np.argmin(np.abs(z[:, 1] - FermiEnergy - cbm)), 0]   # k do CBM
gap_tipo = 'direto' if abs(xv - xc) < 1e-3 else 'indireto'
print(f'VBM={vbm:.3f} eV  CBM={cbm:.3f} eV  Gap={gap:.3f} eV ({gap_tipo})')

###############################################################################
# 2. Carregar PDOS por elemento  (soma das componentes m -> ldos do orbital)
###############################################################################
files = sorted(
    str(ORB_DIR / f)
    for f in os.listdir(ORB_DIR)
    if '.pdos_atm#' in f and 'wfc#' in f
)

element_pdos = defaultdict(lambda: None)
energy_axis = None

for filepath in files:
    fname = os.path.basename(filepath)
    try:
        atom_label = fname.split('.pdos_atm#')[1].split('(')[1].split(')')[0]
    except IndexError:
        print(f"[WARN] Nome mal formatado: {fname}")
        continue

    data = np.loadtxt(filepath)
    energy = data[:, 0] - FermiPdos
    total = np.sum(data[:, 2:], axis=1)

    if energy_axis is None:
        energy_axis = energy
    elif not np.allclose(energy_axis, energy):
        print(f"[ERROR] Eixos de energia inconsistentes em {filepath}")
        continue

    if element_pdos[atom_label] is None:
        element_pdos[atom_label] = total
    else:
        element_pdos[atom_label] += total

if not element_pdos:
    raise RuntimeError('Nenhum arquivo PDOS válido foi lido.')

total_dos = sum(element_pdos.values())

###############################################################################
# 2b. Cor fixa por elemento (independe de quais átomos existem na estrutura)
###############################################################################
def assign_colors(elements):
    """Elemento conhecido -> ATOM_COLORS; desconhecido -> COLORS_FALLBACK em ordem."""
    colors, n_fallback = {}, 0
    for element in sorted(elements):
        if element in ATOM_COLORS:
            colors[element] = ATOM_COLORS[element]
        else:
            colors[element] = COLORS_FALLBACK[n_fallback % len(COLORS_FALLBACK)]
            n_fallback += 1
    return colors

element_color = assign_colors(element_pdos.keys())

###############################################################################
# 3. Figura combinada: bandas (esquerda) + PDOS rotacionada 90° (direita)
###############################################################################
fig, (ax_b, ax_d) = plt.subplots(
    1, 2, sharey=True, figsize=(10, 6),
    gridspec_kw={'width_ratios': [3, 1], 'wspace': 0.05},
)

# ---- Painel das bandas -----------------------------------------------------
for b in bands:
    ax_b.plot(b[:, 0], b[:, 1], color="#050505", linewidth=1.0)

ax_b.set_xticks(eixo)
ax_b.set_xticklabels(labels)
ax_b.set_xlim(0.0, eixo[-1])
ax_b.set_ylim(E_min, E_max)
ax_b.set_ylabel('Energy (eV)', fontsize=16)

# linhas verticais nos pontos de simetria
for e in eixo[1:-1]:
    ax_b.axvline(e, color='k', linewidth=0.7)

# nível de Fermi
ax_b.axhline(0, color='gray', linestyle='--', linewidth=0.8)

# rótulo do gap no centro do gráfico (cai dentro do gap -> não cobre bandas)
ax_b.text(eixo[-1] / 2, (vbm + cbm) / 2,
          f'$E_g$ = {gap:.2f} eV',
          #  f'$E_g$ = {gap:.2f} eV\n({gap_tipo})',
          ha='center', va='center', fontsize=14,
          bbox=dict(boxstyle='round', facecolor='white', edgecolor='black', alpha=0.9))

ax_b.yaxis.set_ticks_position('both')
ax_b.minorticks_on()
ax_b.tick_params(axis='y', which='minor', length=4, color='gray', right=False)
ax_b.tick_params(axis='y', which='major', right=False)
ax_b.tick_params(axis='both', labelsize=16)

# ---- Painel da PDOS (eixos trocados: DOS em X, energia em Y) ----------------
ax_d.plot(total_dos, energy_axis, color='black', linewidth=1.0, label='Total')
for element in sorted(element_pdos.keys()):
    ax_d.plot(element_pdos[element], energy_axis,
              color=element_color[element], linewidth=1.5, label=element)

# autoescala do eixo X (DOS) dentro da janela de energia
mask = (energy_axis >= E_min) & (energy_axis <= E_max)
xmax = 1.05 * np.max(total_dos[mask])
ax_d.set_xlim(0, xmax)

ax_d.axhline(0, color='gray', linestyle='--', linewidth=0.8)
ax_d.set_xlabel('DOS (states/eV)', fontsize=16)
ax_d.tick_params(axis='x', labelsize=14)
ax_d.tick_params(axis='y', labelleft=False)
ax_d.legend(fontsize=16, loc='center right', frameon=True, framealpha=0,
            bbox_to_anchor=(1.0 + LEGEND_DX, 0.5 + LEGEND_DY),
            bbox_transform=ax_d.transAxes, borderaxespad=0.5)

plt.savefig(OUT_PATH, dpi=300, bbox_inches='tight')
print(f'PNG salvo: {OUT_PATH}')
plt.show()
