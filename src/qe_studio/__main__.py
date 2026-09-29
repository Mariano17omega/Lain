"""``python -m qe_studio`` / ``lain`` entry point."""

import sys

from .ui.app import main

if __name__ == "__main__":
    sys.exit(main())
