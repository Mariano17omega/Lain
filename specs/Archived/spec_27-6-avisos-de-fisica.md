# Spec 27-6: Avisos de física — gap "no caminho", seleção de átomos de outra geometria e SCF convergido

| | |
|---|---|
| **Prioridade** | 27-6 |
| **Status** | Implementada. Desvios:<br>- **Sem "metálico" com a nota:** com E_F fora de [VBM, CBM] o rodapé não diz "metálico" (a nota ⚠ diz "indeterminado"; os dois juntos se contradiriam).<br>- **"(no caminho)" também no gap global** do spin (`gap global (no caminho) …`): todo gap das bandas é do caminho.<br>- **Tooltip:** `bands/params.py:BANDS_LEGEND_GAP_FIELD` (bandas e bandas + DOS); a PDOS mantém o `LEGEND_GAP_FIELD` compartilhado.<br>- **`GeometryDrift(atom, distance, counts)`:** com número de átomos diferente, `atom`/`distance` são None e `counts` = (salvo, atual), com texto próprio ("… com outra estrutura (N átomos; esta tem M)").<br>- **Onde o desvio é calculado:** o loader não tem os stores, então `pdos/atoms.py:stored_params` (ao montar a sessão) preenche `PdosDataset.selection_drift` e `save_stored` o limpa; só há aviso quando a seleção salva está em uso.<br>- **Avisos do SCF em texto simples** (sem crases), com `./` como outdir quando o input não define um; o de prefix/outdir vem primeiro. O teste do controlador estende `test_scf_from_relax_ui.py` (já existia um teste pela janela). |
| **Depende de** | spec 13 (spin e gaps por canal), spec 20 (gap na legenda), spec 21 (seleção de átomos), spec 24 (SCF convergido) |
| **Usada por** | nenhuma |
| **Esforço** | P/M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): três correções independentes e pequenas, todas com o comportamento esperado e os testes a atualizar descritos abaixo; a única decisão de física (a tolerância do gap) é uma constante já existente. |

## Itens de origem (`specs/report-04-10-26.md`)

- **F3 (Médio):** o gap das bandas vem só da contagem de elétrons, sem conferir E_F, e é um gap *ao longo do caminho*.
- **F6 (Baixo):** a seleção de átomos da PDOS é guardada só pela sequência de espécies; outra geometria do mesmo composto reaproveita a seleção sem aviso.
- **F7 (Baixo):** "Gerar SCF convergido" herda `prefix` e `outdir` do relax e faltam dois avisos.

## Situação atual

- **F3.** `core/calculations/bands/data.py:238-254` (`_band_edges`, sem spin): `occupied = pw.n_electrons if pw.noncollinear else pw.n_electrons / 2`;
  `n_occ = occupied_count(occupied, n_bands)` (`None` para valores fracionários ou fora da faixa); `edges = count_edges(energies, n_occ, pw.fermi)` (`:75`: topo da banda `n_occ−1`
  e base da banda `n_occ`; `fermi` só é copiado para `ChannelEdges.fermi`). Nenhum uso de `fermi_kind` nem teste de E_F ∈ [VBM, CBM]; o único teste de metal é a sobreposição de bandas
  dentro de `EDGE_TOL = 1e-3` (`:17`). Um metal com número par de elétrons, cujas bandas `n_occ` e `n_occ+1` não se tocam **no caminho**, mas cujo E_F cai dentro de uma banda por
  causa de bolsões fora do caminho, mostra "gap X eV". O caminho com spin (`spin_channel_edges`, `:257`) é melhor: com `fermi_kind in ("homo","homo_lumo")` usa `n_electrons_up_down`,
  senão `channel_edges(energies, fermi)` testa o cruzamento com E_F. `BandsDataset.fermi_kind` (`data.py:91`, preenchido em `:152`) vale `"fermi" | "spin_fermi" | "homo_lumo" | "homo"`
  (`FermiKind`, `core/qe/pw_output.py:17`). Onde o gap aparece: rodapé/readout (`bands/render.py:318-319`, `E_gap = X.XXX eV` ou "metálico"; `_spin_gaps` `:326`; vai para `RenderInfo.summary`
  e `ParamsBody.update_readout`, `params_body.py:111`), legenda (`gap_handles`, `bands/gap.py:48`, rótulo `gap_label` = `$E_{gap}$ = 1.234 eV`, `core/plotting/gap_label.py:10`), e a
  legenda de `bands_dos` (`bands_dos/render.py:55`). `gap_entries` (`bands/gap.py:25`) é a fonte única. Não existe tooltip de gap. PDOS (`pdos/gap.py:pdos_gap`, `:22`) já considera E_F
  (`homo_lumo` usa `lumo − fermi`; senão `projwfc.dos_gap`, que devolve `None` com E_F dentro de uma banda). Testes: `test_legend_gap_bands.py`, `test_legend_gap_pdos.py`,
  `test_gap_label.py`, `test_bands_spin_data.py`.
