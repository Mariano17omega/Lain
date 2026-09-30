# Spec 4: Arquivos de job do cluster (`.o<jobid>` e `.qsub`)

| | |
|---|---|
| **Prioridade** | 4 |
| **Status** | Rascunho para revisão |
| **Depende de** | nenhuma |
| **Usada por** | spec 5 (a grade exibe os rótulos definidos aqui) |
| **Esforço** | P |

## Itens de origem (`Ideias.md`)

> - Os arquivos do tipo '*.o*' são arquivos de saida de informações de erro da simulação. Trate eles como arquivos de texto, permitindo que o usuario veja o conteúdo deles na aba de visualização de inputs. Se o arquivo estiver vazio, significa que não houve erro na simulação, se tiver conteúdo, significa que houve erro na simulação.
> - Os arquivos com extenção '.qsub' são scripts de submissão de tarefas para o cluster. O Lain deve ser capaz de identificar esses arquivos e tratá-los como arquivos de texto, permitindo que o usuario veja o conteudo deles na aba de visualização de inputs. Não deve ser possivel editar o conteudo desses arquivos dentro dolain, apenas visualizar.

## Situação atual

- **`.qsub` já funciona quase por completo:** `.qsub` está em `TEXT_SUFFIXES`
  (`src/qe_studio/ui/file_types.py:9-13`), então `viewer_kind` devolve `text` e o duplo clique abre no
  `TextViewer`, que é somente leitura (`QPlainTextEdit.setReadOnly(True)`,
  `src/qe_studio/ui/widgets/workspace.py:80`). O Lain não tem nenhuma ação de salvar texto. O ícone é
  `code` (`file_types.py:25`, testado em `tests/test_file_types.py`), e o sniff pula o arquivo
  (`SKIP_SUFFIXES`, `src/qe_studio/core/sniff.py:27-31`). Falta teste que garanta abertura interna e
  somente leitura.
- **Logs de job (`job.o12345`) não funcionam:** o sufixo `.o12345` não está em `TEXT_SUFFIXES` e não é
  vazio, então `viewer_kind` (`file_types.py:43`) devolve `external` e o arquivo abre no programa do
  sistema. A grade e a árvore mostram só o tamanho (`FileCardDelegate._meta`,
  `src/qe_studio/ui/widgets/file_grid.py:150`; `ExplorerDelegate._paint_file_meta`,
  `src/qe_studio/ui/widgets/explorer.py:82`).
- Atenção: o glob literal `*.o*` também casaria `scf.out`, `bands.out` etc. O padrão precisa ser
  específico.

## Requisitos

### R1: Reconhecer logs de job
1. Novo predicado `is_job_log(path) -> bool` em `src/qe_studio/ui/file_types.py`, verdadeiro quando o
   nome casa com `^.+\.o\d+(?:[.-]\d+)?$`, sem diferenciar maiúsculas/minúsculas. Cobre
   `job.o12345` (PBS/Torque/SGE) e `job.o12345.1` / `job.o12345-1` (job arrays).
2. `.out`, `.o` sem número, `foo.obj` etc. **não** são logs de job.

### R2: Abrir no visualizador interno
1. `viewer_kind` devolve `text` para logs de job, então duplo clique ou Enter abre uma aba no workspace
   (e exibe o workspace, spec 1 R2).
2. Ícone próprio em `file_visual`: `assignment_late`, token `icon_output`. O ícone precisa ser
   vendorizado via `scripts/fetch_assets.py` se ainda não existir.

### R3: Rótulo de estado (grade e árvore)
1. O rótulo depende **só do tamanho** do arquivo, fornecido pelo `QFileSystemModel`, sem ler o arquivo
   na thread da GUI:
   - tamanho 0 → **"SEM ERROS"**, token `success`;
   - tamanho > 0 → **"ERRO"**, token `error`.
