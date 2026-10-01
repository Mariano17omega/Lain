# Spec 12: Resumo de saídas do QE

| | |
|---|---|
| **Prioridade** | 12 |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 5 (menu de contexto), spec 9 (ordem das ações no menu), spec 10 (abas do workspace) |
| **Usada por** | nenhuma |
| **Esforço** | M |

## Itens de origem

> **F8. Painel Resumo** de saída pw.x: WALL/CPU, ecut, nat, k-pontos, pressão, magnetização, versão, nº MPI. Só existe o rótulo OK/INCOMPLETO. Para quem roda em cluster, tempo e custo importam. Parser regex de rodapé (`PWSCF : … CPU … WALL`).

Pedido do usuário (30/09/2026):
> No Caso do F8, Adicione a função 'Resumo' no menu do botão direito para outputs. O botão gerar o resumo de saida dos calculos e mostra na aba lateral de visualização. O resumo não é salvo, é apenas uma extração do output representada de forma organizada, não precisa salvar.

Decisão confirmada: o resumo abre como **uma aba no workspace**, a mesma área das abas de texto e de
imagem.

## Situação atual

- Da saída, o usuário só vê o rótulo de estado (`OK`/`INCOMPLETO`/`AVISO`,
  `ui/file_types.py:77-89`) e o texto bruto no `TextViewer`.
- `parse_pw_output` (`core/qe/pw_output.py:97-146`) lê versão, `calculation`, Fermi/HOMO-LUMO,
  k-pontos, elétrons, bandas, alat, spin, `JOB DONE` e convergência. Não lê tempo, paralelização,
  cutoffs, XC, pressão, forças, magnetização, pseudopotenciais nem mensagens de erro.
- O sniff de saídas que não são do pw.x (`sniff.py:162-168`) guarda só `program` e `job_done`.
- Linhas relevantes de uma saída pw.x 7.3.1 (`tests/fixtures/al_bands/al.scf.out`):
  ```
  Program PWSCF v.7.3.1 starts on  3Jan2025 at  6:59:51      (l.2)
  Serial version                                              (l.12; em MPI: "Parallel version (MPI), running on N processors")
  Message from routine set_cutoff:                            (l.27, seguida da mensagem)
  unit-cell volume / number of atoms/cell                     (l.42-43)
  kinetic-energy cutoff / charge density cutoff               (l.47-48)
  scf convergence threshold / mixing beta                     (l.49-50)
  Exchange-correlation= PBE                                   (l.52)
  number of k points=    47  Gaussian smearing, width (Ry)=  0.0100   (l.96)
  !    total energy              =      -5.03855495 Ry       (l.390)
  convergence has been achieved in   4 iterations            (l.401)
  PWSCF        :      1.88s CPU      1.90s WALL              (l.443)
  This run was terminated on:   6:59:53   3Jan2025          (l.446)
  JOB DONE.                                                  (l.449)
  ```
  E de um vc-relax (`kao_vc_relax/vc-relax.out`): `number of atomic types` (l.53), `number of electrons`
  (l.54), `PseudoPot. # 1 for Al read from file:` (l.83), `Total force =` (l.596) e
  `total   stress … P=` (l.602).
- O menu de contexto tem as 4 ações da spec 5, e a spec 9 acrescenta "Plotar" para saídas SCF.

## Requisitos

### R1: Extrator `core/qe/summary.py` (sem Qt)
1. `summarize(path) -> OutputSummary`. Leitura linha a linha (streaming), porque saídas de relax podem
   ter centenas de MB. Roda no worker.
2. Estrutura: `OutputSummary(program, sections: list[SummarySection], issues: list[SummaryIssue])`, com
   `SummarySection(title, rows: list[SummaryRow(label, value, level=None, line=None)])`. `level` ∈
   `success|warning|error|None` colore o valor; `line` é a linha de origem no arquivo, usada pelo R3.4.
3. Valores com unidade, mantendo o ponto decimal do QE (`1.90 s`, `100.0 Ry`). Na UI, os números usam
   fonte mono.
