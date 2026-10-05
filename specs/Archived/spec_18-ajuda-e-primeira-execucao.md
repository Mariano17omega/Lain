# Spec 18: Ajuda, atalhos, paleta de comandos e primeira execução

| | |
|---|---|
| **Prioridade** | 18 |
| **Status** | Implementada |
| **Depende de** | spec 15 (registro de ações), spec 16 (favoritos/recentes na paleta) |
| **Usada por** | nenhuma |
| **Esforço** | M |

## Itens de origem (`report.md` §3)

> - **Estado vazio de primeira execução** (sem `config.yaml`/pasta inexistente): "Escolher pasta…", "Abrir config".
> - **Menu Ajuda**: Atalhos (Ctrl+G/E/T e F5 não têm descoberta), Sobre (versão, caminho do log em `cache_dir()/qe_studio.log`), "Abrir log".
> - Legenda dos badges/rótulos (BANDS, PDOS, RELAX, SCF, CALC, INCOMPLETO, AVISO) em tooltip.
> - Rodapé: `set_readout` (`bars.py:234`) não elide; em janelas estreitas o texto longo espreme a mensagem. Elidir + tooltip.
> - **Paleta de comandos** Ctrl+K.

Decisão do usuário (30/09/2026): a "primeira execução" **entra**, embora toque no F13 (abrir pasta /
multiprojeto), que foi adiado. Aqui ela cobre só o estado vazio, sem multiprojeto.

## Situação atual

- **Menus** (`ui/main_window.py:282-300`): Arquivo, Cluster, Gráficos e Ferramentas. Não há Ajuda nem
  Sobre. Os atalhos (F5, Ctrl+Q, Ctrl+G, Ctrl+E, Ctrl+T) só aparecem ao lado dos itens de menu. Backspace
  e Alt+↑ da grade (`file_grid.py:230-233`) não aparecem em lugar nenhum.
- **Log:** `setup_logging` (`ui/app.py:20-26`) grava em `cache_dir()/qe_studio.log` (rotativo,
  1 MB × 2). O caminho só aparece no diálogo de erro inesperado (l.47).
- **Badges e rótulos:**
  - badges nas pastas da árvore (`explorer.py:60-62`, `ui/painting.py:10`);
  - rótulos de estado nos arquivos (`ui/file_types.py:77-89`);
  - nenhum dos dois tem tooltip explicando o significado.
- **Rodapé:** `StatusBar.set_readout` (`ui/widgets/bars.py:234-235`) só faz `setText`, sem elidir. O
  texto do readout ("Estrutura de bandas · E_F = … · 1200×900 px (300 DPI)", montado em
  `main_window.py:848-859`) pode ocupar o espaço da mensagem.
- **Primeira execução:**
  - sem `config.yaml`, `load_config` usa os padrões com o aviso "config.yaml não encontrado; usando
    valores padrão.";
  - com `local_root` inexistente, `_warnings` (`core/config.py:253-256`) avisa "Pasta local não
    encontrada: …";
  - o `MainWindow` só põe o primeiro aviso no rodapé (`main_window.py:212-215`). Árvore e grade ficam
    com um índice raiz inválido;
  - `open_config` (l.576-585) sem config carregado diz "Copie config.example.yaml para config.yaml e
    reinicie o Lain.";
  - o `config.example.yaml` fica na raiz do repositório e não vai junto com o pacote.

## Requisitos

### R1: Menu Ajuda
Novo menu "Ajuda", o último da barra:
1. **"Atalhos de teclado"** (F1): diálogo não modal com uma tabela Ação | Atalho | Onde, gerada do
   registro de ações (`MainWindow._actions`, spec 15), mais os atalhos de contexto declarados pelos
   widgets:
   - grade: Backspace, Alt+↑, Ctrl+F;
   - texto: Ctrl+F, F3, Ctrl+L, Ctrl+Home/End;
   - abas: Ctrl+W, botão do meio;
   - navegação: Alt+←/→;
   - input: F8.

   Cada widget expõe `shortcut_help() -> list[tuple[str, str, str]]`, para a lista não ficar
   desatualizada. Campo de busca no topo do diálogo.
