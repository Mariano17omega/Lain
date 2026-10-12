# Spec 35: "Plotar" no menu de contexto das saídas de relax e vc-relax

| | |
|---|---|
| **Prioridade** | 35 (pequena e independente; depois dos defeitos da spec 33) |
| **Status** | Implementada (12/10/2026); ver "Decisões na implementação" |
| **Depende de** | spec 6 (gráficos de relaxamento), spec 9 (`single_file_role`, "Plotar" do menu, botão "Plotar SCF"), spec 27-7 (vc-relax) |
| **Usada por** | nenhuma |
| **Esforço** | M |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que a spec 9 abriu para o SCF (um `ClassVar`, o `plot_target` por saída e um rótulo). |

## Itens de origem (`Ideias.md`)

> - Nas pastas com calculo de relaxamento, quando é para fazer o plot do output do relaxamento, o grafico é feito clicando no botão "Gerar Gráfico" na barra superior. Isso não é muito pratico, porque pode ter mais de um output na pasta. Quero que no menu do botão direito do mouse, adicione a oção de plot para os aquivos de output de relaxamento, iqual como é feito para os outputs de scf. O botão na barra superior continuar funcionando como um atalho, util quando tiver apenas um output de calculo na pasta.

## Situação atual

- **Só o SCF plota um arquivo.** `ScfModule.single_file_role = "scf_out"` (`core/calculations/scf.py:102`) é o único `single_file_role` do
  registro; `module_for_file(sniff)` (`core/calculations/__init__.py:31-44`) devolve o módulo plotável cujo papel aceita aquele arquivo, e
  `ItemActions.file_actions_of` (`ui/widgets/context_menu.py:108-117`) põe "Plotar" no menu (`:141-142`) quando ele existe.
  `RelaxModule` (`relax.py:118-142`) tem os papéis `relax_in` e `relax_out` e **nenhum** `single_file_role`: a saída de relax não tem
  "Plotar".
- **Duas saídas na mesma pasta** (medido com duas cópias da fixture `si_relax`, `si.rel.*` e `si_b.rel.*`): `detect_folder` devolve **um**
  resultado, com `si_b.rel.in` / `si_b.rel.out` (a última por nome), sem aviso; `si.rel.out` só se plota por mapeamento manual. O
  "Gerar Gráfico" escolhe sozinho. Com o mapeamento forçado `{"relax_out": [si.rel.out]}`, `manual_result` casa o `relax_in` **por conteúdo**
  e devolve `si_b.rel.in`: os limiares (`etot_conv_thr`, `forc_conv_thr`) e a pressão-alvo saem do input de **outra** corrida.
- **A aba é por pasta.** `RelaxModule.plot_target` é o padrão (a pasta): a chave `plot:relax:<pasta>` é uma só, então plotar a segunda saída
  substitui a primeira. O SCF devolve o arquivo (`scf.py`, `plot_target`).
- **O botão "Plotar SCF"** (`ui/widgets/bars.py:228-233`, tooltip "Plotar a convergência do SCF do arquivo aberto") aparece quando a aba
  atual é um `TextViewer` cujo arquivo `module_for_file` reconhece (`ui/plot_workflow.py:464-475`; `plot_file_available(bool)` em `:83`,
  ligado a `setVisible` em `ui/main_window.py:244`). Com o relax reconhecido, ele apareceria com o rótulo "Plotar SCF" numa saída de relax.
- **Limites:** `ui/plot_workflow.py` tem 478 linhas (limite 500) e `ui/main_window.py` 447 (limite 450).

## Requisitos

### R1: "Plotar" nas saídas de relax / vc-relax

1. `RelaxModule.single_file_role = "relax_out"`: o clique direito numa saída de `calculation = 'relax'` ou `'vc-relax'` (sniff em cache,
   `output_of(PW_OUT, "relax", "vc-relax")`) mostra "Plotar", e `PlotWorkflow.plot_file` abre o gráfico daquele arquivo, sem salvar em
   `plots/` (como no SCF).
