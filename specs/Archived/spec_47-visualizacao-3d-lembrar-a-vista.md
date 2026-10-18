# Spec 47: Visualização 3D lembra a vista: `view3d.plot` na pasta do cálculo, uma seção por arquivo

| | |
|---|---|
| **Prioridade** | 47 (depois da 46, cujos campos novos ela grava). Independente das specs 33–42 e 45. |
| **Status** | Implementada (14/10/2026). Desvios:<br>- `load_view` / `LoadedView` ficam em `core/structure3d/view_file.py` (Qt-free, a função do worker), com `view_file_path(pasta)`; `CameraState` ganhou `of(camera)` e `apply(camera)`, para o canvas não lidar com numpy.<br>- O enquadramento automático do primeiro quadro é o novo `StructureCanvas._frame(viewport)`; `reset_view()` (tecla R e botão) é o do usuário, sem o argumento `viewport`, e marca `dirty`. O canvas ganhou a propriedade `framed`, que `view_session()` lê.<br>- `apply_options` com algo que não é um dicionário devolve `["options"]`; um `dict`/lista com uma entrada inválida (`species_colors`, `species_hidden`, `reps`) cai inteiro.<br>- Um aviso de gravação vai ao toast e ao log.<br>- O teste "só clicar em átomos e medir" abre uma cópia do slab 2×1×1: os dois Si de `si.scf.in` se sobrepõem na vista isométrica.<br>- **Corrigido em 18/10/2026** (revisão de código): a gravação do `view3d.plot` ao fechar saiu da thread da GUI. Vai para uma fila própria do `Structure3DController` (uma escrita por vez, na ordem em que as janelas fecharam: com duas janelas do mesmo arquivo, a última vence); o passo "vistas 3D" do fechamento (`ui/shutdown.py`) e o renomear (`wait_saves`) esperam por ela. O sinal `saved` e `saving` servem aos testes (`close_view` em `tests/structure3d_helpers.py`). |
| **Depende de** | spec 46 (`show_abc`, `show_xyz`, `abc_width`, `xyz_width`, `label_size`, `rotate_structure`, `restore_defaults` e `restored`), spec 43 (`StructureWindow`, `DisplayOptions`, `Camera`, `Structure3DController`), spec 3 (o formato `<kind>.plot`: `core/plotting/plot_file.py`), spec 27-3 (`atomic_write_text`), spec 15 (`run_task`) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: M; R2 e R3: M; R4: P) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): formato novo gravado no fechamento (pasta renomeada com a janela aberta, arquivo compartilhado por várias janelas, `fixtures` que não podem ser tocadas) e um sinal de "alterado" espalhado pela câmera e pelo painel. |

## Itens de origem (`Ideias.md`, 14/10/2026)

> - As configurações feitas na aba esqueda da janela 3D (como posição da estrutura, rotação, zoom, etc) devem ser salvas e restauradas quando a janela for fechada e aberta novamente. Essas configurações devem ser salvas em um arquivo 'view3d.plot' dentro da própria pasta do cálculo.
> - Para o caso de visualização de mais de uma estrutura 3D, como por exemplo, a estrutura 3D de dois scf's diferentes dentro da mesma pasta. Cada arquivo aberto na visualização 3D deve ter uma sessão diferente dentro do 'view3d.plot'. Assim o usuário pode salvar configurações diferentes para cada estrutura 3D, independentemente de qual ela seja.

Os ajustes de interface do mesmo pedido (barra, eixos, rótulos, "Rotação", "Apagar", "Print") estão na spec 46.

Interpretação:

