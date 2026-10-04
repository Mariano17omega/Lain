"""Band detection: which bands.x products belong together, and what is missing or inconsistent.

With a spin-polarized SCF, bands.x runs twice (``spin_component`` 1 and 2 of ``&BANDS``), each run
writing its own ``filband`` and ``<filband>.gnu``. The ↑ files live in the ``gnu`` / ``filband``
roles and the ↓ ones in ``gnu_down`` / ``filband_down``. Pairing needs to know that the run has
spin, which may only be known once the SCF output was found in a neighbour folder, so it runs in
``finalize`` (``assign_channels``), not in ``select``.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...sniff import FileKind, FileSniff
from ..base import DetectionResult, FolderListing, Method, SniffFn
from .data import CHANNEL_ROLES, read_bands_input

EIGEN_SOURCES = ("gnu", "filband", "bands_out")
KIND_OF_ROLE = {"gnu": FileKind.GNU_DATA, "filband": FileKind.FILBAND}  # ↑ role → kind of file
CHANNEL_SYMBOL = {"up": "↑", "down": "↓"}
# ``up``, ``dw``, ``dn`` or ``down`` as a word of the file name (``bands_up.dat.gnu``, not ``group``).
_CHANNEL_TOKEN = re.compile(r"(?<![a-z])(up|dw|dn|down)(?![a-z])", re.I)


def named_by_bandsx(
    role_id: str,
    candidates: list[Path],
    sniffs: dict[Path, FileSniff],
    result: DetectionResult,
) -> Path | None:
    """The ``.gnu`` / ``filband`` file a bands.x output says it wrote (or the ``.gnu`` of the
    chosen ``filband``)."""
    names = []
    for path in candidates + list(sniffs):
        s = sniffs.get(path)
        if s and s.bandsx:
            names.append(s.bandsx.gnu_name if role_id == "gnu" else s.bandsx.filband_name)
    if role_id == "gnu":
        names += [f"{p.name}.gnu" for p in result.files.get("filband", [])]
    by_name = {p.name: p for p in candidates}
    for name in names:
        if name and Path(name).name in by_name:
            return by_name[Path(name).name]
    return None


def has_spin(result: DetectionResult, sniff: SniffFn) -> bool:
    """Is the band run spin-polarized (collinear), judged by the SCF or the pw.x bands output?"""
    for role in ("scf_out", "bands_out"):
        path = result.file(role)
        if path is not None and (pw := sniff(path).pw) is not None and pw.spin_polarized:
            return True
    return False


def _channel_of_name(name: str) -> str | None:
    match = _CHANNEL_TOKEN.search(name)
    if match is None:
        return None
    return "up" if match.group(1).lower() == "up" else "down"


def pair_channels(
    kind: str,
    candidates: list[Path],
    result: DetectionResult,
    sniffs: dict[Path, FileSniff],
) -> tuple[dict[str, Path], list[Path]]:
    """Channel → file for the ``kind`` (``gnu`` / ``filband``) candidates that can be identified:
    by the bands.x input (``spin_component``, ``filband``), else by the file a bands.x output says
    it wrote (for the channel left without an input), else by ``up`` / ``dw`` in the name.

    Also returns the files that the bands.x inputs of *both* channels name (a repeated ``filband``):
    such a file holds whichever run was last, so it is given to no channel.
    """
    by_name = {p.name: p for p in candidates}
    named: list[tuple[str, Path]] = []
    for path in result.files.get("bandsx_in", []):
        parsed = read_bands_input(path)
        if parsed is None:
            continue
        filband = Path(str(parsed.get("bands", "filband", "bands.out"))).name
        channel = "down" if parsed.get("bands", "spin_component", 1) == 2 else "up"
        target = by_name.get(filband + (".gnu" if kind == "gnu" else ""))
        if target is not None:
            named.append((channel, target))
    shared = sorted({t for c, t in named if (_other(c), t) in named})
    found: dict[str, Path] = {}
    for channel, target in named:
        if target not in shared:
            found.setdefault(channel, target)

    written = []
    for s in sniffs.values():
        name = None
        if s.bandsx:
            name = s.bandsx.gnu_name if kind == "gnu" else s.bandsx.filband_name
        path = by_name.get(Path(name).name) if name else None
        if path is not None and path not in written and path not in shared:
            written.append(path)
    open_files = [p for p in written if p not in found.values()]
    open_channels = [c for c in CHANNEL_SYMBOL if c not in found]
    if found and len(open_files) == 1 and len(open_channels) == 1:
        found[open_channels[0]] = open_files[0]

    for path in candidates:
        channel = _channel_of_name(path.name)
        if channel and channel not in found and path not in found.values() and path not in shared:
            found[channel] = path
    return found, shared


def _other(channel: str) -> str:
    return "down" if channel == "up" else "up"


def assign_channels(
    result: DetectionResult, listing: FolderListing, sniffs: dict[Path, FileSniff], sniff: SniffFn
) -> None:
    """Fill the ``*_down`` roles and correct the ↑ ones when the run has spin (else: no-op).

    A role the user mapped by hand is never touched. When nothing says which of several files is
    which channel, the default ↑ pick stays, the ↓ role stays empty and a warning asks for the
    manual mapping: an order of file names is not evidence.
    """
    if not has_spin(result, sniff):
        return
    ambiguous = False
    shared: set[str] = set()  # filband names both channels' inputs write
    for up_role, file_kind in KIND_OF_ROLE.items():
        down_role = f"{up_role}_down"
        manual = {r for r in (up_role, down_role) if result.methods.get(r) is Method.MANUAL}
        if len(manual) == 2:
            continue
        taken = {p for r in manual for p in result.files[r]}
        candidates = [p for p in listing.files if sniffs[p].kind is file_kind and p not in taken]
        found, same_file = pair_channels(up_role, candidates, result, sniffs)
        shared |= {p.name.removesuffix(".gnu") for p in same_file}
        if not found and len(candidates) == 1 and not same_file:
            found = {"up": candidates[0]}  # a lone file is bands.x's default, spin_component = 1
        elif not found and len(candidates) > 1 and not manual:
            ambiguous = True
        method = Method.CONTENT if result.methods.get(up_role) is not Method.NAME else Method.NAME
        for channel, role in (("up", up_role), ("down", down_role)):
            if role in manual:
                continue
            if channel in found:
                result.files[role] = [found[channel]]
                result.methods[role] = method
            elif channel == "down":
                result.files.pop(role, None)
                result.methods.pop(role, None)
        if up_role not in manual and result.file(up_role) == result.file(down_role) is not None:
            # The default ↑ pick is the ↓ file: take another candidate, if there is one.
            others = sorted(p for p in candidates if p != result.file(down_role))
            if others:
                result.files[up_role] = [others[0]]
            else:
                result.files.pop(up_role)
                result.methods.pop(up_role, None)
    _channel_warnings(result, ambiguous, shared)


def _channel_warnings(result: DetectionResult, ambiguous: bool, shared: set[str]) -> None:
    up = any(result.file(role) for role in KIND_OF_ROLE)
    down = any(result.file(f"{role}_down") for role in KIND_OF_ROLE)
    if shared:
        result.warnings.append(
            f"as entradas do bands.x de ↑ e ↓ escrevem o mesmo arquivo ({', '.join(sorted(shared))}): "
            "ele guarda só a última execução; use filband diferentes ou o mapeamento manual"
        )
    elif ambiguous:
        result.warnings.append(
            "não foi possível identificar o canal ↑/↓ dos arquivos de bandas: "
            "use o mapeamento manual (só o canal ↑ será plotado)"
        )
    elif up and not down:
        result.warnings.append("só o canal ↑ foi encontrado: rode o bands.x com spin_component = 2")
    elif down and not up:
        result.warnings.append("só o canal ↓ foi encontrado: rode o bands.x com spin_component = 1")


def check_bands(result: DetectionResult, sniffs: dict[Path, FileSniff], sniff: SniffFn) -> None:
    """Missing eigenvalue data, missing labels and a k-point count that disagrees with the run."""
    if not any(source in result.files for source in EIGEN_SOURCES):
        result.missing.append("gnu")
    if "bands_in" not in result.files:
        result.warnings.append("entrada de bandas não encontrada: pontos k sem rótulos")

    expected = None
    bands_out = result.file("bands_out")
    if bands_out is not None:
        pw = sniff(bands_out).pw
        expected = pw.n_kpoints if pw else None
    if expected is None:
        parsed = read_bands_input(result.file("bands_in"))
        if parsed and parsed.kpoints is not None and len(parsed.kpoints.weights):
            kp = parsed.kpoints
            expected = kp.path_length if kp.is_path else len(kp.weights)

    counts: dict[str, int] = {}
    for channel, roles in CHANNEL_ROLES.items():
        data_file = result.file(roles[0]) or result.file(roles[1])
        if data_file is not None:
            shape = (sniffs.get(data_file) or sniff(data_file)).shape
            if shape:
                counts[channel] = shape[1]
    for channel, nks in counts.items():
        if expected is not None and nks != expected:
            which = f" {CHANNEL_SYMBOL[channel]}" if "down" in counts else ""
            result.warnings.append(
                f"os dados de bandas{which} têm {nks} pontos k, mas o cálculo de bandas tem "
                f"{expected} (bands.x rodou sobre outra execução?)"
            )
    if len(set(counts.values())) > 1:
        result.warnings.append("os canais ↑/↓ têm pontos k diferentes")
