# Visualizador de texto e inputs

Arquivos de texto abrem em abas com números de linha.

- **Busca** `Ctrl+F` (`F3` / `Shift+F3` próximo/anterior), **Ir à linha…** `Ctrl+L`.
- Saídas QE coloridas (energias, erros, avisos, convergência).
- Arquivos > 4 MB mostram o início (1 MB) e o fim (2 MB) com números reais; o banner oferece **Abrir no editor
  externo** e **Carregar tudo** (até 64 MB).
- Menu da aba (ou clique do meio): **Fechar** (`Ctrl+W`), *outras / à direita / todas*, **Copiar caminho**,
  **Revelar no explorador**.
- Arquivos de job (`job.o<id>`, `.qsub`, `.slurm`, `.pbs`) abrem **somente leitura**; Markdown é renderizado.

## Inputs do QE

Cores de sintaxe e verificação de **escrita** (não do significado dos parâmetros): aspas abertas, namelist sem `/`,
linha sem `=`, parêntese desbalanceado, lógico/número malformado, namelist ou card com nome errado, opção de card
inválida. Problemas são sublinhados em vermelho, marcados na margem e contados num banner (**Ir ao primeiro**,
`F8` / `Shift+F8`). Uma faixa de *chips* mostra `calculation`, cutoffs, malha `K_POINTS` etc. (clique vai à linha).

**Comparar com…** abre uma aba com os parâmetros que diferem (`1d-8` = `1.0e-8`) ou os dois arquivos lado a lado.

## Resumo

Toda saída QE (pw.x, bands.x, projwfc.x…) tem **Resumo**: estado (`Concluído`/`Incompleto`/`Erro`), tempos WALL/CPU,
paralelização, memória, sistema, resultados (energias, Fermi/HOMO-LUMO e gap, magnetização, pressão, forças, progresso
do SCF e do BFGS) e avisos/erros — lido do arquivo, nunca salvo. **Copiar**, **Atualizar** e duplo clique abre a
saída na linha de origem.

Código: `ui/widgets/viewer/`, `core/viewer/`, `core/qe/input_lexer.py`, `input_lint.py`, `input_diff.py`,
`core/qe/summary/`.