- **"pasta do cálculo"** = a pasta do input aberto na janela.
- **"configurações … posição da estrutura, rotação, zoom, etc"** = todas as opções da janela (`DisplayOptions`: estilo, raio, ligações, repetição, rótulos, caixa, eixos, perspectiva, fundo, cores e visibilidade das espécies) e a **câmera** (rotação, zoom, deslocamento). Não entram: as medidas e o átomo atual (decisão 1).
- **"sessão"** = uma seção do YAML, a do arquivo aberto.
- **"quando a janela for fechada e aberta novamente"** = grava ao fechar, restaura ao abrir (sem gravação enquanto a janela está aberta).
- **"Restaurar padrões"** (pedido na revisão da spec 46): o botão é da spec 46 (R6); esta spec dá o efeito dele no arquivo: a seção da janela é **apagada ao fechar** (R3.5), para o próximo "abrir" voltar aos padrões.

## Situação atual

- **R1 (nada é gravado).** `ui/widgets/structure3d/window.py:1-7` e `core/structure3d/options.py:1` dizem "nothing is saved": a janela nasce com `DisplayOptions(background=<tema>)` (`window.py:68-69`) e a câmera é enquadrada no primeiro quadro (`_framed`, `canvas.py:170-171`, `:184-187`). O controlador cria `StructureWindow(structure, self.theme, self.settings)` depois de `read_structure` num worker (`ui/structure3d_controller.py:64-80`) e tira a janela da lista pelo sinal `closed` (`:94-96`), emitido pelo `closeEvent` (`window.py:152-154`) e também por `close_dialog()` (`:98-102`), que a janela principal chama ao fechar. A spec 43 (R4.4 e "Fora de escopo": "Lembrar as configurações de uma janela por arquivo ou entre sessões: … nada é gravado") e a 44 ("Gravar as medidas entre sessões ou por arquivo") deixaram isso de fora; esta spec supera a primeira.
- **R2 (a família `.plot`).** `core/plotting/plot_file.py`: `<pasta>/<kind>.plot`, YAML `{lain_plot: 1, kind, params}` (`:30-32`, `:91-95`), lido por `read_plot_file(folder, kind)` (`:68-88`): `params` é qualquer dicionário (verificado num script do scratchpad: `read_plot_file(pasta, "view3d")` devolve um dicionário de seções como está), arquivo ausente não é aviso, versão ou `kind` errados voltam como aviso. `write_plot_file` recebe um dataclass (`stored_params` usa `asdict`) e `apply_stored` valida pelas anotações de tipo, e o `_fits` (`:188-208`) não aceita `tuple` (`reps: tuple[int, int, int]`) nem `dict[int, tuple]` (`species_colors`): o `DisplayOptions` **não passa** por eles como está. `atomic_write_text` (`core/appdirs.py:63-82`) **cria a pasta** (`path.parent.mkdir(parents=True, exist_ok=True)`); verificado: escrever numa pasta que foi renomeada a recria. Uma janela fechada depois de renomear a pasta do cálculo deixaria uma pasta fantasma com o nome antigo.
- **R3 (o que muda).** O estado de uma janela é o `DisplayOptions` (`options.py:27-44`; `species_colors` e `species_hidden` indexados pela **posição** da espécie) mais a `Camera` (`rotation`, `center`, `zoom`, `pan`, `focal`: `camera.py:48-56`). Toda edição do painel passa por `StructureCanvas.refresh_options` (`canvas.py:103-119`: `panel._changed`, `set_species_color`, `set_species_visible`, `restore_colors`); a câmera, por `_interacting()` (`:227-232`: arrastar, mover, roda, `+`/`-`), `view_along` (`:135-137`), `reset_view` (`:121-133`, chamado também pelo enquadramento automático do primeiro quadro, `:170-171` e `:186-187`) e, da spec 46, `rotate_structure`; a tecla P grava `options.perspective` direto (`:327-330`). As linhas das espécies do painel usam o **índice** (`_color_of(index)`, `panel.py:237-239`), que depende da ordem de `ATOMIC_SPECIES`.
- **R4 (várias estruturas na pasta).** Uma pasta tem vários inputs (`scf.in`, `scf_convergido_….in`, `nscf…`) e cada um abre a sua janela (`window_title` leva o nome do arquivo, `window.py:41-48`); nada é compartilhado entre janelas.
- **Onde gravar (armadilhas).** `tests/structure3d_helpers.py:94-96` (`Windows.open`) cria `StructureWindow` direto sobre caminhos de **fixtures** (`SI_SCF`…): uma janela que gravasse o `view3d.plot` no próprio fechamento sujaria `tests/fixtures/si_bands/` e `test_fixtures_untouched.py` falharia. Quem grava é o **controlador** (que recebe `closed`); a janela sozinha não grava. Sincronização: `*.plot` nunca sobe (`DEFAULT_PUSH_EXCLUDES = ["plots/", "*.plot"]`, `core/config.py:59`), o pull não toca arquivos que só existem localmente (`core/sync/planner.py:6`), o sniff pula `.plot` (`core/sniff.py:37`) e o visualizador de texto o abre (`core/file_kinds.py:18`). Precedente de gravar no fechamento: `PlotSettingsStore.flush_now` (`ui/plot_settings.py:100-120`) escreve na thread da GUI.

