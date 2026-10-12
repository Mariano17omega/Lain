# Specs do Lain: QE Studio

`Archived/spec_0-PRD.md` é o documento de requisitos original. As specs 1–6 organizam a primeira rodada de
`Ideias.md` (ajustes, correções e funcionalidades novas), as specs 7–19 organizam `report.md` (análise de
30/09/2026) e as specs 20–27 organizam a **segunda rodada** de `Ideias.md` (04/10/2026: gap de energia na legenda,
átomos da PDOS, bandas com DOS, Grids, SCF convergido, "Criar cálculo" e envio ao cluster) e as specs 28–31
organizam a **terceira rodada** (05/10/2026: padrões de unidade de simulação, modo Padrão/Avançado, carga, diferença
de carga e Projetos) e a spec 32 a **quarta** (06/10/2026: nomes de exportação com o caminho do projeto, CSV dos dados, roda do
mouse no painel de ajustes e o botão "Átomos…" da PDOS) e as specs 33–39 a **quinta** (12/10/2026: pequenos defeitos do Resumo,
do menu e da barra, método do gap, "Plotar" do relax, deslocamento da legenda, grade e árvore, Markdown e `.qsub` no visualizador,
e o "Criar cálculo": "Continuar" mudo e edição no modo Avançado), em grupos de itens relacionados e em ordem de prioridade. A internacionalização (`spec_end`)
fica por último. Cada spec é autossuficiente e pode virar um `/plan` de implementação separado, nesta ordem:

```
/plan implementar specs/spec_end-internacionalizacao.md
```

## Roadmap

