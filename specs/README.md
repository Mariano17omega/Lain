# Specs do Lain: QE Studio

`spec_0-PRD.md` é o documento de requisitos original. As specs 1–6 organizam a primeira rodada de
`Ideias.md` (ajustes, correções e funcionalidades novas), as specs 7–19 organizam `report.md` (análise de
30/09/2026) e as specs 20–27 organizam a **segunda rodada** de `Ideias.md` (04/10/2026: gap de energia na legenda,
átomos da PDOS, bandas com DOS, Grids, SCF convergido, "Criar cálculo" e envio ao cluster), em grupos de itens
relacionados e em ordem de prioridade. A internacionalização (`spec_end`) fica por último. Cada spec é
autossuficiente e pode virar um `/plan` de implementação separado, nesta ordem:

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
| 20 | [spec_20-legenda-com-gap-de-energia.md](spec_20-legenda-com-gap-de-energia.md) | Checkbox "Gap de energia na legenda" em bandas e PDOS (gap = CBM − VBM, não a energia de Fermi); na PDOS vem do HOMO/LUMO ou da curva de DOS | 13 | M |
| 21 | [spec_21-selecao-de-atomos-na-pdos.md](spec_21-selecao-de-atomos-na-pdos.md) | Botão "Átomos…" em Projeções; seleção por composto (fórmula + ordem das espécies) lembrada em `compounds.json` | 20 | M |
| 22 | [spec_22-bandas-com-dos.md](spec_22-bandas-com-dos.md) | "Bandas com DOS" no menu de contexto (1 pasta de bandas + 1 de PDOS): figura com eixo de energia compartilhado | 13, 16, 20, 21 | G |
| 23 | [spec_23-grids-de-graficos.md](spec_23-grids-de-graficos.md) | Botão "Grids": grade N×M de gráficos já plotados, com posição e título, salva por nome | 15, 22 | G |
| 24 | [spec_24-editor-de-inputs-e-scf-convergido.md](spec_24-editor-de-inputs-e-scf-convergido.md) | Editor de inputs do pw.x que preserva formatação; "Gerar SCF convergido" (só o `.in`) no menu de saídas de relax/vc-relax convergidos | 5, 11, 17 | M |
| 25 | [spec_25-criar-calculo-templates-e-geracao.md](spec_25-criar-calculo-templates-e-geracao.md) | Backend de "Criar cálculo": templates Jinja2 (`qsub/`, `qe/`), extração do SCF, k-path (pymatgen), pasta sem sobrescrever | 24 | G |
| 26 | [spec_26-criar-calculo-janela.md](spec_26-criar-calculo-janela.md) | Botão "Criar cálculo" na barra lateral; janela em duas etapas com abas por arquivo, Arquivos e Descrição (`.md`) | 18, 25 | G |
| 27 | [spec_27-enviar-ao-cluster.md](spec_27-enviar-ao-cluster.md) | Push seguro: só arquivos novos, nunca sobrescreve o remoto, sempre com prévia | 15, 17 | M |
| fim | [spec_end-internacionalizacao.md](spec_end-internacionalizacao.md) | Português (padrão) e inglês via gettext; `ui.language` | todas | G |

Critério de ordem: primeiro as correções e ajustes que afetam o uso diário e são pré-requisito de
outras specs (1, 2), depois a persistência que depende delas (3), os ganhos pequenos e independentes (4),
o menu de contexto (5, maior e isolado) e, por último, a funcionalidade nova maior (6), que reaproveita
estilo e persistência.

Critério de ordem das specs 7–`end` (decisão de 30/09/2026: "base mínima primeiro"):
1. **Base mínima (7, 8):** CI e o contrato dos módulos, que barateiam e protegem tudo o que vem depois.
2. **Features novas (9–13):** SCF, visualizador de texto e de input, resumo e spin. O texto (10) vem antes
   do input (11), que o estende.
3. **Desempenho e refatoração (14, 15):** feitas depois das features, para que o código novo seja movido
   uma vez só.
4. **Interface (16–19):** navegação, sync, ajuda e acessibilidade, sobre a janela já dividida.
5. **Plots e geração de cálculos (20–27, decisão de 04/10/2026):** primeiro os plots do dia a dia, em
   cadeia (gap na legenda → átomos da PDOS → bandas com DOS → Grids), depois a geração de inputs (24 cria o
   editor de inputs e os nomes sem sobrescrever que 25 reaproveita; 26 é só a janela sobre 25) e por último o
   envio ao cluster (27). As specs 20 e 24 são independentes e podem vir antes das demais do seu grupo.
