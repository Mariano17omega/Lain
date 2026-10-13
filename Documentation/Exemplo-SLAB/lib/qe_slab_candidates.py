"""
qe_slab_candidates.py — busca de sítios de superfície não-equivalentes na
supercélula 2x1x1 JÁ RELAXADA (scf-kaolinite-slab-<hkl>-2x1x1.in), como
candidatos para `site_atom` em qe_slab_adsorb.generate_adsorbed (rodado via
generate_001_adsorbed.py / generate_010_adsorbed.py).

Identificação da superfície (topo): por JANELA DE ALTURA ao longo da normal
(+z, convenção já usada em todo o pipeline — ver qe_slab_supercell.py/
qe_slab_adsorb.py, `normal = [0,0,1]`), não por `Slab.get_surface_sites()`.

Motivo (medido, não hipotético): `Slab.get_surface_sites()` usa
`VoronoiNN` com CN ponderado por ângulo sólido, comparado ao CN mínimo do
`oriented_unit_cell` (bulk) por espécie — um átomo só é "superfície" se seu
CN cai abaixo do CN mínimo do bulk para a mesma espécie. Testado direto
contra `scf-kaolinite-slab-001-2x1x1.in`: o CN ponderado dos átomos de Al
expostos no topo do slab (~5.94) sai MAIOR que o CN mínimo do Al no bulk
(~5.57) — perder o vizinho cortado pelo vácuo faz os vizinhos remanescentes
dominarem mais do ângulo sólido, e o CN ponderado sobe em vez de cair. Isso
faz `get_surface_sites()` devolver `{"top": [], "bottom": []}` para essa
estrutura (confirmado também em `qe_slab_adsorb.adsorb()`, que já falha com
"no surface O atoms identified by get_surface_sites()" pra essa mesma
referência) — limitação documentada do pymatgen ("only work for
single-element systems for now" no próprio docstring), não um bug deste
módulo. `qe_slab_adsorb.py` continua como está (não foi alterado); este
módulo novo usa o critério de altura só para si.

Sítios não-equivalentes: SpacegroupAnalyzer/spglib sobre a estrutura
completa, restrito aos índices da janela de superfície — captura tanto
simetria pontual real do slab quanto a simetria de translação pura
introduzida pela duplicação 2x1x1 (dois átomos que só diferem por x+0.5
caem no mesmo grupo).

Escreve um relatório `candidatos.md` com label, coordenada fracionária e
vizinhos de cada representante; nenhum `.in`/`.cif` é emitido. Todo
parâmetro físico/numérico vem da referência (via qe_slab_common) ou dos
parâmetros do chamador (height_window, symprec, bond_scale) — nada
hardcoded aqui.
"""

from pathlib import Path

import numpy as np
from ase.data import atomic_numbers, covalent_radii
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from qe_slab_common import ROOT, load_ref


def neighbor_summary(struct, idx, bond_scale, rmax=3.0):
    """Vizinhos ligados do átomo `idx` (distância < bond_scale * soma dos
    raios covalentes, mesmo critério de qe_slab_common.bond_count/
    fixed_indices), como lista rotulada "símbolo(distância)" ordenada por
    distância — não uma contagem agregada, para ajudar o usuário a
    distinguir quimicamente os sítios (ex.: O só com Al vizinho vs. O com H
    vizinho = hidroxila) sem inventar nomenclatura do artigo."""
    site = struct[idx]
    ri = covalent_radii[atomic_numbers[site.specie.symbol]]
    out = []
    for nb in struct.get_neighbors(site, r=rmax):
        rj = covalent_radii[atomic_numbers[nb.specie.symbol]]
        if nb.nn_distance < bond_scale * (ri + rj):
            out.append((nb.specie.symbol, float(nb.nn_distance)))
    out.sort(key=lambda p: p[1])
    return out


