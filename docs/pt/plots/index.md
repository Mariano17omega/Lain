# Gráficos — visão geral

Os gráficos são feitos com matplotlib e pensados para publicação. Há cinco tipos detectáveis e dois compostos:

| Tipo | Origem | Página |
|---|---|---|
| Estrutura de bandas | pasta `BANDS` | [Bandas](bands.md) |
| PDOS | pasta `PDOS` | [PDOS](pdos.md) |
| Bandas + DOS | 1 pasta de bandas + 1 de PDOS | [Bandas com DOS](bands-dos.md) |
| Relax / vc-relax | saída do `pw.x` | [Relax](relax.md) |
| Convergência do SCF | saída do `pw.x` | [SCF](scf.md) |
| Grid de gráficos | gráficos já abertos | [Grids](grids.md) |

## Como plotar

1. Selecione a pasta (ou, para Bandas + DOS, as duas pastas com `Ctrl`-clique).
2. **Plot** na barra de atividades, **Gerar gráfico** (`Ctrl+G`) ou **Plotar** no menu de contexto.
3. O painel esquerdo troca para os **ajustes** (botão **Árvore** volta). O painel é gerado a partir da lista de
   `ParamField` do módulo, em seções (Energia, Eixo x, Estilo, Spin, Projeções…).
4. **Exportar** (`Ctrl+E`) salva em `plots/` da simulação.

Pastas já plotadas reabrem como estavam (a partir do `.plot`) sem salvar de novo. Com
`ui.auto_generate_plot: false`, uma pasta nunca plotada só abre o painel e **Gerar Plot** plota.

Passar o mouse mostra os valores sob o cursor na barra do gráfico (k e energia com o ponto de alta simetria mais
próximo, PDOS, passo do relax, iteração do SCF). Zoom/pan da barra atualizam a janela de energia.

## Ajustes persistentes (`.plot`)

Os ajustes ficam em `<tipo>.plot` (por exemplo `bands.plot`) em `<simulação>/plots/` e voltam na próxima vez.
**Restaurar padrões** apaga o arquivo. Um `.plot` antigo na pasta da simulação não é mais lido.

## Nível de Fermi em isolantes { #fermi-em-isolantes }

Em um isolante ou semicondutor intrínseco, o nível de Fermi fica dentro do gap, aproximadamente no meio. O `pw.x` não
imprime esse valor: com ocupações fixas ele dá o HOMO (o topo da valência) e, com smearing, um ponto qualquer do gap.
Por isso, quando o gap está comprovado, o E_F dos gráficos é o **meio do gap**, `(VBM + CBM) / 2`. Nos demais casos, é
o valor impresso pelo `pw.x`.

| Gráfico | A regra vale quando | Meio do gap |
|---|---|---|
| Bandas, sem spin | a contagem de elétrons enche bandas inteiras e há VBM e CBM: ocupações fixas, ou smearing com E_F entre o VBM e o CBM | `(VBM + CBM) / 2` ao longo do caminho k |
| Bandas, com spin | os dois canais têm gap, o gap global abre, as bandas de valência dos dois canais somam o número de elétrons e o `pw.x` imprimiu um único E_F | VBM e CBM globais |
| PDOS, par impresso | o `pw.x` imprimiu HOMO e LUMO (do NSCF, senão do SCF) e o par abre um gap. Um par do SCF, quando o NSCF não imprimiu o seu, precisa concordar com a DOS: se o meio dele cair em estados, vale a região vazia logo acima do HOMO | média do HOMO e do LUMO, ou o meio dessa região |
| PDOS, ocupações fixas sem LUMO | uma região vazia da DOS total começa a até 0.25 eV acima do HOMO | meio dessa região |
| PDOS, smearing | o E_F do NSCF ou do SCF está **dentro** de uma região vazia da DOS total e o número de elétrons pode encher bandas inteiras | meio dessa região |

Uma **região vazia** é um trecho em que a DOS total (os dois canais de spin somados) fica em até 0.1 % do seu máximo,
com estados dos dois lados, e chega a no máximo 0.01 estados/eV no seu ponto mais fundo. Um E_F do NSCF dentro de uma
banda, além da cauda alargada (0.25 eV), indica um metal, e o SCF não é consultado.

