"""
qe_slab_surface.py — Estágio 1: superfície pura de caulinita (001)/(010) como
sua própria célula vc-relax de referência, construída *aumentando só a altura
da caixa* da célula bulk de scf-kaolinite.in (sem SlabGenerator, sem
supercélula). O vetor de rede fora do plano é multiplicado por um escalar real
para abrir vácuo; a camada mantém sua geometria exata do bulk.

Diferença por plano (ver reporte.md):
  (001) clivamento basal natural de 0 ligações quebradas (Al-OH em cima,
        siloxano embaixo);
  (010) corte de borda ao longo do eixo b (y do bulk): a borda octaédrica de
        Al é exposta em +z (topo), as hidroxilas rompidas são curadas e os
        poliedros de borda truncados (octaedro de Al + tetraedro de Si) são
        completados com O + protonados (Al-OH aluminol + Si-OH silanol).

Todo parâmetro físico/numérico é lido das referências via qe_slab_common; nada
físico é hardcoded aqui.
"""

import itertools
from pathlib import Path

import numpy as np
from ase.data import atomic_numbers, covalent_radii
from pymatgen.core import Element, Structure
from pymatgen.io.ase import AseAtomsAdaptor

from qe_slab_common import (
    ROOT,
    assemble_namelists,
    assemble_species,
    build_molecule,
    count_by_species,
    fixed_indices,
    geometry_checks,
    load_ref,
    rescale_kmesh,
    write_qe_input,
    write_report_md,
)


# ------------------------------------------------------------ cura / completação de borda

def heal_cut_hydroxyls(bulk, stack_idx):
    """Reconecta o H hidroxila cuja ligação O-H seria rompida pelo corte de
    vácuo ao longo de `stack_idx`. make_surface abre o slab esticando um vetor
    de rede do bulk, então qualquer ligação O-H cuja imagem mínima cruza a
    fronteira 0/1 daquele eixo é quebrada, deixando o H perdido a ~2-3 Å do
    seu O. Para cada uma dessas ligações o H é movido para junto do seu
    próprio O parceiro ao longo do vetor O->H nativo do bulk (~0.97 Å) do lado
    do vácuo, mantendo a superfície totalmente hidroxilada — nenhum átomo é
    adicionado ou removido, estequiometria e ordem dos átomos preservadas.
    Ligações que cruzam apenas os eixos no plano ficam intocadas, então isso
    é um no-op para terminações que não rompem nenhuma ligação O-H (ex.: o
    clivamento basal do (001)).

    O O parceiro é o O mais próximo sob a convenção de imagem mínima (o mesmo
    raciocínio de rede/imagem mínima usado em bond_count e complete_edge_metals);
    um H hidroxila fica a ~0.97 Å dele, inequivocamente mais perto que qualquer
    outro O (> 1.9 Å).

    Retorna (coordenadas cartesianas curadas, [(H_idx, O_idx, bond_len), ...]).
    """
    frac = bulk.frac_coords
    lat = bulk.lattice.matrix
    syms = [s.specie.symbol for s in bulk]
    o_idx = [i for i, s in enumerate(syms) if s == "O"]
    cart = bulk.cart_coords.copy()
    healed = []
    for h in (i for i, s in enumerate(syms) if s == "H"):
        best_d, best_o, best_img = np.inf, None, None
        for o in o_idx:
            d0 = frac[h] - frac[o]
            for img in itertools.product((-1, 0, 1), repeat=3):
                d = np.linalg.norm((d0 + np.array(img)) @ lat)
                if d < best_d:
                    best_d, best_o, best_img = d, o, np.array(img)
        if best_d > 1.2:
            raise RuntimeError(
                f"H{h}: no O within 1.2 Å (nearest {best_d:.2f} Å); cannot "
                "identify the O-H bond to heal")
        if best_img[stack_idx] != 0:            # ligação rompida pelo corte de vácuo
            cart[h] = cart[best_o] + (frac[h] - frac[best_o] + best_img) @ lat
            healed.append((h, best_o, round(float(best_d), 3)))
    return cart, healed