| # | Spec | Resumo | Depende de | Esforço | Modelo |
|---|---|---|---|---|---|
| 1 | [spec_1-paineis-e-navegacao.md](Archived/spec_1-paineis-e-navegacao.md) | Workspace oculto no início, abre sozinho; divisores mantêm a proporção; sem botão "Ajuste"; "Plot" plota sem salvar; rodapé coerente | nenhuma | M | — |
| 2 | [spec_2-fundo-das-figuras.md](Archived/spec_2-fundo-das-figuras.md) | Figura sempre com fundo branco, independente do tema; parâmetro "Cor de fundo" | nenhuma | P | — |
| 3 | [spec_3-persistencia-de-estado.md](Archived/spec_3-persistencia-de-estado.md) | Divisores persistidos; ajustes do gráfico em `<tipo>.plot` na pasta da simulação | 1, 2 | M | — |
| 4 | [spec_4-arquivos-de-job-do-cluster.md](Archived/spec_4-arquivos-de-job-do-cluster.md) | `job.o<id>` como texto com SEM ERROS/ERRO; `.qsub` somente leitura | nenhuma | P | — |
| 5 | [spec_5-grade-e-menu-de-contexto.md](Archived/spec_5-grade-e-menu-de-contexto.md) | Grade sem tamanho; atalho `..`; menu de contexto (Abrir local, Abrir com, Copiar, Renomear) | 4 | G | — |
| 6 | [spec_6-graficos-de-relaxamento.md](Archived/spec_6-graficos-de-relaxamento.md) | \|ΔE\| e Força vs passo BFGS para relax/vc-relax | 2, 3 | G | — |
| 7 | [spec_7-qualidade-ci-e-higiene.md](Archived/spec_7-qualidade-ci-e-higiene.md) | CI (GitHub Actions), ícone e `.desktop`, link do PRD, fixtures QE 7.2/7.4, Hypothesis, remoção de código morto, servidor SSH local (paramiko) nos testes de sync | nenhuma | G | — |
| 8 | [spec_8-contrato-dos-modulos.md](Archived/spec_8-contrato-dos-modulos.md) | Hooks no `CalculationModule` (sem `kind ==` na UI), `ParamField.refreshes`, tipagem + pyright, painel de ajustes por sessão | 7 | M | — |
| 9 | [spec_9-convergencia-scf.md](Archived/spec_9-convergencia-scf.md) | Gráfico de convergência do SCF; "Plotar" no menu de contexto; botão "Plotar SCF" | 5, 8 | M | — |
| 10 | [spec_10-visualizador-de-texto-e-abas.md](Archived/spec_10-visualizador-de-texto-e-abas.md) | Busca Ctrl+F, realce de saídas, números de linha, arquivos grandes, menu das abas, coordenadas do cursor | 8 | M | — |
| 11 | [spec_11-visualizador-de-input.md](Archived/spec_11-visualizador-de-input.md) | Realce de inputs, erros de escrita em vermelho, extrato e comparação de dois inputs | 10 | G | — |
| 12 | [spec_12-resumo-de-saidas.md](Archived/spec_12-resumo-de-saidas.md) | "Resumo" no menu de contexto: aba com tempo, paralelização, sistema, resultados e erros da saída | 5, 9, 10 | M | — |
| 13 | [spec_13-spin-em-bandas-e-pdos.md](Archived/spec_13-spin-em-bandas-e-pdos.md) | Divide `bands.py` em módulos; bandas com dois canais (bands.x `spin_component`), gaps por canal, modos de spin na PDOS | 8 | G | — |
| 14 | [spec_14-desempenho-da-deteccao.md](Archived/spec_14-desempenho-da-deteccao.md) | Medir primeiro; ASE tardio, sniff único, F5 sem limpar cache, `.gnu`/pw.x grandes; `FolderMemory` relativo | 7 | M | — |
| 15 | [spec_15-workers-e-divisao-da-janela.md](Archived/spec_15-workers-e-divisao-da-janela.md) | Helper único de tarefas, sem cursor global, exportação em worker, backend de `ui/` movido para `core/`, `MainWindow` dividido em 3 controladores, teste das regras de arquitetura | 7, 8 | G | — |
| 16 | [spec_16-navegacao-e-multi-selecao.md](Archived/spec_16-navegacao-e-multi-selecao.md) | Caminho clicável, histórico Alt+←/→, filtros, favoritos/recentes, multi-seleção na grade | 5, 10, 11, 14 | G | — |
| 17 | [spec_17-sincronizacao-previa-e-escopo.md](Archived/spec_17-sincronizacao-previa-e-escopo.md) | Prévia do plano antes de baixar, escopo explícito, sucesso sem diálogo modal | 15 | M | — |
| 18 | [spec_18-ajuda-e-primeira-execucao.md](Archived/spec_18-ajuda-e-primeira-execucao.md) | Menu Ajuda, paleta Ctrl+K, legenda dos badges, rodapé elidido, estado vazio da primeira execução | 15, 16 | M | — |
| 19 | [spec_19-tema-e-acessibilidade.md](Archived/spec_19-tema-e-acessibilidade.md) | Tema "Sistema", `ui.font_scale`, contraste WCAG dos tokens, foco visível e ordem de Tab | nenhuma | M | — |
| 20 | [spec_20-legenda-com-gap-de-energia.md](Archived/spec_20-legenda-com-gap-de-energia.md) | Checkbox "Gap de energia na legenda" em bandas e PDOS (gap = CBM − VBM, não a energia de Fermi); na PDOS vem do HOMO/LUMO ou da curva de DOS | 13 | M | — |
| 21 | [spec_21-selecao-de-atomos-na-pdos.md](Archived/spec_21-selecao-de-atomos-na-pdos.md) | Botão "Átomos…" em Projeções; seleção por composto (fórmula + ordem das espécies) lembrada em `compounds.json` | 20 | M | — |
| 22 | [spec_22-bandas-com-dos.md](Archived/spec_22-bandas-com-dos.md) | "Bandas com DOS" no menu de contexto (1 pasta de bandas + 1 de PDOS): figura com eixo de energia compartilhado | 13, 16, 20, 21 | G | — |
| 23 | [spec_23-grids-de-graficos.md](Archived/spec_23-grids-de-graficos.md) | Botão "Grids": grade N×M de gráficos já plotados, com posição e título, salva por nome | 15, 22 | G | — |
| 24 | [spec_24-editor-de-inputs-e-scf-convergido.md](Archived/spec_24-editor-de-inputs-e-scf-convergido.md) | Editor de inputs do pw.x que preserva formatação; "Gerar SCF convergido" (só o `.in`) no menu de saídas de relax/vc-relax convergidos | 5, 11, 17 | M | — |
| 25 | [spec_25-criar-calculo-templates-e-geracao.md](Archived/spec_25-criar-calculo-templates-e-geracao.md) | Backend de "Criar cálculo": templates Jinja2 (`qsub/`, `qe/`), extração do SCF, k-path (pymatgen), pasta sem sobrescrever | 24 | G | — |
| 26 | [spec_26-criar-calculo-janela.md](Archived/spec_26-criar-calculo-janela.md) | Botão "Criar cálculo" na barra lateral; janela em duas etapas com abas por arquivo, Arquivos e Descrição (`.md`) | 18, 25 | G | — |
| 27 | [spec_27-enviar-ao-cluster.md](Archived/spec_27-enviar-ao-cluster.md) | Push seguro: só arquivos novos, nunca sobrescreve o remoto, sempre com prévia | 15, 17 | M | — |
| 27-1 | [spec_27-1-pdos-gerado-script-e-ocupacao.md](Archived/spec_27-1-pdos-gerado-script-e-ocupacao.md) | PDOS gerado: `mv *pdos_atm#* orbitals/` (o `mv *wfc*` movia `projwfc.in/out`); `projwfc.in` sem `ngauss/degauss` com tetraedros | 25, 26 | P | Sonnet 5.5 |
| 27-2 | [spec_27-2-caminho-de-bandas-sem-sugestao.md](Archived/spec_27-2-caminho-de-bandas-sem-sugestao.md) | Remove "Sugerir caminho" e o `pymatgen`; avisa segmentos que colapsam no eixo x do `bands.x`; botão "Distribuir pelo comprimento"; `nan`/`inf` e quebra no editor | 25, 26 | M | Sonnet 5.5 |
| 27-3 | [spec_27-3-sync-e-gravacao-seguros.md](Archived/spec_27-3-sync-e-gravacao-seguros.md) | `StrictHostKeyChecking=yes` imposto; renomear recusado durante sync/export; corrida do pull; escrita atômica com `fsync` e instância única; `rename` sem sobrescrever | 15, 17, 27 | M | Opus 5.5 |
| 27-4 | [spec_27-4-memoria-e-cancelamento.md](Archived/spec_27-4-memoria-e-cancelamento.md) | Cache de datasets por bytes e esvaziado ao fechar a aba; parsers com pico menor; cancelamento cooperativo (`core/cancel.py`) dos loaders | 14, 15 | M | Opus 5.5 |
| 27-5 | [spec_27-5-fechamento-dialogos-e-erros.md](Archived/spec_27-5-fechamento-dialogos-e-erros.md) | Fechamento com orçamento de tempo e `hide()`; diálogos fechados antes (B8 corrigido); `excepthook` sem enxurrada de modais; `main_window.py` ≤ 450 linhas | 15, 26, 27-3, 27-4 | M | Opus 5.5 |
| 27-6 | [spec_27-6-avisos-de-fisica.md](Archived/spec_27-6-avisos-de-fisica.md) | Gap só com E_F coerente e rotulado "no caminho"; aviso de seleção de átomos salva em outra geometria; avisos do SCF convergido | 13, 20, 21, 24 | P/M | Sonnet 5.5 |
| 27-7 | [spec_27-7-vc-relax-entalpia-e-celula.md](Archived/spec_27-7-vc-relax-entalpia-e-celula.md) | vc-relax: \|ΔH\| no lugar de \|ΔE\|, pressão, volume e célula por passo; painéis `all`; resumo | 6, 12 | M | Opus 5.5 |
| 27-8 | [spec_27-8-gui-grid-sistema-de-arquivos-e-deteccao.md](Archived/spec_27-8-gui-grid-sistema-de-arquivos-e-deteccao.md) | Grid 6×6 desenhado em worker (a GUI pára 0,1 s em vez de 2,4 s); menos `resolve` na GUI e teste de arquitetura; invalidação só das irmãs `*scf*`; detecção que não zera a pasta | 14, 15, 22, 23 | M | Sonnet 5.5 |
| 27-9 | [spec_27-9-pequenos-defeitos-e-dados-pessoais.md](Archived/spec_27-9-pequenos-defeitos-e-dados-pessoais.md) | "Abrir com" oculta programas de terminal; pedido repetido de carga substitui o anterior; placeholders no `config.example.yaml` e cabeçalhos anonimizados | 5, 7, 15 | P | Sonnet 5.5 |
| 28 | [spec_28-padroes-e-modo-padrao-avancado.md](Archived/spec_28-padroes-e-modo-padrao-avancado.md) | Padrão de nomes (pastas `Bands_<nome>`, inputs `scf_<prefix>.in`…), pasta autossuficiente (`outdir './tmp/'`, `jobs.pseudo_dir`, `jobs.nk`); botão "Padrão / Avançado" no "Criar cálculo" | 25, 26, 27-1, 27-2 | G | Opus 5.5 |
| 29 | [spec_29-calculo-de-carga.md](Archived/spec_29-calculo-de-carga.md) | Tipo "Carga" (`pp.x`): `pp_<nome>_charge.in`, `charge.qsub` com `mkdir -p cdd_xsf`; lint reconhece inputs do `pp.x` | 28 | M | Sonnet 5.5 |
| 30 | [spec_30-diferenca-de-carga.md](Archived/spec_30-diferenca-de-carga.md) | Tipo "Diferença de carga": aba "Átomos", SCFs `_clean` e `_isolated` gerados do base, `pp_charge_diff.in` (Δρ = base − clean − isolated) | 29, 28, 21 | G | Opus 5.5 |
| 31 | [spec_31-projetos.md](Archived/spec_31-projetos.md) | Pastas de 1º nível de `local_root` = Projetos; dropdown "Projeto" filtra árvore, grade, breadcrumb e paleta; "Criar projeto…"; sync do projeto selecionado | 16, 17, 18, 26, 27 | M/G | Opus 5.5 |
| 32 | [spec_32-exportacao-nomes-csv-e-ajustes.md](Archived/spec_32-exportacao-nomes-csv-e-ajustes.md) | Figuras exportadas como `<projeto>-<pastas>-<tipo>.png`; CSV (`;`, vírgula decimal, nomes das colunas) ao lado das figuras de bandas, PDOS e bandas + DOS; a roda do mouse não mexe nos campos do painel de ajustes; corrige o botão "Átomos…" da PDOS (`WA_DeleteOnClose` + `exec`) | 15, 21, 22, 31 | G | Opus 5.5 |
| 33 | [spec_33-pequenos-defeitos-resumo-reveal-e-barra.md](Archived/spec_33-pequenos-defeitos-resumo-reveal-e-barra.md) | Resumo: "k-pontos irredutíveis" e "Malha k" (do input de mesmo nome); "Abrir local de origem" lê a resposta D-Bus com `QDBusPendingReply` (hoje falha em toda chamada); barra superior só com o LED (o `usuario@host` vai para o tooltip) | 5, 11, 12 | P | Sonnet 5.5 |
| 34 | [spec_34-gap-metodo-de-calculo.md](Archived/spec_34-gap-metodo-de-calculo.md) | Parâmetro `gap_method` (automático, HOMO/LUMO do SCF, maior intervalo na janela) em bandas, PDOS e bandas + DOS; legenda e rodapé seguem o método; reproduz o "metálico" da pasta real (já corrigido em `f5492fb`, mas com 0,07 eV) | 13, 20, 21, 22, 27-6 | M | Opus 5.5 |
| 35 | [spec_35-plotar-saida-de-relax-pelo-menu.md](Archived/spec_35-plotar-saida-de-relax-pelo-menu.md) | "Plotar" no menu das saídas de relax/vc-relax: aba por saída, input pareado por nome (hoje casa o de outra corrida), aviso de várias saídas, rótulo do botão por módulo | 6, 9, 27-7 | M | Sonnet 5.5 |
| 36 | [spec_36-deslocamento-da-legenda.md](spec_36-deslocamento-da-legenda.md) | Campos `dx` e `dy` na seção "Legenda" (fração do painel; `best` com deslocamento = `upper right`), para todos os módulos | 8, 20, 22, 23 | P | Sonnet 5.5 |
| 37 | [spec_37-grade-nomes-completos-e-arvore-com-arquivos.md](spec_37-grade-nomes-completos-e-arvore-com-arquivos.md) | Nome do arquivo quebra linha no cartão da grade (altura única por pasta, até 6 linhas); árvore só de pastas por padrão, com `ui.tree_show_files` | 5, 16, 19, 31 | M | Sonnet 5.5 |
| 38 | [spec_38-visualizador-markdown-e-qsub.md](spec_38-visualizador-markdown-e-qsub.md) | `.md` renderizado (alterna para o texto, sem HTML cru, links locais não abrem); `.qsub` com `ShellHighlighter` e verificação de escrita em `core/qsub_lint.py` | 10, 11, 19, 26 | G | Sonnet 5.5 |
| 39 | [spec_39-criar-calculo-falha-silenciosa-e-edicao-avancada.md](spec_39-criar-calculo-falha-silenciosa-e-edicao-avancada.md) | "Continuar" nunca mudo e rede de testes tipo × SCF (a Diferença de carga **não foi reproduzida**); prévia editável só no Avançado, a edição vence o formulário | 24, 26, 28, 30, 38 | M | Opus 5.5 |
| fim | [spec_end-internacionalizacao.md](spec_end-internacionalizacao.md) | Português (padrão) e inglês via gettext; `ui.language` | todas | G | — |

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
6. **Padrões e Projetos (28–31, decisão de 05/10/2026):** primeiro o padrão de nomes e o modo Padrão/Avançado (28),
   base dos dois tipos novos, depois a carga (29), cujo template e script a diferença de carga (30) reaproveita. Os
   Projetos (31) não dependem de 28–30 e podem vir antes deles.
