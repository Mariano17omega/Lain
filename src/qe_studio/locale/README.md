# Translations

The texts in the code are Portuguese, the source language: `pt_BR` needs no catalog. English lives in
`en/LC_MESSAGES/lain.po`; `lain.mo` next to it is compiled from it and versioned, so `uv run lain`
needs no build step. The language is chosen once, at startup (`ui.language`, `QE_STUDIO_LANGUAGE`):
see `qe_studio/i18n.py`.

## Workflow

After changing a text in the code:

```bash
uv run python scripts/i18n.py update           # new messages go into lain.po, empty; a changed one is "fuzzy"
# translate the empty entries; review each fuzzy one and delete its "#, fuzzy" line
uv run python scripts/i18n.py compile          # lain.po → lain.mo, with the translated messages only
uv run python scripts/i18n.py check            # per area: messages and untranslated ones
uv run python scripts/i18n.py check --area 53  # the untranslated messages of one area, with their files
```

Commit `lain.po` and `lain.mo` together. A message left empty is shown in Portuguese. `compile`
refuses a fuzzy message, a plural with an empty form and a translation that lost or gained a
`{field}`, a rich-text tag or an `&` of its source.

In the code:

- `_("…")` for a text shown and `ngettext(singular, plural, n)` for a count.
- `N_("…")` for a Portuguese token that is also data (compared or stored). It translates nothing, so
  the code that shows the token calls `_(token)`.
- Format after translating: `_("Abrir {name}").format(name=…)`, never `_(f"…")` nor `_("a" + b)`.
- A module that imports `_` names nothing else `_` (use `_sep`, `_line`).

## Checks (`tests/test_i18n.py`)

- `tests/i18n_static.py`: no visible text outside `_()` (accented letters, common Portuguese words,
  the arguments of `setText`-like calls). A Portuguese token that is data goes into its `EXCEPTIONS`,
  with the reason.
- The `.po` follows the code (`update` was run) and the `.mo` follows the `.po` (`compile` was run).
- The per-area gate, until spec 60: `tests/i18n_areas.py` maps file prefixes to the spec of the
  series (53–59) that translates them. A spec adds its number to `DONE` when its area is translated;
  from then on, an untranslated message with a location there fails the test.
- The code in a sentence (`lost_code_tokens`): in a finished area a translation keeps, as the source
  writes them, the namelists (`&SYSTEM`), command-line options (`-pe`), `JOB DONE`, `#!`, cards and
  variables (`CELL_PARAMETERS`, `celldm(1)`), backticked spans and escapes (`\r`).
- Data does not follow the language. What other tools read stays as the source writes it: the columns
  of a CSV (`Banda 1 (E−E_F, eV)`, `estados/eV`), the first line and the values of a `.plot`, the names
  of the exported files, the stored value of a `choice` (`ParamField.choices` is `(value, label)`:
  only the label goes through `_()`). Such a literal is Portuguese on purpose and goes into the
  `EXCEPTIONS` of `tests/i18n_static.py` with the reason; the probe's `csv` and `plot_files` scenarios
  compare what is written between the languages. A data token shown to the user (`N_("padrão do QE")`)
  is translated where it is shown, once.
- Numbers use the decimal point in both languages (QE reads `.`: `15.10 Å`, never `15,10`); a literal
  such as `0.05 eV` in a message is written with the point too. The CSV export is the one file with a
  decimal comma (spec 32).
- The leak probe: `tests/i18n_probe.py` opens the window in a language, in a process of its own, and
  lists the texts of every widget. A text equal to a translated `msgid` is a leak: it reached the
  screen without `_()`. Each spec adds the scenarios of its area to `SCENARIOS`. Painted text (the
  badges of the tree and the grid, figures, the 3D view) belongs to no widget: the spec of its area
  tests it through its model (the `figures` scenario asks matplotlib for the text of every artist).
- `uv run python scripts/screenshot.py --language en` renders the window in English
  (`main_dark_en.png`).

## Style of the English

- US English: `color`, `favorite`.
- Sentence case for menus, buttons, titles and labels: `Open data folder`, `Project settings`. One
  exception: **Generate Plot**, the button of the adjustments panel ("Plot" names the feature, as in
  the Portuguese "Gerar Plot").
- Quantum ESPRESSO names stay as they are: programs (`pw.x`, `projwfc.x`, `bands.x`), files
  (`scf.out`, `bands.dat.gnu`), namelists and variables (`&SYSTEM`, `ecutwfc`, `K_POINTS`),
  `JOB DONE`. So do the product's and the files' names: `config.yaml`, `Rsync`, `XCrySDen`, `.lain`.
