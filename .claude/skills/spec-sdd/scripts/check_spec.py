#!/usr/bin/env python3
"""Check the structure and the references of one or more specs (specs/spec_N-*.md).

Usage: check_spec.py specs/spec_33-xxx.md [more.md ...]

Errors (exit 1): missing header row or section, sections out of order, R numbering with a gap,
no acceptance checkbox, a `[[PREENCHER` placeholder left in.
Warnings (exit 0): a path that does not exist in the repository (fine when the spec creates it:
the author confirms each one), a `file:line` past the end of the file, a "Depende de" spec that
does not exist, a spec missing from specs/README.md.

Run from anywhere inside the repository.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HEADER_ROWS = (
    "Prioridade",
    "Status",
    "Depende de",
    "Usada por",
    "Esforço",
    "Modelo recomendado",
)
SECTIONS = (
    "## Itens de origem",
    "## Situação atual",
    "## Requisitos",
    "## Fora de escopo",
    "## Decisões assumidas",
    "## Notas de implementação",
    "## Critérios de aceite",
)
TITLE = re.compile(r"^# Spec (end|\d+(?:-\d+)?): .+")
FILE_ID = re.compile(r"^spec_(end|\d+(?:-\d+)?)(?:-|\.)")
ROW = re.compile(r"^\| \*\*(.+?)\*\* \| (.*) \|\s*$")
R_HEAD = re.compile(r"^### R(\d+): .+")
SPEC_REF = re.compile(r"\bspecs? ((?:\d+(?:-\d+)?\s*(?:,|e|–|-|/|…)?\s*)+)")
SPEC_ID = re.compile(r"\d+(?:-\d+)?")
BACKTICK = re.compile(r"`([^`\n]+)`")
LINE_REF = re.compile(r"^(.+?\.[A-Za-z]+):(\d+)(?:[-–](\d+))?$")
NEW_WORDS = re.compile(r"\b(nov[oa]s?|cri[ae]\w*|extra[ií]\w*|passa a existir)\b", re.I)

# a path with a "/" may be any of these; a bare name only the code and doc ones
EXT_WITH_DIR = {".py", ".md", ".yaml", ".yml", ".json", ".j2", ".qss", ".toml", ".sh", ".svg"}
EXT_BARE = {".py", ".md", ".j2", ".qss", ".toml", ".yaml", ".yml"}
IGNORE = {"config.yaml"}  # git-ignored on purpose
TOKEN_OK = re.compile(r"^[\w./-]+$")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in (Path.cwd(), *Path.cwd().parents, *here.parents):
        if (base / "specs" / "README.md").is_file():
            return base
    sys.exit("specs/README.md não encontrado: rode dentro do repositório.")


def repo_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", "__pycache__", "node_modules"}
        return [
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and not skip & set(p.parts)
        ]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def section_bounds(lines: list[str]) -> dict[str, tuple[int, int]]:
    heads = [(i, ln) for i, ln in enumerate(lines) if ln.startswith("## ")]
    bounds: dict[str, tuple[int, int]] = {}
    for n, (i, ln) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        for name in SECTIONS:
            if ln.startswith(name):
                bounds[name] = (i, end)
    return bounds


def check_structure(path: Path, lines: list[str], report: Report) -> dict[str, str]:
    if not lines or not TITLE.match(lines[0]):
        report.error("linha 1: esperado `# Spec <N>: <título>`")
    else:
        wanted = FILE_ID.match(path.name)
        got = TITLE.match(lines[0])
        if wanted and got and wanted.group(1).lower() != got.group(1).lower():
            report.error(
                f"linha 1: título é spec {got.group(1)}, o arquivo é spec {wanted.group(1)}"
            )

    rows = {m.group(1): m.group(2) for ln in lines if (m := ROW.match(ln))}
    for name in HEADER_ROWS:
        if name not in rows:
            report.error(f"tabela do cabeçalho sem a linha **{name}**")
    effort = rows.get("Esforço", "")
    if effort and not re.match(r"^[PMG](/[PMG])?\b", effort):
        report.warn(f"Esforço deveria começar por P, M ou G: {effort[:40]!r}")
    model = rows.get("Modelo recomendado", "")
    if model and not re.search(r"(Opus|Sonnet) 5\.5", model):
        report.warn("Modelo recomendado: esperado Opus 5.5 ou Sonnet 5.5, com o motivo")

    bounds = section_bounds(lines)
    last = -1
    for name in SECTIONS:
        if name not in bounds:
            report.error(f"seção ausente: `{name}`")
            continue
        start = bounds[name][0]
        if start < last:
            report.error(f"seção fora de ordem: `{name}` (linha {start + 1})")
        last = max(last, start)

    if "## Requisitos" in bounds:
        start, end = bounds["## Requisitos"]
        heads = [(i, int(m.group(1))) for i in range(start, end) if (m := R_HEAD.match(lines[i]))]
        if not heads:
            report.error("`## Requisitos` sem nenhum `### R<n>: título`")
        numbers = [n for _, n in heads]
        if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
            report.error(f"numeração dos requisitos com salto ou fora de ordem: {numbers}")
        if numbers and numbers[0] not in (0, 1):
            report.error("os requisitos começam em R0 ou R1")
        for n, (i, _) in enumerate(heads):
            stop = heads[n + 1][0] if n + 1 < len(heads) else end
            body = lines[i + 1 : stop]
            if not any(re.match(r"^\s*(\d+\.|-)\s", ln) for ln in body):
                report.warn(f"linha {i + 1}: requisito sem itens numerados ou em lista")

    key = next((k for k in bounds if k.startswith("## Critérios")), None)
    if key:
        start, end = bounds[key]
        body = lines[start:end]
        open_boxes = sum(1 for ln in body if ln.lstrip().startswith("- [ ]"))
        done_boxes = sum(1 for ln in body if re.match(r"^\s*- \[[xX]\]", ln))
        if open_boxes + done_boxes == 0:
            report.error("`## Critérios de aceite e testes` sem nenhum `- [ ]`")
        if done_boxes and rows.get("Status", "").startswith("Rascunho"):
            report.warn("spec em rascunho com critério já marcado `[x]`")

    for i, ln in enumerate(lines, 1):
        if "[[PREENCHER" in ln:
            report.error(f"linha {i}: sobrou um `[[PREENCHER …]]`")
    return rows


def check_dependencies(rows: dict[str, str], specs_dir: Path, report: Report) -> None:
    known = {
        m.group(1)
        for folder in (specs_dir, specs_dir / "Archived")
        for p in folder.glob("spec_*.md")
        if (m := re.match(r"^spec_(\d+(?:-\d+)?)-", p.name))
    }
    for label in ("Depende de", "Usada por"):
        for ref in SPEC_REF.finditer(rows.get(label, "")):
            for ident in SPEC_ID.findall(ref.group(1)):
                if ident not in known:
                    report.warn(
                        f"{label}: spec {ident} não existe em specs/ nem em specs/Archived/"
                    )


def check_readme(path: Path, specs_dir: Path, report: Report) -> None:
    readme = (specs_dir / "README.md").read_text(encoding="utf-8")
    if f"({path.name})" not in readme and f"(Archived/{path.name})" not in readme:
        report.warn("specs/README.md não tem o link desta spec (linha do roadmap)")


def check_references(lines: list[str], files: list[str], root: Path, report: Report) -> None:
    sizes: dict[str, int] = {}

    def matches(token: str) -> list[str]:
        return [f for f in files if f == token or f.endswith("/" + token)]

    def length(rel: str) -> int:
        if rel not in sizes:
            try:
                sizes[rel] = len((root / rel).read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                sizes[rel] = 0
        return sizes[rel]

    seen_missing: set[str] = set()
    for lineno, ln in enumerate(lines, 1):
        for m in BACKTICK.finditer(ln):
            token = m.group(1).strip()
            if token.startswith("./"):
                token = token[2:]
            ref = LINE_REF.match(token)
            path_part = ref.group(1) if ref else token
            if path_part in IGNORE or not TOKEN_OK.match(path_part):
                continue
            if path_part.startswith(("/", "~", "$")) or path_part.split("/")[0] == "plots":
                continue
            ext = Path(path_part).suffix
            allowed = EXT_WITH_DIR if "/" in path_part else EXT_BARE
            if ext not in allowed:
                continue
            found = matches(path_part)
            if not found:
                if path_part in seen_missing:
                    continue
                seen_missing.add(path_part)
                note = "novo?" if NEW_WORDS.search(ln) else "NÃO diz que é novo"
                report.warn(f"linha {lineno}: `{path_part}` não existe no repositório ({note})")
                continue
            if ref:
                last = int(ref.group(3) or ref.group(2))
                biggest = max(length(f) for f in found)
                if last > biggest:
                    report.warn(
                        f"linha {lineno}: `{token}` aponta para a linha {last}, "
                        f"o arquivo tem {biggest}"
                    )


def check(path: Path, root: Path, files: list[str]) -> Report:
    report = Report()
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = check_structure(path, lines, report)
    specs_dir = root / "specs"
    check_dependencies(rows, specs_dir, report)
    check_readme(path, specs_dir, report)
    check_references(lines, files, root, report)
    return report


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = repo_root()
    files = repo_files(root)
    failed = False
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_file():
            print(f"{arg}: arquivo não encontrado")
            failed = True
            continue
        report = check(path, root, files)
        print(f"{arg}: {len(report.errors)} erro(s), {len(report.warnings)} aviso(s)")
        for msg in report.errors:
            print(f"  ERRO  {msg}")
        for msg in report.warnings:
            print(f"  aviso {msg}")
        failed = failed or bool(report.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
