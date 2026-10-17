#!/usr/bin/env python3
"""Print what specs/ holds: the next spec number, drafts still open, the last round and today.

Usage: next_number.py [N]
  N  also print the next sub-spec number of N (27 -> 27-10), for corrections that belong to a
     group, like specs 27-1 ... 27-9.

Run from anywhere inside the repository.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

SPEC = re.compile(r"^spec_(\d+)(?:-(\d+))?-")
STATUS = re.compile(r"^\| \*\*Status\*\* \| (.*) \|$", re.M)
ROUNDS = re.compile(r"^## (Rastreabilidade: .*)$", re.M)


def find_specs_dir() -> Path:
    here = Path(__file__).resolve()
    for base in (Path.cwd(), *Path.cwd().parents, *here.parents):
        if (base / "specs" / "README.md").is_file():
            return base / "specs"
    sys.exit("specs/README.md não encontrado: rode dentro do repositório.")


def status_of(path: Path) -> str:
    found = STATUS.search(path.read_text(encoding="utf-8"))
    return found.group(1).split("<br>")[0].strip() if found else "(sem linha Status)"


def main() -> None:
    specs = find_specs_dir()
    numbers: dict[int, set[int]] = {}
    for folder in (specs, specs / "Archived"):
        for path in folder.glob("spec_*.md"):
            found = SPEC.match(path.name)
            if found:
                subs = numbers.setdefault(int(found.group(1)), set())
                if found.group(2):
                    subs.add(int(found.group(2)))

    highest = max(numbers, default=0)
    print(f"próximo número: {highest + 1}  (maior existente: {highest})")
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        n = int(sys.argv[1])
        subs = numbers.get(n, set())
        print(f"próximo sub-número de {n}: {n}-{max(subs, default=0) + 1}")

    print(f"hoje: {date.today():%d/%m/%Y}")

    print("\nabertas em specs/ (fora de Archived):")
    opened = sorted(specs.glob("spec_*.md"))
    for path in opened:
        print(f"  {path.name}: {status_of(path)}")
    if not opened:
        print("  (nenhuma)")

    rounds = ROUNDS.findall((specs / "README.md").read_text(encoding="utf-8"))
    print("\núltimas tabelas de rastreabilidade do README:")
    for title in rounds[-3:]:
        print(f"  {title}")


if __name__ == "__main__":
    main()
