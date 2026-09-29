---
name: Quantum Precision IDE
colors:
  surface: '#101319'
  surface-dim: '#101319'
  surface-bright: '#363940'
  surface-container-lowest: '#0b0e14'
  surface-container-low: '#191c22'
  surface-container: '#1d2026'
  surface-container-high: '#272a30'
  surface-container-highest: '#32353b'
  on-surface: '#e1e2eb'
  on-surface-variant: '#bbc9cf'
  inverse-surface: '#e1e2eb'
  inverse-on-surface: '#2d3037'
  outline: '#859399'
  outline-variant: '#3c494e'
  surface-tint: '#47d6ff'
  primary: '#a5e7ff'
  on-primary: '#003543'
  primary-container: '#00d2ff'
  on-primary-container: '#00566a'
  inverse-primary: '#00677f'
  secondary: '#b4c5ff'
  on-secondary: '#002a78'
  secondary-container: '#0053db'
  on-secondary-container: '#cdd7ff'
  tertiary: '#69f6b9'
  on-tertiary: '#003824'
  tertiary-container: '#48d99e'
  on-tertiary-container: '#005b3d'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#b6ebff'
  primary-fixed-dim: '#47d6ff'
  on-primary-fixed: '#001f28'
  on-primary-fixed-variant: '#004e60'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#101319'
  on-background: '#e1e2eb'
  surface-variant: '#32353b'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  headline-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
  body-lg:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  body-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '400'
    lineHeight: 12px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.5rem
  margin: 0.5rem
  space-xs: 0.125rem
  space-sm: 0.25rem
  space-md: 0.5rem
  space-lg: 0.75rem
  space-xl: 1rem
---

## Brand & Style

O design system estabelece uma linguagem visual para instrumentação científica de alta precisão, simulação computacional e análise quântica de materiais. Projetado para pesquisadores, físicos computacionais e engenheiros químicos, o sistema equilibra a densidade informacional de ferramentas desktop de classe IDE (como VS Code e PyCharm) com a sobriedade analítica de laboratórios e terminais de supercomputação (HPC).

A experiência visual elimina ruídos ornamentais para priorizar a acurácia de leitura, a manipulação rápida de parâmetros numéricos e o foco estendido em telas durante longas sessões de modelagem estrutural e cálculos SCF (Self-Consistent Field). O estilo combina o **Modern Technical Minimalism** com sutis camadas tonais de inspiração em aplicações nativas PyQt6/C++, garantindo contraste cirúrgico, bordas estruturais ultraprecisas e acentos cromáticos que traduzem níveis de energia, densidade de estados e topologia orbital.

## Colors

A paleta cromática foi estruturada para mitigar a fadiga ocular em ambientes de trabalho contínuos e garantir clareza diagnóstica inequívoca. O espectro tonal opera em camadas escuras com base em carvão profundo e ardósia fria, reservando frequências luminosas para sinalização de estados térmicos, orbitais e fluxos computacionais.

### Camadas de Superfície e Estrutura
- **Base Canvas (`#0f1216`)**: Fundo mestre da aplicação, sob abas inativas e trilhos de rolagem.
- **Surface Level 1 / Sidebar (`#15181e`)**: Superfície da árvore hierárquica (Tree View), toolbars e barras de status do sistema.
- **Surface Level 2 / Workspace (`#1e222b`)**: Área ativa de visualização de dados, editores de script e painéis de plotagem.
- **Surface Level 3 / Inspetores & Popovers (`#282c37`)**: Painéis de propriedades, tooltips analíticos e campos de entrada de foco.
- **Borda Estrutural (`#323846`)**: Divisores nítidos de 1px entre painéis redimensionáveis e abas.

### Luz Quântica e Acentos Funcionais
- **Eletric Cyan (`#00d2ff`)**: Destaque primário, bandas de condução, cursores de precisão e seleções de nós em árvores.
- **Cobalt Blue (`#2563eb`)**: Superfície de botões acionáveis (Rsync, Plot), foco em inputs estruturais e guias ativas.
- **Deep Blue Accent (`#1d4ed8`)**: Hover e estados pressionados de controles principais.

### Sinalização de Execução e Status HPC
- **SCF Concluído / Convergência OK (`#10b981`)**: Verde esmeralda analítico para status de cálculo convergido e conexão ativa com o cluster.
- **Job em Fila / Sync Ativo (`#f59e0b`)**: Âmbar vibrante indicando processamento assíncrono em nós remotos ou escrita I/O de disco.
- **Divergência / Falha de Matriz (`#f43f5e`)**: Vermelho coral cirúrgico para erros de autoconsistência (SCF not converged), limites de memória ou sintaxe de input.
- **Orbitais e Projeções Quânticas**:
  - *Orbital s*: Ouro espectral (`#fbbf24`)
  - *Orbital p*: Ciano ionizado (`#06b6d4`)
  - *Orbital d*: Violeta de valência (`#a855f7`)
  - *Orbital f*: Magenta magnético (`#ec4899`)