4. "Último valor vence" para grandezas que se repetem (energia, força, pressão, magnetização). A seção
   "Resultados" também mostra o **primeiro** valor quando o cálculo é relax/vc-relax (ex.: "E inicial" e
   "E final").

### R2: Conteúdo por programa
**Geral** (toda saída do QE: pw.x, bands.x, projwfc.x, dos.x, ph.x, pp.x…):
| Linha | Origem |
|---|---|
| Programa | `Program X v.Y` |
| Início | `starts on DATE at TIME` |
| Término | `This run was terminated on: TIME DATE` |
| Estado | `JOB DONE` → "Concluído" (success). Sem ele → "Incompleto" (warning). Com bloco de erro `%%%%` → "Erro" (error) |
| Tempo | `<PROG> : X CPU Y WALL` (formato humano: `1h 02min 05s`) |
| Paralelização | `Serial version` / `Parallel version (MPI…), running on N processors` / `Number of MPI processes:`; `Threads/MPI process:`; `K-points division: npool`; `R & G space division: proc/nbgrp/npool/nimage`; `GPU acceleration is ACTIVE` |
| Memória | `MiB available memory on the printing compute node`; `Estimated max dynamical RAM per process` |

**Sistema** (pw.x):
- `calculation` (de `pw_output._calculation`), fórmula (ASE `read_structure` só se o arquivo tiver
  < 16 MB; senão "—"), `number of atoms/cell`, `number of atomic types`, `lattice parameter (alat)`,
  `unit-cell volume`;
- `number of electrons`, `number of Kohn-Sham states`, `kinetic-energy cutoff`, `charge density
  cutoff`, `Exchange-correlation`;
- `number of k points` e o smearing da mesma linha, spin ("colinear (nspin=2)", "não colinear",
  "spin-órbita");
- pseudopotenciais: uma linha por espécie (`PseudoPot. # n for X read from file:` + o nome do arquivo
  da linha seguinte).

**Resultados** (pw.x):
- energia total final (`!`), energia de Fermi / HOMO-LUMO (de `parse_pw_output`), gap se houver
  HOMO-LUMO;
- magnetização total e absoluta (última);
- pressão (`P=` em kbar) e tensor de stress (3×3, em kbar, numa linha expansível);
- `Total force` (Ry/Bohr);
- SCF: iterações e convergência (`achieved in N` / `NOT achieved`), usando o parser da spec 9 se ela já
  existir; senão, regex direto;
- relax/vc-relax: passos BFGS (do `core/qe/relax.py`), `bfgs converged`, `Final energy` / `Final
  enthalpy`, `new unit-cell volume` (inicial → final).

**Avisos e erros** (todos os programas):
- blocos de erro `%%%%…` (rotina e mensagem, level `error`);
- `Message from routine X:` + a linha seguinte (level `warning`). Repetições idênticas aparecem uma vez,
  com "(×N)".

**Outros programas:** só "Geral" e "Avisos e erros". Extras simples quando a linha existe: bands.x
(arquivos `.gnu`/filband escritos), projwfc.x (`filpdos`), dos.x (`fildos`).

### R3: UI: item "Resumo" e aba
1. Item **"Resumo"** no menu de contexto para todo arquivo cujo sniff em cache é uma saída do QE
   (`FileSniff.is_output`). Ordem no topo do menu: "Plotar" (só SCF, spec 9), "Resumo", separador, e as
   4 ações da spec 5. Sem sniff em cache, vale a mesma regra da spec 9 R6.2 (o item não aparece, e a
   detecção da pasta é pedida).
2. A ação abre (ou traz à frente) a aba "Resumo · <arquivo>" no workspace: chave `summary:<caminho>`,
   ícone `summarize`, tooltip com o caminho. O workspace é mostrado se estiver oculto (spec 1).
3. `SummaryView`: rolagem vertical, uma seção por bloco (título em maiúsculas, como os `PanelHeader`),
   linhas rótulo/valor em duas colunas, valores em JetBrains Mono, cor por `level`. O stress e os
   pseudopotenciais ficam em sub-blocos expansíveis.