def _bulk_oh_length(bulk):
    """Comprimento O-H nativo do bulk (média sobre as hidroxilas, imagem
    mínima) — usado para posicionar o H dos novos aluminois sem hardcodar
    nenhum comprimento de ligação."""
    frac = bulk.frac_coords
    lat = bulk.lattice.matrix
    syms = [s.specie.symbol for s in bulk]
    o_idx = [i for i, s in enumerate(syms) if s == "O"]
    lens = []
    for h in (i for i, s in enumerate(syms) if s == "H"):
        best = np.inf
        for o in o_idx:
            d0 = frac[h] - frac[o]
            for img in itertools.product((-1, 0, 1), repeat=3):
                best = min(best, np.linalg.norm((d0 + np.array(img)) @ lat))
        lens.append(best)
    return float(np.mean(lens))


def complete_edge_metals(bulk, healed_cart, stack_idx, bond_scale):
    """(010) borda: completa cada poliedro de metal truncado pelo corte de
    vácuo ao longo de `stack_idx` — o octaedro de Al (Al-OH aluminol) e o
    tetraedro de Si (Si-OH silanol) — e protona o O adicionado.

    O corte de vácuo rompe as ligações metal-O cuja imagem mínima cruza a
    fronteira 0/1 do eixo de empilhamento, deixando um metal de borda
    sub-coordenado (Al 4 em vez de 6; Si 3 em vez de 4). No bulk: `Al1` perde
    `O11` (2.04 Å) e `O20` (1.87 Å); `Si5` perde `O13` (1.64 Å). Após a
    inversão t1=-c em make_surface esses metais ficam expostos em +z. Para
    cada ligação metal-O rompida, um NOVO O é adicionado exatamente no vértice
    que faltava — O_new = cart[M] + (frac[O] - frac[M] + img) @ lattice — a
    mesma matemática de vetor de heal_cut_hydroxyls, mas criando um átomo novo
    em vez de mover um existente, fechando o poliedro na direção real do bulk
    (que aponta para o lado do vácuo). Cada O novo recebe um H a ~comprimento
    O-H nativo do bulk, colinear com M-O apontando para fora (para o vácuo) —
    um chute inicial que o vc-relax refina -> Al-OH / Si-OH.

    A face O inferior fica na região fixa (proxy do bulk). Nenhuma espécie
    nova é introduzida (só O e H), então ATOMIC_SPECIES é preservado.

    Retorna (cart estendido, species estendido,
    [(metal, M_idx, O_parceiro, d), ...]).
    """
    frac = bulk.frac_coords
    lat = bulk.lattice.matrix
    cart_bulk = bulk.cart_coords
    syms = [s.specie.symbol for s in bulk]
    o_idx = [i for i, s in enumerate(syms) if s == "O"]
    r_o = covalent_radii[atomic_numbers["O"]]
    oh_len = _bulk_oh_length(bulk)

    cart = [np.asarray(c, dtype=float) for c in healed_cart]
    species = list(bulk.species)
    added = []
    for metal in ("Al", "Si"):                # octaedro de Al + tetraedro de Si
        cutoff = bond_scale * (covalent_radii[atomic_numbers[metal]] + r_o)
        for m in [i for i, s in enumerate(syms) if s == metal]:
            for o in o_idx:
                d0 = frac[o] - frac[m]        # deslocamento metal -> O (imagem mínima)
                best_d, best_img = np.inf, None
                for img in itertools.product((-1, 0, 1), repeat=3):
                    d = np.linalg.norm((d0 + np.array(img)) @ lat)
                    if d < best_d:
                        best_d, best_img = d, np.array(img)
                if best_d <= cutoff and best_img[stack_idx] != 0:
                    # novo O no vértice faltante = metal + vetor metal->O do bulk
                    o_new = cart_bulk[m] + (d0 + best_img) @ lat
                    out = o_new - cart_bulk[m]
                    h_new = o_new + oh_len * out / np.linalg.norm(out)
                    cart.append(o_new)
                    species.append(Element("O"))
                    cart.append(h_new)
                    species.append(Element("H"))
                    added.append((metal, m, o, round(float(best_d), 3)))
    return np.array(cart), species, added


