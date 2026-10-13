"""
qe_slab_adsorb.py — Estágio 3: metilmercúrio (H3CHg) adsorvido na supercélula
2x1x1 JÁ RELAXADA da superfície (scf-kaolinite-slab-<hkl>-2x1x1.in), emitido
como entrada de relaxação iônica de célula fixa (`calculation='relax'` —
decisão do usuário). Rode depois que a supercélula do Estágio 2 tiver sido
relaxada pelo usuário.

Um input por átomo de superfície candidato: a enumeração de sítios
não-equivalentes vem de qe_slab_candidates.find_candidates (janela de altura +
spglib), filtrada por espécie (padrão: só O — o Hg ancora em O, como no artigo
de referência). Para cada candidato a molécula é posta ontop do átomo via
AdsorbateSiteFinder.find_adsorption_sites(symm_reduce=0), que devolve um sítio
ontop exatamente acima de cada átomo de superfície; a posição é um chute
inicial que o relax refina.

Opcionalmente (`remove_anchor_h`, ligado só no (001) — decisão do usuário) o
único H da hidroxila do O âncora é removido antes da adsorção, modelando a
desprotonação superfície–O–H + CH3Hg⁺ → superfície–O–HgCH₃ + H⁺ (o Hg
substitui o próton); a célula permanece neutra (ver reporte/README).

Geometria e todo parâmetro físico/numérico da superfície vêm de
`slab_2x1x1_ref`; a molécula e suas espécies (Hg, C) vêm de `molecule_ref`.
A janela de altura (mesmo critério de find_candidates) é o conjunto
autoritativo de superfície; `Slab.get_surface_sites()` (API preferida do brief)
é tentada mas só rotula o método quando o reproduz — para este sistema ela
devolve vazio (CN Voronoi ponderado dos átomos de topo sobe em vez de cair —
medido, ver docstring de qe_slab_candidates.py) ou, uma vez desprotonada a
hidroxila âncora, um subconjunto parcial espúrio; nunca sobrepõe a aceitação.
"""

from pathlib import Path

import numpy as np
from ase.data import atomic_numbers, covalent_radii
from pymatgen.analysis.adsorption import AdsorbateSiteFinder
from pymatgen.core import Molecule
from pymatgen.core.surface import Slab
from pymatgen.io.ase import AseAtomsAdaptor

from qe_slab_candidates import find_candidates, top_surface_indices
from qe_slab_common import (
    ROOT,
    assemble_namelists,
    assemble_species,
    build_molecule,
    count_by_species,
    fixed_indices,
    geometry_checks,
    load_ref,
    write_qe_input,
    write_report_md,
)


# ------------------------------------------------------------------ orientação

def rot_from_z(v):
    """Matriz de rotação que mapeia +z sobre o vetor unitário v (Rodrigues)."""
    v = np.asarray(v, dtype=float)
    v = v / np.linalg.norm(v)
    z = np.array([0.0, 0.0, 1.0])
    k = np.cross(z, v)
    s = np.linalg.norm(k)
    c = float(np.dot(z, v))
    if s < 1e-8:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / s**2)


def slab_from_ref(struct, miller, bulk_ref):
    """Embrulha uma Structure lida da referência 2x1x1 relaxada como um
    pymatgen Slab, para que as APIs de pymatgen.analysis.adsorption
    (Slab.get_surface_sites e AdsorbateSiteFinder) funcionem. A referência do
    Estágio 2 já está escrita com a normal da superfície em +z (c ao longo de
    z, vácuo em z), então não reorienta a rede (reorient_lattice=False) — a
    orientação canônica de slab é preservada exatamente.

    `bulk_ref` (caulinita bulk de scf-kaolinite.in) é passado como
    oriented_unit_cell: Slab.get_surface_sites() o usa *só* como template de
    coordenação (conjunto de números de coordenação por elemento) para
    detectar átomos de superfície sub-coordenados. Nenhum parâmetro físico vem
    daqui — célula, cutoffs, pseudos e k-mesh continuam todos vindo da
    referência 2x1x1."""
    return Slab(
        struct.lattice,
        struct.species,
        struct.frac_coords,
        miller_index=tuple(miller),
        oriented_unit_cell=bulk_ref,
        shift=0.0,
        scale_factor=np.eye(3, dtype=int),
        reorient_lattice=False,
    )


# ---------------------------------------------------------------- desprotonação

def anchor_hydrogen(struct, site_atom, bond_scale, site_atom_tol):
    """Índice do H da hidroxila do átomo âncora, para desprotonar o O de
    superfície antes da adsorção (só (001) — decisão do usuário: o Hg
    substitui o próton da hidroxila, superfície–O–H + CH3Hg⁺ →
    superfície–O–HgCH₃ + H⁺).

    Casa `site_atom` (coord fracionária) ao átomo do slab mais próximo pelo
    mesmo critério de `adsorb()` (imagem mínima via lattice.get_all_distances,
    tolerância `site_atom_tol`); erra se o átomo casado não for O. Conta os H
    ligados a esse O (distância < bond_scale*(rO+rH), mesmo critério de ligação
    do resto do código). Se o número de H ligados != 1, levanta RuntimeError
    (o sítio não é uma hidroxila de 1 H — decisão do usuário: abortar em vez de
    adivinhar). Retorna (h_index, o_index)."""
    lat = struct.lattice
    slab_frac = np.array([s.frac_coords for s in struct])
    symbols = np.array([s.specie.symbol for s in struct])

    target = np.array(site_atom, dtype=float)
    if target.shape != (3,):
        raise ValueError(
            f"site_atom must be a 3-tuple of fractional coords, got {site_atom!r}")
    d = lat.get_all_distances([target], slab_frac)[0]
    o_idx = int(np.argmin(d))
    if d[o_idx] > site_atom_tol:
        raise ValueError(
            f"site_atom {tuple(target)} is {d[o_idx]:.3f} Å from the nearest "
            f"slab atom (#{o_idx} {symbols[o_idx]}); no atom within "
            f"{site_atom_tol} Å — check the coordinate")
    if symbols[o_idx] != "O":
        raise RuntimeError(
            f"anchor atom #{o_idx} is {symbols[o_idx]}, not O — "
            "deprotonation only applies to a surface hydroxyl O")

    cut = bond_scale * (covalent_radii[atomic_numbers["O"]]
                        + covalent_radii[atomic_numbers["H"]])
    d_o = lat.get_all_distances([slab_frac[o_idx]], slab_frac)[0]
    h_bonded = [int(i) for i in np.flatnonzero(symbols == "H") if d_o[i] < cut]
    if len(h_bonded) != 1:
        raise RuntimeError(
            f"anchor O #{o_idx} has {len(h_bonded)} bonded H "
            f"(distances {[round(float(d_o[i]), 3) for i in h_bonded]} Å), "
            "expected exactly 1 for a surface hydroxyl — cannot deprotonate; "
            "inspect the site")
    return h_bonded[0], o_idx


