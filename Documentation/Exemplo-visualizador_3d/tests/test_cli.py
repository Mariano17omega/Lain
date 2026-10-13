from viewer3d.__main__ import build_parser


def test_defaults():
    args = build_parser().parse_args([])
    assert args.file is None
    assert args.size == (1000, 800)
    assert tuple(args.repeat) == (1, 1, 1)
    assert args.style == "bola-vareta"


def test_options():
    args = build_parser().parse_args(
        ["x.in", "--screenshot", "o.png", "--size", "640x480", "--repeat", "2", "1", "3"]
    )
    assert args.size == (640, 480)
    assert tuple(args.repeat) == (2, 1, 3)