# --------------------------------------------------------- orientação / esticamento

def _ortho_frame(v0, v1):
    """Referencial ortonormal destrógiro [e0|e1|e2] (colunas) com e0 ao longo
    de v0 e e2 ao longo de v0 x v1."""
    e0 = v0 / np.linalg.norm(v0)
    e2 = np.cross(v0, v1)
    e2 /= np.linalg.norm(e2)
    e1 = np.cross(e2, e0)
    return np.column_stack([e0, e1, e2])


def _orient_and_stretch(t0, t1, s, place_cart, measure_cart, species,
                        vacuum_budget):
    """Constrói a célula de slab moldada no bulk com linhas {t0, t1, f*s}
    rotacionada rigidamente para que a normal da superfície seja Cartesiana
    +z (linhas no plano ficam com z = 0), e posiciona `place_cart` nela
    centralizada ao longo do eixo de vácuo.

    `f` é o escalar real que estica o vetor de empilhamento `s` para que o
    vácuo perpendicular acima de `measure_cart` seja igual a `vacuum_budget`
    — nunca um acréscimo vertical (0,0,z), então inclinação e todos os
    ângulos de célula são preservados (ideia.md). Retorna (Structure,
    normal = +z, f).
    """
    F = _ortho_frame(t0, t1)                 # e2 = normal da superfície no referencial do bulk
    n_hat = F[:, 2]
    ext_proj = measure_cart @ n_hat
    extent = ext_proj.max() - ext_proj.min()
    f = (extent + vacuum_budget) / abs(np.dot(s, n_hat))
    c_out = f * s
    if np.dot(n_hat, c_out) < 0.0:           # mantém célula destrógira (volume positivo)
        c_out = -c_out                       # normal passa a apontar para o lado +c_out (vácuo)

    # F.T rotaciona o referencial do bulk para o referencial canônico do slab:
    # t0 -> +x, plano t0/t1 -> plano xy, normal da superfície -> +z.
    lattice = np.array([t0, t1, c_out]) @ F
    new = Structure(lattice, species, place_cart @ F, coords_are_cartesian=True)
    fc = new.frac_coords
    fc[:, 2] = (fc[:, 2] - fc[:, 2].mean() + 0.5) % 1.0   # centraliza o slab ao longo do eixo de vácuo
    new = Structure(lattice, new.species, fc)
    return new, np.array([0.0, 0.0, 1.0]), f


