# Specs do Lain: QE Studio

`spec_0-PRD.md` é o documento de requisitos original. As specs 1–6 organizam `Ideias.md` (ajustes,
correções e funcionalidades novas), e as specs 7–20 organizam `report.md` (análise de 30/09/2026), em
grupos de itens relacionados e em ordem de prioridade. Cada spec é autossuficiente e pode virar um
`/plan` de implementação separado, nesta ordem:

```
/plan implementar specs/spec_1-paineis-e-navegacao.md
```

## Roadmap

| # | Spec | Resumo | Depende de | Esforço |
|---|---|---|---|---|
| 1 | [spec_1-paineis-e-navegacao.md](spec_1-paineis-e-navegacao.md) | Workspace oculto no início, abre sozinho; divisores mantêm a proporção; sem botão "Ajuste"; "Plot" plota sem salvar; rodapé coerente | nenhuma | M |
| 2 | [spec_2-fundo-das-figuras.md](spec_2-fundo-das-figuras.md) | Figura sempre com fundo branco, independente do tema; parâmetro "Cor de fundo" | nenhuma | P |
| 3 | [spec_3-persistencia-de-estado.md](spec_3-persistencia-de-estado.md) | Divisores persistidos; ajustes do gráfico em `<tipo>.plot` na pasta da simulação | 1, 2 | M |
| 4 | [spec_4-arquivos-de-job-do-cluster.md](spec_4-arquivos-de-job-do-cluster.md) | `job.o<id>` como texto com SEM ERROS/ERRO; `.qsub` somente leitura | nenhuma | P |
| 5 | [spec_5-grade-e-menu-de-contexto.md](spec_5-grade-e-menu-de-contexto.md) | Grade sem tamanho; atalho `..`; menu de contexto (Abrir local, Abrir com, Copiar, Renomear) | 4 | G |
| 6 | [spec_6-graficos-de-relaxamento.md](spec_6-graficos-de-relaxamento.md) | \|ΔE\| e Força vs passo BFGS para relax/vc-relax | 2, 3 | G |
| 7 | [spec_7-qualidade-ci-e-higiene.md](spec_7-qualidade-ci-e-higiene.md) | CI (GitHub Actions), ícone e `.desktop`, link do PRD, fixtures QE 7.2/7.4, Hypothesis, remoção de código morto, servidor SSH local (paramiko) nos testes de sync | nenhuma | G |
| 8 | [spec_8-contrato-dos-modulos.md](spec_8-contrato-dos-modulos.md) | Hooks no `CalculationModule` (sem `kind ==` na UI), `ParamField.refreshes`, tipagem + pyright, painel de ajustes por sessão | 7 | M |
| 9 | [spec_9-convergencia-scf.md](spec_9-convergencia-scf.md) | Gráfico de convergência do SCF; "Plotar" no menu de contexto; botão "Plotar SCF" | 5, 8 | M |
| 10 | [spec_10-visualizador-de-texto-e-abas.md](spec_10-visualizador-de-texto-e-abas.md) | Busca Ctrl+F, realce de saídas, números de linha, arquivos grandes, menu das abas, coordenadas do cursor | 8 | M |
| 11 | [spec_11-visualizador-de-input.md](spec_11-visualizador-de-input.md) | Realce de inputs, erros de escrita em vermelho, extrato e comparação de dois inputs | 10 | G |
| 12 | [spec_12-resumo-de-saidas.md](spec_12-resumo-de-saidas.md) | "Resumo" no menu de contexto: aba com tempo, paralelização, sistema, resultados e erros da saída | 5, 9, 10 | M |
| 13 | [spec_13-spin-em-bandas-e-pdos.md](spec_13-spin-em-bandas-e-pdos.md) | Divide `bands.py` em módulos; bandas com dois canais (bands.x `spin_component`), gaps por canal, modos de spin na PDOS | 8 | G |
| 14 | [spec_14-desempenho-da-deteccao.md](spec_14-desempenho-da-deteccao.md) | Medir primeiro; ASE tardio, sniff único, F5 sem limpar cache, `.gnu`/pw.x grandes; `FolderMemory` relativo | 7 | M |
| 15 | [spec_15-workers-e-divisao-da-janela.md](spec_15-workers-e-divisao-da-janela.md) | Helper único de tarefas, sem cursor global, exportação em worker, backend de `ui/` movido para `core/`, `MainWindow` dividido em 3 controladores, teste das regras de arquitetura | 7, 8 | G |
| 16 | [spec_16-navegacao-e-multi-selecao.md](spec_16-navegacao-e-multi-selecao.md) | Caminho clicável, histórico Alt+←/→, filtros, favoritos/recentes, multi-seleção na grade | 5, 10, 11, 14 | G |
| 17 | [spec_17-sincronizacao-previa-e-escopo.md](spec_17-sincronizacao-previa-e-escopo.md) | Prévia do plano antes de baixar, escopo explícito, sucesso sem diálogo modal | 15 | M |
| 18 | [spec_18-ajuda-e-primeira-execucao.md](spec_18-ajuda-e-primeira-execucao.md) | Menu Ajuda, paleta Ctrl+K, legenda dos badges, rodapé elidido, estado vazio da primeira execução | 15, 16 | M |
| 19 | [spec_19-tema-e-acessibilidade.md](spec_19-tema-e-acessibilidade.md) | Tema "Sistema", `ui.font_scale`, contraste WCAG dos tokens, foco visível e ordem de Tab | nenhuma | M |
| 20 | [spec_20-internacionalizacao.md](spec_20-internacionalizacao.md) | Português (padrão) e inglês via gettext; `ui.language` | todas | G |

