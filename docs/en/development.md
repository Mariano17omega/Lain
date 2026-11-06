# Development

## Environment

```bash
uv sync                      # dependencies + dev group
uv sync --group docs         # + MkDocs (this documentation)
```

Python ≥ 3.11; PyQt6, matplotlib, numpy, pydantic, PyYAML, Jinja2, ASE, spglib, scipy. Dev: pytest, pytest-qt,
pytest-timeout, Hypothesis, paramiko, ruff (line length 100), pyright (basic mode over `src/`).

## Commands

```bash
uv run pytest                                     # full suite, headless
uv run pytest -m "not realdata and not perf"      # what CI runs
uv run pytest tests/test_detection.py::test_name  # a single test
uv run pytest -m perf -s                          # latency budgets
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run python scripts/screenshot.py --plot        # PNGs of both themes into screenshots/
uv run python scripts/i18n.py update|compile|check
```

## Tests

- `tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen` and `MPLBACKEND=Agg`, and redirects `XDG_*` to temp folders;
  every test has a 60 s timeout.
- `tests/fixtures/` holds real, trimmed QE outputs — **never write there** (`copy_fixture` first).
- The `main_window` fixture builds a full `MainWindow` with isolated stores.
- Sync tests run the real `rsync`/`ssh` against `tests/ssh_server.py` (paramiko on `127.0.0.1`).
- **The cluster is production**: no test or verification reaches it; an automatic guard fails a test that reads the
  real `config.yaml` or contacts any other host.
- Figure *goldens* guard default behavior: a change must pass them, not regenerate them.
- `test_i18n.py` fails when a text is outside `_()`, a translation is missing/stale, or the `.mo` lags.

## Internationalization

Text in Portuguese inside `_()` (or `N_()` for a token that is also data). `scripts/i18n.py update` → translate in the
`.po` → `compile`. CI runs `scripts/i18n.py check`. Code, comments and commit messages are in **English**.

## Historical internal names (do not rename)

Package `qe_studio`, `QE_STUDIO_*` variables, `~/.config/qe-studio`, `~/.cache/qe-studio`, QSettings keys,
`qe-studio-askpass`. Product and CLI are `lain`.

## Logging

INFO tells the session; DEBUG what repeats; new messages in English, through `logging.getLogger(__name__)`, with `%s`
and a fixed leading word (`session:`, `action:`, `sync:`, `cluster:`…). Never in the log: a password, `jobs.myemail`, a
child's environment, a file's content, a command's whole stdout.

## This documentation

```bash
uv sync --group docs
uv run mkdocs serve            # http://127.0.0.1:8000
uv run mkdocs build --strict   # what GitHub Actions runs
```

`docs/pt/` and `docs/en/` have the **same file names**; when you add a page, create both and add it to the `nav` of
`mkdocs.yml` (and to `nav_translations`). Diagrams are Mermaid in ` ```mermaid ` blocks. The site is published by the
`.github/workflows/docs.yml` workflow (in *Settings ▸ Pages*, choose *Source: GitHub Actions*).