def top_surface_indices(struct, height_window):
    """Índices dos átomos dentro de `height_window` Å do ponto mais alto ao
    longo da normal +z (convenção do pipeline: as referências 2x1x1 já
    relaxadas têm a normal da superfície exatamente em +z — ver
    qe_slab_supercell.py/qe_slab_adsorb.py). Substitui
    Slab.get_surface_sites() (ver docstring do módulo) por um critério
    puramente geométrico, sem depender de coordenação/Voronoi."""
    proj = struct.cart_coords[:, 2]
    top = proj.max() - height_window
    idx = set(np.flatnonzero(proj >= top).tolist())
    if not any(struct[i].specie.symbol == "O" for i in idx):
        raise RuntimeError(
            f"no surface O atoms within height_window={height_window} Å "
            "of the top — widen the window or check the normal convention")
    return idx


def find_candidates(miller, *, slab_2x1x1_ref, height_window, symprec,
                    bond_scale, site_symbols=("O",)):
    """Enumera os átomos de superfície (topo, por janela de altura — ver
    módulo) simetricamente não-equivalentes da supercélula 2x1x1 relaxada
    `slab_2x1x1_ref`. Função pura (não escreve nada): fonte única da
    enumeração, usada tanto pelo relatório (generate_candidates) quanto pelo
    Estágio 3 (qe_slab_adsorb.generate_adsorbed_candidates).

    `site_symbols` restringe os candidatos por espécie (padrão só O — o Hg
    ancora em O, como no artigo; os H que caem na janela de altura das
    hidroxilas não são sítios de adsorção). O filtro só descarta linhas; os
    índices/labels vêm da estrutura simetrizada completa e não mudam.

    Retorna (candidates, meta): candidates é uma lista de dicts com
    index/symbol/frac/multiplicity/members/neighbors; meta traz
    spacegroup/n_top/ref_rel para os relatórios."""
    miller = tuple(miller)
    ref = load_ref(slab_2x1x1_ref, with_structure=True)
    struct = AseAtomsAdaptor.get_structure(ref.atoms)
    if "selective_dynamics" in struct.site_properties:
        struct.remove_site_property("selective_dynamics")

    top_idx = top_surface_indices(struct, height_window)

    sga = SpacegroupAnalyzer(struct, symprec=symprec)
    sym_struct = sga.get_symmetrized_structure()
    spacegroup = sga.get_space_group_symbol()

    candidates = []
    for group in sym_struct.equivalent_indices:
        members = sorted(int(i) for i in group if int(i) in top_idx)
        if not members:
            continue
        rep = members[0]
        site = struct[rep]
        if site.specie.symbol not in site_symbols:
            continue
        candidates.append({
            "index": rep,
            "symbol": site.specie.symbol,
            "frac": tuple(round(float(x), 5) for x in site.frac_coords),
            "multiplicity": len(members),
            "members": members,
            "neighbors": neighbor_summary(struct, rep, bond_scale),
        })
    candidates.sort(key=lambda c: (c["symbol"], c["index"]))

    meta = {
        "spacegroup": spacegroup,
        "n_top": len(top_idx),
        "ref_rel": Path(slab_2x1x1_ref).relative_to(ROOT),
    }
    return candidates, meta