## Requisitos

### R1: O arquivo e o núcleo (Qt-free)

1. **Arquivo** `<pasta do input>/view3d.plot`, da mesma família dos `<kind>.plot` (`lain_plot: 1`, `kind: view3d`); `params` é um dicionário **nome do arquivo → sessão**:

   ```text
   # Lain: ajustes da visualização 3D, uma seção por arquivo. Gerado automaticamente; apague para voltar aos padrões.
   lain_plot: 1
   kind: view3d
   params:
     scf.in:
       options:
         style: bola-vareta
         radius_scale: 1.25
         bond_factor: 1.15
         show_bonds: true
         reps: [1, 1, 1]
         labels: nenhum
         label_size: 11
         show_cell: true
         show_xyz: true
         show_abc: false
         xyz_width: 2.0
         abc_width: 1.8
         perspective: true
         background: escuro
         species_colors: {Si: '#ff00ff'}
         species_hidden: [H]
       camera:
         rotation: [[0.7, -0.7, 0.0], [0.4, 0.4, 0.8], [-0.6, -0.6, 0.6]]
         zoom: 24.71
         pan: [0.0, 0.0]
         focal: 12.0
   ```

   As **espécies são gravadas pelo rótulo** (`Si`, `H`), não pelo índice: o índice depende da ordem de `ATOMIC_SPECIES`. Números gravados são `float` / `int` do Python (o `yaml.safe_dump` recusa os escalares do numpy: `plot_file._plain`). Um campo ausente fica no padrão da janela.
2. **`core/structure3d/view_state.py`** (novo): `CameraState(rotation, zoom, pan, focal)` (dataclass congelado); `session_of(structure, options, camera) -> dict` (a sessão: `options` e, se `camera` não é `None`, `camera`); `apply_options(options, stored, structure) -> list[str]` (põe os valores válidos em `options` e devolve os nomes ignorados; **nunca levanta**, o espírito de `plot_file.apply_stored`); `camera_from_stored(data) -> CameraState | None`. Validação por campo:
   - `style`, `labels`, `background`: uma das chaves de `STYLES`, `LABEL_MODES`, `BACKGROUNDS`; `radius_scale`, `bond_factor`, `abc_width`, `xyz_width`: número finito (um `bool` não é número) dentro de `MIN_…`/`MAX_…` de `options.py`; `label_size`: inteiro dentro do intervalo; `show_*`, `perspective`: `bool` de verdade;
   - `reps`: lista de três inteiros em `MIN_REPEAT … MAX_REPEAT`;
   - `species_colors`: dicionário rótulo → `#rrggbb` (seis dígitos hexadecimais) e **só** rótulos que são espécies da estrutura; `species_hidden`: lista de rótulos da estrutura; os rótulos viram os índices de `structure.species`;
   - câmera: `rotation` 3 × 3 de números finitos, **ortonormal** (`‖R Rᵀ − I‖ ≤ 1e-6`) com determinante positivo; `zoom` finito > 0; `pan` dois números finitos; `focal` finito > 0. Qualquer falha: a câmera inteira é descartada (`None`) e a vista nasce enquadrada como sem sessão.
   - Chaves desconhecidas são ignoradas ao ler e **preservadas** ao regravar a seção de *outro* arquivo (R1.3).