7. **Correções da revisão de 04/10/2026 (27-1 … 27-9, decisão de 05/10/2026):** o usuário implementa antes da spec 28.
   27-1 e 27-2 antes de tudo (a 28 parte do `pdos.qsub` e do caminho das bandas que elas deixam); 27-3 e 27-5 extraem
   código de `main_window.py` (496/500 linhas) e abrem folga para a 31; 27-4 antes da 27-5 (loaders canceláveis tornam o
   fechamento rápido). As demais (27-6 … 27-9) são independentes entre si.
8. **Exportação e ajustes (32, decisão de 06/10/2026):** independente de 28–31 e sem pressa por ordem, mas o R1 (botão "Átomos…"
   da PDOS, um defeito) pode ser feito já, antes de tudo, e o R2 (roda do mouse) também; R3 (nomes) vem antes de R4 (CSV).
9. **Ajustes de 12/10/2026 (33–39):** os defeitos primeiro (33: "Abrir local de origem" falha em toda chamada hoje), depois o método
   do gap (34, a queixa mais antiga da lista), os ganhos pequenos e independentes (35 relax, 36 legenda), os dois ajustes de painel (37),
   o visualizador (38) e, por último, o "Criar cálculo" (39), que usa o `lint_script` da 38 para o script editado. A 33 (R2) pode
   sair antes de tudo; nenhuma depende das outras do grupo, só a 39 da 38 (e só para verificar o script).
