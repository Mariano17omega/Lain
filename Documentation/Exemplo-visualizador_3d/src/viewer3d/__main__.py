"""Command line entry point (``viewer3d [FILE] [--screenshot OUT.png] ...``)."""

from __future__ import annotations

import argparse
import os
import sys

STYLES = ("bola-vareta", "vareta", "fio", "espaco-cheio")


def _size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        size = (int(w), int(h))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use LARGURAxALTURA, por exemplo 1000x800") from exc
    if size[0] < 16 or size[1] < 16:
        raise argparse.ArgumentTypeError("tamanho mínimo 16x16")
    return size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viewer3d",
        description="Visualizador 3D de estrutura a partir de um input SCF do Quantum ESPRESSO.",
    )
    parser.add_argument("file", nargs="?", help="input do pw.x (sem arquivo: Si diamante embutido)")
    parser.add_argument("--screenshot", metavar="SAIDA.png", help="renderiza sem janela e sai")
    parser.add_argument("--size", type=_size, default=(1000, 800), metavar="LxA")
    parser.add_argument(
        "--repeat", type=int, nargs=3, default=(1, 1, 1), metavar=("N1", "N2", "N3")
    )
    parser.add_argument("--style", choices=STYLES, default=STYLES[0])
    return parser


def _load(path: str | None):
    from viewer3d.core.example import SI_DIAMOND_INPUT
    from viewer3d.core.qe_input import parse_input, read_structure

    return parse_input(SI_DIAMOND_INPUT) if path is None else read_structure(path)


def _apply(canvas, args) -> None:
    from viewer3d.ui.options import MAX_REPEAT, MIN_REPEAT

    canvas.options.style = args.style
    canvas.options.reps = tuple(min(MAX_REPEAT, max(MIN_REPEAT, n)) for n in args.repeat)


def run_screenshot(args) -> int:
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QApplication

    from viewer3d.core.structure import StructureError
    from viewer3d.ui.canvas import Canvas

    structure = _load(args.file)
    if isinstance(structure, StructureError):
        print(f"erro: {structure.message}", file=sys.stderr)
        return 1
    app = QApplication.instance() or QApplication(sys.argv[:1])
    canvas = Canvas()
    canvas.resize(*args.size)
    _apply(canvas, args)
    canvas.set_structure(structure)
    image = canvas.render_image(QSize(*args.size))
    if not image.save(args.screenshot):
        print(f"erro: não foi possível gravar {args.screenshot}", file=sys.stderr)
        return 1
    for warning in structure.source.warnings:
        print(f"aviso: {warning}", file=sys.stderr)
    del app
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return run_screenshot(args)
    from PyQt6.QtWidgets import QApplication

    from viewer3d.ui.main_window import MainWindow
    from viewer3d.ui.options import MAX_REPEAT, MIN_REPEAT

    app = QApplication(sys.argv[:1])
    window = MainWindow()
    window.canvas.options.style = args.style
    window.canvas.options.reps = tuple(min(MAX_REPEAT, max(MIN_REPEAT, n)) for n in args.repeat)
    window.panel.display.sync()
    window.resize(*args.size)
    window.show()
    if args.file:
        window.open_path(args.file)
    else:
        window.open_example()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
