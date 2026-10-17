# Spec [[PREENCHER: N]]: [[PREENCHER: título curto, o que muda para o usuário]]

| | |
|---|---|
| **Prioridade** | [[PREENCHER: N, e por que nessa posição ("independente das demais", "defeito: pode ser entregue antes do resto")]] |
| **Status** | Rascunho para revisão |
| **Depende de** | [[PREENCHER: spec 21 (o que usa dela), ou "nenhuma"]] |
| **Usada por** | [[PREENCHER: spec M, ou "nenhuma"]] |
| **Esforço** | [[PREENCHER: P, M ou G; por requisito se diferem: "G (R1 e R2: P; R3: M)"]] |
| **Modelo recomendado** | **[[PREENCHER: Opus 5.5 ou Sonnet 5.5]]** (`[[PREENCHER: claude-opus-5-5 ou claude-sonnet-5-5]]`): [[PREENCHER: o motivo, em uma frase]] |

## Itens de origem ([[PREENCHER: `Ideias.md` ou "ideias de DD/MM/AAAA"]])

> - [[PREENCHER: o texto do usuário, literal, um item por linha]]

[[PREENCHER: a interpretação, quando o texto é ambíguo ("Grap" = gap de energia, não o nível de Fermi), e o que o
usuário já decidiu no pedido]]

## Situação atual

- **R1 ([[PREENCHER: nome curto]]).** [[PREENCHER: arquivo:linha, função, comportamento de hoje, por que acontece, como
  foi reproduzido ou medido, por que os testes de hoje não pegam]]

## Requisitos

### R1: [[PREENCHER: o que é entregue]]

1. [[PREENCHER: uma decisão: módulo, função, assinatura, texto exato entre aspas, camada (`core/` ou `ui/`)]]
2. [[PREENCHER: casos de borda]]
3. **Testes:** [[PREENCHER: arquivo, fixture e o que cada teste prova; em defeito, o teste que falha sem a correção]]

## Fora de escopo

- [[PREENCHER: o que um leitor razoável acharia que entra, e para onde vai ("adiado", "outra spec", "decisão do usuário")]]

## Decisões assumidas (confirmar na revisão)

1. [[PREENCHER: o que foi decidido no lugar do usuário, e por quê, em uma ou duas frases]]

## Notas de implementação

- Novos: [[PREENCHER: caminhos]].
- Alterados: [[PREENCHER: caminhos e o que muda em cada um]].
- Limites: [[PREENCHER: `arquivo.py` com N de 500 linhas e o que sai dele, ou "nenhum arquivo perto do limite"]].
- Documentação ao implementar: [[PREENCHER: seção do `CLAUDE.md`, `README.md`, PRD que muda]].

## Critérios de aceite e testes

- [ ] [[PREENCHER: padrão que não muda: o teste de regressão (goldens, figuras) passa sem regenerar]]
- [ ] [[PREENCHER: um critério por comportamento, com o teste ou a fixture que o prova]]
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