10. **Idioma (`spec_end`):** por último, quando os textos estiverem estáveis.

Esforço: P = pequeno (horas), M = médio (~1 dia), G = grande (mais de 1 dia).

Specs já implementadas (1–35, inclusive 27-1 … 27-9) e o PRD (`spec_0`) ficam em [`Archived/`](Archived/); aqui na
raiz ficam as propostas ainda abertas (`spec_end` e as specs 36–39) e os relatórios. Ao implementar uma spec, mova-a para `Archived/` e
ajuste o link da tabela abaixo.

Modelo (specs a partir da 28): o modelo Claude recomendado para implementar a spec. **Opus 5.5**
(`claude-opus-5-5`) quando a spec muda contratos usados em vários lugares, mexe em física ou em código perto do limite
de 500 linhas; **Sonnet 5.5** (`claude-sonnet-5-5`) quando segue um caminho que outra spec já abriu. O motivo está na
tabela do início de cada spec. "—" = spec já implementada ou anterior a esta convenção.

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

## Rastreabilidade: `report-04-10-26.md` → specs

| Achado | Destino |
|---|---|
| F1 `mv *wfc*` do `pdos.qsub` (Alto) + Q1(a) | spec 27-1, R1–R2 |
| F2 `npts` uniforme / eixo x colapsado (Alto) + Q1(b) | spec 27-2, R2–R3 e R5 (sem sugestão automática: decisão do usuário) |
| F3 gap só pela contagem de elétrons | spec 27-6, R1 |
| F4 vc-relax: entalpia, pressão, célula | spec 27-7 |
| F5 PDOS: `Emax` × `nbnd`; `degauss` × tetraedros | spec 27-1, R3–R4 (só texto para `Emax`) |
| F5 malha do NSCF = malha do SCF | **mantida** (decisão do usuário: sem aviso) |
| F6 seleção de átomos por sequência de espécies | spec 27-6, R2 |
| F7 SCF convergido reaproveita `prefix`/`outdir` | spec 27-6, R3 |
| F8 fixtures reais de ibrav 4 e 5 | adiado (precisa de saídas reais do usuário; spec 27-2, "Fora de escopo") |
| F9 mapeamento pymatgen → célula | **obsoleto** (spec 27-2 remove "Sugerir") |
| B1 "Abrir com" e `Terminal=true` | spec 27-9, R1 (ocultar) |
| B2 renomear com sync em andamento | spec 27-3, R2 |
| B3 editor de k-path (`nan`/`inf`, quebra) | spec 27-2, R4 |
| B4 `_detect` engole exceções | spec 27-8, R5 |
| B5 `excepthook` | spec 27-5, R3 |
| B6 `_load` ignora o pedido repetido | spec 27-9, R2 |
| B7 corridas (pull; `flush_now`) | spec 27-3, R3 |
| B8 diálogos não modais ao fechar | spec 27-5, R2 (o achado foi corrigido na verificação: `GridDialog` não tem pergunta) |
| T1 fechamento lento | spec 27-5, R1 |
| T2 grid na GUI thread | spec 27-8, R1–R2 (medir primeiro) |
| T3 loaders não cancelam | spec 27-4, R1 |
| T4 sistema de arquivos na GUI | spec 27-8, R3 |
| T5 `invalidate` apaga as irmãs | spec 27-8, R4 |
| M1 cache de datasets | spec 27-4, R2–R3 |
| S1 `StrictHostKeyChecking` | spec 27-3, R1 |
| S2 escrita atômica e instância única | spec 27-3, R4 |
| S3 `rename_item` e TOCTOU | spec 27-3, R5 |
| S4 dados pessoais | spec 27-9, R3 (placeholders; fixtures e histórico fora) |
| Q1 testes que travam o erro | specs 27-1 (a) e 27-2 (b) |
| Q2 `main_window.py` com 496/500 linhas | specs 27-3 (`rename_path`) e 27-5 (`closeEvent` etc.), R4 |
| Q3 `pymatgen` runtime / CI | `pymatgen` removido (spec 27-2); CI (3.13, cobertura, `--locked`, pyright): sem decisão |
| Q4 `specs/Ideias.md` zerado | sem spec (estado do working tree do usuário) |