def make_surface(bulk, miller, vacuum_budget, bond_scale):
    """Superfície pura construída aumentando a altura da caixa. A célula final
    é a célula do bulk com o vetor fora do plano multiplicado por um escalar
    real f para que o vácuo perpendicular acima da camada seja igual a
    `vacuum_budget`; a camada mantém sua geometria do bulk e só o vácuo cresce.

    Eixos no plano / de empilhamento lidos da célula do bulk:
      (001): no plano {a, b}, empilhamento c — clivamento basal natural de
             0 ligações quebradas (Al-OH em cima, siloxano embaixo);
      (010): no plano {a, c}, empilhamento b (eixo y do bulk). O segundo vetor
             no plano é tomado como **-c** (t1_sign = -1): isso reverte a
             normal da superfície de modo que a borda octaédrica de Al fique
             exposta em +z (topo, lado do vácuo/adsorbato), a orientação
             pedida (octaedros para cima, tetraedros para baixo). É uma
             reindexação própria (célula destrógira preservada, sem espelhar
             o cristal triclínico), verificada mantendo volume > 0 e as
             linhas no plano com z = 0. heal_cut_hydroxyls cura as O-H
             rompidas e complete_edge_metals fecha os poliedros de borda com
             O + H (Al-OH aluminol + Si-OH silanol) antes do vc-relax.

    A célula é rotacionada rigidamente para que a normal seja exatamente +z.
    Retorna (Structure, normal = +z, axis_map, f, healed, added) onde
    axis_map[i] = eixo do bulk do qual deriva o eixo i (no plano) do slab,
    healed = pares (H, O, bond) reconectados e added = [(metal, M, O, d), ...]
    dos aluminois/silanois adicionados (vazio para (001))."""
    if miller == (0, 0, 1):
        inplane, stack_idx, t1_sign = (0, 1), 2, 1
    elif miller == (0, 1, 0):
        inplane, stack_idx, t1_sign = (0, 2), 1, -1
    else:
        raise ValueError(f"no surface rule for miller {miller}")
    axis_map = {0: inplane[0], 1: inplane[1]}

    L = bulk.lattice.matrix
    t0 = L[inplane[0]]
    t1 = t1_sign * L[inplane[1]]
    s = L[stack_idx]
    # Cura qualquer ligação O-H que o corte de vácuo ao longo de `stack_idx`
    # romperia; no-op quando o corte não quebra nenhuma O-H (ex.: (001)).
    healed_cart, healed = heal_cut_hydroxyls(bulk, stack_idx)
    if miller == (0, 1, 0):
        # Completa os poliedros de metal de borda (Al-OH + Si-OH); (001) idêntico.
        cart, species, added = complete_edge_metals(bulk, healed_cart, stack_idx, bond_scale)
    else:
        cart, species, added = healed_cart, list(bulk.species), []
    # As coordenadas cartesianas já estão no referencial {t0, t1, s} (sem
    # reorientação a desfazer), então vão direto ao núcleo compartilhado.
    new, normal, f = _orient_and_stretch(
        t0, t1, s, cart, cart, species, vacuum_budget)
    return new, normal, axis_map, f, healed, added


# -------------------------------------------------- Estágio 1: gerador

