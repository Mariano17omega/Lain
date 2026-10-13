"""
qe_slab_common.py — núcleo compartilhado dos três estágios de geração de
entradas pw.x do Quantum ESPRESSO para caulinita:

    qe_slab_surface.py    (Estágio 1: superfície pura a partir do bulk)
    qe_slab_supercell.py  (Estágio 2: supercélula 2x1x1 da superfície relaxada)
    qe_slab_adsorb.py     (Estágio 3: H3CHg adsorvido na supercélula relaxada)

Todo parâmetro físico/numérico (célula, posições, espécies, massas,
pseudopotenciais, cutoffs, smearing, conv_thr, mixing_beta, k-mesh, prefixos,
pseudo_dir, outdir, ...) é lido em tempo de geração a partir de entradas de
referência validadas — nunca hardcoded. Este módulo só contém lógica
compartilhada (E/S, propagação de namelists, k-mesh, constrangimentos,
verificações geométricas); não define nenhuma referência de arquivo nem
constante numérica ajustável.

Os caminhos de referência (scf-kaolinite.in, scf-H3CHg.in,
scf-kaolinite-slab-<hkl>.in, scf-kaolinite-slab-<hkl>-2x1x1.in) e as
constantes metodológicas do pipeline (vácuo mínimo, distância de
posicionamento, tolerância de ligação, guardas geométricas do Estágio 3,
multiplicidade de supercélula, nomes de diretório de saída) são definidos no
topo de cada script `generate_*.py` (um por estágio/plano) e passados
explicitamente para as funções de estágio (`generate_surface`,
`generate_supercell`, `generate_adsorbed`) — esse é o lugar único para o
usuário ajustá-los, sem tocar neste núcleo.

E/S de arquivo é feita com o módulo Quantum ESPRESSO do ASE (ase.io.espresso):
read_fortran_namelist / read_espresso_in / get_atomic_species /
get_atomic_positions para leitura, write_espresso_in para escrita. Manipulação
de estrutura e adsorção usam pymatgen.
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from ase.constraints import FixAtoms
from ase.data import atomic_numbers, covalent_radii
from ase.io.espresso import (
    get_atomic_positions,
    get_atomic_species,
    read_espresso_in,
    read_fortran_namelist,
    write_espresso_in,
)
from pymatgen.core import Molecule
from pymatgen.io.ase import AseAtomsAdaptor

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ leitura

def load_ref(path, with_structure):
    """Lê uma entrada pw.x de referência com ASE.

    Retorna um namespace com: namelists (dicts tipados de
    read_fortran_namelist), species [(symbol, mass, upf)] de
    get_atomic_species, kmesh/koffset a partir do cartão K_POINTS automatic
    (None para gamma), e ou .atoms (Atoms completo via read_espresso_in,
    para o bulk periódico) ou .positions (tuplas símbolo/coordenada via
    get_atomic_positions, para a caixa de molécula ibrav=14 que
    read_espresso_in não consegue carregar)."""
    with open(path) as fd:
        namelists, cards = read_fortran_namelist(fd)
    system = namelists["system"]
    species = get_atomic_species(cards, n_species=system["ntyp"])

    kmesh = koffset = None
    for j, line in enumerate(cards):
        tok = line.split()
        if tok and tok[0].lower() == "k_points" and "automatic" in line.lower():
            after = [ln for ln in cards[j + 1:] if ln.strip()]
            nums = [int(x) for x in after[0].split()[:6]]
            kmesh, koffset = tuple(nums[:3]), tuple(nums[3:6])
            break

    ref = SimpleNamespace(path=Path(path), namelists=namelists, species=species,
                          kmesh=kmesh, koffset=koffset, atoms=None, positions=None)
    if with_structure:
        ref.atoms = read_espresso_in(path)
    else:
        header = next(ln for ln in cards
                      if ln.strip().lower().startswith("atomic_positions"))
        if "angstrom" not in header.lower():
            raise ValueError(f"{path}: expected ATOMIC_POSITIONS in angstrom")
        ref.positions = get_atomic_positions(cards, n_atoms=system["nat"])
    return ref


def build_molecule(ref):
    """Molécula com o átomo âncora (Hg, o mais pesado) na origem e o eixo
    âncora->C ao longo de +z, como exigido por AdsorbateSiteFinder.add_adsorbate
    com translate=False (a âncora cai exatamente no sítio de adsorção, grupo
    metila apontando para longe da superfície = ligação Hg-down, como no
    artigo de referência)."""
    symbols = [p[0] for p in ref.positions]
    coords = np.array([p[1] for p in ref.positions])
    anchor = int(np.argmax([atomic_numbers[s] for s in symbols]))
    coords = coords - coords[anchor]
    heavy = [k for k, s in enumerate(symbols) if s != "H" and k != anchor]
    axis = coords[heavy[0]] / np.linalg.norm(coords[heavy[0]])
    if axis[2] < 0.98:
        raise ValueError(
            f"{ref.path}: molecule axis (anchor->{symbols[heavy[0]]}) is not "
            "along +z; reorient the reference geometry"
        )
    span = coords[:, 2].max() - coords[:, 2].min()
    return Molecule(symbols, coords), span, anchor


# ------------------------------------------------------------ ligações / coordenação

def bond_count(struct, scale, rmax=3.0):
    """Número de ligações covalentes (distância do par < scale * soma dos
    raios covalentes, tabela ASE). Usado de forma diferencial (bulk vs
    slab) para ranquear terminações de slab e para contar coordenação."""
    cnt = 0
    for i, nbrs in enumerate(struct.get_all_neighbors(rmax)):
        ri = covalent_radii[atomic_numbers[struct[i].specie.symbol]]
        for nb in nbrs:
            rj = covalent_radii[atomic_numbers[nb.specie.symbol]]
            if nb.nn_distance <= scale * (ri + rj):
                cnt += 1
    return cnt // 2


# ------------------------------------------------------------------- k-points

def rescale_kmesh(bulk_mesh, axis_map, mults):
    """Malha do slab a partir da malha do bulk: divide pela multiplicidade de
    supercélula do eixo do bulk do qual cada vetor no plano do slab deriva;
    1 ao longo do vácuo."""
    k = [1, 1, 1]
    for i in (0, 1):
        k[i] = max(1, int(round(bulk_mesh[axis_map[i]] / mults[i])))
    k[2] = 1
    return tuple(k)


# ------------------------------------------------------ construção de entrada QE

def assemble_namelists(kaol, mol_ref, adsorbed, prefix, calculation="vc-relax",
                       nbnd_mult=1):
    """Regras de propagação (ver reporte.md):
    - control/system/electrons partem da referência primária (bulk no
      Estágio 1, superfície relaxada no Estágio 2, supercélula relaxada no
      Estágio 3);
    - prefix renomeado; pseudo_dir mantido da referência (decisão do usuário,
      também para o sistema adsorvido); nat/ntyp descartados —
      write_espresso_in os deriva da estrutura, garantindo consistência;
    - sistema puro: `calculation` escolhido pelo chamador — 'vc-relax' para
      a relaxação de superfície do Estágio 1 (adiciona &ions vazio + &cell
      com cell_dofree='2Dxy' para que só a célula no plano relaxe e a altura
      de vácuo reservada não possa encolher), 'relax' para relaxação iônica
      de célula fixa (adiciona só &ions vazio), 'scf' para o ponto único da
      supercélula do Estágio 2 (sem &ions/&cell). nbnd é escalado por
      `nbnd_mult` (1 para a célula de superfície única, a multiplicidade da
      supercélula do Estágio 2 para a 2x1x1);
    - adsorvido (Estágio 3): calculation = 'relax' (célula fixa, herdada
      intacta da referência 2x1x1 — decisão do usuário: adiciona só &ions
      vazio) — a posição do adsorbato proposta pelo pymatgen é só um chute
      inicial e precisa relaxar. nbnd descartado
      (padrão do QE; a contagem de valência da molécula não é derivável das
      entradas de referência), occupations/smearing/degauss tomados da
      referência da molécula (o adsorbato pode fechar o gap), mixing_beta =
      o mais conservador (menor) das duas referências.
    """
    ctrl = dict(kaol.namelists["control"])
    ctrl["prefix"] = prefix
    sys_ = dict(kaol.namelists["system"])
    sys_.pop("nat", None)
    sys_.pop("ntyp", None)
    ele = dict(kaol.namelists["electrons"])
    extra = {}
    if not adsorbed:
        ctrl["calculation"] = calculation
        if "nbnd" in sys_:
            sys_["nbnd"] = int(round(sys_["nbnd"] * nbnd_mult))
        if calculation == "vc-relax":
            cell = dict(kaol.namelists.get("cell", {}))
            cell["cell_dofree"] = "2Dxy"
            extra = {"ions": {}, "cell": cell}
        elif calculation == "relax":
            extra = {"ions": {}}
        # scf: ponto único, sem &ions/&cell
    else:
        ctrl["calculation"] = "relax"   # relaxa adsorbato + superfície; célula fixa
        ctrl["etot_conv_thr"] = 1e-04
        ctrl["forc_conv_thr"] = 1e-03
        extra = {"ions": {}}
        sys_.pop("nbnd", None)
        msys = mol_ref.namelists["system"]
        if "occupations" in msys:
            sys_["occupations"] = msys["occupations"]
            for key in ("smearing", "degauss"):
                if key in msys:
                    sys_[key] = msys[key]
        mb_k = kaol.namelists["electrons"].get("mixing_beta")
        mb_m = mol_ref.namelists["electrons"].get("mixing_beta")
        if mb_k is not None and mb_m is not None:
            ele["mixing_beta"] = min(mb_k, mb_m)
    return {"control": ctrl, "system": sys_, "electrons": ele, **extra}


def assemble_species(kaol, mol_ref, adsorbed):
    """Espécies da referência primária literalmente; para o sistema adsorvido
    anexa as espécies da molécula ainda não presentes (Hg, C). O H fica
    portanto unificado ao pseudopotencial da caulinita (decisão do usuário,
    anotada em reporte.md)."""
    species = list(kaol.species)
    if adsorbed:
        have = {s[0] for s in species}
        for sp in mol_ref.species:
            if sp[0] not in have:
                species.append(sp)
                have.add(sp[0])
    return species


def write_qe_input(path, namelists, species, struct, kmesh, koffset, fixed=None):
    """Escreve com write_espresso_in do ASE: massas de referência são
    carregadas via atoms.set_masses(), nomes de arquivo de pseudopotencial
    via o dict pseudopotentials; célula ibrav=0 + posições em coordenadas
    cristalinas + nat/ntyp são derivados do próprio objeto Atoms. Os índices
    de `fixed` viram uma constraint FixAtoms do ASE, que o escritor emite
    como flags if_pos '0 0 0'."""
    import io
    import re

    atoms = AseAtomsAdaptor.get_atoms(struct)
    if fixed:
        atoms.set_constraint(FixAtoms(indices=list(fixed)))
    # O round trip pymatgen->ASE anexa momentos magnéticos (zeros nos átomos
    # do slab, NaN nos átomos de adsorbato anexados); o ASE então separaria
    # espécies por magmom distinto e emitiria nspin/starting_magnetization.
    # Não faz parte das entradas de referência -> descarta.
    atoms.set_initial_magnetic_moments(None)
    mass_of = {sym: mass for sym, mass, _ in species}
    atoms.set_masses([mass_of[s] for s in atoms.get_chemical_symbols()])

    buf = io.StringIO()
    write_espresso_in(
        buf,
        atoms,
        input_data=namelists,
        pseudopotentials={sym: upf for sym, _, upf in species},
        kpts=kmesh,
        koffset=koffset,
        crystal_coordinates=True,
    )
    content = buf.getvalue()
    # Remove blocos de namelists vazios (&CELL\n/, &FCP\n/, &RISM\n/)
    content = re.sub(r"&(CELL|FCP|RISM)\s*\n\s*/\n?", "", content, flags=re.IGNORECASE)

    with open(path, "w") as fd:
        fd.write(content)


def write_report_md(outdir, prefix, lines):
    """Salva o resumo de geração (mesmo conteúdo impresso no terminal) como
    Markdown em outdir/<prefix>.md, ao lado do .in/.cif."""
    path = Path(outdir) / f"{prefix}.md"
    path.write_text("\n".join([f"# {prefix}", ""] + lines) + "\n")
    return path


# ---------------------------------------------------- dinâmica seletiva

def fixed_indices(struct, miller, normal, n_slab=None, *, bond_scale):
    """Átomos do slab a congelar (QE if_pos = 0 0 0), conforme o artigo de
    referência (Guo et al. 2025, Models): no Kln(001) "a geometria da
    camada tetraédrica de silício inferior (O–Si–O) permanece constrangida"
    enquanto a camada octaédrica Al–O–H relaxa; no Kln(010) só relaxam "a
    camada tetraédrica de silício superior (Si–O–H) e a camada octaédrica
    de alumínio (Al–O–H)".

    (001): fixed = todo Si mais todo O ligado a um Si (ligação = distância
    < bond_scale x soma dos raios covalentes, mesmo critério do ranking de
    terminação) — exatamente a folha basal-O/Si/O-apical, sem índices
    escolhidos à mão. (010): o modelo de borda mais espesso do artigo é
    adaptado ao nosso slab de uma camada do bulk como fixed = átomos abaixo
    do plano médio do slab ao longo da normal da superfície, para que as
    unidades de borda superior expostas (Si–O–H / Al–O–H) relaxem.

    Só os primeiros n_slab sítios (o slab em si) são considerados, para que
    um futuro sistema adsorvido (molécula anexada depois do slab) congele
    os mesmos átomos. Sob vc-relax if_pos zera as forças; átomos congelados
    ainda seguem a deformação homogênea de célula no plano permitida por
    cell_dofree='2Dxy', mantendo a folha comensurável com a célula.
    """
    n_slab = len(struct) if n_slab is None else n_slab
    syms = np.array([s.specie.symbol for s in struct])[:n_slab]
    n_hat = np.asarray(normal, dtype=float)
    n_hat = n_hat / np.linalg.norm(n_hat)
    proj = struct.cart_coords[:n_slab] @ n_hat
    mid = 0.5 * (proj.min() + proj.max())

    if miller == (0, 0, 1):
        si = np.flatnonzero(syms == "Si")
        if proj[si].mean() > mid:
            raise RuntimeError("(001) Si sheet is not the bottom layer")
        cut = bond_scale * (covalent_radii[atomic_numbers["Si"]]
                            + covalent_radii[atomic_numbers["O"]])
        o_idx = np.flatnonzero(syms == "O")
        frac = struct.frac_coords
        d = struct.lattice.get_all_distances(frac[o_idx], frac[si])
        fixed = sorted(si.tolist() + o_idx[(d < cut).any(axis=1)].tolist())
    elif miller == (0, 1, 0):
        fixed = np.flatnonzero(proj < mid).tolist()
    else:
        raise ValueError(f"no constraint rule for miller {miller}")
    if not 0 < len(fixed) < n_slab:
        raise RuntimeError(f"implausible fixed-atom set: {len(fixed)}/{n_slab}")
    return fixed


def count_by_species(struct, indices):
    """Conta `indices` por símbolo de espécie (resumo de átomos fixos nos logs)."""
    counts = {}
    for i in indices:
        sym = struct[i].specie.symbol
        counts[sym] = counts.get(sym, 0) + 1
    return counts


# ------------------------------------------------------------------- verificações

def geometry_checks(struct, normal, n_mol_atoms, adsorbed, required_gap):
    """Gap de vácuo ao longo da normal da superfície (>= required_gap: o
    orçamento completo que reserva espaço para a molécula em slabs puros, o
    vácuo mínimo do estágio quando o adsorbato já ocupa parte dele) e, se
    adsorvido,
    orientação Hg-down + distância de ancoragem do Hg. Retorna um dict para
    o resumo."""
    n_hat = np.asarray(normal, dtype=float)
    n_hat = n_hat / np.linalg.norm(n_hat)
    proj = struct.cart_coords @ n_hat
    height = abs(np.dot(struct.lattice.matrix[2], n_hat))
    gap = height - (proj.max() - proj.min())
    if gap < required_gap - 1e-6:
        raise RuntimeError(f"vacuum gap {gap:.2f} Å < required {required_gap} Å")
    out = {"vacuum_gap": round(float(gap), 2)}
    if adsorbed:
        n_slab = len(struct) - n_mol_atoms
        hg_idx = n_slab  # adsorbato anexado na ordem da molécula, âncora primeiro
        c_idx = [k for k in range(n_slab, len(struct))
                 if struct[k].specie.symbol == "C"][0]
        if (proj[c_idx] - proj[hg_idx]) <= 0:
            raise RuntimeError("adsorbate is not Hg-down (C below Hg)")
        nbrs = [nb for nb in struct.get_neighbors(struct[hg_idx], r=3.5)
                if nb.index < n_slab]
        nearest = min(nbrs, key=lambda nb: nb.nn_distance)
        o_nbrs = [nb for nb in nbrs if nb.specie.symbol == "O"]
        if not o_nbrs:
            raise RuntimeError("no surface O within 3.5 Å of Hg — not O-anchored")
        nearest_o = min(o_nbrs, key=lambda nb: nb.nn_distance)
        out["hg_nearest"] = (nearest.specie.symbol, round(float(nearest.nn_distance), 3))
        out["hg_O"] = round(float(nearest_o.nn_distance), 3)
        if nearest.nn_distance < 1.5:
            raise RuntimeError(f"Hg clashes with {nearest.specie.symbol} "
                               f"at {nearest.nn_distance:.2f} Å")
    return out