3. **`core/structure3d/view_file.py`** (novo): `VIEW_KIND = "view3d"`, `read_session(folder, name) -> tuple[dict | None, list[str]]` (worker: `read_plot_file(folder, VIEW_KIND)` e `params[name]`; uma seção que não é dicionário é `None`; os avisos de `read_plot_file` voltam como estão: "view3d.plot inválido; usando ajustes padrão.", "view3d.plot ignorado: versão de formato desconhecida (…)"), `write_session(folder, name, session) -> str | None` (nunca levanta; devolve o aviso para o usuário) e `remove_session(folder, name) -> str | None` (tira só a seção `name`; se não sobra nenhuma, apaga o `view3d.plot`; arquivo ou seção ausente, pasta que sumiu ou arquivo ilegível: **nada a fazer**, nada é criado nem reescrito e o retorno é `None`; só um `OSError` ao regravar ou apagar devolve o aviso "Não foi possível atualizar view3d.plot em `<pasta>`: `<motivo>`"). Regras da escrita:
   1. `folder` que não é uma pasta → "A pasta `<nome>` não existe mais: a vista de `<arquivo>` não foi salva em view3d.plot." e **nada é criado** (nem a pasta: o `atomic_write_text` a recriaria);
   2. lê o arquivo atual (`read_plot_file`); as seções dos **outros** nomes ficam como foram lidas (ordem e chaves desconhecidas), a deste nome é trocada no lugar (um nome novo vai ao fim); arquivo ilegível ou de outra versão é substituído por um só com esta seção (como `write_plot_file` faz com um `.plot`);
   3. `atomic_write_text` com o cabeçalho acima; `OSError` → "Não foi possível salvar view3d.plot em `<pasta>`: `<motivo>`".
4. **Testes** (`tests/test_structure3d_view_file.py`, novo, sem Qt; `test_properties.py` para a propriedade):
   - ida e volta: todas as opções trocadas dos padrões (para `si_bands/si.scf.in` e `scf-kaolinite-slab-001-2x1x1.in`) passam por `session_of` → YAML → `apply_options` num `DisplayOptions` novo e voltam **iguais** (`==`);
   - espécies por rótulo: dois inputs com os mesmos rótulos em `ATOMIC_SPECIES` de **ordem diferente** recebem as mesmas cores nos mesmos rótulos (e índices diferentes);
   - valores inválidos caem um a um e o resto vale, sem levantar: `style: "foo"`, `radius_scale: 99`, `reps: [0, 9, 1]`, `show_cell: "sim"`, `label_size: 3.5`, `species_colors: {Si: "vermelho", Zz: "#ffffff"}`, `species_hidden: ["Nope"]`;
   - câmera: rotação não ortonormal, espelhada (determinante −1), `zoom` NaN, `zoom` ≤ 0, `pan` de três números → `None`; uma válida volta igual a 1e-12;
   - `write_session`: cria o arquivo com o cabeçalho, `lain_plot: 1` e `kind: view3d`, que `read_plot_file(pasta, "view3d")` lê; um segundo nome acrescenta uma seção e a primeira fica igual; o mesmo nome troca só a sua seção, mantendo a ordem e uma chave desconhecida da outra; um YAML quebrado e um `lain_plot: 2` são substituídos; pasta que sumiu → o aviso e `not gone.exists()`; pasta sem permissão de escrita (`chmod 0o500`, pulado como root) → o aviso e nenhum `.tmp` sobra;
   - `remove_session`: tira só a seção pedida e as outras ficam como estavam (ordem, chave desconhecida); a última seção apaga o arquivo; nome ausente, arquivo ausente, pasta que sumiu e YAML quebrado não criam nem mudam nada e devolvem `None`; sem permissão de escrita → o aviso;
   - `test_properties.py` (Hypothesis): `apply_options` sobre estruturas JSON arbitrárias nunca levanta e deixa cada campo válido e dentro do intervalo; `camera_from_stored` idem.