## Typography

A tipografia é tratada como instrumento de mensuração técnica. A escala adota uma densidade compacta de classe desktop, permitindo que cientistas inspecionem centenas de variáveis por viewport sem perda de legibilidade.

### Divisão de Papéis
- **Inter**: Governa títulos de painéis, abas de arquivo, rótulos de navegação, cabeçalhos de diálogo e textos explicativos de interface.
- **JetBrains Mono**: Governa todos os valores de ponto flutuante ($E_F$, tensores de estresse, energias de corte k-point), logs de console (standard out/error), caminhos de arquivo Unix, etiquetas heurísticas (BANDS, PDOS) e entradas de coordenadas atômicas.

### Regras de Renderização e Alinhamento
- Todos os números flutuantes e vetores de lattice devem ativar numerais tabulares (`tnum`) para alinhamento vertical rígido em tabelas e inspetores.
- Entradas de texto monoespaçadas preservam espaçamento de caractere regular para evitar quebras visuais em strings de comando do cluster (`rsync -avzP`).

## Layout & Spacing

O layout rejeita o espaçamento difuso característico da web comercial em favor de uma grade estruturada de dock multi-painel com ancoragem de alta densidade inspirada no Qt Framework (QSplitter e QDockWidget).

### Modelo de Layout
- **Toolbar Superior**: Altura rígida de 36px, agrupando atalhos rápidos de execução, perfil de conexão com o cluster e comandos de viewport.
- **Sidebar de Navegação / Tree View**: Painel esquerdo colapsável com largura padrão de 260px (mínimo 200px, redimensionável via splitter de 2px).
- **Workspace Central**: Visualizadores de estrutura cristalina (3D Canvas), editores de input QE ou gráficos matplotlib/canvas interativos com abas superiores de 28px de altura.
- **Inspetor de Plotagem e Propriedades**: Painel direito ancorado (largura padrão de 320px) composto por grupos dobráveis (collapsible accordions) contendo inputs de precisão numérica e controles espectrais.
- **Status Bar Inferior**: Altura fixa de 22px contendo status do job SCF, latência do nó e consumo de memória RAM/VRAM.

### Ritmo de Espaçamento Interno
- **Densidade Compacta**: A escala padrão opera com divisores de 2px, 4px e 8px. Nenhum elemento de formulário técnico excede 24px de altura padrão.
- **Gaps e Margens**: Elementos em linha no inspetor de plotagem (ex.: Rótulo $E_F$ + Input + Unidade 'eV') mantêm espaçamento estrito de 4px (`space-sm`) entre si.

## Elevation & Depth

Em consonância com interfaces nativas PyQt6 e computação científica de alto desempenho, este design system elimina sombras suaves puramente estéticas. A profundidade espacial é comunicada através de **camadas tonais de superfície estrutural**, **linhas de separação de 1px** e **contrastes de borda ativa**.

### Níveis de Profundidade
1. **Piso Base (`#0f1216`)**: O nível mais recuado, utilizado em calhas de rolagem e fundos de áreas colapsadas.
2. **Superfície Secundária (`#15181e`)**: Docas estáticas, barras de ferramentas e visualizadores hierárquicos laterais.
3. **Superfície Ativa (`#1e222b`)**: Área central de trabalho e cartões de propriedades de plotagem.
4. **Camada Flutuante / Overlays (`#282c37`)**: Menus de contexto acionados com botão direito, tooltips de coordenadas e paletas de cores de orbitais. Utiliza borda sólida de 1px em `#323846` acrescida de uma sombra técnica nítida: `0 4px 12px rgba(0, 0, 0, 0.45)`.
5. **Indicação de Foco Ativo**: O elemento em edição ativa (input numérico, nó da árvore focado) ganha uma borda externa de 1px em `#00d2ff` com suave realce de brilho periférico (`box-shadow: 0 0 0 1px rgba(0, 210, 255, 0.25)`), assegurando que o operador do software identifique o foco imediato do teclado.

## Shapes

A linguagem de formas adota a precisão mecânica com cantos suavemente lapidados (`roundedness: 1`), transmitindo robustez e integração perfeita com os estilos gráficos do sistema operacional desktop.