## Rastreabilidade: ideias da terceira rodada (05/10/2026) → specs

As ideias vieram no pedido (não em `Ideias.md`); cada spec cita o trecho de origem.

| # | Ideia (resumida) | Spec |
|---|---|---|
| 1 | Cada pasta é uma simulação completa e independente, sem caminhos absolutos ou externos | spec 28, R2 (`outdir './tmp/'`, `jobs.pseudo_dir`) |
| 2 | "Unidade de simulação" = pasta de cálculo, com `.qsub`, `.in` e `.out` | spec 28, R1 (só nome: sem tratamento especial na árvore/grade, decisão do usuário) |
| 3 | Pastas `<calculo>_<nome>` ou `<calculo>` (Bands, Relax, PDOS, Charge, Diff_Charge, SCF…) | spec 28, R1.1–R1.2; specs 29 e 30, R1 |
| 4 | Inputs `scf/nscf/relax/vc-relax_<prefix>.in`; `bands_pp.in`, `projwfc.in`; saídas com `.out` | spec 28, R1.3–R1.4 |
| 5 | `pp_<nome>_charge.in`, `pp_charge.in`, `pp_charge_diff.in` | spec 29, R1; spec 30, R1 |
| 6 | Pastas `<numero>_Bands_<nome>` existentes continuam válidas, sem ser o padrão | spec 28, "Fora de escopo" (detecção por conteúdo) |
| 7 | Botão "Avançado/Padrão" na janela de criação | spec 28, R3–R5 |
| 8 | Bandas Padrão: só `K_POINTS crystal_b`; `bands_pp.in` com `filband './band'`; NP 64, NK 4 | spec 28, R3.3 e R3.5; R2.3 |
| 9 | PDOS Padrão: `projwfc.in` fixo (DeltaE, ngauss, degauss 0.000735), só Emin/Emax editáveis | spec 28, R3.3–R3.4 (malha do NSCF = a do SCF, oculta) |
| 10 | Carga: template `pp_<nome>_charge.in`, só nome e SCF no Padrão | spec 29 |
| 11 | Diferença de carga: SCFs `_clean` e `_isolated`, aba com tabela de átomos e "selecionar todos", `pp_charge_diff.in` | spec 30 |
| 12 | Pastas de 1º nível de `local_root` = Projetos isolados | spec 31, R1 |
| 13 | Reconhecer as unidades do projeto em qualquer subpasta | spec 31, R3.1 (a árvore do projeto mostra todas; sem lista nova, decisão do usuário) |
| 14 | Dropdown "Projeto" acima da árvore, filtrando-a | spec 31, R2–R3 |
| 15 | "Criar Projeto" no dropdown, com diálogo de nome | spec 31, R4 |
| — | (`report-04-10-26.md` F1) `mv *wfc*` do `pdos.qsub` move `projwfc.in/out` | spec 27-1, R1 (a spec 28 R6 só aponta para ela) |

