# Specs do Lain: QE Studio

`spec_0-PRD.md` é o documento de requisitos original. As demais specs organizam
`Ideias.md` (ajustes, correções e funcionalidades novas) em grupos de itens relacionados, em ordem de
prioridade. Cada spec é autossuficiente e pode virar um `/plan` de implementação separado, nesta ordem:

```
/plan implementar specs/spec_1-paineis-e-navegacao.md
```

## Roadmap

| # | Spec | Resumo | Depende de | Esforço |
|---|---|---|---|---|
| 1 | [spec_1-paineis-e-navegacao.md](spec_1-paineis-e-navegacao.md) | Workspace oculto no início, abre sozinho; divisores mantêm a proporção; sem botão "Ajuste"; "Plot" só abre; rodapé coerente | nenhuma | M |
| 2 | [spec_2-fundo-das-figuras.md](spec_2-fundo-das-figuras.md) | Figura sempre com fundo branco, independente do tema; parâmetro "Cor de fundo" | nenhuma | P |
| 3 | [spec_3-persistencia-de-estado.md](spec_3-persistencia-de-estado.md) | Divisores persistidos; ajustes do gráfico em `<tipo>.plot` na pasta da simulação | 1, 2 | M |
| 4 | [spec_4-arquivos-de-job-do-cluster.md](spec_4-arquivos-de-job-do-cluster.md) | `job.o<id>` como texto com SEM ERROS/ERRO; `.qsub` somente leitura | nenhuma | P |
| 5 | [spec_5-grade-e-menu-de-contexto.md](spec_5-grade-e-menu-de-contexto.md) | Grade sem tamanho; atalho `..`; menu de contexto (Abrir local, Abrir com, Copiar, Renomear) | 4 | G |
| 6 | [spec_6-graficos-de-relaxamento.md](spec_6-graficos-de-relaxamento.md) | \|ΔE\| e Força vs passo BFGS para relax/vc-relax | 2, 3 | G |

Critério de ordem: primeiro as correções e ajustes que afetam o uso diário e são pré-requisito de
outras specs (1, 2), depois a persistência que depende delas (3), os ganhos pequenos e independentes (4),
o menu de contexto (5, maior e isolado) e, por último, a funcionalidade nova maior (6), que reaproveita
estilo e persistência.

Esforço: P = pequeno (horas), M = médio (~1 dia), G = grande (mais de 1 dia).

## Rastreabilidade: `Ideias.md` → specs

| # | Item de `Ideias.md` (resumido) | Spec |
|---|---|---|
| 1 | Workspace de gráficos/inputs não deve iniciar ao abrir o programa | spec 1, R1 |
| 2 | Duplo clique num input ou figura abre o workspace | spec 1, R2 |
| 3 | Divisórias mantêm a proporção ao abrir ou fechar abas | spec 1, R3 |
| 4 | Remover o botão "Ajuste" da barra lateral | spec 1, R4 |
| 5 | Grade: remover o tamanho do arquivo, manter OK/incompleto | spec 5, R1 |
| 6 | Botão "Plot" só abre o workspace e os ajustes, sem gerar | spec 1, R5 |
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

## Decisões já tomadas (30/09/2026)
- Workspace **sempre** oculto ao abrir o Lain, com a largura lembrada.
- Relax: **uma figura com dois painéis**, com parâmetros "Painéis" (ambos/|ΔE|/força) e "Escala".
- Ajustes persistidos em **um arquivo por tipo** (`bands.plot`, `pdos.plot`, `relax.plot`, YAML).
- "Abrir com": **submenu** de programas instalados (`.desktop`) + "Outro programa…".

Cada spec tem ainda uma seção **"Decisões assumidas (confirmar na revisão)"** com os pontos que foram
interpretados e que devem ser confirmados ou corrigidos antes de implementar.