Critério de ordem: primeiro as correções e ajustes que afetam o uso diário e são pré-requisito de
outras specs (1, 2), depois a persistência que depende delas (3), os ganhos pequenos e independentes (4),
o menu de contexto (5, maior e isolado) e, por último, a funcionalidade nova maior (6), que reaproveita
estilo e persistência.

Critério de ordem das specs 7–20 (decisão de 30/09/2026: "base mínima primeiro"):
1. **Base mínima (7, 8):** CI e o contrato dos módulos, que barateiam e protegem tudo o que vem depois.
2. **Features novas (9–13):** SCF, visualizador de texto e de input, resumo e spin. O texto (10) vem antes
   do input (11), que o estende.
3. **Desempenho e refatoração (14, 15):** feitas depois das features, para que o código novo seja movido
   uma vez só.
4. **Interface (16–19):** navegação, sync, ajuda e acessibilidade, sobre a janela já dividida.
5. **Idioma (20):** por último, quando os textos estiverem estáveis.

Esforço: P = pequeno (horas), M = médio (~1 dia), G = grande (mais de 1 dia).

## Rastreabilidade: `Ideias.md` → specs

| # | Item de `Ideias.md` (resumido) | Spec |
|---|---|---|
| 1 | Workspace de gráficos/inputs não deve iniciar ao abrir o programa | spec 1, R1 |
| 2 | Duplo clique num input ou figura abre o workspace | spec 1, R2 |
| 3 | Divisórias mantêm a proporção ao abrir ou fechar abas | spec 1, R3 |
| 4 | Remover o botão "Ajuste" da barra lateral | spec 1, R4 |
| 5 | Grade: remover o tamanho do arquivo, manter OK/incompleto | spec 5, R1 |
| 6 | Botão "Plot" abre o workspace e os ajustes e plota sem salvar | spec 1, R5 |
| 7 | Clique direito: Abrir local de origem, Abrir com, Copiar, Renomear | spec 5, R3 |
| 8 | Grade: atalho `..` como primeiro elemento | spec 5, R2 |
| 9 | Rodapé com informações do gráfico desatualizadas | spec 1, R6 |
| 10 | Arquivos `*.o*` (erros do job) como texto; vazio = sem erro | spec 4, R1–R4 |
| 11 | Fundo da figura sempre branco (hoje segue o tema) | spec 2, R1 |
| 12 | Parâmetro de cor de fundo na aba de ajustes (padrão branco) | spec 2, R2–R5 |
| 13 | Persistir mudanças de runtime após fechar o app | spec 3 (+ extras propostos) |
| 14 | `.qsub` como texto, somente visualização | spec 4, R5 |
| 15 | Plots de relax/vc-relax (\|ΔE\| e Força vs passo BFGS, log/linear) | spec 6 |
| 16 | (persistir) posição dos divisores verticais | spec 3, R1 |
| 17 | (persistir) ajustes do gráfico em arquivo `.plot` na pasta da simulação | spec 3, R2 |

## Rastreabilidade: `report.md` → specs