2. `RelaxModule.plot_target(folder, files)` devolve a **saída** (como `ScfModule`) quando o papel `relax_out` está preenchido, senão a
   pasta: cada saída tem a sua aba. O `relax.plot` continua **um por pasta** (as duas saídas de uma pasta partilham os ajustes, como as
   do SCF).
3. O "Gerar Gráfico" da barra superior não muda: detecta a pasta e plota o que ela escolhe.

### R2: O input certo para a saída escolhida

1. Com `relax_out` forçado, o `relax_in` é o **de mesmo nome** da saída (`X.out` → `X.in`, que `looks_like_input` e é um input de
   relax/vc-relax: a regra de `scf_from_relax.pair_input`, que sobe para um helper compartilhado em `core/`). Sem um de mesmo nome:
   o único input de relax da pasta, se houver só um; com vários e nenhum de mesmo nome, nenhum (o relax já sabe plotar sem input:
   limiares do cabeçalho, ou "padrões do QE" no aviso `defaulted_thresholds`).
2. A regra vale no `finalize()` do módulo (o gancho de lógica entre papéis), então vale também para o mapeamento manual e para o
   "Gerar Gráfico".

### R3: Aviso de mais de uma saída na pasta

1. Quando a pasta tem mais de uma saída de relax/vc-relax, o resultado leva um aviso em `DetectionResult.warnings`: "N saídas de
   relax/vc-relax na pasta; mostrando `<nome>`. As outras: botão direito ▸ Plotar." (aparece onde os avisos da detecção aparecem hoje).

### R4: O botão da barra superior diz o que plota

1. `CalculationModule.plot_file_label: ClassVar[str] = "Plotar"` (e `plot_file_tip`); `ScfModule` = "Plotar SCF" /
   "Plotar a convergência do SCF do arquivo aberto" (o texto de hoje); `RelaxModule` = "Plotar relaxamento" / "Plotar os passos do
   relaxamento do arquivo aberto". Nenhum arquivo de `ui/` conhece o módulo: o rótulo vem do hook.
2. `plot_file_available` passa a `pyqtSignal(bool, str, str)` (visível, rótulo, tooltip) e `TopBar.set_plot_file(visible, label,
   tip)` o recebe; a ligação em `main_window.py:244` troca de `setVisible` para esse método, **sem linha nova** (447 de 450).

### R5: Testes

- `tests/test_relax.py`: `module_for_file` reconhece a saída de relax e de vc-relax e não a de SCF; duas saídas na mesma pasta →
  `plot_target` por saída e o `relax_in` de mesmo nome (a fixture de `si_relax` copiada com outro nome, como na medição); só um input
  de relax e nome diferente → ele; vários sem nome igual → nenhum e sem exceção; o aviso de R3.
- `tests/test_plot_file.py`: "Plotar" no menu de uma saída de relax abre uma aba por saída; o botão da barra mostra "Plotar relaxamento"
  numa aba de relax e "Plotar SCF" numa de SCF e some nas demais.
- `tests/test_relax_figures.py` e `relax_golden.json` passam **sem** regenerar (o desenho não muda).
- `tests/test_scf_from_relax.py` continua verde com o helper movido.

## Fora de escopo
- Escolher entre saídas no "Gerar Gráfico" (um diálogo de escolha): o aviso de R3 e o menu resolvem.
- Um `.plot` por saída (`relax.plot` segue por pasta; o do SCF também).
- Plotar saídas de `bands` / `nscf` pelo menu (o SCF e o relax são os que têm gráfico próprio de um arquivo).

## Decisões assumidas (confirmar na revisão)
1. A aba do relax passa a ser **por saída** (como a do SCF), não por pasta: é o que torna "mais de um output na pasta" utilizável.
2. Os ajustes ficam por pasta (`relax.plot`): trocar de saída reaproveita a escala e as cores. Um `.plot` por saída muda o formato dos
   arquivos e pede migração; ficou de fora.
