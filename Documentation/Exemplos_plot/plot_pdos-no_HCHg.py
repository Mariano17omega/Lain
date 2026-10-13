import os
import re
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

# ── Caminhos ──────────────────────────────────────────────────────────────────
script_path = os.path.abspath(__file__)
PDOS_DIR    = os.path.dirname(script_path)
SCF_OUT     = os.path.join(PDOS_DIR, 'scf.out')

subdir      = 'orbitals'
subdir_path = os.path.join(PDOS_DIR, subdir)

# ── Config gap ────────────────────────────────────────────────────────────────
DOS_GAP_TOL        = 1.0      # states/eV: DOS < tol = "vazio"
DOS_GAP_WINDOW     = (-7.0, 6.0)  # eV (eixo deslocado)
DOS_GAP_MINW       = 0.05     # eV: largura mínima para contar como gap

# ── Mapeamento fixo atomo → cor ──────────────────────────────────────────────
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

# ── Átomos a excluir ──────────────────────────────────────────────────────────
EXCLUDE_ATOMS = set()
# EXCLUDE_ATOMS = {'H', 'C', 'Hg'}

# ── Leitura do scf.out ────────────────────────────────────────────────────────
def read_scf_quantities(scf_path):
    fermi = None
    homo = None
    lumo = None

    re_fermi = re.compile(r'the Fermi energy is\s+([-\d.]+)\s+ev', re.IGNORECASE)
    re_hl    = re.compile(
        r'highest occupied, lowest unoccupied level \(eV\):\s*([-\d.]+)\s+([-\d.]+)',
        re.IGNORECASE
    )

    with open(scf_path, 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            m = re_fermi.search(line)
            if m:
                fermi = float(m.group(1))

            m = re_hl.search(line)
            if m:
                homo = float(m.group(1))
                lumo = float(m.group(2))

    if fermi is None:
        raise RuntimeError(f'Energia de Fermi não encontrada em {scf_path}')

    return fermi, homo, lumo


FermiEnergy, HOMO, LUMO = read_scf_quantities(SCF_OUT)
print(f'E_Fermi = {FermiEnergy:.6f} eV')

# ── Gap por autovalores (se disponível) ───────────────────────────────────────
gap_info = None
gap_source = None

if (HOMO is not None) and (LUMO is not None):
    vbm = HOMO - FermiEnergy
    cbm = LUMO - FermiEnergy
    gap_info = (vbm, cbm)
    gap_source = 'eigenvalues'
    print(f'HOMO = {HOMO:.6f} eV')
    print(f'LUMO = {LUMO:.6f} eV')
    print(f'Gap por autovalores = {cbm - vbm:.6f} eV')
else:
    print('[INFO] HOMO/LUMO não encontrados no scf.out (use fixed + nbnd adequado). Usando gap por DOS.')

# ── Leitura dos arquivos PDOS ─────────────────────────────────────────────────
files = sorted([
    os.path.join(subdir_path, f)
    for f in os.listdir(subdir_path)
    if '.pdos_atm#' in f and 'wfc#' in f
])

element_pdos = defaultdict(lambda: None)
energy_axis  = None

for filepath in files:
    fname = os.path.basename(filepath)

    try:
        atom_label = fname.split('.pdos_atm#')[1].split('(')[1].split(')')[0]
    except IndexError:
        print(f'[WARN] Nome mal formatado: {fname}')
        continue

    if atom_label in EXCLUDE_ATOMS:
        continue

    data = np.loadtxt(filepath)
    energy = data[:, 0] - FermiEnergy
    pdos = data[:, 2:]
    total = np.sum(pdos, axis=1)

    if energy_axis is None:
        energy_axis = energy
    elif not np.allclose(energy_axis, energy):
        print(f'[ERROR] Eixos de energia inconsistentes em {filepath}')
        continue

    if element_pdos[atom_label] is None:
        element_pdos[atom_label] = total
    else:
        element_pdos[atom_label] += total

if not element_pdos:
    raise RuntimeError('Nenhum arquivo PDOS válido foi lido.')

total_dos = np.sum(np.vstack(list(element_pdos.values())), axis=0)

# ── Gap aproximado por DOS (fallback) ─────────────────────────────────────────
def detect_gap_from_dos(energy, dos, tol=DOS_GAP_TOL,
                        window=DOS_GAP_WINDOW, minw=DOS_GAP_MINW):
    lo_w, hi_w = window
    vazio = dos < tol
    melhor = None
    inicio = None

    def testa_intervalo(i0, i1):
        lo, hi = energy[i0], energy[i1]
        largura = hi - lo
        centro = 0.5 * (lo + hi)
        if largura >= minw and lo_w <= centro <= hi_w:
            return (lo, hi)
        return None

    for i, is_vazio in enumerate(vazio):
        if is_vazio and inicio is None:
            inicio = i
        elif not is_vazio and inicio is not None:
            candidato = testa_intervalo(inicio, i - 1)
            if candidato and (melhor is None or (candidato[1] - candidato[0]) > (melhor[1] - melhor[0])):
                melhor = candidato
            inicio = None

    if inicio is not None:
        candidato = testa_intervalo(inicio, len(energy) - 1)
        if candidato and (melhor is None or (candidato[1] - candidato[0]) > (melhor[1] - melhor[0])):
            melhor = candidato

    return melhor

if gap_info is None:
    dos_gap = detect_gap_from_dos(energy_axis, total_dos)
    if dos_gap is not None:
        gap_info = dos_gap
        gap_source = 'dos'
        print(f'[WARN] Gap por DOS: {gap_info[1] - gap_info[0]:.6f} eV')
    else:
        print('[WARN] Gap não detectado em DOS.')
        gap_source = 'none'

# ── Função auxiliar: cor fixa por átomo ───────────────────────────────────────
def get_atom_color(element, fallback_state={'idx': 0}):
    if element in ATOM_COLORS:
        return ATOM_COLORS[element]
    color = COLORS_FALLBACK[fallback_state['idx'] % len(COLORS_FALLBACK)]
    fallback_state['idx'] += 1
    return color

# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(e_min, e_max, show_gap, out_name):
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(
        energy_axis, total_dos,
        label='Total DOS',
        color='#000000',
        linewidth=1.2,
        linestyle='-',
        zorder=2
    )

    for element in sorted(element_pdos.keys()):
        color = get_atom_color(element)
        ax.plot(
            energy_axis,
            element_pdos[element],
            label=element,
            color=color,
            linewidth=2.0,
            zorder=3
        )

    if show_gap and gap_info is not None:
        vbm, cbm = gap_info
        ax.axvspan(
            vbm, cbm,
            color='#cccccc',
            alpha=0.35,
            zorder=1,
            label=f'Gap = {cbm - vbm:.2f} eV'
        )
        ax.axvline(vbm, color='#666666', linestyle=':', linewidth=1.0, zorder=4)
        ax.axvline(cbm, color='#666666', linestyle=':', linewidth=1.0, zorder=4)

    ax.axvline(
        0.0,
        color='#444444',
        linestyle='--',
        linewidth=1.0,
        label=r'$E_F$',
        zorder=4
    )

    ax.set_xlabel('Energy - $E_F$ (eV)', fontsize=16)
    ax.set_ylabel('Density of States (states/eV)', fontsize=16)
    ax.set_xlim(e_min, e_max)

    mask = (energy_axis >= e_min) & (energy_axis <= e_max)
    if np.any(mask):
        ymax = max([total_dos[mask].max()] + [v[mask].max() for v in element_pdos.values()])
        ax.set_ylim(0, 1.05 * ymax if ymax > 0 else 1.0)
    else:
        ax.set_ylim(0, 1.0)

    ax.tick_params(axis='both', which='major', labelsize=15)
    ax.tick_params(axis='both', which='minor', length=3)
    ax.minorticks_on()

    title_source = {
        'eigenvalues': 'Gap from eigenvalues (HOMO/LUMO)',
        'dos': 'Gap from DOS (fallback)',
        'none': 'Gap unavailable'
    }.get(gap_source, 'Gap')

#    ax.set_title(title_source, fontsize=14)

    leg = ax.legend(
        fontsize=14,
        loc='upper right',
        framealpha=0.85,
        edgecolor='#cccccc',
        handlelength=3.0,
        handleheight=1.2
    )
    for lh in leg.legend_handles:
        lh.set_linewidth(2.5)

    fig.tight_layout()
    out_path = os.path.join(PDOS_DIR, out_name)
    fig.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f'PNG salvo: {out_path}')

# ── Geração ───────────────────────────────────────────────────────────────────
make_plot(-7.0, 5.0,  show_gap=True,  out_name=f'{subdir}_PDOS_gap.png')
make_plot(-7.0, 5.0,  show_gap=False, out_name=f'{subdir}_PDOS_pure.png')
make_plot(-20.0, 10.0, show_gap=False, out_name=f'{subdir}_PDOS_wide.png')