A regra **não** se aplica, e fica o valor impresso, quando:

- o sistema é metálico: uma banda cruza E_F, ou E_F cai fora de [VBM, CBM] no caminho;
- o número de elétrons não enche bandas inteiras (contagem ímpar sem spin);
- o E_F não foi encontrado (as energias ficam absolutas);
- de um cálculo com spin só o canal ↑ foi encontrado;
- todas as bandas da saída estão cheias, sem banda vazia para medir o gap;
- há duas energias de Fermi (↑/↓), de um cálculo com magnetização total fixa.

**O que acompanha o novo E_F:** a linha de Fermi, o zero do eixo (`E − E_F`), o limite dos estados ocupados preenchidos,
a cor de valência e condução, o CSV e os Grids. Em **Bandas + DOS**, os dois painéis seguem o E_F das bandas.

**O rodapé** diz quando a regra está em vigor: `HOMO = … eV · E_F = … eV (meio do gap)` com ocupações fixas (na PDOS,
`HOMO = … eV (SCF)` ou `(NSCF)`, o cálculo de onde veio) e `E_F = … eV (meio do gap)` com smearing. Nas bandas, a
referência `E_F (SCF)` passa a se chamar `E_F (meio do gap)`. O campo **E_F de** (SCF/NSCF) some do painel da PDOS quando
não teria efeito.

**O que não muda:** o **Método do gap** e as referências `Topo da valência (VBM)`, `Meio do gap` e `Absoluta`. Com a regra
em vigor, o gap que a legenda da PDOS mostra em *Automático* é o da região em que o E_F foi colocado.

!!! note "Limites"
    - Numa PDOS com smearing cujo E_F cai na cauda alargada de uma banda, fica o valor impresso: a regra prefere não mover
      o E_F de um metal.
    - Numa PDOS com só o HOMO impresso e alargamento acima de cerca de 0.1 eV, a região vazia começa longe demais do HOMO e
      fica o valor impresso.
    - Nas bandas, o meio do gap é o do caminho k. Um extremo fora do caminho desloca esse valor.
    - Bandas e PDOS do mesmo material podem diferir um pouco, pois medem o gap em malhas diferentes.

## Estilos { #estilos }

O visual de um gráfico novo (tamanho, largura de linha, cores, fundo, legenda) vem do **estilo** escolhido em
**Estilo do gráfico** (primeiro campo da seção Estilo). Cada estilo é um YAML em
`src/qe_studio/resources/templates/plot_styles/`; `padrao.yaml` é o padrão. Para criar um, copie-o com outro nome,
defina `name:` e mantenha só os campos que mudam:

```yaml
lain_style: 1
name: Escuro
params:
  background: "#111827"
  valence_color: "#facc15"
  orbital_colors: {s: "#f97316"}   # somado ao mapa do padrão, não substitui
```

Um estilo novo aparece após **Recarregar config.yaml** (ou na próxima partida). O Lain só **lê** estilos.

!!! info "Figuras independem do tema do app"
    O estilo vem dos parâmetros (`core/plotting/style.py:figure_style`), nunca do tema escuro/claro, para que prévia e
    exportação sejam idênticas. O fundo padrão é branco.

## Exportação

- Formatos: `plot.export.formats` (`png`, `svg`, `pdf`) e DPI `plot.export.dpi` (300/600).
- Nome: `<projeto>-<pastas>-<gráfico>.png` (caminho desde a raiz); em Bandas, PDOS e Bandas + DOS há também um `.csv`
  dos dados plotados (separador `;` e vírgula decimal, para Excel/Origin em pt-BR).
- Um arquivo existente nunca é substituído sem perguntar.
- Gráfico de pasta remota: cópia em `tmp_remote/`, exportações em `tmp_remote/plots_remote/`.

Código: `core/calculations/*` (módulos), `core/plotting/*` (estilo, exportação, sessão), `ui/plot/*`.
Para criar um tipo novo: [Mapa do código](../code-map.md#adicionar-um-grafico).
