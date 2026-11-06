# Desenvolvimento

## Ambiente

```bash
uv sync                      # dependências + grupo dev
uv sync --group docs         # + MkDocs (esta documentação)
```

Python ≥ 3.11; PyQt6, matplotlib, numpy, pydantic, PyYAML, Jinja2, ASE, spglib, scipy. Dev: pytest, pytest-qt,
pytest-timeout, Hypothesis, paramiko, ruff (linha 100), pyright (modo básico sobre `src/`).

## Comandos

```bash
uv run pytest                                     # suíte completa, sem tela
uv run pytest -m "not realdata and not perf"      # o que o CI roda
uv run pytest tests/test_detection.py::test_nome  # um teste
uv run pytest -m perf -s                          # orçamentos de latência
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run python scripts/screenshot.py --plot        # PNGs dos dois temas em screenshots/
uv run python scripts/i18n.py update|compile|check
```

## Testes

- `tests/conftest.py` força `QT_QPA_PLATFORM=offscreen` e `MPLBACKEND=Agg`, e redireciona `XDG_*` para pastas
  temporárias; todo teste tem 60 s de limite.
- `tests/fixtures/` guarda saídas reais do QE reduzidas — **nunca escreva ali** (`copy_fixture` primeiro).
- A fixture `main_window` monta uma `MainWindow` completa com *stores* isolados.
- Testes de sync rodam o `rsync`/`ssh` reais contra `tests/ssh_server.py` (paramiko em `127.0.0.1`).
- **O cluster é produção**: nenhum teste ou verificação o alcança; um guarda automático falha o teste que ler o
  `config.yaml` real ou contatar outro host.
- *Goldens* de figuras guardam o comportamento padrão: uma mudança deve passar neles, não regenerá-los.
- `test_i18n.py` falha se há texto fora de `_()`, tradução faltando/desatualizada ou `.mo` atrasado.

## Internacionalização

Texto em português dentro de `_()` (ou `N_()` para um token que também é dado). `scripts/i18n.py update` → traduzir no
`.po` → `compile`. O CI roda `scripts/i18n.py check`. Código, comentários e mensagens de commit são em **inglês**.

## Nomes internos históricos (não renomeie)

Pacote `qe_studio`, variáveis `QE_STUDIO_*`, `~/.config/qe-studio`, `~/.cache/qe-studio`, chaves do QSettings,
`qe-studio-askpass`. Produto e CLI são `lain`.

## Log

INFO conta a sessão; DEBUG o que se repete; mensagens novas em inglês, via `logging.getLogger(__name__)`, com `%s` e
uma palavra fixa no início (`session:`, `action:`, `sync:`, `cluster:`…). Nunca no log: senha, `jobs.myemail`, ambiente
de um filho, conteúdo de arquivo, stdout inteiro de um comando.

## Esta documentação

```bash
uv sync --group docs
uv run mkdocs serve            # http://127.0.0.1:8000
uv run mkdocs build --strict   # o que o GitHub Actions roda
```

`docs/pt/` e `docs/en/` têm os **mesmos nomes de arquivo**; ao criar uma página, crie as duas e adicione ao `nav` do
`mkdocs.yml` (e ao `nav_translations`). Diagramas são Mermaid em blocos ` ```mermaid `. O site é publicado pelo
workflow `.github/workflows/docs.yml` (em *Settings ▸ Pages*, escolha *Source: GitHub Actions*).
