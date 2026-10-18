---
name: spec-sdd
description: "Transforma as ideias do usuário (texto do pedido ou specs/Ideias.md) em specs de Spec-Driven Development do Lain, salvas em specs/spec_N-<slug>.md: investiga o código, escreve situação atual verificada, requisitos numerados e testáveis, decisões assumidas e critérios de aceite, e atualiza o roadmap e a rastreabilidade de specs/README.md. Use SEMPRE que o usuário pedir para criar, escrever, organizar ou revisar uma spec, falar em SDD, em 'transformar ideias em spec' ou 'organizar o Ideias.md', ou colar uma lista de bugs, ajustes e funcionalidades do Lain para planejar, mesmo sem dizer a palavra spec. Só especifica: não implementa."
---

# spec-sdd: das ideias às specs do Lain

Uma spec do Lain é o contrato entre uma ideia e a sua implementação. Quem implementa (`/plan implementar
specs/spec_N-….md`) é outra sessão, muitas vezes de outro modelo, que tem só a spec, o `CLAUDE.md` e o código: não viu esta
conversa. Por isso a spec precisa bastar a si mesma, e a "Situação atual" precisa ser **verificada no código**: um
plano feito sobre um `arquivo:linha` inventado só falha no meio da implementação, a hora mais cara de descobrir.

Esta skill só **especifica**. Escreve em `specs/`; não toca em `src/` nem em `tests/`.

Arquivos desta skill, para ler quando o passo pedir:
- `assets/spec-template.md`: o esqueleto (cada `[[PREENCHER: …]]` some antes de entregar).
- `references/guia-das-secoes.md`: o que cada seção contém, com exemplos das specs reais e os erros comuns.
- `references/lain-checklist.md`: as regras do `CLAUDE.md` como perguntas que a spec precisa responder.
- `scripts/next_number.py` e `scripts/check_spec.py`: próximo número e validação.

## Fluxo

### 1. Orientar
- `python3 .claude/skills/spec-sdd/scripts/next_number.py`: próximo número, data de hoje, specs ainda em
  rascunho e as últimas tabelas de rastreabilidade (diz qual foi a última "rodada").
- Leia `specs/README.md`: o roadmap diz o que existe e de quê depende; as "Decisões já tomadas" são lei, não
  as reabra.
- **De onde vêm as ideias:** o texto do pedido; se o usuário apontou `specs/Ideias.md` ou não deu texto nenhum,
  leia o `Ideias.md`. Só leia: ele é o arquivo de trabalho do usuário, que o zera quando quiser.
- Uma ideia sobre uma spec ainda em rascunho (na raiz de `specs/`) **entra nela** (novo R + linha na
  rastreabilidade). Specs em `Archived/` estão implementadas e congeladas: ideia nova sobre a área delas é spec
  nova, com a antiga em "Depende de".

### 2. Quebrar em itens
Numere as ideias, mantendo as palavras do usuário. Ideia com dois pedidos vira dois itens. Classifique cada um:
defeito, ajuste ou funcionalidade. Já coberto por uma spec existente? Anote para a rastreabilidade e não gere
spec (confirme no código antes: "já coberto" também é uma afirmação).

### 3. Investigar o código
Para cada item, ache onde ele vive (`grep`, leitura) e leia o código e a spec arquivada da área (`specs/Archived/`: os
comentários do código citam "spec N"). Anote o que a
"Situação atual" vai afirmar: `arquivo:linha`, o comportamento de hoje, **a causa**, o teste que existe e por que
não pega. Defeito: reproduza (script no scratchpad, nunca no repositório) e diga o que mediu. Meça com `wc -l`
os arquivos que a spec vai tocar (limite 500; `ui/main_window.py`, 450).

Regra: todo caminho, linha e identificador na spec foi **visto nesta sessão**. O que não deu para verificar vai
escrito como "não verificado". Se a ideia é de física (QE), a fonte é o `INPUT_*` do QE ou o que o código lê:
nada de memória.

### 4. Agrupar e numerar
- Uma spec = itens que mexem na mesma área ou dado e que um `/plan` entrega junto. Itens sem relação ficam em
  specs separadas, mesmo pequenas; uma spec que só cabe em duas sessões se divide.