# ---------------------------------------------------------------- adsorção

def identify_surface_method(slab, lat, slab_frac, symbols, top_indices,
                            asf_height):
    """Rótulo do método que identificou os átomos de superfície (topo). A janela
    de altura (`top_indices`, top_surface_indices) é AUTORITATIVA;
    `Slab.get_surface_sites()` (API preferida do brief) é tentada e só creditada
    quando reproduz esse conjunto — para estes slabs devolve vazio ou um
    subconjunto espúrio (CN Voronoi ponderado sobe em vez de cair; ver
    qe_slab_candidates.py), então normalmente o rótulo cai na janela de altura.
    Só rotula; nunca sobrepõe a aceitação de átomo feita pela janela."""
    surf = slab.get_surface_sites()
    top = surf["top"] if isinstance(surf, dict) else surf
    top_sites = [e[0] if isinstance(e, (list, tuple)) else e for e in top]
    gss_indices = set()
    if top_sites:
        gss_frac = np.array([s.frac_coords for s in top_sites])
        gss_indices = set(int(i) for i in
                          np.argmin(lat.get_all_distances(gss_frac, slab_frac),
                                    axis=1))
    if gss_indices == top_indices and any(symbols[i] == "O" for i in gss_indices):
        # Só credita a API preferida quando ela reproduz o conjunto autoritativo.
        return "Slab.get_surface_sites()"
    if not gss_indices:
        return (f"height window {asf_height} Å "
                "(get_surface_sites() returned no surface site)")
    return (f"height window {asf_height} Å (get_surface_sites() returned only "
            f"{len(gss_indices)} spurious site(s), unusable for this system — "
            "see qe_slab_candidates.py)")


def match_surface_atom(lat, slab_frac, symbols, coord, top_indices,
                       site_atom_tol, which):
    """Casa `coord` (fracionária) ao átomo de slab mais próximo por imagem
    mínima (mesmo critério de adsorb()), exigindo que seja O e pertença ao
    conjunto de superfície autoritativo `top_indices`. Aborta com mensagem
    clara em vez de adivinhar (coord fora de tolerância, átomo não-O ou não de
    superfície). Retorna o índice do átomo casado."""
    target = np.asarray(coord, dtype=float)
    if target.shape != (3,):
        raise ValueError(
            f"{which} must be a 3-tuple of fractional coords, got {coord!r}")
    d = lat.get_all_distances([target], slab_frac)[0]
    idx = int(np.argmin(d))
    if d[idx] > site_atom_tol:
        raise ValueError(
            f"{which} {tuple(target)} is {d[idx]:.3f} Å from the nearest slab "
            f"atom (#{idx} {symbols[idx]} at {tuple(np.round(slab_frac[idx], 5))}); "
            f"no atom within {site_atom_tol} Å tolerance — check the coordinate")
    if symbols[idx] != "O":
        raise RuntimeError(
            f"{which} atom #{idx} is {symbols[idx]}, not O — Hg anchors on "
            "surface O (bidentate bridges two surface O)")
    if idx not in top_indices:
        raise RuntimeError(
            f"{which} atom #{idx} ({symbols[idx]}) is not a surface site — "
            "pick an exposed top O")
    return idx