6. **Idioma (`spec_end`):** por último, quando os textos estiverem estáveis.

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
| §5 Decisão 4: idioma (`tr()`) | spec end |
| `CLAUDE.md`: testes de sync com servidor SSH local (paramiko) | spec 7, R7 |
| `CLAUDE.md`: arquivos de até ~500 linhas | spec 13, R0 (`bands.py`); spec 15, R4 e R6 (`main_window.py` e teste automático) |
| `CLAUDE.md`: `ui/` só com lógica de interface | spec 15, R5 e R6 |

## Rastreabilidade: `Ideias.md` (segunda rodada, 04/10/2026) → specs

| # | Item de `Ideias.md` (resumido) | Spec |
|---|---|---|
| 1 | Botão "Grids": grade N×M, um gráfico já plotado por quadrante, posição (linha, coluna) e título | spec 23 |
| 2 | Checkbox para incluir o gap de energia ("grap") na legenda (só bandas e PDOS) | spec 20 |
| 3 | "Bandas com DOS" no menu de contexto (pasta de bandas + pasta de DOS), mesmo eixo y | spec 22 (e F5 do `report.md`) |
| 4 | PDOS, seção Projeções: botão "Átomos" (tabela com elemento, x, y, z e checkbox), seleção salva por composto | spec 21 |
| 5 | "Gerar SCF convergido" no menu de relax/vc-relax convergidos (`scf_convergido<prefix>.in`) | spec 24 |
| 6 | Módulo gráfico "Criar cálculo" (scripts e inputs de relax, vc-relax, scf, dos, bandas…), botão na barra lateral | specs 25 (backend) e 26 (janela) |
| 6a | Templates Jinja2 em `resources/templates/qsub/` e `resources/templates/qe/`, por tipo de cálculo | spec 25, R2 |
| 6b | Scripts `.qsub` a partir de `Documentation/Referencia_de_scripts_QSUB`; `#$ -N`, `#$ -pe physica NP`, `nk`; nomes `relax.qsub`, `pdos.qsub`… | spec 25, R3, R6 |
| 6c | Templates de inputs (`projwfc.in`, `bands_pp`, …) | spec 25, R2 (v1: `bands_pp.in`, `projwfc.in`; `pp.x` adiado) |
| 6d | SCF obrigatório; NSCF = cópia com `calculation = 'nscf'`; prefix e demais dados extraídos | spec 25, R4; spec 24, R1 (editor) |
| 6e | Pontos de simetria das bandas com pymatgen, em `K_POINTS crystal_b`; rede manual nos demais | spec 25, R5 (e a decisão 3 da spec) |
| 6f | Campos de formulário (sem editar texto), padrão do SCF, padrão do template quando vazio | specs 25 (R3) e 26 (R4) |
| 6g | Local e sufixo da pasta (`bandas_Al`, `relax_Si`) | spec 25, R7; spec 26, R3 |
| 6h | Nunca substituir: sufixo `_1`, `_2` | spec 24, R2; spec 25, R7 |
| 6i | Criação local; envio ao cluster pela ferramenta de sincronização | spec 27 (push seguro) |
| 6j | Janela com tipo (dropdown), SCF, nome, local; depois abas por template e lista de arquivos | spec 26, R2–R4 |
| 6k | Aba "Descrição" salva em `.md` na pasta do cálculo | spec 26, R4.7; spec 25, R7 |
| 6l | Pasta só criada ao clicar "Criar"; cancelar não cria nada | spec 26, R2 e R5; spec 25, R7 |

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

Decisões de 04/10/2026 (segunda rodada de `Ideias.md`):
- **Envio ao cluster:** spec própria de **push seguro** (27): só arquivos novos, nunca sobrescreve o remoto,
  sempre com prévia. O PRD §5 e o `CLAUDE.md` passam a dizer isso quando a spec for implementada.
- **"Criar cálculo", tipos da v1:** `scf`, `relax`, `vc-relax`, `bandas` e `pdos` (os que o Lain plota). `dos.x`,
  cargas (`pp.x`) e ELF 3D ficam para depois; o registro de tipos facilita acrescentá-los.
- **Átomos da PDOS:** o composto é identificado por **fórmula + ordem das espécies**; a seleção fica no
  diretório de dados do app, nunca na pasta da simulação.
- **SCF convergido:** só o input (`.in`); o `.out` é o nome que o `pw.x` dará ao rodar no cluster.
- Dependências novas (spec 25): `jinja2` e `pymatgen`, ambos com import tardio (como o ASE).
- Convenção de nomes: esta rodada ocupa as specs 20–27; a de idioma passou a se chamar `spec_end`.