- **F6.** `core/compounds.py`: `compound_key(species)` (`:50`) = `"Al2O3:<sha1[:10]>"` da sequência ordenada de espécies; posições não entram (decisão da spec 21). `Compound(key, formula)` (`:35`).
  `compounds.json`: `{"version": 1, "compounds": {key: {"formula": …, "atoms": […]}}}` (`FORMAT_VERSION = 1`, `:27`). `selection(key)` lê só `entry.get("atoms")` (chaves extras são ignoradas
  na leitura); `save(key, formula, atoms)` (`:113-122`) **reescreve a entrada inteira** como `{"formula", "atoms"}` (um campo novo seria perdido no próximo `save`); `forget` = `save(key, "", None)`.
  `_load` (`:134-151`) trata `version != 1` como arquivo desconhecido e o põe de lado como corrompido. `Site(index, species, x, y, z)` (`core/qe/structure.py:20`, Cartesiano em Å) vem de
  `read_sites` (`pdos/data.py:60`); `PdosDataset.sites` / `.compound`. Testes: `tests/test_compounds.py`, `test_pdos_atoms.py`, `tests/atoms_helpers.py`.
- **F7.** `core/qe/scf_from_relax.py:119-146` remove só `restart_mode`, `nstep` e as namelists `&ions`/`&cell`; `prefix` e `outdir` ficam como no relax (o docstring `:6` diz isso). Rodar o SCF gerado
  regrava `<outdir>/<prefix>.save` do relax (densidade e funções de onda), o que impede reiniciar o relax. No vc-relax o `ibrav` vira 0 com `CELL_PARAMETERS` (correto), e o pw.x passa a detectar a
  simetria por tolerância numérica. Os avisos viajam em `ScfResult(text, prefix, warnings)` (`:46-49,146`) → `GeneratedScf(path, warnings)` → `derive_controller.py:73-75`
  (`details = "\n".join([str(path), *generated.warnings])` → `Toast.show_message(…, "success", details)`). Testes: `test_scf_from_relax.py:171` (`result.warnings == ()`) e `:238` (tupla exata de um elemento).

## Requisitos

### R1: Gap das bandas só quando E_F é coerente, e rotulado "no caminho" (F3)
1. `_band_edges` (sem spin): quando `pw.fermi_kind == "fermi"` (smearing/metal), o gap só é aceito se `vbm − tol ≤ E_F ≤ cbm + tol` com `tol = EDGE_TOL`; caso contrário o dataset fica **sem
   gap** (`gap = None`, `vbm`/`cbm` ausentes) e ganha `gap_note = "gap indeterminado: E_F fora de [VBM, CBM] no caminho"`. `fermi_kind in ("homo", "homo_lumo")` (ocupação fixa) não muda.
   Sem `pw.fermi` (nenhum E_F lido), o comportamento atual se mantém, com a nota "E_F não encontrado: gap pela contagem de elétrons".
2. `gap_note` entra em `RenderInfo.notes` (aparece como "⚠" sob o readout, mecanismo da spec 22) e **não** é desenhado na figura.
3. **Rótulos:** o rodapé/readout passa a "E_gap (no caminho) = X.XXX eV" (sem spin e por canal: `gap ↑ (no caminho)`); "metálico" fica como está. A legenda mantém o rótulo `$E_{gap}$ = …` (spec 20,
   curto, vai para o artigo) e o tooltip do checkbox "Gap de energia na legenda" ganha "gap ao longo do caminho de k; o gap indireto verdadeiro pode estar fora dele".
4. O caminho com spin não muda de lógica (já testa E_F por canal). `bands_dos` herda por usar o mesmo dataset.
5. Testes: (a) isolante com `occupations='fixed'` (fixtures `si_*`): gap igual ao de hoje; (b) metal sintético com `fermi_kind="fermi"`, bandas `n_occ`/`n_occ+1` separadas no caminho mas E_F
   dentro da banda `n_occ`: **sem** gap e com a nota; (c) isolante com smearing e E_F no meio do gap: gap igual ao de hoje; (d) textos do rodapé (`test_legend_gap_bands.py`,
   `test_bands_spin_data.py`, goldens de figura que contenham `E_gap =` atualizados) e do tooltip.

### R2: Seleção de átomos salva em outra geometria (F6)
1. `CompoundStore.save(key, formula, atoms, sites=None)` guarda, junto da seleção, `"sites": [[x, y, z], …]` (Å, arredondado a 0,01) das posições vistas ao salvar, **sem subir
   `FORMAT_VERSION`** (a chave é ignorada por leitores antigos, e a versão 1 continua válida). `save` passa a **mesclar** com a entrada existente em vez de reescrevê-la. Entradas sem
   `"sites"` continuam válidas.
2. `CompoundStore.stored_sites(key) -> list[tuple[float, float, float]] | None`.
3. Ao carregar a PDOS, `PdosDataset` compara `sites` atuais com os guardados: `geometry_drift(saved, current, tol=0.5) -> GeometryDrift | None` (Qt-free, em `core/compounds.py`): número de
   átomos diferente, ou algum átomo deslocado mais que `tol` (Å) → `GeometryDrift(atom, distance)` (o pior). Só compara quando há `"sites"`; sem eles, nada.