- **Bordas de Painéis e Abas**: 0px de raio de curvatura em arestas conectadas a splitters; 3px em cantos superiores de abas e botões de abas.
- **Controles Interativos (Inputs, Botões, Dropdowns)**: Raio padrão de 4px (`0.25rem`). Mantém a aparência técnica sem aspereza bruta.
- **Tags Heurísticas (BANDS, PDOS, RELAX)**: Raio de 2px a 3px com preenchimento interno ultra-compacto.
- **Indicadores de Status e Paletas**: Círculos perfeitos (100% de raio) exclusivamente para seletores de cor de orbital e LEDs virtuais de estado do cluster.

## Components

### 1. Botões de Ação de Engenharia
- **Primary Action (Sincronizar Cluster Rsync / Gerar Gráfico)**: Fundo `#2563eb`, texto `#ffffff`, altura de 26px, padding horizontal de 12px, cantos arredondados de 4px. Em hover, transiciona para `#1d4ed8`; ao clicar (active), recua 1px no eixo vertical.
- **Secondary Action (Exportar SVG/EPS, Reset Zoom)**: Fundo `#1e222b`, borda de 1px em `#323846`, texto `#cbd5e1`. Em hover, fundo `#282c37` e borda `#00d2ff`.
- **Status Trigger (Abort Calculation)**: Borda e texto em `#f43f5e`, fundo transparente. Em hover, fundo translúcido `rgba(244, 63, 94, 0.15)`.

### 2. Controles de Ajuste de Gráfico e Inputs Numéricos
- **Input de Precisão ($E_{Fermi}$, Energia $E - E_F$, Smearing Gaussian)**:
  - Fundo `#15181e`, borda `#323846`, texto em `JetBrains Mono` (`#00d2ff`).
  - Altura de 22px, alinhamento numérico à direita.
  - Sufixo de unidade imutável à direita (ex.: `eV`, `Ry`, `Å`) em cinza médio (`#64748b`).
  - Botões micro-stepper (+/-) embutidos no lado direito com feedback tátil instantâneo.
- **Range Slider Bipolar ($E_{min}$ até $E_{max}$)**:
  - Trilho fino de 3px em `#323846`, faixa ativa entre limitadores em `#00d2ff`.
  - Manipuladores retangulares de precisão com centro vazado de 10px x 14px em `#282c37` com borda ciano.

### 3. Hierarquia em Tree View (Estrutura de Arquivos e Cálculos)
- Linha de nó com altura rígida de 22px, indentação modular de 12px por nível de pasta.
- **Seleção Ativa**: Fundo `rgba(0, 210, 255, 0.12)` com borda lateral esquerda de 2px em `#00d2ff`.
- **Ícones de Arquivo**: Distinção clara entre inputs (`.in` em azul cobalto), outputs de texto bruto (`.out` em cinza claro) e binários quânticos (`.xml`, `.save` em ciano).
- **Tags Heurísticas**: Pequenos crachás monoespaçados (badge de 16px de altura) dispostos à direita do nome do cálculo:
  - `BANDS`: Fundo `rgba(37, 99, 235, 0.2)`, texto `#93c5fd`, borda `rgba(37, 99, 235, 0.4)`.
  - `PDOS`: Fundo `rgba(168, 85, 247, 0.2)`, texto `#d8b4fe`, borda `rgba(168, 85, 247, 0.4)`.
  - `RELAX`: Fundo `rgba(16, 185, 129, 0.2)`, texto `#6ee7b7`, borda `rgba(16, 185, 129, 0.4)`.

### 4. Seletor de Paleta de Orbitais (Orbital Color Swatches)
- Fileira compacta de seletores para orbitais $s$, $p$, $d$, $f$.
- Cada item exibe o glifo da subcamada em `JetBrains Mono` seguido por um disco circular de cor de 12px com borda `#323846`.
- Ao clicar no disco, exibe-se uma matriz popover flutuante com perfis pré-calibrados: viridis, plasma, cividis e paletas de contraste atômico isoladas.

### 5. Abas de Documento e Workspace (Tabs)
- Altura de 28px, fundo inativo `#15181e`, separador vertical sutil `#323846`.
- Aba ativa em `#1e222b`, com linha superior de 2px em `#00d2ff` e botão de fechamento (ícone de x de 8px) que surge em hover.
- Suporte a indicador de arquivo não salvo (ponto circular de 6px em `#f59e0b`).

### 6. Painel de Propriedades e Inspetor de Plotagem (Inspector Accordion)
- Cabeçalhos colapsáveis com seta direcional sutil em 90 graus, título em negrito de 11px em caixa alta (`Inter`, tracking +0.5px).
- Grade interna em duas colunas: Rótulo do parâmetro à esquerda (largura fixa de 40%, alinhamento à esquerda, cor `#94a3b8`) e campo de entrada à direita (60%).