def generate_candidates(miller, *, slab_2x1x1_ref, height_window, symprec,
                        bond_scale, out_path, site_symbols=("O",)):
    """Wrapper de relatório sobre find_candidates(): escreve `out_path`
    (Markdown) com label, coordenada fracionária (crystal) e vizinhos de cada
    candidato — coordenadas prontas para `site_atom=(x, y, z)` em
    generate_00X_adsorbed.py. `site_symbols` (padrão só O) restringe a espécie
    dos candidatos (o Hg ancora em O — H de hidroxila não é sítio de adsorção).
    """
    miller = tuple(miller)
    candidates, meta = find_candidates(
        miller, slab_2x1x1_ref=slab_2x1x1_ref, height_window=height_window,
        symprec=symprec, bond_scale=bond_scale, site_symbols=site_symbols)
    spacegroup = meta["spacegroup"]
    ref_rel = meta["ref_rel"]
    lines = [
        f"# Candidatos de sítio de adsorção — {ref_rel.name}",
        "",
        f"- **referência**: `{ref_rel}` (supercélula 2x1x1 já relaxada)",
        f"- **miller**: {miller}",
        f"- **grupo espacial detectado**: {spacegroup} (symprec={symprec} Å)",
        f"- **átomos de superfície (topo)**: {meta['n_top']} "
        f"(janela de altura {height_window} Å ao longo de +z — "
        "`Slab.get_surface_sites()` não é usável para este sistema: "
        "CN ponderado do Voronoi sobe, não cai, no topo do slab; ver "
        "docstring de `qe_slab_candidates.py`)",
        f"- **espécie dos candidatos**: {', '.join(site_symbols)} "
        "(o Hg ancora em O; H de hidroxila na janela não é sítio de adsorção)",
        f"- **sítios não-equivalentes**: {len(candidates)}",
        "",
        "| label | índice | x (crystal) | y (crystal) | z (crystal) | "
        "multiplicidade | índices equivalentes | vizinhos (Å) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in candidates:
        label = f"{c['symbol']}{c['index']}"
        x, y, z = c["frac"]
        members_str = ", ".join(str(m) for m in c["members"])
        nbrs_str = ", ".join(f"{sym}({d:.2f})" for sym, d in c["neighbors"])
        lines.append(f"| {label} | {c['index']} | {x} | {y} | {z} | "
                     f"{c['multiplicity']} | {members_str} | {nbrs_str} |")
    lines.append("")
    lines.append("Uso: copie `(x, y, z)` de uma linha para `site_atom=(...)` "
                 "em `generate_00X_adsorbed.py` (ver comentário no topo "
                 "desses scripts).")

    out_path = Path(out_path)
    out_path.write_text("\n".join(lines) + "\n")

    print(f"== candidatos de sítio — {ref_rel.name} ==")
    print(f"  grupo espacial : {spacegroup} (symprec={symprec} Å)")
    print(f"  superfície topo: {meta['n_top']} átomos (janela de altura "
          f"{height_window} Å; get_surface_sites() indisponível p/ este "
          "sistema)")
    print(f"  não-equivalentes: {len(candidates)}")
    print(f"  escrito em     : {out_path.relative_to(ROOT)}")
    print()

    return candidates


def frac_for_labels(miller, *, slab_2x1x1_ref, labels, height_window,
                    site_symbols=("O",)):
    """Resolve rótulos de átomo (ex.: 'O42') às suas coordenadas fracionárias
    (crystal), direto contra a MESMA janela de superfície autoritativa
    (`top_surface_indices`) usada em todo o resto do pipeline — não passa
    pela redução por simetria (spglib) de find_candidates.

    Rótulo = símbolo + índice bruto da estrutura, a mesma indexação das
    colunas "índice"/"índices equivalentes" de candidatos-<hkl>.md. Aceita
    tanto o representante de cada grupo simétrico (ex.: 'O42', a linha do
    relatório) quanto qualquer outro membro do mesmo grupo (ex.: 'O43', não
    listado como linha própria mas presente em "índices equivalentes":
    42, 43) — os dois são átomos de superfície reais e distintos, só
    colapsados na mesma linha do relatório por simetria; útil para
    complexação bidentada entre dois O da mesma hidroxila/anel.

    Devolve a lista de coords (tuplas) na ordem de `labels`. Rótulo
    inexistente, fora da janela de superfície ou de espécie fora de
    `site_symbols` levanta ValueError listando os rótulos disponíveis."""
    ref = load_ref(slab_2x1x1_ref, with_structure=True)
    struct = AseAtomsAdaptor.get_structure(ref.atoms)
    if "selective_dynamics" in struct.site_properties:
        struct.remove_site_property("selective_dynamics")
    top_idx = top_surface_indices(struct, height_window)
    by_label = {
        f"{struct[i].specie.symbol}{i}":
            tuple(round(float(x), 5) for x in struct[i].frac_coords)
        for i in top_idx if struct[i].specie.symbol in site_symbols
    }
    coords = []
    for lab in labels:
        if lab not in by_label:
            raise ValueError(
                f"label {lab!r} not among the surface atoms of "
                f"{Path(slab_2x1x1_ref).name} — available: "
                f"{', '.join(sorted(by_label))}")
        coords.append(by_label[lab])
    return coords