2. **"Abrir log"**: abre `cache_dir()/qe_studio.log` numa aba do visualizador de texto (spec 10).
3. **"Abrir pasta de dados"**: `QDesktopServices.openUrl` em `data_dir()` (onde ficam `folders.json` e
   `navigation.json`).
4. **"Sobre o Lain"**: diálogo com:
   - nome, versão (`__version__`) e o ícone (spec 7);
   - versões de Python, Qt, PyQt, matplotlib, numpy e ASE (esta última importada só ao abrir o diálogo,
     spec 14);
   - caminhos do config carregado (ou "nenhum"), do log e dos dados;
   - link para o repositório.

   Botão "Copiar informações", para relatar problemas.

### R2: Paleta de comandos (Ctrl+K)
1. Ctrl+K (e o item "Ajuda ▸ Paleta de comandos") abre uma janela sem moldura, centrada no topo, com um
   campo de busca e uma lista.
2. Fontes da lista, cada uma com prefixo de categoria e ícone:
   - **Ações** do registro (spec 15), com o atalho à direita. Ações desabilitadas no momento não
     aparecem;
   - **Pastas do projeto**: um índice de pastas montado em worker a partir de `local_root` (respeita
     `ui.hidden_dirs`, até 20 000 pastas, construído na primeira abertura e invalidado pelo F5).
     Escolher navega até a pasta;
   - **Favoritos** e **Recentes** (spec 16), primeiro na lista vazia;
   - **Abas abertas**: escolher ativa a aba.
3. Busca aproximada: subsequência sem diferenciar maiúsculas nem acentos, ordenada por pontuação
   (prefixo > início de palavra > subsequência) e depois por recência. Prefixos opcionais restringem:
   `>` ações, `/` pastas, `@` abas.
4. Teclado: ↑/↓, Enter executa, Esc fecha. Até 50 resultados visíveis.
5. Nenhuma leitura de disco no thread da GUI: o índice de pastas vem do worker. Enquanto ele carrega, a
   seção mostra "Indexando pastas…".

### R3: Legenda dos badges e rótulos
1. Tooltip nos badges da árvore (e nos cards de pasta da grade) com o `display_name` do módulo e uma
   frase curta. Exemplos:
   - BANDS: "Estrutura de bandas: bands.x/.gnu detectados";
   - SCF: "Cálculo SCF (pw.x)";
   - CALC: "Saída do QE sem tipo plotável".

   O texto vem do módulo (`CalculationModule.description`, novo `ClassVar`), não de uma tabela na UI
   (spec 8).
2. Tooltip nos rótulos de estado dos arquivos:
   - OK: "Execução concluída (JOB DONE)";
   - INCOMPLETO: "Sem JOB DONE: job rodando ou interrompido";
   - AVISO: os avisos do sniff, um por linha;
   - ERRO / SEM ERROS (log de job): o significado da spec 4.
3. Os tooltips são calculados no `helpEvent` dos delegates, só com dados em cache (`peek`).

### R4: Rodapé elidido
1. `set_readout(text)` guarda o texto completo, mostra a versão elidida à direita (`ElideMiddle`,
   `QFontMetrics.elidedText`) na largura disponível, recalcula no `resizeEvent` e põe o texto completo
   no tooltip.
2. A mensagem (à esquerda, com stretch) tem largura mínima de 200 px. Quando falta espaço, quem elide é
   o readout.
3. A mesma regra vale para o caminho do rodapé (`set_path`).

