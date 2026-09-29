"""SSH_ASKPASS helper: hands ssh the password QE Studio put in the child environment.

ssh runs this program with its prompt as argument. Host-key confirmation prompts are
answered "no" so an unknown cluster key is never accepted silently.
"""

from __future__ import annotations

import os
import sys

SECRET_ENV = "QE_STUDIO_ASKPASS_SECRET"


def main(argv: list[str] | None = None) -> int:
    prompt = " ".join(sys.argv[1:] if argv is None else argv)
    if "yes/no" in prompt:
        print("no")
        return 0
    secret = os.environ.get(SECRET_ENV)
    if not secret:
        return 1
    print(secret)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
