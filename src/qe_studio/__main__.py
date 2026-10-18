"""``python -m qe_studio`` / ``lain`` entry point."""

import sys


def main() -> int:
    """Install the language, and only then import the application: its texts are translated while
    its modules load (spec end R1)."""
    from .ui.language import install_startup_language

    install_startup_language(sys.argv[1:])
    from .ui.app import main as run

    return run()


if __name__ == "__main__":
    sys.exit(main())