- Keep the fields of the source (`{name}`, `{value:.2f}`), its tags and its `&`; their order may
  change.
- Keep the `…` of an action that asks something before acting and the keys shown in a text
  (`Ctrl+G`).
- Units and symbols as in the source: `eV`, `Ry/Bohr`, `Å`, `E_F`, `Γ`.
- Sync: `Download` and `Upload` name the two directions in every menu, button, preview and report. A
  sentence that says what is **not** done keeps its negation and its subject (`Already on the cluster, will
  not be changed`): `test_the_sync_catalog_keeps_every_negation` fails a translation of area 58 that drops it.
  The hint for a failed connection follows the language; the ssh/rsync text it is chosen by, the log and
  the `SSH_ASKPASS` password never do.

## Glossary

The fixed terms of the interface, the same in every message.

| Português | English |
|---|---|
| Aba | Tab |
| Abrir | Open |
| Abrir com | Open with |
| Abrir local de origem | Show in file manager |
| Ajuste do gráfico | Plot settings |
| Alargamento | Smearing |
| Âncora, átomo âncora (da molécula na superfície) | Anchor, anchor atom |
| Arquivo, Arquivos | File, Files |
| Árvore | Tree |
| Átomo | Atom |
| Átomos fixos (if_pos 0 0 0) | Fixed atoms |
| Atualizar | Refresh |
| Autovalores | Eigenvalues |
| Avançado / Padrão (modo dos campos do Criar cálculo) | Advanced / Standard |
| Aviso / AVISO | Warning / WARNING |
| Bandas, estrutura de bandas | Bands, band structure |
| Baixar (do cluster) | Download (from the cluster) |
| Bidentado / Monodentado | Bidentate / Monodentate |
| Cálculo | Calculation |
| Caminho k (das bandas) | k-path |
| Cancelar | Cancel |
| Carga, Diferença de carga (tipos do Criar cálculo) | Charge, Charge difference |
| Célula | Cell |
| Ciclo SCF (um SCF inteiro, no relax) | SCF cycle |
| Condução / Valência | Conduction / Valence |
| Configurações | Settings |
| Continuar (passo seguinte de uma janela) | Continue |
| Criar (barra lateral) | Create |
| Criar cálculo | Create calculation |
| Energia de Fermi, nível de Fermi | Fermi energy, Fermi level |
| Energia total | Total energy |
| Enviar (ao cluster) | Upload (to the cluster) |
| Entrada / Saída (de um programa do QE) | Input / Output |
| Erro / ERRO | Error / ERROR |
| Espécie | Species |
| Excluir | Delete |
| Explorador de pastas | Folder explorer |
| Exportar | Export |
| Favorito | Favorite |
| Fechar | Close |
| Folga (distância mínima) | Clearance |
| Força | Force |
| Gerar | Generate |
| Gerar gráfico | Generate plot |
| Gerar Plot | Generate Plot |
| Gráfico, Gráficos (menu, painel) | Plot, Plots |
| Grade (de arquivos) | Grid |
| Grids (gráficos numa grade N×M) | Grids |
| Iteração (dentro de um SCF) | SCF iteration |
| Já existe no cluster (arquivo que o envio não altera) | Already on the cluster |
| Limiar (de convergência) | Threshold |
| Mais recente no computador (cópia local mais nova que a do cluster) | Newer on this computer |
| Molécula na superfície (tipo do Criar cálculo) | Molecule on surface |
| Numerar (a pasta do Criar cálculo) | Number |
| Painel (do gráfico) | Panel |
| Paralelização | Parallelization |
| Passo (do BFGS) | BFGS step |
| Pasta | Folder |
| Plotar | Plot |
| Pontos k, k-pontos | k-points |
| Pressão | Pressure |
| Prévia (dos arquivos a criar) | Preview |
| Problema de escrita (do verificador de inputs e scripts) | Syntax problem |
| Projeto | Project |
| Pseudopotencial | Pseudopotential |
| Raiz, pasta raiz | Root, root folder |
| Rede de k-points (K_POINTS automatic) | k-point mesh |
| Selo | Badge |
| Sincronizar | Sync |
| Sítio (de adsorção) | Site |
| Slab | Slab |
| Supercélula | Supercell |
| Superfície | Surface |
| Tempo de CPU / de parede (WALL) | CPU time / Wall time |
| Vácuo | Vacuum |