def adsorb(slab, mol, site_atom, distance, asf_height, h_clearance,
           site_atom_tol):
    """Posiciona a molécula ontop do átomo de superfície `site_atom`
    (coordenada fracionária, vinda de qe_slab_candidates).

    Identificação de superfície: a janela de altura (`top_surface_indices`,
    mesmo critério que qe_slab_candidates.find_candidates usa para enumerar o
    candidato) é o conjunto AUTORITATIVO usado para aceitar o átomo pedido.
    `Slab.get_surface_sites()` (API preferida do brief) ainda é tentada, mas só
    rotula o método quando concorda com a janela de altura — nunca sobrepõe a
    aceitação. É inutilizável para estes slabs (ver docstring de
    qe_slab_candidates.py): devolve vazio no slab protonado e um conjunto
    parcial espúrio assim que a hidroxila âncora é removida (desprotonação do
    (001)). O método efetivamente usado é reportado em
    info["surface_id_method"].

    Posicionamento: AdsorbateSiteFinder.find_adsorption_sites(symm_reduce=0)
    devolve um sítio ontop exatamente acima de cada átomo de superfície; o
    ontop mais próximo em planta (x,y) do átomo escolhido é usado (snap
    medido: ~0.002 Å). O ponto é então erguido ao longo da normal até nenhum
    átomo do slab ficar mais perto do Hg que `distance` — necessário porque
    os O de topo são hidroxilas com H ereto ~1 Å acima do O, diretamente no
    caminho vertical (Hg a 2 Å do O ficaria a ~1 Å do H); o relax refina a
    aproximação. A escolha do usuário nunca é substituída por outro sítio; se
    a folga (h_clearance) falhar, isso só é reportado (clearance_ok=False),
    não contornado.
    """
    asf = AdsorbateSiteFinder(slab, height=asf_height)

    lat = slab.lattice
    slab_frac = np.array([s.frac_coords for s in slab])
    symbols = np.array([s.specie.symbol for s in slab])

    # Conjunto AUTORITATIVO de superfície = janela de altura: o mesmo critério
    # que qe_slab_candidates.find_candidates usa para enumerar o candidato, e o
    # substituto documentado de Slab.get_surface_sites() (inutilizável para
    # este sistema: CN Voronoi ponderado sobe em vez de cair — devolve vazio no
    # slab protonado e um conjunto parcial espúrio assim que a hidroxila âncora
    # é removida; ver qe_slab_candidates.py). get_surface_sites() (API preferida
    # do brief) ainda é tentada, mas só rotula o método quando concorda com a
    # janela de altura — nunca sobrepõe a aceitação do átomo pedido.
    top_indices = top_surface_indices(slab, asf_height)
    if not any(symbols[i] == "O" for i in top_indices):
        raise RuntimeError("no surface O atoms identified")

    surface_id_method = identify_surface_method(
        slab, lat, slab_frac, symbols, top_indices, asf_height)

    target_frac = np.array(site_atom, dtype=float)
    if target_frac.shape != (3,):
        raise ValueError(
            f"site_atom must be a 3-tuple of fractional coords, got {site_atom!r}")
    d = lat.get_all_distances([target_frac], slab_frac)[0]
    idx = int(np.argmin(d))
    if d[idx] > site_atom_tol:
        raise ValueError(
            f"site_atom {tuple(target_frac)} is {d[idx]:.3f} Å from the nearest "
            f"slab atom (#{idx} {symbols[idx]} at {tuple(np.round(slab_frac[idx], 5))}); "
            f"no atom within {site_atom_tol} Å tolerance — check the coordinate")
    if idx not in top_indices:
        raise RuntimeError(
            f"atom #{idx} ({symbols[idx]}) is not a surface site "
            f"({surface_id_method}) — pick an exposed atom")

    sites = asf.find_adsorption_sites(distance=distance, symm_reduce=0)
    ontop = sites.get("ontop", [])
    if not ontop:
        raise RuntimeError("find_adsorption_sites() returned no ontop candidates")
    atom_cart = lat.get_cartesian_coords(slab_frac[idx])
    chosen = min(ontop, key=lambda c: np.linalg.norm(np.asarray(c)[:2] - atom_cart[:2]))
    chosen = np.asarray(chosen, dtype=float)
    snap = float(np.linalg.norm(chosen[:2] - atom_cart[:2]))
    if snap > site_atom_tol:
        raise RuntimeError(
            f"nearest ontop site is {snap:.3f} Å (in-plane) from atom #{idx} "
            f"{symbols[idx]} — symm_reduce=0 should place one above each "
            "surface atom; check asf_height/height_window consistency")

    # Ergue o ponto ao longo de +z (normal do pipeline) até nenhum átomo do
    # slab ficar mais perto do Hg que `distance` (H de hidroxila ereto bloqueia
    # o caminho vertical acima do O âncora). Imagens 3x3 no plano cobrem a
    # periodicidade; imagens em c são vácuo.
    slab_cart = lat.get_cartesian_coords(slab_frac)
    images = np.vstack([slab_cart + i * lat.matrix[0] + j * lat.matrix[1]
                        for i in (-1, 0, 1) for j in (-1, 0, 1)])
    r2 = np.sum((images[:, :2] - chosen[:2]) ** 2, axis=1)
    near = r2 < distance**2
    z_needed = float(np.max(images[near, 2] + np.sqrt(distance**2 - r2[near])))
    lift = max(0.0, z_needed - chosen[2])
    chosen[2] += lift

    normal = getattr(asf, "mvec", slab.normal)
    mol_local = mol.cart_coords @ rot_from_z(normal).T  # âncora (Hg) na origem

    pts = np.asarray(chosen) + mol_local
    frac = np.array([lat.get_fractional_coords(p) for p in pts])
    dmat = lat.get_all_distances(frac, slab_frac)
    o_cols = symbols == "O"
    h_cols = symbols == "H"
    hg_o = float(np.sort(dmat[0][o_cols])[0])
    hg_h = float(dmat[0][h_cols].min())
    rest = float(dmat[1:].min())
    clearance_ok = hg_h >= h_clearance and rest >= h_clearance

    mol_rotated = Molecule([s.specie.symbol for s in mol], mol_local)
    ads_struct = asf.add_adsorbate(mol_rotated, chosen,
                                   translate=False, reorient=False)
    info = {
        "surface_id_method": surface_id_method,
        "surface_sites_top": len(top_indices),
        "surface_O_top": int(sum(1 for i in top_indices if symbols[i] == "O")),
        "n_ontop": len(ontop),
        "clearance_ok": clearance_ok,
        "site_cart": [round(float(x), 4) for x in chosen],
        "site_snap": round(snap, 4),
        "site_lift": round(lift, 3),
        "site_dO": round(hg_o, 3),
        "site_dH": round(hg_h, 3),
        "mol_clearance": round(rest, 3),
        "site_atom_requested": [round(float(x), 5) for x in target_frac],
        "site_atom_index": idx,
        "site_atom_symbol": str(symbols[idx]),
    }
    return ads_struct, info


# ---------------------------------------------------------------- bidentado

