# Spec 44: Medidas de distância e ângulo na "Visualização 3D"

| | |
|---|---|
| **Prioridade** | 44 (logo depois da 43, que cria a janela) |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 43 (`core/structure3d/`: `Structure`, `AtomRef`, `atom_name`; `StructureWindow`, `StructureCanvas`, `StructurePanel` e o lugar da seção "Medidas") |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: P; R2: M) |
| **Modelo recomendado** | **Sonnet 5.5** (`claude-sonnet-5-5`): segue o caminho que a spec 43 abre (uma seção a mais no painel e um módulo pequeno em `core/`), sem contrato compartilhado nem física nova além de distância e ângulo. |

## Itens de origem (`Ideias.md`, 13/10/2026)

> - No painel direito, a parte de metrica ( distancias e angulos). Quero que tenha um botão 'Distancia' e um botão 'Angulos' para selecionar o tipo de calculo.
> - Quando o 'Distancia' está ativo, o usuario seleciona dois atomos, e o programa mostra a distancia entre eles.
> - Quando o usuario selecionar o 'Angulos', quando o usuario seleciona tres atomos, e o programa mostre o angulo entre eles, igual como é feito no xcrysden.
> - O botão 'Distancia' e o botão 'Angulos' devem ser mutually exclusive. O usuario deve selecionar um deles para realizar o calculo.
> - A distancia sempre será calculada para um par de atomos.
> - As distancias devem ser calculadas automaticamente e mostradas em uma tabela, por exemplo: O usuario sleciona dois atomos, é calculado a distancia deles. Depois seleciona mais dois atomos, e é calculado a distancia entre eles, e é add uma nova linha na tabela dos resutados, por exemplo
>
>   O1 - O2 1.5 Å
>   O1 - O3 2.1 Å
>   O2 - O3 1.8 Å
>
> - Os angulos devem ser calculadas automaticamente e mostradas em uma tabela, por exemplo: O usuario sleciona tres atomos, é calculado o angulo entre eles. Depois seleciona mais tres atomos, e é calculado o angulo entre eles, e é add uma nova linha na tabela dos resutados, por exemplo
>
>   O1 - O2 - O3 120.0°
>   O1 - O2 - O4 135.0°

Interpretação e decisões do usuário (13/10/2026):

- **"No painel direito"**: as medidas ficam numa **seção do painel esquerdo** da janela 3D, entre "Átomo" e "Exibição" (decisão do
  usuário, perguntada antes de escrever: duas colunas, como o exemplo).
- **"O1 - O2"**: o número é o do QE (`O43` = 43º átomo do input), não uma contagem por elemento (decisão do usuário).
- **"igual como é feito no xcrysden"**: no XCrySDen os botões Distance / Angle ficam no canto da janela, o usuário clica nos átomos e a
  medida sai em Å / graus (documentação 1.5.60, `doc/measure.html` no espelho do MIT). Qual átomo é o vértice a documentação **não diz**
  (não verificado); aqui o vértice é o **segundo** clicado, como no Jmol ("about the center atom") e no `measure.angle` do exemplo.
- "O usuário deve selecionar um deles": sem nenhum botão ativo, clicar num átomo só o mostra em "Átomo" (spec 43) e não mede nada.

## Situação atual

- **Depois da spec 43** (implementada em 13/10/2026) a janela 3D seleciona um átomo atual por clique e não mede nada; a seção "Medidas" tem o lugar
  reservado no painel (spec 43, R5.1). O núcleo não tem `measure.py` (a 43 não o porta).
- **No exemplo** (`Documentation/Exemplo-visualizador_3d/`): a seleção acumula até 4 átomos (`ui/canvas.py:16` `MAX_SELECTION`, `select`
  em `:131-149`: o 5º clique recomeça) e o **tipo da medida depende da contagem** (`ui/panel_measures.py:25` `KINDS = {2: "Distância (Å)",
  3: "Ângulo (°)", 4: "Diedro (°)"}`, `_measure` em `:78`); uma linha entra na tabela sempre que a contagem cresce (`:116`). Então clicar
  em três átomos grava uma distância **e** um ângulo com os mesmos átomos (na captura desta sessão: "Distância H70–H71" e "Ângulo
  H70–H71–C69"); não há como medir dois pares seguidos sem limpar. A tabela tem seis colunas ("Medida", "Átomos", "Valor", Δx, Δy, Δz,
  `:24`) que cortam os nomes ("H7…"). "Usar imagem mais próxima" (`:128`) troca a cópia do último átomo.
- **As contas existem**: `core/measure.py` do exemplo, `distance` (`:20`, entre as cópias exatas, sem imagem mínima implícita) e `angle`
  (`:26-34`, vértice em `b`, NaN quando um braço tem comprimento zero); `dihedral` (`:37`) e `nearest_image` (`:52`) não são pedidos.

## Requisitos

### R1: Medidas no núcleo