### R2: Abrir a janela restaura a vista

1. **Leitura no worker que já lê a estrutura:** `Structure3DController.open` roda `load_view(path) -> LoadedView(structure, session, warnings)` = `read_structure(path)` e `read_session(path.parent, path.name)` (a sessão é `None` sem arquivo ou sem a seção). A GUI não lê nada; um erro de `read_structure` segue sendo o toast "Visualização 3D de X: …".
2. **`_on_done`:** `options = DisplayOptions(background=<fundo do tema>)`; com sessão, `apply_options(options, session.get("options", {}), structure)` (um `background` gravado **vence** o tema do app; ausente, o tema, como hoje) e `camera = camera_from_stored(session.get("camera"))`. Avisos do arquivo (ilegível, versão): `toast.show_message(aviso, "warning")` e a janela abre com os padrões. Campos descartados um a um: `log.warning`, sem toast.
3. **Janela:** `StructureWindow(structure, theme, settings=None, *, options=None, camera=None, root=None)` (o `root` é o da spec 46). `options=None` é `DisplayOptions(background=<tema>)` como hoje. `camera` dado → `StructureCanvas.restore_camera(state)`: põe `rotation`, `zoom`, `pan` e `focal`, o `center` do bloco (como `_fit_keep_rotation`) e `_framed = True`, de modo que o primeiro quadro **não reenquadra**. O painel (criado depois do canvas) já mostra os valores restaurados (caixas, campos, cores e visibilidade das espécies).
4. O zoom e o deslocamento ficam em px por Å e em px: reabrir com outro tamanho de janela mostra a estrutura do mesmo tamanho e centrada como antes.
5. **Testes** (`tests/test_structure3d_session.py`, novo; fixture `main_window` e uma cópia de `si_bands` em `tmp_path`, como `test_structure3d_ui.py`; **nunca** em `tests/fixtures/`): um `view3d.plot` com raio 1.5, "Fio", cor de `Si`, `show_abc: false`, `label_size: 16`, zoom 33.0 e uma rotação → a janela aberta pelo menu mostra as mesmas `canvas.options`, os campos do painel e, depois de `canvas.grab()`, `canvas.camera` com zoom, pan e rotação gravados (**não reenquadrados**); sem arquivo, os padrões e o fundo do tema (os testes de hoje de `test_structure3d_ui.py` seguem verdes); `background: claro` com o tema escuro vence; um arquivo ilegível dá o toast com o aviso e os padrões; um campo inválido sozinho é ignorado e o resto vale; a seção de **outro** nome de arquivo é ignorada.

### R3: Fechar grava só o que o usuário mudou

1. **Sinal de "alterado".** `StructureCanvas.dirty: bool`, `False` ao construir e depois de `restore_camera`; vira `True` com toda mudança feita pelo usuário: qualquer edição do painel e de espécie (tudo o que chama `refresh_options` depois da construção), a tecla P, `_interacting()` (girar, mover, roda, `+`/`-`), `view_along` (teclas e menu), `rotate_structure` (spec 46) e a tecla R ou o botão "Resetar vista" (o enquadramento **automático** do primeiro quadro chama `reset_view` sem o usuário e não conta). **Não** mudam o sinal: cliques, passagem do mouse, o átomo atual, as medidas e seus modos, abrir ou fechar seções do painel (QSettings) nem redimensionar a janela.
2. **Gravação.** `Structure3DController._on_closed(window)` (o sinal `closed`, também o que `close_dialog()` provoca ao fechar a janela principal): se `window.canvas.dirty`, `write_session(pasta, nome, window.view_session())`, com `pasta = Path(structure.source.path).parent` e `nome = Path(structure.source.path).name`; um aviso devolvido vai para `toast.show_message(aviso, "warning")`. `StructureWindow.view_session()` é `session_of(structure, canvas.options, camera)` com `camera = None` se a vista ainda não foi enquadrada. A gravação é **síncrona na thread da GUI** (cerca de 1 KB; é a escolha do `flush_now` do `.plot`, e o arquivo precisa existir quando uma nova abertura o ler); um disco lento pediria uma fila como a dos gráficos, que esta spec não desenha.
   - `StructureWindow` **não** conhece o arquivo: uma janela criada sem o controlador (o helper `Windows`, scripts) não grava nada.