def adsorb_bidentate(slab, mol, site_atom_1, site_atom_2, distance, asf_height,
                     h_clearance, site_atom_tol):
    """Posiciona a molécula (Hg-down) acima do PONTO MÉDIO de dois átomos de O
    de superfície `site_atom_1`/`site_atom_2` (coordenadas fracionárias),
    modelando a complexação bidentada — o único Hg do metilmercúrio faz ponte
    entre os dois O (bridging Hg-O/Hg-O, como no artigo de referência).

    Identificação de superfície: a MESMA janela de altura autoritativa de
    adsorb()/qe_slab_candidates (`top_surface_indices`). Os dois O pedidos têm
    de casar átomos O reais dentro de `site_atom_tol`, ser distintos e pertencer
    a esse conjunto (senão aborta — nunca adivinha).

    Ponto médio por imagem mínima no plano (a,b periódicos; c é vácuo): usa a
    imagem 3x3 de O2 mais próxima de O1, mid = (O1 + O2_img)/2. O ponto é então
    erguido ao longo de +z (mesma lógica de folga de adsorb()) até nenhum átomo
    do slab ficar mais perto do Hg que `distance`; o relax refina a aproximação.

    `find_adsorption_sites(symm_reduce=0)` é chamado só como VERIFICAÇÃO CRUZADA:
    reporta o sítio `bridge` mais próximo do ponto médio em planta e o snap, e
    credita o método quando concorda — nunca sobrepõe o ponto médio pedido (mesmo
    tratamento que adsorb() dá a get_surface_sites())."""
    asf = AdsorbateSiteFinder(slab, height=asf_height)

    lat = slab.lattice
    slab_frac = np.array([s.frac_coords for s in slab])
    symbols = np.array([s.specie.symbol for s in slab])

    # Conjunto AUTORITATIVO de superfície = janela de altura (ver adsorb()).
    top_indices = top_surface_indices(slab, asf_height)
    if not any(symbols[i] == "O" for i in top_indices):
        raise RuntimeError("no surface O atoms identified")
    surface_id_method = identify_surface_method(
        slab, lat, slab_frac, symbols, top_indices, asf_height)

    idx1 = match_surface_atom(lat, slab_frac, symbols, site_atom_1,
                              top_indices, site_atom_tol, "site_atom_1")
    idx2 = match_surface_atom(lat, slab_frac, symbols, site_atom_2,
                              top_indices, site_atom_tol, "site_atom_2")
    if idx1 == idx2:
        raise RuntimeError(
            f"site_atom_1 and site_atom_2 match the same atom #{idx1} — "
            "bidentate adsorption needs two distinct surface O")

    # Ponto médio por imagem mínima no plano: imagem 3x3 de O2 mais próxima de O1
    # (dois O em bordas opostas da célula dão o meio correto, não x~0.5 espúrio).
    o1_cart = lat.get_cartesian_coords(slab_frac[idx1])
    o2_imgs = np.array([lat.get_cartesian_coords(slab_frac[idx2])
                        + i * lat.matrix[0] + j * lat.matrix[1]
                        for i in (-1, 0, 1) for j in (-1, 0, 1)])
    o2_cart = o2_imgs[int(np.argmin(np.linalg.norm(o2_imgs - o1_cart, axis=1)))]
    oo_dist = float(np.linalg.norm(o2_cart - o1_cart))
    mid = 0.5 * (o1_cart + o2_cart)

    # Ergue o ponto médio ao longo de +z (mesma lógica de adsorb()): sem os H
    # eretos das duas hidroxilas (removidos antes) o Hg parte perto do plano dos
    # O; erguer até nenhum átomo do slab ficar mais perto que `distance` dá o
    # arranjo bidentado (Hg-O1 ~ Hg-O2 ~ distance). Imagens 3x3 no plano cobrem a
    # periodicidade; imagens em c são vácuo.
    chosen = mid.copy()
    slab_cart = lat.get_cartesian_coords(slab_frac)
    images = np.vstack([slab_cart + i * lat.matrix[0] + j * lat.matrix[1]
                        for i in (-1, 0, 1) for j in (-1, 0, 1)])
    r2 = np.sum((images[:, :2] - chosen[:2]) ** 2, axis=1)
    near = r2 < distance**2
    lift = 0.0
    if near.any():
        z_needed = float(np.max(images[near, 2] + np.sqrt(distance**2 - r2[near])))
        lift = max(0.0, z_needed - chosen[2])
    chosen[2] += lift

    normal = getattr(asf, "mvec", slab.normal)
    mol_local = mol.cart_coords @ rot_from_z(normal).T  # âncora (Hg) na origem

    pts = np.asarray(chosen) + mol_local
    frac = np.array([lat.get_fractional_coords(p) for p in pts])
    dmat = lat.get_all_distances(frac, slab_frac)
    h_cols = symbols == "H"
    hg_o1 = float(dmat[0][idx1])
    hg_o2 = float(dmat[0][idx2])
    hg_h = float(dmat[0][h_cols].min()) if h_cols.any() else float("nan")
    rest = float(dmat[1:].min())
    clearance_ok = (np.isnan(hg_h) or hg_h >= h_clearance) and rest >= h_clearance

    # Verificação cruzada: sítio bridge mais próximo do ponto médio (em planta).
    sites = asf.find_adsorption_sites(distance=distance, symm_reduce=0)
    bridge = sites.get("bridge", [])
    if bridge:
        bsnap = min(float(np.linalg.norm(np.asarray(b)[:2] - mid[:2]))
                    for b in bridge)
        if bsnap <= site_atom_tol:
            placement_method = (
                f"midpoint of O#{idx1}/O#{idx2}; matches "
                f"find_adsorption_sites() bridge (snap {bsnap:.3f} Å)")
        else:
            placement_method = (
                f"midpoint of O#{idx1}/O#{idx2} (nearest find_adsorption_sites() "
                f"bridge {bsnap:.3f} Å away in-plane — this O-O pair is not an ASF "
                "bridge; midpoint used as requested)")
    else:
        placement_method = (f"midpoint of O#{idx1}/O#{idx2} "
                            "(find_adsorption_sites() returned no bridge site)")

    mol_rotated = Molecule([s.specie.symbol for s in mol], mol_local)
    ads_struct = asf.add_adsorbate(mol_rotated, chosen,
                                   translate=False, reorient=False)
    info = {
        "surface_id_method": surface_id_method,
        "surface_sites_top": len(top_indices),
        "surface_O_top": int(sum(1 for i in top_indices if symbols[i] == "O")),
        "n_bridge": len(bridge),
        "placement_method": placement_method,
        "clearance_ok": clearance_ok,
        "site_cart": [round(float(x), 4) for x in chosen],
        "oo_dist": round(oo_dist, 3),
        "site_lift": round(lift, 3),
        "hg_O1": round(hg_o1, 3),
        "hg_O2": round(hg_o2, 3),
        "site_dH": round(hg_h, 3) if not np.isnan(hg_h) else None,
        "mol_clearance": round(rest, 3),
        "o1_index": idx1,
        "o1_symbol": str(symbols[idx1]),
        "o1_requested": [round(float(x), 5) for x in np.asarray(site_atom_1, float)],
        "o2_index": idx2,
        "o2_symbol": str(symbols[idx2]),
        "o2_requested": [round(float(x), 5) for x in np.asarray(site_atom_2, float)],
    }
    return ads_struct, info