1. `core/structure3d/measure.py` (novo, Qt-free, em `QT_FREE`): `distance(structure, a, b) -> float` (Å) e `angle(structure, a, b, c) ->
   float` (graus, vértice em `b`, NaN com um braço nulo), portados do exemplo, sobre `AtomRef` (cópia exata: numa célula repetida, mede
   entre as cópias clicadas, que são as que o usuário vê).
2. `core/structure3d/measurements.py` (novo, Qt-free):
   - `MeasureMode = Literal["distancia", "angulo"]`, `NEEDED = {"distancia": 2, "angulo": 3}`.
   - `Measurement(kind, refs, value)` (frozen) e `Measurer(structure)`: `mode: MeasureMode | None` (começa `None`), `pending:
     tuple[AtomRef, ...]`, `set_mode(mode | None)` (limpa `pending`), `click(ref) -> Measurement | None`, `clear_pending()`.
   - `click`: sem modo devolve None e não guarda nada; com modo, um `ref` que já está em `pending` é ignorado (não há distância zero nem
     ângulo com átomo repetido); ao chegar a `NEEDED[mode]` calcula, **esvazia `pending`** e devolve a medida. Assim cada par (ou trio)
     é independente: os cliques 3 e 4 fazem o segundo par, como no exemplo do pedido.
   - `row_text(structure, m) -> tuple[str, str]`: `("O1 - O2", "1.500 Å")` / `("O1 - O2 - O3", "120.00°")`: nomes de `atom_name` (spec
     43) unidos por " - ", distância com 3 casas e " Å", ângulo com 2 casas e "°", ponto decimal; um ângulo NaN (dois átomos na mesma
     posição) é "—".
   - `to_tsv(rows) -> str`: cabeçalho "Medida\tÁtomos\tValor" e uma linha por medida ("Distância" / "Ângulo", átomos, o número sem
     unidade), na ordem em que foram feitas.
3. **Testes** (`tests/test_structure3d_measure.py`, novo): em `si_bands/si.scf.in`, a distância Si1–Si2 é `√3/4 · a_cúbico` (a ligação do
   diamante, de `celldm(1)`) e o ângulo Si–Si–Si com cópias deslocadas (`AtomRef` com `shift`) é 109,47° (tetraedro); `angle(a, b, c) ==
   angle(c, b, a)`; `Measurer`: sem modo nada; distância com 4 cliques = 2 medidas; ângulo com 6 cliques = 2; um átomo repetido é
   ignorado; trocar de modo no meio de um par o descarta; `row_text` e `to_tsv` com os formatos acima. `test_properties.py`: a distância
   entre duas cópias não muda ao somar o mesmo deslocamento de rede às duas, e o ângulo fica em [0°, 180°].

### R2: Seção "Medidas" e a vista

1. Seção "Medidas" no `StructurePanel` (spec 43), entre "Átomo" e "Exibição", aberta ao abrir a janela:
   - Dois botões de alternar lado a lado, "Distância" e "Ângulos" (`QToolButton` checáveis, no estilo do `ModeSwitch` do "Criar cálculo",
     `ui/dialogs/calc_create/mode_switch.py`), **mutuamente exclusivos e podendo ficar os dois desligados**: ligar um desliga o outro;
     clicar no que está ligado o desliga. Começam desligados.
   - Uma linha de instrução (`text_meta`): sem modo, "Escolha Distância ou Ângulos para medir."; "Distância": "Clique em dois átomos.";
     "Ângulos": "Clique em três átomos; o segundo é o vértice.". Com átomos pendentes, a linha diz quais: "Selecionados: O1 → O2".
   - Duas tabelas, "Distâncias" (colunas "Átomos", "Distância") e "Ângulos" (colunas "Átomos", "Ângulo"), cada uma visível só depois da
     primeira linha. Uma medida nova entra **no fim** da sua tabela e rola para ela; a linha mais recente fica selecionada.
   - "Copiar" (o `to_tsv` das duas tabelas para a área de transferência; aviso na barra de status da janela "Medidas copiadas") e
     "Limpar" (esvazia as duas tabelas e os pendentes); a tecla Delete remove as linhas selecionadas. Desabilitados sem medidas.
2. Vista (`StructureCanvas`): com um modo ligado, cada clique em átomo vai para `Measurer.click` **e** continua mudando o átomo atual da
   seção "Átomo"; os pendentes ganham anéis numerados na ordem do clique (o selo do exemplo, `renderer_overlay.py`; no Lain os anéis são de
   `ui/widgets/structure3d/overlay.py:draw_overlays`, que hoje desenha só o do átomo atual e o do ponteiro); quando a medida
   fecha, os átomos dela ficam marcados até o próximo clique. Selecionar uma linha de uma tabela marca os átomos daquela medida. Clique no
   vazio e Esc limpam os pendentes (as tabelas ficam). Trocar ou desligar o modo limpa os pendentes. Nada disso mexe na câmera (spec 43,
   R3).