4. Havendo `GeometryDrift`, o módulo acrescenta `RenderInfo.notes`: "A seleção de átomos salva foi feita com outras coordenadas (átomo 5 moveu 2,1 Å). Confira em ‘Átomos…’". O aviso **não**
   altera a seleção nem impede o gráfico. Salvar de novo pelo diálogo "Átomos…" atualiza `"sites"` e o aviso some.
5. **Limitação conhecida (registrada na spec):** um átomo que sai por um lado da célula e reentra pelo outro (translação por vetor da rede) conta como deslocamento grande; é um falso positivo
   aceito.
6. Testes: `save` mescla e preserva `atoms`; arquivo antigo sem `sites` lê e salva sem erro e sem mudar a versão; `geometry_drift` com `tol` (deslocamento de 0,3 Å não avisa; 2 Å avisa;
   número de átomos diferente avisa); PDOS com seleção salva em geometria alterada mostra a nota e a seleção é a mesma; `tests/atoms_helpers.py:pdos_folder` gera as duas geometrias.

### R3: Avisos do SCF convergido (F7)
1. `scf_from_relax` acrescenta **sempre** a `warnings`: "O SCF usa o mesmo prefix (`<prefix>`) e outdir do relax: rodá-lo regrava `<outdir>/<prefix>.save` e impede reiniciar o relax. Mude o
   prefix ou o outdir antes de rodar." (o texto cita o `prefix` e o `outdir` reais).
2. No vc-relax (`ibrav → 0` com `CELL_PARAMETERS`) acrescenta também: "Cálculo vc-relax: a célula foi escrita com `ibrav = 0`; o pw.x detecta a simetria pela tolerância numérica da célula final."
3. Os avisos chegam ao "Detalhes" do toast pelo caminho existente (`derive_controller.py:73-75`), sem mudança de UI. A saída continua sendo só o `.in` (spec 24).
4. Testes: `test_scf_from_relax.py:171` passa a esperar o aviso do prefix/outdir em vez de `()`; `:238` (a tupla de um elemento, hoje só o de `alat`) ganha o novo; vc-relax tem os dois; um teste do
   controlador (`DeriveController`, hoje sem teste) confere que `details` contém os avisos.

## Fora de escopo
- Mudar o prefix/outdir do SCF gerado automaticamente (só avisa; spec 24 manteve o texto fiel).
- Calcular o gap verdadeiro (em toda a zona de Brillouin) a partir de um NSCF denso.
- Hash estrutural completo ou identificação de polimorfos além do deslocamento de átomos.
- Mudar a legenda do gap da PDOS ou o gap da PDOS (já considera E_F).

## Decisões assumidas (confirmar na revisão)
1. Tolerância do teste de E_F: a constante `EDGE_TOL` já existente (1e-3 eV). Se gerar falso "indeterminado" em isolantes com smearing, ela sobe (constante nomeada) sem mudar a estrutura.
2. O gap indeterminado vira **sem número** + nota, em vez de número com aviso: o relatório pede "um aviso, não um número".
3. Limiar de 0,5 Å para o deslocamento de átomos (relaxamentos típicos movem menos; um dopante em outro sítio move mais).
4. O aviso de F7 aparece **sempre** (o SCF gerado sempre herda os dois); nenhuma condicional.

## Notas de implementação
- Alterados: `core/calculations/bands/data.py`, `core/calculations/bands/render.py`, `core/calculations/bands/params.py` (tooltip), `core/compounds.py`, `core/calculations/pdos/data.py`/`module.py`
  (nota), `ui/dialogs/atoms.py` ou `PlotWorkflow` (passar `sites` ao `save` por `save_stored` do módulo PDOS), `core/qe/scf_from_relax.py`, e os testes citados.
- `ParamsBody` mostra `RenderInfo.notes` desde a spec 22; nenhum widget novo.
- `CLAUDE.md`: spec 21 (formato de `compounds.json` com `sites`) e spec 24 (avisos do SCF convergido).

## Critérios de aceite e testes
- [x] Metal com E_F dentro de uma banda e `fermi_kind="fermi"`: sem número de gap e com a nota; isolantes, ocupação fixa e spin como antes.
- [x] Rodapé diz "no caminho"; legenda com o rótulo da spec 20; tooltip atualizado.
- [x] `compounds.json` antigo lê e salva sem erro e sem mudar a versão; `save` mescla; `geometry_drift` e a nota da PDOS cobertos.
- [x] `scf_from_relax`: aviso de prefix/outdir sempre; aviso de `ibrav = 0` no vc-relax; toast "Detalhes" os mostra.
- [x] `ruff`, `pyright`, `test_architecture.py`, goldens de figura (só a string `E_gap` muda) e suíte verdes.