## Rastreabilidade: ideias da quarta rodada (06/10/2026) → specs

As ideias vieram no pedido (não em `Ideias.md`, que está vazio); a spec cita o trecho de origem.

| # | Ideia (resumida) | Spec |
|---|---|---|
| 1 | Nome das figuras com a estrutura de pastas a partir do projeto: `projeto_ilita-bulk-bandas-bands.png` | spec 32, R3 |
| 2 | CSV com os dados de todos os eixos (bandas, PDOS, bandas com PDOS), vírgula decimal, nomes das colunas, mesma pasta e mesmo nome da imagem | spec 32, R4 (e R3.1 para o nome) |
| 3 | A roda do mouse sobre os campos do painel de ajustes rola o painel, nunca o valor | spec 32, R2 |
| 4 | "Átomos…" da PDOS: marcar, salvar e nada acontece (erro em `ask_atoms`) | spec 32, R1 |
| — | (`report.md` F3) Exportar dados (CSV) | spec 32, R4 (só bandas, PDOS e bandas + DOS; os demais módulos ficam abertos pelo hook `table`) |

## Rastreabilidade: ideias da quinta rodada (12/10/2026) → specs

As ideias vieram em `Ideias.md` (escritas em 06/10/2026, tratadas em 12/10/2026); cada spec cita o trecho de origem.