### R5: Primeira execução e estados vazios
1. **Sem `config.yaml`:** a área da árvore e da grade mostra um estado vazio centralizado:
   - título "Bem-vindo ao Lain", com o texto "Nenhum config.yaml encontrado. O Lain usa um arquivo de
     configuração (não há janela de configurações).";
   - botão **"Criar config…"**: com confirmação, copia o modelo de configuração (R5.4) para
     `~/.config/qe-studio/config.yaml`, abre no visualizador e no editor externo e mostra "Depois de
     editar, use Ferramentas ▸ Recarregar config.yaml";
   - botão **"Escolher pasta…"**: `QFileDialog.getExistingDirectory`. Com confirmação ("Criar
     config.yaml com esta pasta como projeto?"), cria o config do modelo com `paths.local_root` trocado
     pela pasta escolhida (substitui só a linha `local_root:` do modelo, que é um texto conhecido) e
     recarrega.
2. **Config existe, mas `local_root` não existe:** estado vazio com "A pasta do projeto não foi encontrada:
   `<caminho>`" e os botões:
   - **"Abrir config"**: abre o config no visualizador e no editor externo;
   - **"Escolher pasta…"**: navega para a pasta escolhida **só nesta sessão** e mostra no rodapé "Pasta
     temporária: para fixar, edite paths.local_root no config.yaml". O Lain **não** reescreve um config
     existente (PRD §6: o config é do usuário).
3. **Config inválido:** continua o diálogo crítico atual (`ui/app.py:74-77`). A spec não muda isso.
4. O modelo de configuração passa a ir junto com o pacote: `src/qe_studio/resources/config.example.yaml`,
   lido com `importlib.resources`. O `config.example.yaml` da raiz continua como documentação, e um teste
   garante que os dois arquivos são idênticos.
5. `open_config` sem config carregado oferece o mesmo "Criar config…" do R5.1, em vez da mensagem
   atual.

## Fora de escopo
- Multiprojeto, "projetos recentes" e lista `projects:` (F13, adiado).
- Assistente de várias etapas (cluster, senha, chave ssh).
- Janela de configurações (PRD §6).
- Atualização automática do app.

## Decisões assumidas (confirmar na revisão)
1. O Lain só **cria** um config novo (R5.1). Nunca edita um existente. Com config existente e pasta
   inválida, "Escolher pasta…" vale só para a sessão (R5.2).
2. F1 abre "Atalhos de teclado" (R1.1).
3. O índice de pastas da paleta tem limite de 20 000 pastas (R2.2).
4. As descrições dos badges ficam no módulo (`description`), coerente com o contrato da spec 8.

## Notas de implementação
- Novos:
  - `ui/dialogs/shortcuts.py`, `ui/dialogs/about.py`, `ui/widgets/command_palette.py`;
  - `ui/widgets/empty_state.py`, `src/qe_studio/resources/config.example.yaml`;
  - `tests/test_help.py`, `tests/test_command_palette.py`, `tests/test_first_run.py`.
- Alterados:
  - `ui/main_window.py` (menu, ações, estados vazios), `ui/widgets/bars.py` (elidir);
  - `ui/widgets/explorer.py`, `ui/widgets/file_grid.py` (tooltips);
  - `core/calculations/*` (`description`);
  - `core/config.py` (caminho do modelo), `pyproject.toml` (incluir `resources/` no pacote, se preciso).
- Testes de primeira execução usam os diretórios `XDG_*` temporários do `conftest.py` (nunca o home
  real).

## Critérios de aceite e testes
- [x] O menu "Ajuda" tem `["Atalhos de teclado", "Paleta de comandos", "Abrir log", "Abrir pasta de
      dados", "Sobre o Lain"]`.
- [x] O diálogo de atalhos lista Ctrl+G, Ctrl+E, Ctrl+T, F5, Ctrl+K, Ctrl+F (grade e texto), Alt+←/→ e
      Backspace.
- [x] "Sobre" mostra a versão e o caminho do log. "Copiar informações" põe esses dados na área de
      transferência.
- [x] Paleta: digitar "gerar" mostra "Gerar gráfico (Ctrl+G)", e Enter dispara a ação. Com `/rel`,
      mostra só pastas cujo nome casa (ex.: `01_relax` do `demo_project`). O índice é montado em worker.
- [x] Tooltip do badge RELAX contém "Otimização estrutural". Tooltip do rótulo INCOMPLETO contém "JOB
      DONE".
- [x] Readout longo numa janela de 600 px de largura fica elidido, e o tooltip tem o texto completo.
- [x] Sem config (XDG temporário, cwd sem config): estado vazio visível. "Escolher pasta…" com diálogo e
      confirmação patchados cria `~/.config/qe-studio/config.yaml` (XDG temporário) com o `local_root`
      escolhido, e a árvore mostra a pasta.
- [x] Config com `local_root` inexistente: estado vazio. "Escolher pasta…" não altera o arquivo de
      config (hash igual antes e depois).
- [x] `resources/config.example.yaml` é idêntico ao da raiz.