def generate_surface(miller, *, kaolinite_ref, molecule_ref, vacuum_min,
                     ads_distance, bond_scale, out_dir):
    """Estágio 1 — superfície pura (001)/(010) como sua própria célula
    vc-relax, construída aumentando só a altura da caixa (make_surface).
    Escreve <out_dir>/vc-relax-<prefix>.in (+ .cif + .md).

    O vácuo fora do plano já reserva o espaço que a molécula de
    metilmercúrio vai precisar (vacuum_min + extensão em z da molécula +
    distância de posicionamento, ideia.md §3), então a rede não vai precisar
    crescer na etapa de adsorção.
    """
    kaol = load_ref(kaolinite_ref, with_structure=True)
    mol_ref = load_ref(molecule_ref, with_structure=False)
    bulk = AseAtomsAdaptor.get_structure(kaol.atoms)
    _, mol_span, _ = build_molecule(mol_ref)

    vacuum = vacuum_min + mol_span + ads_distance
    struct, normal, axis_map, f, healed, added = make_surface(bulk, miller, vacuum, bond_scale)
    kmesh = rescale_kmesh(kaol.kmesh, axis_map, {0: 1, 1: 1})

    mstr = "".join(str(x) for x in miller)
    prefix = f"{kaol.namelists['control']['prefix']}-slab-{mstr}"
    outdir = Path(out_dir)

    species = assemble_species(kaol, mol_ref, adsorbed=False)
    if {s.specie.symbol for s in struct} != {sp[0] for sp in species}:
        raise RuntimeError("structure species do not match ATOMIC_SPECIES")
    namelists = assemble_namelists(kaol, mol_ref, False, prefix,
                                   calculation="vc-relax", nbnd_mult=1)
    checks = geometry_checks(struct, normal, 0, False, vacuum)
    fixed = fixed_indices(struct, miller, normal, n_slab=len(struct), bond_scale=bond_scale)

    outdir.mkdir(parents=True, exist_ok=True)
    in_path = outdir / f"vc-relax-{prefix}.in"
    write_qe_input(in_path, namelists, species, struct, kmesh, kaol.koffset,
                   fixed=fixed)
    struct.to(filename=str(outdir / f"{prefix}.cif"))

    a, b, c = (np.linalg.norm(v) for v in struct.lattice.matrix)
    stack_idx = ({0, 1, 2} - {axis_map[0], axis_map[1]}).pop()
    fix_by_sp = count_by_species(struct, fixed)
    print(f"== {prefix}  (Stage 1: surface, vc-relax) ==")
    print(f"  input        : {in_path.relative_to(ROOT)}")
    print(f"  atoms        : {len(struct)}  (species: {[sp[0] for sp in species]})")
    print(f"  lattice |a|,|b|,|c| : {a:.3f}, {b:.3f}, {c:.3f} Å")
    print(f"  out-of-plane : {f:.4f} × bulk axis {'abc'[stack_idx]} "
          f"(vacuum budget {vacuum:.2f} Å = {vacuum_min} + molecule "
          f"{mol_span:.2f} + {ads_distance})")
    print(f"  vacuum gap   : {checks['vacuum_gap']} Å (required ≥ {vacuum:.2f})")
    print(f"  fixed atoms  : {len(fixed)}/{len(struct)} {fix_by_sp} "
          f"(if_pos 0 0 0; paper layer constraint)")
    print(f"  k-mesh       : {' '.join(map(str, kmesh))} (bulk "
          f"{' '.join(map(str, kaol.kmesh))}, axis map {axis_map}, no supercell)")
    if healed:
        pairs = ", ".join(f"H{h}-O{o} ({d} Å)" for h, o, d in healed)
        print(f"  healed O-H   : {pairs} reattached across the "
              f"{'abc'[stack_idx]} cut (fully hydroxylated edge)")
    if added:
        pairs = ", ".join(f"{mt}{m}+O ({d} Å)" for mt, m, o, d in added)
        print(f"  M-OH added   : {len(added)} O + {len(added)} H completing "
              f"edge polyhedra at {pairs} (aluminol + silanol edge, +z)")
    print()

    md = [
        f"- **entrada**: `{in_path.relative_to(ROOT)}`",
        f"- **átomos**: {len(struct)} (espécies: {[sp[0] for sp in species]})",
        f"- **rede \\|a\\|,\\|b\\|,\\|c\\|**: {a:.3f}, {b:.3f}, {c:.3f} Å",
        f"- **fora do plano**: {f:.4f} × eixo bulk {'abc'[stack_idx]} "
        f"(orçamento de vácuo {vacuum:.2f} Å = {vacuum_min} + molécula "
        f"{mol_span:.2f} + {ads_distance})",
        f"- **gap de vácuo**: {checks['vacuum_gap']} Å (requerido ≥ {vacuum:.2f})",
        f"- **átomos fixos**: {len(fixed)}/{len(struct)} {fix_by_sp} "
        f"(if_pos 0 0 0; constrangimento de camada do artigo)",
        f"- **k-mesh**: {' '.join(map(str, kmesh))} (bulk "
        f"{' '.join(map(str, kaol.kmesh))}, axis map {axis_map}, sem supercélula)",
    ]
    if healed:
        pairs = ", ".join(f"H{h}-O{o} ({d} Å)" for h, o, d in healed)
        md.append(f"- **O-H curados**: {pairs} reconectados através do corte em "
                  f"{'abc'[stack_idx]} (borda totalmente hidroxilada)")
    if added:
        pairs = ", ".join(f"{mt}{m}+O ({d} Å)" for mt, m, o, d in added)
        md.append(f"- **M-OH adicionados**: {len(added)} O + {len(added)} H "
                  f"completando poliedros de borda em {pairs} "
                  f"(borda aluminol + silanol protonada, +z)")
    write_report_md(outdir, prefix, md)

    return {"prefix": prefix, "kmesh": kmesh, "checks": checks,
            "lattice": (a, b, c), "n_atoms": len(struct), "f": f,
            "healed": healed, "added": added}