| # | Ideia (resumida) | Spec |
|---|---|---|
| 1 | Botão do gap na legenda de bandas diz "metálico" num isolante de gap > 1 eV | spec 34, R1–R2 (reproduzido com a pasta real: o aviso foi corrigido em `f5492fb`; o valor esperado vem do método "Maior intervalo na janela") |
| 2 | Os dois métodos de gap dos scripts de `Documentation/Exemplos_plot/` (HOMO/LUMO e maior intervalo) como escolha do usuário em bandas, PDOS e bandas com PDOS | spec 34, R1–R4 |
| 3 | Campos `dx` e `dy` na seção "Legenda" | spec 36 |
| 4 | Resumo: a linha "k-points" mostra 15 em vez de 5 5 5 | spec 33, R1 (o código não soma: é a contagem de pontos irredutíveis; a malha vem do input) |
| 5 | "Abrir local de origem": `QDBusPendingCallWatcher` sem `isError` | spec 33, R2 |
| 6 | Barra superior: só o círculo de estado do cluster, sem usuário nem endereço | spec 33, R3 |
| 7 | Markdown renderizado no visualizador | spec 38, R1 |
| 8 | `.qsub` com realce e erros de escrita como os inputs | spec 38, R2 |
| 9 | "Diferença de carga": nada acontece depois de escolher o SCF e clicar em "Continuar" | spec 39, R1 (**não reproduzido**; a spec torna a falha visível e pede o SCF que falhou) |
| 10 | Editar inputs e script na própria prévia, só no modo Avançado | spec 39, R2 |
| 11 | "Plotar" no menu das saídas NSCF | **retirada pelo usuário** (12/10/2026): a saída do NSCF não tem iterações de SCF, não há o que plotar |
| 12 | "Plotar" no menu das saídas de relax/vc-relax; o botão "Gerar Gráfico" fica como atalho | spec 35 |
| 13 | Nome completo do arquivo na grade, quebrando linha em vez de `...` | spec 37, R1 |
| 14 | Árvore só com pastas por padrão, com parâmetro no `config.yaml` para mostrar arquivos | spec 37, R2 |

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


Decisões de 05/10/2026 (terceira rodada):
- **Modo Avançado** = os campos que a janela já tem (specs 25/26) e os nomes dos arquivos; **Padrão** mostra só o que o
  tipo pede (caminho das bandas, Emin/Emax da PDOS, átomos da diferença de carga).
- **pseudo_dir** vem de `jobs.pseudo_dir` no `config.yaml`; **NP/NK** de `jobs.cores` e `jobs.nk` (64 e 4), ocultos no
  Padrão.