# -------------------------------------------------- Estágio 3: gerador

def generate_adsorbed(miller, *, slab_2x1x1_ref, kaolinite_ref, molecule_ref,
                      vacuum_min, ads_distance, asf_height, h_clearance,
                      site_atom_tol, bond_scale, out_dir, site_atom,
                      site_label, remove_anchor_h=False):
    """Estágio 3 — H3CHg adsorvido ontop do átomo `site_atom` (coordenada
    fracionária) da supercélula 2x1x1 relaxada (`slab_2x1x1_ref`). Escreve
    <out_dir>/<site_label>/relax-<prefix>.in (+ .cif + .md), onde
    <prefix> = <prefix do slab>-<prefix da molécula>-<site_label> — o
    subdiretório por sítio evita colisão do outdir='./tmp' entre corridas QE.

    Fonte da superfície: a supercélula 2x1x1 JÁ RELAXADA (não o bulk, não a
    superfície 1x1) — todos os cutoffs/pseudos/k-mesh vêm dela. A molécula e
    suas espécies (Hg, C) vêm de `molecule_ref`. `calculation='relax'`:
    adsorbato e átomos de superfície livres relaxam; célula fixa (herdada
    intacta da referência 2x1x1); os átomos da camada inferior ficam
    congelados (mesmo constrangimento do slab puro).

    Se `remove_anchor_h` (só (001) — decisão do usuário), o único H da
    hidroxila do O âncora é removido ANTES de embrulhar o slab e de contar
    `n_slab` (desprotonação: o Hg substitui o próton, ver anchor_hydrogen);
    sem o H ereto o Hg parte de ~2.0 Å do O e o erguimento em adsorb() some.
    """
    miller = tuple(miller)
    ref = load_ref(slab_2x1x1_ref, with_structure=True)
    mol_ref = load_ref(molecule_ref, with_structure=False)

    slab_struct = AseAtomsAdaptor.get_structure(ref.atoms)
    if "selective_dynamics" in slab_struct.site_properties:
        slab_struct.remove_site_property("selective_dynamics")
    removed_h = None
    if remove_anchor_h:
        h_idx, anchor_o_idx = anchor_hydrogen(
            slab_struct, site_atom, bond_scale, site_atom_tol)
        slab_struct.remove_sites([h_idx])   # pymatgen Structure.remove_sites
        removed_h = {"h_index": h_idx, "o_index": anchor_o_idx}
    n_slab = len(slab_struct)
    mol, mol_span, _ = build_molecule(mol_ref)

    # Bulk lido só como template de coordenação para get_surface_sites (ver
    # slab_from_ref); nenhum parâmetro físico vem dele.
    bulk_ref = AseAtomsAdaptor.get_structure(
        load_ref(kaolinite_ref, with_structure=True).atoms)
    slab = slab_from_ref(slab_struct, miller, bulk_ref)
    struct, ads_info = adsorb(slab, mol, site_atom, ads_distance, asf_height,
                              h_clearance, site_atom_tol)

    slab_prefix = ref.namelists["control"]["prefix"]       # kaolinite-slab-<hkl>-2x1x1
    mol_prefix = mol_ref.namelists["control"]["prefix"]    # H3CHg
    prefix = f"{slab_prefix}-{mol_prefix}-{site_label}"
    outdir = Path(out_dir) / site_label

    species = assemble_species(ref, mol_ref, adsorbed=True)
    if {s.specie.symbol for s in struct} != {sp[0] for sp in species}:
        raise RuntimeError("structure species do not match ATOMIC_SPECIES")
    namelists = assemble_namelists(ref, mol_ref, True, prefix)  # calculation forçado p/ 'relax'
    normal = np.array([0.0, 0.0, 1.0])
    checks = geometry_checks(struct, normal, len(mol), True, vacuum_min)
    fixed = fixed_indices(struct, miller, normal, n_slab=n_slab, bond_scale=bond_scale)

    outdir.mkdir(parents=True, exist_ok=True)
    calc = namelists["control"]["calculation"]
    in_path = outdir / f"{calc}-{prefix}.in"
    write_qe_input(in_path, namelists, species, struct, ref.kmesh, ref.koffset,
                   fixed=fixed)
    struct.to(filename=str(outdir / f"{prefix}.cif"))

    a, b, c = (np.linalg.norm(v) for v in struct.lattice.matrix)
    fix_by_sp = count_by_species(struct, fixed)
    print(f"== {prefix}  (Stage 3: H3CHg adsorbed, {calc}) ==")
    print(f"  from ref     : {Path(slab_2x1x1_ref).relative_to(ROOT)}  (Stage 2 relaxed 2x1x1)")
    print(f"  input        : {in_path.relative_to(ROOT)}")
    print(f"  site_atom    : #{ads_info['site_atom_index']} "
          f"{ads_info['site_atom_symbol']} at {ads_info['site_atom_requested']} "
          f"(frac; ontop snap {ads_info['site_snap']} Å)")
    if removed_h:
        print(f"  deprotonation: removed anchor hydroxyl H#{removed_h['h_index']} "
              f"on O#{removed_h['o_index']} (001 anchor O deprotonated)")
    print(f"  atoms        : {len(struct)}  ({n_slab} slab + {len(mol)} molecule; "
          f"species: {[sp[0] for sp in species]})")
    print(f"  lattice |a|,|b|,|c| : {a:.3f}, {b:.3f}, {c:.3f} Å")
    print(f"  vacuum gap   : {checks['vacuum_gap']} Å (required ≥ {vacuum_min})")
    print(f"  fixed atoms  : {len(fixed)}/{n_slab} slab atoms {fix_by_sp} "
          f"(if_pos 0 0 0; paper layer constraint)")
    print(f"  k-mesh       : {' '.join(map(str, ref.kmesh))} (from 2x1x1 ref, cell unchanged)")
    print(f"  surface atoms (top): {ads_info['surface_sites_top']} "
          f"({ads_info['surface_O_top']} O) via {ads_info['surface_id_method']}")
    print(f"  placed ontop at {ads_info['site_cart']} "
          f"(of {ads_info['n_ontop']} ontop sites, symm_reduce=0; "
          f"lifted +{ads_info['site_lift']} Å along z; clearance "
          f"{'ok' if ads_info['clearance_ok'] else 'RELAXED'}; "
          f"Hg-O {ads_info['site_dO']}, Hg...H {ads_info['site_dH']}, "
          f"CH3-slab {ads_info['mol_clearance']} Å)")
    print(f"  Hg-O {checks['hg_O']} Å ; nearest contact "
          f"{checks['hg_nearest'][0]} at {checks['hg_nearest'][1]} Å")
    print()

    md = [
        f"- **a partir da referência**: `{Path(slab_2x1x1_ref).relative_to(ROOT)}` (Estágio 2 relaxado, 2x1x1)",
        f"- **entrada**: `{in_path.relative_to(ROOT)}`",
        f"- **calculation**: `{calc}` (célula fixa, herdada da referência 2×1×1)",
        f"- **site_atom**: #{ads_info['site_atom_index']} "
        f"{ads_info['site_atom_symbol']} em {ads_info['site_atom_requested']} "
        f"(fracionária; snap ontop {ads_info['site_snap']} Å)",
        *([f"- **desprotonação**: H#{removed_h['h_index']} da hidroxila removido "
           f"do O âncora #{removed_h['o_index']} (só (001))"] if removed_h else []),
        f"- **átomos**: {len(struct)} ({n_slab} slab + {len(mol)} molécula; "
        f"espécies: {[sp[0] for sp in species]})",
        f"- **rede \\|a\\|,\\|b\\|,\\|c\\|**: {a:.3f}, {b:.3f}, {c:.3f} Å",
        f"- **gap de vácuo**: {checks['vacuum_gap']} Å (requerido ≥ {vacuum_min})",
        f"- **átomos fixos**: {len(fixed)}/{n_slab} átomos do slab {fix_by_sp} "
        f"(if_pos 0 0 0; constrangimento de camada do artigo)",
        f"- **k-mesh**: {' '.join(map(str, ref.kmesh))} (da referência 2x1x1, célula inalterada)",
        f"- **átomos de superfície (topo)**: {ads_info['surface_sites_top']} "
        f"({ads_info['surface_O_top']} O) via {ads_info['surface_id_method']}",
        f"- **posicionado** ontop em {ads_info['site_cart']} "
        f"(de {ads_info['n_ontop']} sítios ontop, "
        f"`find_adsorption_sites(symm_reduce=0)`; "
        f"erguido +{ads_info['site_lift']} Å em z; "
        f"clearance {'ok' if ads_info['clearance_ok'] else 'RELAXADO'}; "
        f"Hg-O {ads_info['site_dO']}, Hg...H {ads_info['site_dH']}, "
        f"CH3-slab {ads_info['mol_clearance']} Å)",
        f"- **Hg-O**: {checks['hg_O']} Å ; contato mais próximo "
        f"{checks['hg_nearest'][0]} a {checks['hg_nearest'][1]} Å",
    ]
    write_report_md(outdir, prefix, md)

    return {"prefix": prefix, "kmesh": ref.kmesh, "checks": checks,
            "ads_info": ads_info, "lattice": (a, b, c), "n_atoms": len(struct)}


