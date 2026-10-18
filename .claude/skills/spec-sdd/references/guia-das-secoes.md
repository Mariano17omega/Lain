# Guia das seções de uma spec do Lain

O esqueleto está em `assets/spec-template.md`. Aqui está o que cada parte precisa conter e por quê. Os exemplos
são das specs reais (`specs/Archived/`): abra uma delas quando precisar ver o tom (`spec_27-9` é pequena e
completa; `spec_32` é grande, com defeito, contrato novo e CSV).

## Sumário
- Cabeçalho · Itens de origem · Situação atual · Requisitos · Fora de escopo · Decisões assumidas · Notas ·
  Critérios · Erros comuns

## Cabeçalho

| Linha | Conteúdo |
|---|---|
| Prioridade | o número da spec e a razão da posição. Defeito que pode sair antes do resto: diga. |
| Status | `Rascunho para revisão`. Quem implementa troca por `Implementada. Desvios: …`, listando onde fugiu da spec: é assim que a spec continua verdadeira. |
| Depende de / Usada por | números de spec **e o que se usa delas**: `spec 15 (PlotExporter, exportação em worker)`. "nenhuma" quando é o caso. |
| Esforço | **P** horas, **M** cerca de um dia, **G** mais de um dia. Se os requisitos diferem, diga: `G (R1 e R2: P; R3: M)`. |
| Modelo recomendado | **Opus 5.5** (`claude-opus-5-5`) quando a spec muda contratos usados em vários lugares, mexe em física ou em código perto do limite de 500 linhas. **Sonnet 5.5** (`claude-sonnet-5-5`) quando segue um caminho que outra spec já abriu. Sempre com o motivo. |

## Itens de origem

Cite o que o usuário escreveu, **literalmente** (com os erros de digitação: "grap" ficou "grap" na spec 20), em
bloco `>`. Quem lê depois precisa conseguir discordar da sua interpretação, e só consegue se vir o original.
Depois do bloco, a interpretação, se o texto é ambíguo, e o que o usuário já decidiu no pedido ("Decisão do
usuário: ocultar da lista").

Uma ideia com dois pedidos vira dois itens (`6a`, `6b`, como na tabela de rastreabilidade do README).

## Situação atual

É a parte que separa uma spec de uma lista de desejos. Cada fato tem endereço:

> `core/desktop_apps.py`: `DesktopApp` (`:25`) tem `id, name, exec, icon, mime_types, path` (6 campos);
> `parse_desktop_file` (`:95-113`) lê `Type`, `NoDisplay`, `Hidden`, `Exec`… **`Terminal` não é lido em lugar
> nenhum**.

O que entra: arquivo e linha, comportamento de hoje, **a causa** (não só o sintoma), como foi reproduzido ou
medido ("reproduzido com `exec` real e um `QTimer.singleShot`"), o teste que existe e por que não pega o defeito,
o tamanho dos arquivos que a spec vai tocar (`wc -l`).

O que não entra: a solução (vai em Requisitos) e opinião. O que você não conseguiu verificar fica marcado
**"não verificado"**: uma suposição declarada custa uma linha; uma suposição escondida custa a implementação.

Agrupe por requisito (`**R1 (átomos da PDOS).**`), na mesma ordem de Requisitos.

## Requisitos

Cada `### R<n>:` é uma entrega que se verifica sozinha. Itens numerados, no imperativo, cada um uma **decisão**:

- **Onde mora:** módulo e função, e a camada. Lógica sem widget começa em `core/` (Qt-free); `ui/` só liga.
  Arquivo novo: nome e responsabilidade. Contratos: assinatura (`plan_export(session, root)`).
- **Textos do usuário** entre aspas, em português, exatamente como aparecem ("Sincronizar projeto ilita").
- **Bordas:** vazio, fora da raiz, nome longo, cancelado no meio, arquivo que sumiu. Spec 32 R3.4 é o modelo.
- **Padrões que não mudam:** um parâmetro novo nasce com o valor que deixa as figuras e os goldens de hoje
  idênticos ("Padrão **desligado**").
- **Testes** como último item de cada R: arquivo, fixture, e o que cada teste prova. Para defeito, o teste que
  **falha sem a correção**, com o caminho real que falhava (spec 32 R1: `exec` real, não o `exec` trocado).

Requisito vago ("melhorar", "ajustar", "deixar mais claro") não passa: diga o que se observa depois.
R0 é para um pré-requisito de refatoração que os demais usam (spec 23).

## Fora de escopo

O que um leitor razoável acharia que entra. Cada linha diz para onde vai: "adiado", "outra spec", "decisão do
usuário", "precisa de saída real do QE". Uma fixture inventada não vale: as fixtures são execuções reais
(`tests/fixtures/qe<versão>_<sistema>/`), e uma que falta é adiada e dita.

## Decisões assumidas (confirmar na revisão)

Tudo que você interpretou no lugar do usuário. É a primeira coisa que ele lê. Numerada, uma ou duas frases cada,
com a alternativa quando ela custa pouco ("Se a atribuição precisa ficar, manter só o nome é a alternativa mais
leve"). Diferencie o que o usuário decidiu do que você assumiu.

## Notas de implementação

- **Novos / Alterados:** caminhos, e o que muda em cada um dos alterados.
- **Limites:** arquivo perto de 500 linhas (`ui/main_window.py`: 450) e o que sai dele.
- **Documentação:** `README.md`, PRD e `config.example.yaml` a atualizar ao implementar; o `CLAUDE.md` só quando
  a spec cria ou muda uma regra geral (ele é enxuto: a descrição da funcionalidade fica na spec arquivada).
- **Ordem**, quando um R depende de outro ("R3 antes de R4").

## Critérios de aceite e testes

Caixas `- [ ]`, cada uma com o teste ou a fixture que a prova e o resultado esperado. Sempre:
1. o **padrão que não muda** (a regressão existente passa sem regenerar goldens);
2. um critério por comportamento novo, incluindo as bordas;
3. a linha final da CI: `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, suíte
   `-m "not realdata and not perf"`.

Um critério que ninguém consegue marcar ("funciona bem") é um requisito vago: volte e reescreva o R.
O que só a mão do usuário prova (roda do mouse real) vira "passo manual de aceite", dito como tal.

## Erros comuns

- Citar `arquivo:linha` de memória. Leia o trecho antes: a linha muda a cada commit.
- Misturar ideias sem relação numa spec só, ou uma spec que só se implementa em duas sessões.
- Esquecer que o `.md` entra no `ruff format --check .`: bloco ` ```python ` numa spec é formatado pelo ruff
  0.16 e quebra a CI se não estiver formatado (`specs/report-04-10-26.md` já quebra). Rode
  `uv run ruff format <spec>` ou use ` ```text `.
- Física afirmada sem fonte. Cite o `INPUT_PW`/`INPUT_PP`, o log do QE ou o código que lê, e marque como
  "suposição não verificada" o que não foi conferido (spec 30 faz isso com o `Hubbard_V`).
- Um item de ideia que some: toda ideia do pedido aparece na tabela de rastreabilidade do README, mesmo a que
  não virou spec ("já coberto pela spec 17", "adiado: precisa de saída real").