3. O input pareado é o de **mesmo nome**; sem ele, o único da pasta. Foi o que o experimento mostrou errado hoje (o input de outra corrida).
4. O "Gerar Gráfico" continua escolhendo sozinho (a última por nome, o que `match` já faz) e agora avisa.

## Notas de implementação
- Alterados: `core/calculations/relax.py` (344 linhas: `single_file_role`, `plot_target`, `finalize`, rótulos), `core/calculations/scf.py`
  (rótulo), `core/calculations/base.py` (454: dois `ClassVar`, sem lógica), `core/qe/scf_from_relax.py` (`pair_input` vira helper
  compartilhado, num módulo novo, p. ex. `core/qe/pairing.py`), `ui/widgets/bars.py`, `ui/plot_workflow.py` (478: o sinal e a emissão; **sem crescer
  mais de ~6 linhas**), `ui/main_window.py` (a ligação, sem linha nova).
- Limites: `plot_workflow.py` 478/500 e `main_window.py` 447/450: se passar, extrair `update_plot_file_button` para o helper.
- Documentação ao implementar: `CLAUDE.md`, seções "Detection pipeline" (`single_file_role` agora de SCF **e** relax; `plot_file_label`) e
  "Relax and vc-relax".

## Critérios de aceite e testes
- [ ] "Plotar" aparece no menu de uma saída de relax e de vc-relax e abre uma aba por saída, sem salvar em `plots/`.
- [ ] Duas saídas na pasta: cada uma com o próprio input pareado (por nome) e o próprio gráfico.
- [ ] Aviso de mais de uma saída na detecção da pasta.
- [ ] Botão da barra: "Plotar relaxamento" / "Plotar SCF" conforme a aba; "Gerar Gráfico" inalterado.
- [ ] `test_relax_figures.py` e `relax_golden.json` sem regenerar; `test_module_contract.py` com os `ClassVar` novos no `DummyModule`.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` (`plot_workflow.py` ≤ 500, `main_window.py` ≤ 450) e a suíte
      `-m "not realdata and not perf"` verdes.

## Decisões na implementação

1. As decisões 1–4 acima ficaram como estavam. O aviso de R3 sai também quando a saída é a escolhida pelo menu ou pelo mapeamento
   (o resultado diz "mostrando `<nome>`" nos dois casos): o texto é o da spec e não distingue como a saída foi escolhida.
2. O input de mesmo nome só vale se for um input de relax / vc-relax (`output_of(PW_IN, "relax", "vc-relax")`); um `X.in` de SCF ao
   lado de `X.out` cai na regra "o único input de relax da pasta". Um `relax_in` mapeado pelo usuário nunca é trocado.
3. `same_name_input` ficou em `core/qe/pairing.py` e é o que `scf_from_relax.pair_input` chama; `pair_input` mantém o segundo passo
   (o `relax_in` do resultado cuja saída é esta), que o relax não precisa.
4. Uma célula de grade de relax passa a ser o arquivo de saída (`PlotRef.path`, como a do SCF). Uma grade salva com a pasta continua
   carregando (`ref_target` detecta a pasta); com a pasta apagada a célula diz "Arquivo não encontrado" em vez de "Pasta não
   encontrada" (`test_a_cell_of_a_gone_folder_is_unavailable`).
5. O rótulo e o tooltip iniciais do botão em `bars.py` ficaram como eram ("Plotar SCF"): o botão só aparece depois de
   `set_plot_file`, que os troca pelos do módulo.
6. A aba, o readout do rodapé e o toast de "Plotar" do relax passam a mostrar o nome da saída (`si.rel.out`), não o da pasta:
   `test_relax_plot` mudou por isso. As exportações seguem `<pasta>-relax*.png` (`PlotSession.folder`).
7. Testes: `test_relax.py` (módulo, pareamento, aviso), `test_plot_workflow.py` (aba por saída, botão), `test_file_grid_menu.py`
   (menu), `test_module_contract.py` (os dois `ClassVar`). `test_plot_file.py` testa o formato do `.plot`, não o menu, por isso não
   recebeu testes.