def generate_adsorbed_bidentate(miller, *, slab_2x1x1_ref, kaolinite_ref,
                                molecule_ref, vacuum_min, ads_distance,
                                asf_height, h_clearance, site_atom_tol,
                                bond_scale, out_dir, site_atom_1, site_atom_2,
                                label=None, remove_anchor_h=True):
    """Estágio 3 (bidentado) — H3CHg em ponte acima do ponto médio de dois O de
    superfície (`site_atom_1`, `site_atom_2`, coordenadas fracionárias) da
    supercélula 2x1x1 JÁ RELAXADA (`slab_2x1x1_ref`). Escreve
    <out_dir>/<label>/relax-<prefix>.in (+ .cif + .md), com <label> padrão
    O{i}-O{j} (índices dos dois O âncora, os mesmos de candidatos-<hkl>.md) —
    o subdiretório por sítio evita colisão do outdir='./tmp' entre corridas QE
    e não colide com os dirs monodentados (`O40`, ...).

    Modela a complexação bidentada: o único Hg faz ponte entre os dois O
    (bridging Hg-O/Hg-O). Se `remove_anchor_h` (padrão; regra do (001), como no
    monodentado), o único H de CADA hidroxila âncora é removido ANTES de
    embrulhar o slab e de contar `n_slab` (desprotonação das duas hidroxilas —
    o Hg substitui os dois prótons; a célula permanece neutra).

    Fonte física/numérica: a supercélula 2x1x1 relaxada (célula/cutoffs/pseudos/
    k-mesh) e scf-H3CHg.in (molécula/espécies Hg, C). calculation='relax',
    célula fixa herdada intacta; a folha inferior fica congelada (mesmo
    constrangimento de camada do slab puro/monodentado)."""
    miller = tuple(miller)
    ref = load_ref(slab_2x1x1_ref, with_structure=True)
    mol_ref = load_ref(molecule_ref, with_structure=False)

    slab_struct = AseAtomsAdaptor.get_structure(ref.atoms)
    if "selective_dynamics" in slab_struct.site_properties:
        slab_struct.remove_site_property("selective_dynamics")

    removed_h = None
    anchor_o = None
    if remove_anchor_h:
        h1, o1 = anchor_hydrogen(slab_struct, site_atom_1, bond_scale, site_atom_tol)
        h2, o2 = anchor_hydrogen(slab_struct, site_atom_2, bond_scale, site_atom_tol)
        if o1 == o2:
            raise RuntimeError(
                f"site_atom_1 and site_atom_2 match the same anchor O #{o1} — "
                "bidentate adsorption needs two distinct surface O")
        if h1 == h2:
            raise RuntimeError(
                f"the two anchor O share a single hydroxyl H #{h1} — cannot "
                "deprotonate both; inspect the sites")
        # Coleta os dois índices de H na estrutura original e remove ambos de uma
        # vez (remover um por vez reindexaria o outro).
        slab_struct.remove_sites(sorted([h1, h2]))
        removed_h = {"h_indices": sorted([h1, h2]), "o_indices": sorted([o1, o2])}
        anchor_o = sorted([o1, o2])
    n_slab = len(slab_struct)
    mol, mol_span, _ = build_molecule(mol_ref)

    # Bulk lido só como template de coordenação para get_surface_sites (ver
    # slab_from_ref); nenhum parâmetro físico vem dele.
    bulk_ref = AseAtomsAdaptor.get_structure(
        load_ref(kaolinite_ref, with_structure=True).atoms)
    slab = slab_from_ref(slab_struct, miller, bulk_ref)
    struct, ads_info = adsorb_bidentate(slab, mol, site_atom_1, site_atom_2,
                                        ads_distance, asf_height, h_clearance,
                                        site_atom_tol)

    if label is None:
        oi, oj = (anchor_o if anchor_o is not None
                  else sorted([ads_info["o1_index"], ads_info["o2_index"]]))
        label = f"O{oi}-O{oj}"

    slab_prefix = ref.namelists["control"]["prefix"]       # kaolinite-slab-<hkl>-2x1x1
    mol_prefix = mol_ref.namelists["control"]["prefix"]    # H3CHg
    prefix = f"{slab_prefix}-{mol_prefix}-{label}"
    outdir = Path(out_dir) / label

    species = assemble_species(ref, mol_ref, adsorbed=True)
    if {s.specie.symbol for s in struct} != {sp[0] for sp in species}:
        raise RuntimeError("structure species do not match ATOMIC_SPECIES")
    namelists = assemble_namelists(ref, mol_ref, True, prefix)  # calculation forçado p/ 'relax'
    normal = np.array([0.0, 0.0, 1.0])
    checks = geometry_checks(struct, normal, len(mol), True, vacuum_min)
    fixed = fixed_indices(struct, miller, normal, n_slab=n_slab, bond_scale=bond_scale)

    outdir.mkdir(parents=True, exist_ok=True)
    calc = namelists["control"]["calculation"]
    in_path = outdir / f"{calc}-{prefix}.in"
    write_qe_input(in_path, namelists, species, struct, ref.kmesh, ref.koffset,
                   fixed=fixed)
    struct.to(filename=str(outdir / f"{prefix}.cif"))

    a, b, c = (np.linalg.norm(v) for v in struct.lattice.matrix)
    fix_by_sp = count_by_species(struct, fixed)
    print(f"== {prefix}  (Stage 3: H3CHg bidentate, {calc}) ==")
    print(f"  from ref     : {Path(slab_2x1x1_ref).relative_to(ROOT)}  (Stage 2 relaxed 2x1x1)")
    print(f"  input        : {in_path.relative_to(ROOT)}")
    print(f"  O1 / O2      : #{ads_info['o1_index']} {ads_info['o1_symbol']} at "
          f"{ads_info['o1_requested']} | #{ads_info['o2_index']} "
          f"{ads_info['o2_symbol']} at {ads_info['o2_requested']} "
          f"(O-O {ads_info['oo_dist']} Å)")
    if removed_h:
        print(f"  deprotonation: removed anchor hydroxyl H {removed_h['h_indices']} "
              f"on O {removed_h['o_indices']} (001 bidentate: both anchor O deprotonated)")
    print(f"  atoms        : {len(struct)}  ({n_slab} slab + {len(mol)} molecule; "
          f"species: {[sp[0] for sp in species]})")
    print(f"  lattice |a|,|b|,|c| : {a:.3f}, {b:.3f}, {c:.3f} Å")
    print(f"  vacuum gap   : {checks['vacuum_gap']} Å (required ≥ {vacuum_min})")
    print(f"  fixed atoms  : {len(fixed)}/{n_slab} slab atoms {fix_by_sp} "
          f"(if_pos 0 0 0; paper layer constraint)")
    print(f"  k-mesh       : {' '.join(map(str, ref.kmesh))} (from 2x1x1 ref, cell unchanged)")
    print(f"  surface atoms (top): {ads_info['surface_sites_top']} "
          f"({ads_info['surface_O_top']} O) via {ads_info['surface_id_method']}")
    print(f"  placed at midpoint {ads_info['site_cart']} "
          f"({ads_info['placement_method']}; lifted +{ads_info['site_lift']} Å "
          f"along z; clearance {'ok' if ads_info['clearance_ok'] else 'RELAXED'}; "
          f"Hg-O1 {ads_info['hg_O1']}, Hg-O2 {ads_info['hg_O2']}, "
          f"Hg...H {ads_info['site_dH']}, CH3-slab {ads_info['mol_clearance']} Å)")
    print(f"  Hg-O(nearest) {checks['hg_O']} Å ; nearest contact "
          f"{checks['hg_nearest'][0]} at {checks['hg_nearest'][1]} Å")
    print()

    md = [
        f"- **a partir da referência**: `{Path(slab_2x1x1_ref).relative_to(ROOT)}` (Estágio 2 relaxado, 2x1x1)",
        f"- **entrada**: `{in_path.relative_to(ROOT)}`",
        f"- **modo**: bidentado — o Hg faz ponte entre dois O de superfície",
        f"- **calculation**: `{calc}` (célula fixa, herdada da referência 2×1×1)",
        f"- **O âncora 1**: #{ads_info['o1_index']} {ads_info['o1_symbol']} em "
        f"{ads_info['o1_requested']} (fracionária)",
        f"- **O âncora 2**: #{ads_info['o2_index']} {ads_info['o2_symbol']} em "
        f"{ads_info['o2_requested']} (fracionária)",
        f"- **distância O-O**: {ads_info['oo_dist']} Å",
        *([f"- **desprotonação**: H {removed_h['h_indices']} das hidroxilas "
           f"removidos dos O âncora {removed_h['o_indices']} (só (001); as duas "
           "hidroxilas desprotonadas)"] if removed_h else []),
        f"- **átomos**: {len(struct)} ({n_slab} slab + {len(mol)} molécula; "
        f"espécies: {[sp[0] for sp in species]})",
        f"- **rede \\|a\\|,\\|b\\|,\\|c\\|**: {a:.3f}, {b:.3f}, {c:.3f} Å",
        f"- **gap de vácuo**: {checks['vacuum_gap']} Å (requerido ≥ {vacuum_min})",
        f"- **átomos fixos**: {len(fixed)}/{n_slab} átomos do slab {fix_by_sp} "
        f"(if_pos 0 0 0; constrangimento de camada do artigo)",
        f"- **k-mesh**: {' '.join(map(str, ref.kmesh))} (da referência 2x1x1, célula inalterada)",
        f"- **átomos de superfície (topo)**: {ads_info['surface_sites_top']} "
        f"({ads_info['surface_O_top']} O) via {ads_info['surface_id_method']}",
        f"- **posicionado** no ponto médio em {ads_info['site_cart']} "
        f"({ads_info['placement_method']}; erguido +{ads_info['site_lift']} Å em z; "
        f"clearance {'ok' if ads_info['clearance_ok'] else 'RELAXADO'}; "
        f"Hg-O1 {ads_info['hg_O1']}, Hg-O2 {ads_info['hg_O2']}, "
        f"Hg...H {ads_info['site_dH']}, CH3-slab {ads_info['mol_clearance']} Å)",
        f"- **Hg-O (mais próximo)**: {checks['hg_O']} Å ; contato mais próximo "
        f"{checks['hg_nearest'][0]} a {checks['hg_nearest'][1]} Å",
    ]
    write_report_md(outdir, prefix, md)

    return {"prefix": prefix, "kmesh": ref.kmesh, "checks": checks,
            "ads_info": ads_info, "lattice": (a, b, c), "n_atoms": len(struct)}