- **PDOS:** o NSCF usa a malha do SCF, oculta no Padrão (o "crystal_b" do item da PDOS era engano).
- **Prefixos de pasta:** `SCF`, `Relax`, `VC-Relax`, `Bands`, `PDOS`, `Charge`, `Diff_Charge`; scripts `scf.qsub`,
  `relax.qsub`, `vc-relax.qsub`, `bands.qsub`, `pdos.qsub`, `charge.qsub`, `charge_diff.qsub`.
- **Unidades de simulação** são pastas normais: nada de lista, aba ou marca nova; árvore e grade como hoje.
- **Projetos:** "Sincronizar projeto" vale para o projeto selecionado; com "Todos os projetos", para a raiz inteira.
- **Modelo recomendado** por spec (coluna "Modelo" do roadmap): Opus 5.5 para 28, 30 e 31; Sonnet 5.5 para 29.

Decisões de 06/10/2026 (quarta rodada, spec 32):
- **CSV largo:** x + uma coluna por série (bandas + DOS: dois blocos lado a lado); colunas separadas por `;` e vírgula decimal. O "padrão do
  software de origem" do pedido chegou sem o padrão; esta decisão o substitui.
- **Roda do mouse:** bloqueada **só no painel de ajustes do gráfico**; "Criar cálculo" e a tabela do grid ficam como estão.
- **Modelo recomendado:** Opus 5.5 para a 32 (contrato novo no `CalculationModule`, `plan_export` e `base.py` no limite de linhas).

Decisões de 05/10/2026 (correções do `report-04-10-26.md`, specs 27-1 … 27-9):
- **Implementar antes da spec 28**, na ordem do roadmap (27-1 primeiro).
- **Malha do NSCF da PDOS:** continua igual à do SCF, **sem aviso** (F5 não muda a decisão da spec 28).
- **"Abrir com":** programas com `Terminal=true` são ocultados (sem emulador de terminal).
- **"Sugerir caminho" das bandas é removido** (o usuário não quer sugestões); `pymatgen` sai das dependências e o
  caminho `crystal_b` é digitado. O que sobra do F2 vira aviso de segmento colapsado e o botão "Distribuir pelo
  comprimento".
- **Dados pessoais:** placeholders no `config.example.yaml` (duas cópias) e nos cabeçalhos de `Documentation/`;
  fixtures e histórico do git ficam como estão.
- **Modelo recomendado:** Opus 5.5 para 27-3, 27-4, 27-5 e 27-7; Sonnet 5.5 para 27-1, 27-2, 27-6, 27-8 e 27-9
  (a 27-8 passa a Opus 5.5 se a medição exigir desenhar o grid em worker).

Decisões de 12/10/2026 (quinta rodada, specs 33–39):
- **NSCF (ideia 11):** retirada pelo usuário; a saída do NSCF não tem iterações de SCF.
- **Gap (34):** o padrão continua `auto` (o comportamento de hoje); o método "Maior intervalo na janela" é do código do script do usuário
  (maior espaçamento entre vizinhas na faixa visível), não da contagem de bandas, que já é o `auto`. Depende da janela de energia.
  Na implementação: o método só vale com "Gap de energia na legenda" ligado (senão `auto`, rodapé incluído), e o rodapé da PDOS
  ganha o gap só em `homo_lumo` / `janela` (em `auto` segue sem gap).
- **"Diferença de carga" (39, R1):** não reproduzida com o `scf.in` real do usuário, variantes dele e 24 inputs de fixtures; sem causa
  conhecida, a spec só torna a falha visível e monta a rede de testes. Falta o SCF que falhou.
- **Visualizador (38):** Markdown renderizado por padrão com botão para o texto; HTML cru e links locais não abrem; o script é verificado
  por regras escritas (`core/qsub_lint.py`), não por `bash -n`.
- **Edição no Avançado (39):** a edição do arquivo vence o formulário; "Restaurar do formulário" volta ao gerado; as edições não bloqueiam "Criar".
- **Grade e árvore (37):** cartão de altura única por pasta, com limite de 6 linhas; a árvore deixa de mostrar arquivos por padrão
  (`ui.tree_show_files`).
- **Modelo recomendado:** Opus 5.5 para 34 e 39; Sonnet 5.5 para 33, 35, 36, 37 e 38.