3. As medidas são da janela: outra janela tem as suas, nada é gravado, e fechar a janela as descarta.
4. **Testes** (`tests/test_structure3d_measure_ui.py`, novo, com os helpers da spec 43 que clicam num átomo pela posição projetada): a
   sequência do pedido (A, B; A, C; B, C) em "Distância" dá três linhas na ordem, com os valores do núcleo; dois trios em "Ângulos" dão
   duas linhas; sem modo, clicar não cria linha; ligar "Ângulos" desliga "Distância" e clicar no ligado o desliga; trocar de modo com um
   átomo pendente o descarta; "Copiar" põe o TSV na área de transferência; "Limpar" esvazia; Delete remove a linha selecionada; zoom, pan
   e rotação iguais antes e depois de tudo; duas janelas do mesmo arquivo têm tabelas independentes.

## Fora de escopo

- Diedro (4 átomos) e "Usar imagem mais próxima" do exemplo: não pedidos. A medida é sempre entre as cópias clicadas; para a imagem
  mínima, o usuário liga a repetição e clica na cópia vizinha.
- Desenhar a medida na cena (linha tracejada com o valor, arco do ângulo): não pedido; os anéis numerados mostram quais átomos entraram.
- Exportar as medidas em arquivo (CSV): "Copiar" cobre colar numa planilha.
- Gravar as medidas entre sessões ou por arquivo: as configurações e o estado são da janela (spec 43).
- Atalhos de teclado para os modos: não pedidos.

## Decisões assumidas (confirmar na revisão)

1. **O vértice do ângulo é o segundo átomo clicado.** A documentação do XCrySDen consultada não diz; Jmol e o exemplo usam o do meio.
2. **Os dois botões podem ficar desligados**, e começam assim ("o usuário deve selecionar um deles para realizar o cálculo"); sem modo, o
   clique só mostra o átomo.
3. **Duas tabelas**, uma por tipo, cada uma aparecendo quando tem a primeira linha; o botão ativo não esconde a tabela do outro tipo (o
   que já foi medido continua à vista).
4. **Casas decimais:** distância com 3 (0,001 Å) e ângulo com 2 (0,01°); o pedido mostra 1, que parece só ilustração. Ponto decimal,
   como o resto da interface.
5. Um átomo repetido dentro do mesmo par ou trio é ignorado (não fecha a medida); a seção "Átomo" ainda mostra o clique.
6. "Copiar" leva as duas tabelas num TSV só, com a coluna "Medida", sem unidade nos números (cola como número numa planilha).

## Notas de implementação

- Novos: `src/qe_studio/core/structure3d/measure.py`, `src/qe_studio/core/structure3d/measurements.py`,
  `src/qe_studio/ui/widgets/structure3d/measures.py` (nova seção: botões, tabelas, copiar/limpar), `tests/test_structure3d_measure.py`,
  `tests/test_structure3d_measure_ui.py`.
- Alterados (criados pela spec 43): `ui/widgets/structure3d/panel.py` (a seção no lugar reservado), `ui/widgets/structure3d/canvas.py` e o overlay (anéis
  numerados dos pendentes e da linha selecionada), `tests/test_architecture.py` (`QT_FREE`), `tests/test_properties.py`.
- Limites: nenhum arquivo perto de 500 linhas (todos novos na spec 43). `ui/main_window.py` **não** muda.
- Documentação ao implementar: a seção "Visualização 3D" do `CLAUDE.md` (criada pela 43) ganha o parágrafo das medidas (`Measurer`, modos,
  vértice no 2º átomo); `README.md`.

## Critérios de aceite e testes

- [ ] Os testes da spec 43 continuam verdes, inclusive os de câmera (as medidas não mexem no zoom).
- [ ] Distância do diamante = `√3/4 · a` e ângulo tetraédrico 109,47° em `si.scf.in` (`test_structure3d_measure.py`, novo).
- [ ] `Measurer`: pares e trios independentes, átomo repetido ignorado, troca de modo descarta os pendentes (`test_structure3d_measure.py`, novo).
- [ ] A sequência do pedido gera "O… - O…" linha a linha nas tabelas "Distâncias" e "Ângulos", na ordem dos cliques
      (`test_structure3d_measure_ui.py`, novo).
- [ ] "Distância" e "Ângulos" são exclusivos e podem ficar os dois desligados; sem modo, nada é medido (`test_structure3d_measure_ui.py`, novo).
- [ ] "Copiar", "Limpar" e Delete funcionam; janelas diferentes têm medidas independentes (`test_structure3d_measure_ui.py`, novo).
- [ ] Passo manual de aceite: o usuário mede, numa estrutura real, as distâncias e ângulos que conhece (por exemplo, O–H e H–O–H de uma
      hidroxila) e confere os valores e o vértice.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