def generate_adsorbed_candidates(miller, *, slab_2x1x1_ref, kaolinite_ref,
                                 molecule_ref, vacuum_min, ads_distance,
                                 asf_height, height_window, symprec,
                                 h_clearance, site_atom_tol, bond_scale,
                                 out_dir, site_symbols=("O",),
                                 remove_anchor_h=False):
    """Orquestrador do Estágio 3: enumera os átomos de superfície
    não-equivalentes da supercélula relaxada (qe_slab_candidates.
    find_candidates — mesma fonte do relatório candidatos-<hkl>.md), filtra
    por espécie (`site_symbols`, padrão só O — âncora Hg-O do artigo) e gera
    um relax por candidato em <out_dir>/<label>/. Se `remove_anchor_h` (só
    (001)), cada candidato tem o H da sua hidroxila âncora removido antes da
    adsorção (desprotonação — ver generate_adsorbed/anchor_hydrogen)."""
    candidates, meta = find_candidates(
        miller, slab_2x1x1_ref=slab_2x1x1_ref, height_window=height_window,
        symprec=symprec, bond_scale=bond_scale, site_symbols=site_symbols)
    chosen = [c for c in candidates if c["symbol"] in site_symbols]
    if not chosen:
        raise RuntimeError(
            f"no candidate surface atoms with symbol in {site_symbols} "
            f"(found: {sorted({c['symbol'] for c in candidates})})")

    print(f"== Stage 3: {len(chosen)} candidate site(s) {site_symbols} of "
          f"{len(candidates)} non-equivalent surface atoms "
          f"({meta['ref_rel'].name}, spacegroup {meta['spacegroup']}) ==\n")

    results = {}
    for c in chosen:
        label = f"{c['symbol']}{c['index']}"
        results[label] = generate_adsorbed(
            miller,
            slab_2x1x1_ref=slab_2x1x1_ref,
            kaolinite_ref=kaolinite_ref,
            molecule_ref=molecule_ref,
            vacuum_min=vacuum_min,
            ads_distance=ads_distance,
            asf_height=asf_height,
            h_clearance=h_clearance,
            site_atom_tol=site_atom_tol,
            bond_scale=bond_scale,
            out_dir=out_dir,
            site_atom=c["frac"],
            site_label=label,
            remove_anchor_h=remove_anchor_h,
        )
    return results
