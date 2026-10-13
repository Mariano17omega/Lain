"""
qe_slab_supercell.py — Estágio 2: supercélula 2x1x1 construída inteiramente a
partir da superfície JÁ RELAXADA do plano (scf-kaolinite-slab-<hkl>.in),
emitida como sua própria célula vc-relax (mesmo padrão do Estágio 1: só a
célula no plano relaxa, camada da base fixa). Rode depois que o vc-relax do
Estágio 1 (qe_slab_surface.generate_surface) tiver convergido e o usuário tiver
produzido a referência relaxada.

Geometria *e* todo parâmetro físico/numérico (cutoffs, espécies,
pseudopotenciais, k-mesh base, prefix, ...) vêm dessa única referência;
scf-kaolinite.in (bulk) não é tocado aqui — é Estágio 1 apenas.
"""

from pathlib import Path

import numpy as np
from pymatgen.io.ase import AseAtomsAdaptor

from qe_slab_common import (
    ROOT,
    assemble_namelists,
    assemble_species,
    count_by_species,
    fixed_indices,
    geometry_checks,
    load_ref,
    rescale_kmesh,
    write_qe_input,
    write_report_md,
)


def generate_supercell(miller, *, slab_ref, out_dir, vacuum_min, supercell_mult,
                       bond_scale):
    """Estágio 2 — supercélula 2x1x1 (dobra o eixo 0 da célula, sempre o
    vetor no plano derivado do bulk-a por construção do Estágio 1) construída
    inteiramente a partir da referência JÁ RELAXADA do plano — `slab_ref`
    (`scf-kaolinite-slab-001.in` / `-010.in`) — como sua própria célula
    `vc-relax` (mesmo padrão do Estágio 1: `cell_dofree='2Dxy'`, só a célula
    no plano relaxa, camada da base fixa via `fixed_indices` recalculado na
    estrutura já dobrada). Geometria *e* todo parâmetro físico/numérico
    (cutoffs, espécies, pseudopotenciais, k-mesh base, prefix, ...) vêm dessa
    única referência; `scf-kaolinite.in` (bulk) não é tocado aqui — é
    Estágio 1 apenas.

    A referência do Estágio 1 é escrita com a normal da superfície exatamente
    em +z e relaxada sob `cell_dofree='2Dxy'` (só a célula no plano se move),
    então `read_espresso_in` já devolve a célula com a normal em +z — nenhuma
    reorientação/recuperação de normal é necessária aqui (ao contrário de um
    round trip via CIF, que reorientaria a célula).

    Escreve <out_dir>/vc-relax-<prefix>-2x1x1.in (+ .cif).
    """
    miller = tuple(miller)
    ref = load_ref(slab_ref, with_structure=True)

    struct = AseAtomsAdaptor.get_structure(ref.atoms)
    # A referência do Estágio 1 carrega if_pos (constrangimentos de camada do
    # vc-relax) como a propriedade de sítio 'selective_dynamics' do pymatgen,
    # mas esses índices não correspondem à supercélula dobrada; descarta
    # antes de make_supercell (senão AseAtomsAdaptor.get_atoms reaplicaria o
    # padrão errado) e recalcula via fixed_indices já na estrutura 2x1x1
    # abaixo, mesmo padrão do Estágio 1.
    if "selective_dynamics" in struct.site_properties:
        struct.remove_site_property("selective_dynamics")
    struct.make_supercell([supercell_mult, 1, 1])

    # Reescala a própria malha da referência (eixo 0, sempre o eixo dobrado);
    # sem referência cruzada ao bulk aqui.
    kmesh = rescale_kmesh(ref.kmesh, {0: 0, 1: 1}, {0: supercell_mult, 1: 1})

    prefix = f"{ref.namelists['control']['prefix']}-2x1x1"
    outdir = Path(out_dir)

    # mol_ref não é necessário: a supercélula pura não tem adsorbato, então
    # tanto assemble_species quanto assemble_namelists o ignoram aqui (adsorbed=False).
    species = assemble_species(ref, None, adsorbed=False)
    if {s.specie.symbol for s in struct} != {sp[0] for sp in species}:
        raise RuntimeError(
            f"structure species {{{','.join(sorted({s.specie.symbol for s in struct}))}}} "
            f"do not match ATOMIC_SPECIES {{{','.join(sorted(sp[0] for sp in species))}}}")
    namelists = assemble_namelists(ref, None, False, prefix,
                                   calculation="vc-relax", nbnd_mult=supercell_mult)
    normal = np.array([0.0, 0.0, 1.0])
    checks = geometry_checks(struct, normal, 0, False, vacuum_min)
    fixed = fixed_indices(struct, miller, normal, n_slab=len(struct), bond_scale=bond_scale)

    outdir.mkdir(parents=True, exist_ok=True)
    in_path = outdir / f"vc-relax-{prefix}.in"
    write_qe_input(in_path, namelists, species, struct, kmesh, ref.koffset,
                   fixed=fixed)
    struct.to(filename=str(outdir / f"{prefix}.cif"))

    a, b, c = (np.linalg.norm(v) for v in struct.lattice.matrix)
    fix_by_sp = count_by_species(struct, fixed)
    print(f"== {prefix}  (Stage 2: 2x1x1 supercell, vc-relax) ==")
    print(f"  from ref     : {Path(slab_ref).relative_to(ROOT)}  (Stage 1 relaxed)")
    print(f"  input        : {in_path.relative_to(ROOT)}")
    print(f"  atoms        : {len(struct)}  (species: {[sp[0] for sp in species]})")
    print(f"  lattice |a|,|b|,|c| : {a:.3f}, {b:.3f}, {c:.3f} Å  (a doubled)")
    print(f"  vacuum gap   : {checks['vacuum_gap']} Å (required ≥ {vacuum_min})")
    print(f"  fixed atoms  : {len(fixed)}/{len(struct)} {fix_by_sp} "
          f"(if_pos 0 0 0; paper layer constraint)")
    print(f"  k-mesh       : {' '.join(map(str, kmesh))} (ref {' '.join(map(str, ref.kmesh))}, "
          f"a halved for the 2x supercell)")
    print()

    md = [
        f"- **a partir da referência**: `{Path(slab_ref).relative_to(ROOT)}` (Estágio 1 relaxado)",
        f"- **entrada**: `{in_path.relative_to(ROOT)}`",
        f"- **átomos**: {len(struct)} (espécies: {[sp[0] for sp in species]})",
        f"- **rede \\|a\\|,\\|b\\|,\\|c\\|**: {a:.3f}, {b:.3f}, {c:.3f} Å (a dobrado)",
        f"- **gap de vácuo**: {checks['vacuum_gap']} Å (requerido ≥ {vacuum_min})",
        f"- **átomos fixos**: {len(fixed)}/{len(struct)} {fix_by_sp} "
        f"(if_pos 0 0 0; constrangimento de camada do artigo)",
        f"- **k-mesh**: {' '.join(map(str, kmesh))} (referência {' '.join(map(str, ref.kmesh))}, "
        f"a dividido por 2 para a supercélula 2x)",
    ]
    write_report_md(outdir, prefix, md)

    return {"prefix": prefix, "kmesh": kmesh, "checks": checks,
            "lattice": (a, b, c), "n_atoms": len(struct)}
