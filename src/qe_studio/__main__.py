"""``python -m qe_studio`` / ``qe-studio`` entry point."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