4. Barra da aba:
   - "Copiar": copia o resumo como texto simples alinhado, uma seção por bloco;
   - "Abrir saída": abre o arquivo no visualizador de texto (spec 10);
   - "Atualizar": relê o arquivo (útil se o job ainda roda).
   Duplo clique numa linha com `line` abre a saída posicionada nessa linha.
5. Nada é gravado em disco. Fechar a aba descarta o resumo.
6. Enquanto o worker lê, a aba mostra "Lendo <arquivo>…". Em erro de leitura: "Não foi possível ler o
   arquivo: …".

## Fora de escopo
- Salvar ou exportar o resumo como arquivo.
- Resumo de inputs (o extrato da spec 11 cobre isso).
- Comparar resumos de várias saídas (parte do F9, adiado).
- Custo em core-horas: depende de dados do cluster que a saída não tem (pode vir com o F11).

## Decisões assumidas (confirmar na revisão)
1. "Aba lateral de visualização" = aba no workspace (confirmado).
2. Saídas de qualquer programa do QE ganham o item "Resumo", e não só o pw.x. Para os outros, o
   resumo é mais curto (R2).
3. A fórmula química via ASE só para arquivos < 16 MB (R2), para não travar o worker em saídas enormes.
4. Com "Atualizar" manual, não há atualização automática (F10 adiado).
5. Os valores numéricos ficam no formato do QE (ponto decimal), sem localizar a vírgula.

## Notas de implementação
- Novos: `core/qe/summary.py`, `ui/widgets/summary_view.py`, `tests/test_summary.py`.
- Alterados:
  - `ui/widgets/context_menu.py` (item "Resumo" e sinal `summary_requested(path)`);
  - `ui/main_window.py` (abrir a aba);
  - `ui/widgets/workspace.py` (tipo de aba);
  - `ui/resources/styles/workspace/viewers.qss`;
  - `tests/test_file_grid_menu.py`.
- Reaproveitar `parse_pw_output`, `core/qe/relax.py` e o parser SCF da spec 9 (o `summary` chama esses
  parsers sobre o mesmo arquivo; quando a leitura dupla custar caro, medir antes de otimizar, conforme
  O8/spec 14).
- O parser é testado sem Qt. A UI é testada com o `main_window` fixture e o patch de `QMenu.exec`.
- Caso de propriedade em `tests/test_properties.py` (spec 7): corte aleatório da saída nunca levanta
  exceção.

## Critérios de aceite e testes
- [ ] `summarize(al_bands/al.scf.out)`: PWSCF 7.3.1, "Concluído", WALL 1.90 s, "Serial", ecutwfc 100.0
      Ry, ecutrho 143.0 Ry, PBE, 47 k-pontos, smearing gaussiano, E total −5.03855495 Ry, convergiu em 4
      iterações, e a mensagem "ecutrho < 4*ecutwfc, are you sure?" em avisos.
- [ ] `kao_vc_relax/vc-relax.out`: 4 espécies com pseudopotencial, `Total force` e `P=` finais,
      passos BFGS, "bfgs converged", volume inicial → final.
- [ ] Saída de bands.x (`al_bands/bands.out`): só "Geral" e "Avisos e erros", com "Concluído".
- [ ] Saída truncada (`copy_fixture` + corte): "Incompleto" e nenhuma exceção.
- [ ] Texto sintético com bloco `%%%%` de `Error in routine cdiaghg`: estado "Erro", com a rotina e a
      mensagem em "Avisos e erros".
- [ ] Menu: numa saída (pw.x ou bands.x) aparece "Resumo". Num input, num `.gnu` ou numa pasta, não.
      Numa saída SCF, a ordem é `["Plotar", "Resumo", "Abrir local de origem", …]`.
- [ ] "Resumo" abre a aba `summary:<path>`. Repetir a ação não duplica a aba. Nenhum arquivo é criado na
      pasta da simulação.
- [ ] "Copiar" põe na área de transferência um texto que contém "WALL" e "JOB DONE"/"Concluído".