3. Abrir e fechar **sem mexer em nada** não cria o arquivo e, havendo um, o deixa **idêntico byte a byte** (nem `mtime`).
4. Duas janelas do mesmo arquivo: cada uma restaura o que o arquivo tinha quando abriu; **vale a última a fechar** (a sua sessão troca a seção). Documentado, não impedido.
5. **"Restaurar padrões" (spec 46, R6).** `StructureCanvas.restore_defaults` deixa `dirty = False` e `restored = True` (a troca das opções chama `refresh_options`, que marcaria `dirty`: o método o desfaz no fim). Ao fechar, `_on_closed` decide por esta ordem: (a) `dirty` → `write_session` (o usuário mudou algo **depois** de restaurar: vale a sessão nova, relativa aos padrões); (b) senão, `restored` → `remove_session(pasta, nome)` (a seção da janela some; o arquivo some se era a única); (c) senão, nada. Um aviso de qualquer um vai para o toast, como na gravação. A remoção é **ao fechar**, não no clique, como toda gravação desta spec: restaurar e fechar deixa a próxima abertura nos padrões; restaurar, mudar algo e fechar grava o novo estado.
6. **Testes** (`tests/test_structure3d_session.py`): abrir → mudar raio, estilo, cor de uma espécie, zoom e clicar um botão de "Rotação" → fechar → o `view3d.plot` tem a seção com os valores (`read_plot_file`) e reabrir os restaura (câmera e painel); abrir e fechar sem tocar → nenhum arquivo; abrir, só clicar em átomos e medir → nenhum arquivo; reabrir um arquivo salvo, não mudar nada, fechar → bytes e `mtime_ns` iguais; reabrir, apertar R, fechar → a seção tem a câmera reenquadrada (o botão e a tecla contam); abrir a seção "Célula" do painel não grava; **renomear a pasta com a janela aberta** (`core/file_ops.rename_item`) e fechar → toast "A pasta … não existe mais …" e o caminho antigo **continua inexistente**; pasta sem permissão de escrita → toast e a janela fecha igual; `main_window.close()` com uma janela alterada grava o arquivo (o caminho de `close_dialogs`); uma `StructureWindow` do helper `Windows` fechada sobre uma fixture não deixa nada em `tests/fixtures/` (`test_fixtures_untouched.py`); **restaurar padrões** (`ask_restore` trocado, resposta Sim): numa janela aberta de uma sessão salva, restaurar e fechar remove a seção, e reabrir dá os padrões; com duas seções (dois inputs), só a da janela some e a outra fica byte a byte igual; com uma só, o arquivo some; restaurar, mudar o raio e fechar grava a seção com o raio novo e o resto nos padrões; restaurar numa janela sem arquivo e fechar não cria nada; restaurar com a resposta Não deixa o arquivo como estava; restaurar com a pasta renomeada não recria nada (`not antiga.exists()`).

### R4: Uma seção por arquivo

