"""Synthetic projects and oversized QE files for the detection performance tests (spec 14 R1).

Everything is built from the real fixtures into a folder the caller owns (``tmp_path``); nothing is
written into ``tests/fixtures/``.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from conftest import FIXTURES

MB = 1024 * 1024
PROJECT_SHAPE = (8, 8, 7)  # folders per level: 8 + 64 + 448 = 520 folders
LEAF_KINDS = ("bands", "pdos", "relax", "scf", "text", "text")


def _text_files(folder: Path) -> None:
    (folder / "notes.txt").write_text("cálculo de teste\nnada de QE aqui\n", encoding="utf-8")
    (folder / "job.o123").write_text("")
    (folder / "run.sh").write_text("#!/bin/sh\nmpirun pw.x -in scf.in > scf.out\n")


def _leaf(folder: Path, kind: str) -> None:
    if kind == "bands":
        shutil.copytree(FIXTURES / "al_bands", folder)
    elif kind == "pdos":
        shutil.copytree(FIXTURES / "al_pdos_flat", folder)
    elif kind == "relax":
        shutil.copytree(FIXTURES / "si_relax", folder)
    elif kind == "scf":
        folder.mkdir()
        for name in ("al.scf.in", "al.scf.out"):
            shutil.copy(FIXTURES / "al_bands" / name, folder / name)
    else:
        folder.mkdir()
    _text_files(folder)


def make_project(root: Path, shape: tuple[int, int, int] = PROJECT_SHAPE) -> list[Path]:
    """A project tree of ``shape`` folders per level (bands, PDOS, relax, SCF and plain text leaves
    copied from the fixtures); returns every folder, parents first."""
    folders: list[Path] = []
    count = 0
    for i in range(shape[0]):
        first = root / f"{i:02d}_grupo"
        first.mkdir(parents=True)
        (first / "README.txt").write_text("grupo de cálculos\n", encoding="utf-8")
        folders.append(first)
        for j in range(shape[1]):
            second = first / f"{j:02d}_sistema"
            second.mkdir()
            folders.append(second)
            for k in range(shape[2]):
                leaf = second / f"{k:02d}_calc"
                _leaf(leaf, LEAF_KINDS[count % len(LEAF_KINDS)])
                folders.append(leaf)
                count += 1
    return folders


def _write_until(path: Path, head: str, body: str, tail: str, size: int) -> None:
    """``head``, then ``body`` repeated until the file reaches ``size`` bytes, then ``tail``."""
    data = body.encode()
    with open(path, "wb") as handle:
        handle.write(head.encode())
        written = len(head.encode()) + len(tail.encode())
        chunk = data * max(1, (8 * MB) // len(data))
        while written + len(chunk) <= size:
            handle.write(chunk)
            written += len(chunk)
        while written < size:
            handle.write(data)
            written += len(data)
        handle.write(tail.encode())


def _index(lines: list[str], marker: str, start: int = 0) -> int:
    return next(i for i in range(start, len(lines)) if marker in lines[i])


def make_huge_relax(path: Path, mb: int = 200) -> Path:
    """A pw.x relax output of about ``mb`` MB: the header of ``si.rel.out``, its BFGS steps repeated,
    then its end (final coordinates, ``JOB DONE``)."""
    lines = (FIXTURES / "si_relax/si.rel.out").read_text().splitlines(keepends=True)
    first_step = _index(lines, "number of bfgs steps") + 1
    end = _index(lines, "bfgs converged")
    end = max(i for i in range(first_step, end) if "number of bfgs steps" in lines[i]) + 1
    head, body, tail = (
        "".join(lines[:first_step]),
        "".join(lines[first_step:end]),
        "".join(lines[end:]),
    )
    _write_until(path, head, body, tail, mb * MB)
    return path


def make_long_header_pw(path: Path, mb: int = 20, header_kb: int = 100) -> Path:
    """An SCF output of about ``mb`` MB whose header holds ``header_kb`` KB of pseudopotential
    notices before the summary (number of electrons, k points), as in big systems."""
    lines = (FIXTURES / "al_bands/al.scf.out").read_text().splitlines(keepends=True)
    notice = "     file Al.pbe-n-kjpaw_psl.1.0.0.UPF: wavefunction(s)  3S 3P renormalized\n"
    padding = notice * (header_kb * 1024 // len(notice) + 1)
    first_iteration = _index(lines, "iteration #")
    end_scf = _index(lines, "End of self-consistent calculation")
    head = "".join(lines[:3]) + padding + "".join(lines[3:first_iteration])
    _write_until(
        path, head, "".join(lines[first_iteration:end_scf]), "".join(lines[end_scf:]), mb * MB
    )
    return path


def gnu_text(n_bands: int, n_kpoints: int, separator: str = "") -> str:
    """``.gnu`` text: one (x, E) block per band, blocks split by ``separator`` lines."""
    x = np.arange(n_kpoints) * 1e-3
    blocks = []
    for band in range(n_bands):
        energies = np.sin(x + band) + band / 5
        blocks.append("".join(f"{xi:10.4f}{e:10.4f}\n" for xi, e in zip(x, energies, strict=True)))
    return f"{separator}\n".join(blocks)


def make_gnu(path: Path, mb: int = 80, n_bands: int = 100) -> tuple[int, int]:
    """A ``.gnu`` of about ``mb`` MB; returns its ``(n_bands, n_kpoints)``. Every band repeats the
    same block (the shape is what matters), so it is written in a blink."""
    n_kpoints = mb * MB // (21 * n_bands) + 1  # 21 bytes per "%10.4f%10.4f\n" line
    block = gnu_text(1, n_kpoints)
    with open(path, "w") as handle:
        handle.writelines(_separated(block, n_bands))
    return n_bands, n_kpoints


def _separated(block: str, count: int) -> Iterable[str]:
    for i in range(count):
        if i:
            yield "\n"
        yield block


def make_filband(path: Path, mb: int = 2, n_bands: int = 20) -> tuple[int, int]:
    """A raw bands.x ``filband`` file of about ``mb`` MB (per k point a line of 3 coordinates, then
    the energies, ten per line in 9-character fields); returns ``(n_bands, n_kpoints)``."""
    per_k = 34 + n_bands * 9 + -(-n_bands // 10)  # bytes: the k line, the energies, their newlines
    n_kpoints = mb * MB // per_k + 1
    rng = np.random.default_rng(7)
    with open(path, "w") as handle:
        handle.write(f" &plot nbnd={n_bands:4d}, nks={n_kpoints:6d} /\n")
        for k in range(n_kpoints):
            handle.write(f"  {0.001 * k:9.6f}  {0.0:9.6f}  {0.5:9.6f}\n")
            energies = rng.uniform(-20, 60, n_bands)
            for start in range(0, n_bands, 10):
                handle.write("".join(f"{e:9.3f}" for e in energies[start : start + 10]) + "\n")
    return n_bands, n_kpoints