| Item do `report.md` | Destino |
|---|---|
| F1 Convergência SCF | spec 9 |
| F2 DOS total (dos.x) | adiado |
| F3 Exportar dados / copiar imagem | adiado (inclusive os botões da barra do gráfico) |
| F4 vc-relax completo | adiado |
| F5 Bandas + DOS combinados | adiado |
| F6 Bandas com spin | spec 13 (R1–R4), com a extensão da PDOS (R5) |
| F7 Predefinições de estilo | adiado |
| F8 Painel Resumo | spec 12 |
| F9 Comparar/sobrepor simulações | adiado (a multi-seleção da spec 16 é a base) |
| F10 Acompanhamento ao vivo | adiado (inclusive "seguir arquivo") |
| F11 Monitor de jobs | adiado (scheduler decidido: SGE) |
| F12 CLI headless | adiado |
| F13 Abrir pasta / recentes / assistente | adiado (só o estado vazio da primeira execução entra, spec 18 R5) |
| F14 Chave do host pela UI / keyring | adiado |
| F15 Visualizador de input | spec 11 |
| F16 Push | adiado (fora de escopo pelo PRD) |
| A1 `MainWindow` com 4 responsabilidades | spec 15, R4 |
| A2 Boilerplate de worker | spec 15, R1 |
| A3 Contrato do módulo vaza para a UI | spec 8, R1–R3 |
| A4 Tipagem frouxa | spec 8, R4 |
| A5 `FolderMemory` com caminho absoluto | spec 14, R7 |
| A6 Sem CI | spec 7, R1 |
| A7 Ícone, `.desktop`, link do README | spec 7, R2–R3 |
| A8 Exportação no thread da GUI | spec 15, R3 |
| O1 `.gnu` lido inteiro no sniff | spec 14, R5.1 |
| O2 `invalidate()` limpa todo o cache | spec 14, R4 |
| O3 Sniff por módulo | spec 14, R3 |
| O4 ASE importado no início | spec 14, R2 |
| O5 `parse_pw_output` varre 16 MB | spec 14, R5.2 |
| O6 `ParamsPanel.bind` reconstrói tudo | spec 8, R5 |
| O7 Cursor global de ocupado | spec 15, R2 |
| O8 Sem teste de latência da detecção | spec 14, R1 |
| Robustez: fixtures 7.2/7.4 | spec 7, R4 (6.x **não**: foco no QE ≥ 7.1) |
| Robustez: testes de propriedade | spec 7, R5 |
| Robustez: `TextViewer.reload` sem uso | spec 7, R6.1 (removido) |
| Robustez: remover `plot.export.theme` | spec 7, R6.2 |
| UI: breadcrumb + histórico | spec 16, R1–R2 |
| UI: filtro rápido e por badge/estado | spec 16, R3 |
| UI: favoritos/recentes | spec 16, R4 |
| UI: multi-seleção na grade | spec 16, R5 |
| UI: paleta de comandos Ctrl+K | spec 18, R2 |
| UI: visualizador de texto (busca, realce, linhas, ir ao fim, arquivos grandes) | spec 10, R1–R4 |
| UI: seguir arquivo | adiado (F10) |
| UI: menu de contexto da aba e botão do meio | spec 10, R5 |
| UI: divisão do workspace | **fora** (decisão do usuário) |
| UI: coordenadas do cursor | spec 10, R6 |
| UI: sucesso do sync não modal | spec 17, R3 |
| UI: rodapé elidido | spec 18, R4 |
| UI: estado vazio de primeira execução | spec 18, R5 |
| UI: menu Ajuda (atalhos, sobre, log) | spec 18, R1 |
| UI: legenda dos badges | spec 18, R3 |
| UI: tema "Sistema" e `ui.font_scale` | spec 19, R1–R2 |
| UI: contraste, ordem de Tab, foco visível | spec 19, R3–R4 |
| UI: prévia do plano de sync | spec 17, R2 |
| UI: escopo explícito do Rsync | spec 17, R1 |
| §5 Decisão 4: idioma (`tr()`) | spec 20 |
| `CLAUDE.md`: testes de sync com servidor SSH local (paramiko) | spec 7, R7 |
| `CLAUDE.md`: arquivos de até ~500 linhas | spec 13, R0 (`bands.py`); spec 15, R4 e R6 (`main_window.py` e teste automático) |
| `CLAUDE.md`: `ui/` só com lógica de interface | spec 15, R5 e R6 |

## Decisões já tomadas (30/09/2026)
- Workspace **sempre** oculto ao abrir o Lain, com a largura lembrada.
- Relax: **uma figura com dois painéis**, com parâmetros "Painéis" (ambos/|ΔE|/força) e "Escala".
- Ajustes persistidos em **um arquivo por tipo** (`bands.plot`, `pdos.plot`, `relax.plot`, YAML).
- "Abrir com": **submenu** de programas instalados (`.desktop`) + "Outro programa…".

Decisões sobre o `report.md` (30/09/2026):
- Features: só **F1** (SCF), **F6** + spin na PDOS, **F8** (Resumo) e **F15** (input). As demais F's
  ficam para depois.
- Arquitetura e otimização: specs para **todos** os itens (A1–A8, O1–O8).
- Robustez: foco no **QE ≥ 7.1**. Nada de fixtures ou suporte para versões mais antigas.
- Interface: tudo, **menos** a divisão do workspace. Dos itens ligados a F's adiadas, entram a
  multi-seleção na grade e a primeira execução. Ficam fora os botões copiar imagem/exportar dados (F3)
  e o "seguir arquivo" (F10).
- SCF: "Plotar" no menu de contexto da saída SCF e o botão "Plotar SCF", visível só com uma saída SCF
  aberta.
- Resumo: **aba no workspace**, não é salvo.
- F15: destaque em vermelho só para **erros de escrita** (aspas, `/`, `=`, parênteses, nome de
  namelist/card). Nome de parâmetro errado fica para uma validação futura.
- Ordem: **base mínima primeiro** (CI + contrato), depois as features, depois refatoração e UI.
- Idioma: spec própria (português padrão + inglês).

Cada spec tem ainda uma seção **"Decisões assumidas (confirmar na revisão)"** com os pontos que foram
interpretados e que devem ser confirmados ou corrigidos antes de implementar.