1. A chave da seção é o **nome do arquivo** (`scf.in`), não o caminho: o arquivo está, por definição, na pasta do seu `view3d.plot`, então a pasta movida ou renomeada leva as sessões junto.
2. Vários inputs na mesma pasta → várias seções no mesmo `view3d.plot`; abrir e fechar um nunca muda o de outro (`write_session` troca só a sua chave).
3. O mesmo nome em outra pasta → outro `view3d.plot`; nada é compartilhado entre pastas.
4. Um arquivo renomeado no Lain começa com os padrões (a seção antiga fica, inofensiva); as seções nunca são podadas.
5. **Testes** (`tests/test_structure3d_session.py`): dois inputs na mesma pasta (`si.scf.in` e uma cópia `si.scf2.in`) com raio, cor e zoom diferentes, fechados em sequência, e reabertos: cada um volta com os seus, e o arquivo tem as duas chaves; fechar um terceiro e depois alterar o primeiro deixa a seção do segundo igual; o mesmo nome em outra pasta não encontra seção; um nome com ponto e espaço (`cálculo 2.in`) faz a ida e volta; a seção de um arquivo que não existe mais permanece.

## Fora de escopo

- Gravar as **medidas**, o átomo atual, o tamanho e a posição da janela e a rolagem do painel: as medidas são resultado de cliques (spec 44) e o pedido fala de configurações; o estado aberto/fechado das seções do painel já é QSettings (spec 43).
- Gravar **enquanto a janela está aberta** (autosave com atraso, como o `.plot` dos gráficos) e a fila de gravação em worker: só no fechamento. Se o Lain cair, a vista da sessão se perde.
- O botão "Restaurar padrões" em si (rodapé do painel, pergunta, o que volta): spec 46, R6. Aqui só o que ele faz com o arquivo (R3.5). Apagar o `view3d.plot` à mão continua voltando tudo ao padrão, como diz o cabeçalho.
- Seguir o arquivo renomeado (migrar a seção) e podar seções de arquivos que sumiram.
- Impedir renomear uma pasta com uma janela 3D aberta (o bloqueio do `RenameController` é para trabalho em andamento): a gravação falha com aviso e nada é recriado.
- Gravar por estrutura em vez de por arquivo (dois arquivos iguais são duas seções).
- Sincronizar `view3d.plot` com o cluster: `*.plot` já não sobe e nenhum pull o toca.

## Decisões assumidas (confirmar na revisão)

1. **As medidas não são gravadas** (a que o usuário mais provavelmente quer rever): são resultado de cliques, não configuração, e a spec 44 as deixou fora. Gravá-las é uma extensão pequena: a sessão ganha `measures: [{kind, atoms: [[índice, [i, j, k]], …]}]` e a `MeasuresSection` as refaz ao abrir.
2. **Grava só ao fechar, na thread da GUI, e só se algo mudou** ("written only after a user edit", como o `.plot` dos gráficos): abrir uma estrutura para olhar não deixa arquivos em todas as pastas.
3. **A chave da seção é o nome do arquivo** (`scf.in`); renomear o arquivo começa de novo.
4. **As espécies vão pelo rótulo**, não pelo índice, para uma mudança na ordem de `ATOMIC_SPECIES` não trocar as cores.
5. **Um `view3d.plot` ilegível ou de outra versão é substituído** na primeira gravação, como o `write_plot_file` faz com um `.plot`; só o visualizador 3D escreve esse arquivo. O aviso aparece ao abrir.
6. **O fundo gravado vence o tema do app** (`claro` salvo e tema escuro: abre claro); sem sessão, o tema, como hoje.
7. **Duas janelas do mesmo arquivo: vale a última a fechar.**
8. **A câmera guarda a rotação, o zoom (px/Å), o deslocamento (px) e a distância focal**, não o enquadramento: um tamanho de janela diferente mostra a estrutura do mesmo tamanho e centrada como antes.
9. **"Restaurar padrões" apaga a seção ao fechar**, não no clique: coerente com "grava só ao fechar" e sem escrita extra na thread da GUI; o dos gráficos apaga na hora (`PlotSettingsStore.delete`), a diferença é só quando. Se o Lain cair entre o clique e o fechamento, a seção antiga fica.

## Notas de implementação