- Número: o de `next_number.py`, consecutivo para as specs da mesma rodada (28–31). Correções de um mesmo
  relatório usam `N-k` (27-1 … 27-9; `next_number.py N` dá o próximo).
- Arquivo: `specs/spec_<N>-<slug>.md`, slug em português, minúsculo, hífens, sem acento nem `ç`.
- Ordem de prioridade: defeitos primeiro (afetam o uso diário e destravam o resto), depois ganhos pequenos e
  independentes, por último o que é grande e depende dos outros. Dependências decidem o empate.

### 5. Dúvidas
O padrão do projeto é **assumir e declarar**: toda interpretação vai para "Decisões assumidas (confirmar na
revisão)", e a spec nasce como rascunho que o usuário revisa antes de qualquer implementação. Pergunte antes
(`AskUserQuestion`, uma vez, até 4 perguntas, com a opção que você recomenda primeiro) só quando a resposta muda o
**formato** da spec (uma ação ou duas, onde o dado mora, comportamento destrutivo) e nem o código nem o README
respondem.

### 6. Escrever
Copie `assets/spec-template.md` para `specs/spec_<N>-<slug>.md` e preencha; leia
`references/guia-das-secoes.md` antes, e passe `references/lain-checklist.md` por cada R. O que decide a
qualidade:
- **Itens de origem:** a fala do usuário, literal, em bloco `>`.
- **Situação atual:** fatos com endereço; sem solução, sem opinião.
- **Requisitos:** decisões (módulo, função, camada, texto exato em português), com bordas e **testes nomeados**;
  em defeito, o teste que falha sem a correção. Parâmetro novo nasce com padrão que não muda as figuras de hoje.
- **Fora de escopo:** o que um leitor razoável acharia que entra, e para onde vai.
- **Critérios:** caixas `- [ ]`, cada uma com o teste ou a fixture que a prova.
- **Modelo recomendado:** Opus 5.5 se muda contrato usado em vários lugares, mexe em física ou em arquivo perto
  do limite; Sonnet 5.5 se segue caminho que outra spec abriu.

Idioma: a spec é em português; caminhos, identificadores e código como estão no repositório.

### 7. Atualizar `specs/README.md`
Com `Edit` pontuais (o usuário costuma ter alterações não commitadas ali; nunca reescreva o arquivo):
1. **Roadmap:** uma linha por spec antes da linha `fim`: `| N | [spec_N-slug.md](spec_N-slug.md) | resumo | Depende de | P/M/G | Modelo |`
   (link na raiz: ao implementar, a spec vai para `Archived/` e o link muda).
2. **Rastreabilidade:** nova seção `## Rastreabilidade: ideias da <ordinal> rodada (DD/MM/AAAA) → specs`,
   depois da última, com `| # | Ideia (resumida) | Spec |`. **Toda** ideia do pedido tem linha, também as que
   não viraram spec ("já coberto: spec 17, R2", "adiado: precisa de saída real").
3. **Critério de ordem:** um item novo na lista numerada (antes de "Idioma") com a decisão da rodada.
4. **Decisões:** bloco `Decisões de DD/MM/AAAA (<ordinal> rodada, specs N–M):` com as decisões do usuário e a
   escolha de modelo por spec.
5. **Parágrafo de abertura:** acrescente as novas specs à frase das rodadas.

### 8. Validar
`python3 .claude/skills/spec-sdd/scripts/check_spec.py specs/spec_<N>-<slug>.md` para cada spec.
- **Erro:** conserte e rode de novo (seção faltando, numeração, `[[PREENCHER` esquecido).
- **Aviso de caminho que não existe:** ou é arquivo novo (e a spec diz "novo" na linha) ou é erro seu: corrija.
  Uma referência a `file:line` além do fim do arquivo é erro seu.
- Se a spec tem bloco ` ```python `: `uv run ruff format --check <spec>`; a CI roda `ruff format --check .` e
  o ruff formata código dentro de Markdown.

### 9. Entregar
Resposta curta: por spec, arquivo, esforço, modelo e dependências; as **decisões assumidas** que mais pesam (o
usuário as confirma); o que não virou spec e por quê; e o próximo passo:
`/plan implementar specs/spec_<N>-<slug>.md`. Não faça commit sem o usuário pedir. Diga que `Ideias.md` não foi
alterado e que as ideias estão na rastreabilidade do README.