2. Exceção: se o sniff em cache (`DetectionService.file_sniff`) identificar o arquivo como saída do QE
   (`FileSniff.is_output`, por exemplo pw.x rodando sem redirecionar a saída, que vai para o `.o`),
   vale o rótulo normal de saída do QE (OK / INCOMPLETO / AVISO), porque aí conteúdo não significa erro.
3. Na grade, o rótulo segue a regra da spec 5 (sem tamanho). Na árvore, o rótulo substitui o tamanho,
   como já acontece com as saídas do QE.

### R4: Banner no visualizador
Ao abrir um log de job, o `TextViewer` mostra um banner acima do texto:
- vazio: "Arquivo vazio: o job não registrou erros." em estilo de sucesso;
- com conteúdo: "O job registrou mensagens de erro." em estilo de erro.

O banner atual (`#viewerBanner`, `src/qe_studio/ui/resources/styles/workspace/viewers.qss:10`) usa
`${warning}`. Adicionar variantes por propriedade (ex.: `[level="success"]`, `[level="error"]`) com os
tokens `success`/`error`, que já existem nos dois temas (`themes/dark.yaml:30-32`,
`themes/light.yaml:29-31`). O aviso de arquivo grande continua como está.

### R5: `.qsub` somente leitura (garantia)
1. `.qsub` continua abrindo no `TextViewer` somente leitura. Nenhum caminho do Lain permite editar ou
   salvar o arquivo.
2. Vale igualmente para `.slurm`, `.pbs` e `.sh`, que já estão em `TEXT_SUFFIXES`.

## Fora de escopo
- Interpretar o conteúdo do log (tipo de erro, linha), ou relacionar o log ao cálculo/pasta.
- Scripts SLURM `slurm-<id>.out`: já abrem como texto por serem `.out`, e o sniff decide se são saída
  do QE.
- Editar scripts de submissão ou submeter jobs.

## Decisões assumidas (confirmar na revisão)
1. Arquivos de erro padrão separados `job.e12345` (stderr, quando o job não usa `-j oe`) recebem o
   mesmo tratamento dos `.o<jobid>`: texto, SEM ERROS/ERRO e banner. O regex passa a ser
   `^.+\.[oe]\d+(?:[.-]\d+)?$`.
2. Quando o `.o` contém a saída do pw.x, prevalece o rótulo do QE (R3.2).
3. A regra "conteúdo = erro" é aplicada literalmente, sem heurística de palavras-chave. Mensagens
   inofensivas do sistema de filas também contam como "ERRO".

## Notas de implementação
- `src/qe_studio/ui/file_types.py`: `JOB_LOG = re.compile(...)`, `is_job_log`; ajustar `viewer_kind` e
  `file_visual`.
- Rótulo compartilhado: extrair para `file_types.py` (ou `ui/painting.py`) uma função
  `status_label(path, size, sniff) -> tuple[str, str] | None`, usada por `FileCardDelegate._meta` e
  `ExplorerDelegate._paint_file_meta`. Hoje a lógica OK/INCOMPLETO está duplicada nos dois delegates.
- `TextViewer` precisa saber se é log de job. Pode receber `kind="job_log"` de `Workspace.open_file`
  ou checar `is_job_log(self.path)`. O banner é definido no `_on_loaded`, a partir do texto carregado
  (já em worker).

## Critérios de aceite e testes
- [ ] `tests/test_file_types.py`: `is_job_log` é verdadeiro para `job.o123`, `run.O99`, `job.o123.4`,
      `job.o123-4`, e falso para `scf.out`, `a.o`, `foo.obj`, `bands.dat`. `viewer_kind(job.o123)` é
      `text` e o ícone é `assignment_late`.
- [ ] `status_label`: tamanho 0 → ("SEM ERROS", "success"); tamanho > 0 → ("ERRO", "error"); sniff de
      pw.x completo dentro de `.o` → ("OK", "success").
- [ ] `tests/test_main_window.py`: abrir `job.o1` vazio cria um `TextViewer` com banner de sucesso;
      com conteúdo, banner de erro.
- [ ] Abrir `job.qsub` cria um `TextViewer` com `editor.isReadOnly()` verdadeiro.