- **Ordem:** depois da spec 46 (os campos `show_abc`, `show_xyz`, `abc_width`, `xyz_width`, `label_size` e `rotate_structure` são dela).
- Novos: `src/qe_studio/core/structure3d/view_state.py`, `src/qe_studio/core/structure3d/view_file.py`, `tests/test_structure3d_view_file.py`, `tests/test_structure3d_session.py`.
- Alterados: `ui/structure3d_controller.py` (`load_view`, restaurar, `_on_closed` grava), `ui/widgets/structure3d/window.py` (`options`, `camera`, `view_session()`; o docstring), `ui/widgets/structure3d/canvas.py` (`dirty`, `restore_camera`; o `restore_defaults` da 46 acerta `dirty` e `restored`), `core/structure3d/options.py` (docstring), `tests/test_architecture.py` (`QT_FREE`: `qe_studio.core.structure3d.view_state` e `view_file`), `tests/test_properties.py`; `tests/test_structure3d_ui.py` só se algum teste de hoje depender do "nada é gravado".
- Limites (`wc -l`, conferido): `structure3d_controller.py` 109 → ≈ 170; `canvas.py` 343 (+ ≈ 25, fora o que a 46 acrescenta); `window.py` 154 (+ ≈ 20, fora a 46). Nenhum passa de 450; `ui/main_window.py` (450/450) **não muda**: `for_window` já leva `config` e `settings`.
- `FS_ALLOWED`: a `ui/` não ganha chamada de disco (a leitura é do worker, a escrita é `core`).
- Documentação ao implementar: a seção "Visualização 3D" do `CLAUDE.md` (a linha da janela que diz "nothing is saved" passa a descrever `view3d.plot`, `view_state`, `view_file`, o sinal `dirty` e a regra de quem grava), o parágrafo da "Visualização 3D" do `README.md` ("os ajustes da vista ficam em `view3d.plot`, na pasta do cálculo, uma seção por arquivo") e o exemplo do formato; o "Fora de escopo" da spec 43 sobre lembrar as configurações fica superado (os arquivos de `Archived/` não se reescrevem).

## Critérios de aceite e testes

- [ ] Com `view3d.plot` ausente, a janela abre como hoje: `test_structure3d_ui.py`, `test_structure3d_canvas.py`, `test_structure3d_panel.py` e `test_structure3d_render.py` passam sem mudar valores esperados.
- [ ] Ida e volta de todas as opções e da câmera, espécies por rótulo, valores inválidos descartados um a um (`test_structure3d_view_file.py`, novo; `test_properties.py`).
- [ ] Mudar a vista, fechar e reabrir restaura opções, painel, zoom, deslocamento e rotação, sem reenquadrar (`test_structure3d_session.py`, novo).
- [ ] Abrir e fechar sem mudar não cria nem reescreve o arquivo (`test_structure3d_session.py`).
- [ ] Dois inputs da mesma pasta têm seções independentes e as outras seções não mudam ao gravar uma (`test_structure3d_session.py`, `test_structure3d_view_file.py`).
- [ ] Pasta renomeada ou sem permissão: aviso e nenhuma pasta recriada (`test_structure3d_session.py`, `test_structure3d_view_file.py`).
- [ ] "Restaurar padrões" + fechar remove só a seção da janela (e o arquivo, se era a única); restaurar e mudar algo grava o estado novo (`test_structure3d_session.py`, `test_structure3d_view_file.py`).
- [ ] `test_fixtures_untouched.py` e `test_architecture.py` verdes (`QT_FREE`, `FS_ALLOWED` sem entrada nova, nenhum arquivo acima do limite).
- [ ] Passo manual de aceite: o usuário abre dois `scf` da mesma pasta, ajusta cada um de um jeito (zoom, rotação, cores), fecha o Lain, abre de novo e confere que cada janela volta como ficou; abre o `view3d.plot` no visualizador de texto e vê duas seções com o nome dos arquivos.
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py` e a suíte `-m "not realdata and not perf"` verdes.
