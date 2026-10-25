# Spec 61: `config.yaml` do Lain em qualquer terminal e pasta de dados portátil (`paths.data`)

| | |
|---|---|
| **Prioridade** | 61, a primeira da rodada: R1 é um defeito do uso diário (no terminal, fora da pasta do projeto, o Lain abre sem o `config.yaml`, em português e com a raiz padrão) e pode sair sozinho, antes de tudo |
| **Status** | Rascunho para revisão |
| **Depende de** | spec 18 (primeira execução: `LoadedConfig.first_run`, "Criar config…"), spec 48 (`project_data.fallback_folder`, que usa `data_dir()`), spec 27-3 (`lain.lock` em `data_dir()`), spec 60 (`startup_language` lê o `config.yaml` antes da janela) |
| **Usada por** | nenhuma |
| **Esforço** | M (R1: P; R2: M) |
| **Modelo recomendado** | **Opus 5.5** (`claude-opus-5-5`): muda a ordem da partida (`QSettings` passa a nascer depois do `config.yaml`) e o `data_dir()`, lido por quatro módulos, e precisa isolar os testes do `config.yaml` real da máquina |

## Itens de origem (`Ideias.md`, 25/10/2026)

> - Quero quem em 'config.yaml' tem a opção de adicionar em 'paths' um caminho para a pasta 'data', para o usuario definir onde os arquivos de configuração do Lain serão salvos, tipo uma alternativa para os caminhos padrões tipo '~/.config/qe-studio/' de forma que se o usuario copiar a pasta, todas as configurações, incluindo as que foram salvas no 'data' sejam levadas junto.
> - Quando inicio o app pelo menu iniciar, é carregado pelo 'config.yaml', no terminal não carrega o arquivo de configurações.
> - Quando inicio pelo terminal, digitando 'lain' no terminal, fora da pasta do projeto, o programa inicia sem sem o 'config.yaml'.
> - Quero poder iniciar o programa em qualquer terminal, sempre lendo o arquivo 'config.yaml' que fica na raiz do projeto lain.

Interpretação: "a raiz do projeto lain" é a pasta do repositório de onde o Lain roda (o checkout, onde estão `pyproject.toml` e o
`config.yaml` git-ignorado), não a `paths.local_root` dos cálculos. "Os arquivos de configuração do Lain" que o `config.yaml` não
guarda são o estado da interface (o `QSettings`) e a pasta de dados do app (`data_dir()`); "copiar a pasta" é copiar a pasta que tem o
`config.yaml` e a `data` ao lado dele.

## Situação atual

- **R1 (`config.yaml` no terminal).** `core/config.py:286` `find_config` procura, nesta ordem, `--config`, `$QE_STUDIO_CONFIG`,
  `<cwd>/config.yaml` e `user_config_path()` (`:278`, `~/.config/qe-studio/config.yaml`); `:301` é o único passo que depende de onde o
  programa foi aberto. O comando `lain` desta máquina é a instalação editável do uv (`~/.local/bin/lain` →
  `~/.local/share/uv/tools/lain/`, recibo `~/.local/share/uv/tools/lain/uv-receipt.toml` com `editable = "/home/m/Projetos/Lain"`), e `~/.config/qe-studio/` só tem o
  `QE Studio.conf` do `QSettings`: não há `config.yaml` lá. Reproduzido com o Python da ferramenta: `find_config(None, environ, Path("/tmp"))`
  devolve `None`; com `cwd` = o checkout devolve `/home/m/Projetos/Lain/config.yaml`. O mesmo vale para o idioma: `core/language.py:64`
  (`startup_language`) chama `find_config(cli_path, environ)` com o `cwd` real, e de `/tmp` devolve `pt_BR` (o sistema), embora o
  `config.yaml` do checkout tenha `ui.language: en`.
  - Pelo menu funciona porque o lançador instalado (`~/.local/share/applications/lain.desktop`) tem `Path=/home/m/Projetos/Lain`: o
    `cwd` do processo é o checkout. Esse `Path=` vem de uma alteração **ainda não commitada** do usuário em
    `scripts/install_desktop.py` (`launcher_text`, com teste em `tests/test_install_desktop.py`); o `packaging/lain.desktop` do
    repositório não tem `Path=`.
  - O `README.md:48-49` hoje manda guardar o config em `~/.config/qe-studio/config.yaml` fora do repositório; `README.md:62-65` e o
    cabeçalho dos dois `config.example.yaml` (`:2-3`) listam a ordem de busca.
  - O pacote sabe onde está: `Path(qe_studio.__file__).resolve()` é `/home/m/Projetos/Lain/src/qe_studio/__init__.py` (verificado com o
    Python da ferramenta); `parents[2]` é o checkout e tem `pyproject.toml` (`name = "lain"`). Numa instalação não editável o pacote
    fica em `site-packages` e não há checkout.
  - Testes que quebrariam **nesta máquina** com um passo novo que acha o checkout (a CI não tem `config.yaml`): `tests/test_config.py:55`
    (`test_search_order` espera `None` no fim), `tests/test_first_run.py:33` (`load_config(None)` com `chdir` para uma pasta vazia espera
    `first_run`) e `tests/test_i18n_closing.py:109` (`run_help` roda `python -m qe_studio --help` com `cwd` temporário e herda o
    `os.environ`; `test_entry_point_language_auto_follows_the_system` acharia o `ui.language: en` do checkout).
- **R2 (pasta de dados).** Fora do `config.yaml` e da pasta `.lain/` da raiz (spec 48), o Lain grava em três lugares do usuário:
  - o `QSettings` (geometria, larguras dos painéis, tema, última pasta, projeto, seções abertas, modo do "Criar cálculo",
    Markdown…): `ui/app.py:151` cria `QSettings()` com os nomes de `ui/app_identity.py` (`ORGANIZATION_NAME = "qe-studio"`,
    `APPLICATION_NAME = "QE Studio"`), isto é `~/.config/qe-studio/QE Studio.conf`. É criado **antes** do `load_config` (`:153`), e o
    tema é lido dele em seguida (`:159`);
  - `core/appdirs.py:15` `data_dir()` (`~/.local/share/qe-studio`): `lock_path()` (`:34`, `lain.lock`), o fallback das configurações de
    uma raiz somente leitura (`core/project_data.py:57`, `roots/<hash>`), o caminho de uma store antes de haver raiz e os arquivos
    antigos que a spec 48 importa (`project_data.py:99` e `:113`), "Abrir pasta de dados" (`ui/help_controller.py:111`) e a linha
    "Dados" do "Sobre" (`:131`). Nesta máquina a pasta está vazia (o `lain.lock` some quando o Lain fecha);
  - `cache_dir()` (`appdirs.py:23`, `~/.cache/qe-studio`): o log, o QSS compilado e o `askpass.sh`. É cache, não configuração.
  - Não existe chave para mudar nenhum dos três: `PathsConfig` (`core/config.py:84`) tem `local_root`, `remote_root` e `xcrysden_path`.
- Tamanhos: `core/config.py` 430 linhas, `core/appdirs.py` 94, `ui/app.py` 177, `ui/help_controller.py` 139,
  `ui/main_window.py` 449/450.

## Requisitos

### R1: o `config.yaml` do checkout vale em qualquer terminal

1. `core/config.py`: nova `checkout_dir() -> Path | None`: a pasta do repositório de onde o pacote roda, isto é
   `Path(qe_studio.__file__).resolve().parents[2]` quando `parents[1].name == "src"` e essa pasta tem `pyproject.toml`; `None` numa
   instalação não editável. Lê `os.environ` (não o `environ` recebido pelas funções): com `QE_STUDIO_NO_CHECKOUT_CONFIG` definido e não
   vazio, devolve `None`.
2. `find_config` ganha o passo do checkout **depois** do `./config.yaml` e antes do `user_config_path()`. Ordem nova: `--config`,
   `$QE_STUDIO_CONFIG`, `./config.yaml`, `<checkout>/config.yaml`, `~/.config/qe-studio/config.yaml`. Assinatura:
   `find_config(cli_path=None, environ=None, cwd=None, checkout: Path | None = None)`; `checkout=None` usa `checkout_dir()`. Um `cwd` que
   já é o checkout não acha o mesmo arquivo duas vezes (é o mesmo caminho, devolvido no passo do `cwd`).
3. `startup_language` (`core/language.py:54`) não muda de código: chama `find_config`, então o idioma do `config.yaml` do checkout passa a
   valer no terminal também.
4. A primeira execução não muda: sem nenhum `config.yaml`, "Criar config…" continua criando em `user_config_path()`.
5. **Testes isolados:** `tests/conftest.py` define `os.environ["QE_STUDIO_NO_CHECKOUT_CONFIG"] = "1"` no topo, junto do
   `QE_STUDIO_LANGUAGE` (os subprocessos de `test_i18n_closing.py` e do `i18n_probe.py` herdam). Os testes do passo novo passam
   `checkout=` explícito ou removem a variável com `monkeypatch.delenv`.
6. `scripts/install_desktop.py`: a alteração não commitada do usuário (`Path=` no lançador) continua válida e não é exigida por esta spec;
   o `Path=` deixa de ser necessário para achar o config. Não mexer nela.
7. **Testes:**
   - `tests/test_config.py::test_search_order` estendido: com um `config.yaml` num checkout falso (`checkout=tmp_path / "repo"`), o
     `cwd` vence o checkout, o checkout vence o do usuário; sem nenhum, `None`.
   - `test_checkout_dir_finds_the_source_tree`: com a variável removida, `checkout_dir()` é a pasta que tem `pyproject.toml` e `src/qe_studio`
     (o próprio repositório dos testes); com `QE_STUDIO_NO_CHECKOUT_CONFIG=1`, `None`.
   - `test_checkout_dir_is_none_outside_a_source_tree`: `checkout_dir` com `qe_studio.__file__` trocado (monkeypatch) por um caminho de
     `site-packages` devolve `None`.
   - `tests/test_language.py`: `startup_language(None, {}, "pt_BR")` com `cwd` vazio e `checkout=` apontando para um config com
     `ui.language: en` dá `en` (falha hoje: o passo não existe).
   - `test_first_run.py`, `test_i18n_closing.py` e `test_search_order` continuam verdes **nesta máquina**, que tem
     `/home/m/Projetos/Lain/config.yaml` (passo manual de aceite: rodar a suíte com o `config.yaml` presente).

### R2: `paths.data`, a pasta de dados do Lain

1. `core/config.py:PathsConfig` ganha `data: Path | None = None`. Vazio (`""`) ou ausente: `None`, o comportamento de hoje. `~` e
   variáveis de ambiente são expandidos (como `local_root`). **Relativo** é relativo à pasta do `config.yaml` que o define: `parse_config`
   (`:358`, que já recebe o `path`) o torna absoluto; um config sem arquivo (`path=None`) mantém `None`.
2. O que vai para `paths.data` quando definida:
   - o `QSettings`, num arquivo `settings.ini` (`QSettings(str(<data>/settings.ini), QSettings.Format.IniFormat)`), com as mesmas chaves
     de hoje;
   - tudo o que hoje é `data_dir()`: `lain.lock`, `roots/<hash>` (fallback da spec 48) e o caminho de uma store antes de ter raiz.
   **Não vão:** o próprio `config.yaml`, a `.lain/` da raiz (já viaja com a raiz, spec 48), os `.plot`, e o `cache_dir()` (log, QSS
   compilado, `askpass.sh`: cache que se refaz).
3. `core/appdirs.py`: `default_data_dir()` (a regra XDG de hoje, renomeada), `set_data_dir(path: Path | None) -> str | None` (fixa a pasta
   do processo; cria a pasta e confere que é gravável; quando não dá, não fixa nada e devolve o aviso), `data_dir()` (a fixada, senão a
   padrão) e `settings_file() -> Path | None` (`<data>/settings.ini` quando há pasta fixada, senão `None`). `StoreFile.legacy`
   (`project_data.py:113`) passa a usar `default_data_dir()`: os arquivos anteriores à spec 48 estão lá, não na pasta nova.
4. `ui/app.py:main`: a ordem passa a ser `load_config` → `set_data_dir(loaded.config.paths.data)` → `QSettings` (o de `settings_file()`,
   ou o `QSettings()` de hoje quando é `None`) → tema → `claim_instance(lock_path())`. O aviso de `set_data_dir` entra no começo de
   `loaded.warnings` (aparece no rodapé e no log, como os outros). Um `ConfigError` continua parando antes de tudo, como hoje.
5. **Migração, uma vez, copiando:** ao abrir um `settings.ini` sem nenhuma chave, as chaves do `QSettings()` padrão são copiadas para ele
   (o arquivo antigo fica intacto, como na spec 48); o log diz de onde para onde. A pasta `data_dir()` antiga não é copiada (hoje só tem
   o `lain.lock` e, se houver, `roots/`: decisão 3).
6. Texto exato do aviso (português, em `_()`): "A pasta de dados {folder} não pode ser usada ({error}); usando {default}." (`{error}` é o
   `strerror`, ou "não é uma pasta"/"não é gravável").
7. **"Recarregar config.yaml"** com outra `paths.data`: a sessão continua com a pasta em uso; toast "A pasta de dados muda ao reiniciar o
   Lain.". Novo `ui/restart_notice.py:restart_notices(config) -> str` junta esse texto ao de `ui/language.py:restart_notice` (que fica como
   está: o `i18n_probe.py` o usa); `ui/main_window.py:43` e `:425` trocam o import e a chamada, sem linha nova.
8. "Sobre" (`help_controller.py:131`): a linha "Dados" já segue `data_dir()`; nova linha "Configurações da interface" com o caminho do
   arquivo do `QSettings` em uso (`settings.fileName()`). "Abrir pasta de dados" abre a pasta em uso.
9. Os dois `config.example.yaml` (raiz e `src/qe_studio/resources/`, idênticos): `data: ""` em `paths:`, com o comentário "Pasta dos dados
   do Lain (estado da interface, trava de instância). Relativa a este arquivo; vazia: os lugares padrão do sistema." (em inglês, como os
   outros comentários do arquivo) e o exemplo `# data: data`. O cabeçalho dos dois passa a listar o passo do checkout.
10. `.gitignore`: `/data/` (uma `paths.data: data` no checkout não aparece no `git status`).
11. **Testes** (`tests/test_data_dir.py`, novo, e `tests/test_config.py`):
    - `test_data_is_unset_by_default_and_documented`: `AppConfig().paths.data is None`; a chave está nos dois exemplos.
    - `test_relative_data_is_relative_to_the_config_file`: `data: dados` num config em `<tmp>/a/config.yaml` vira `<tmp>/a/dados`; `~` e
      `$VAR` expandidos; `""` é `None`.
    - `test_set_data_dir_moves_lock_and_fallback`: depois de `set_data_dir(p)`, `lock_path()` e `fallback_folder(root)` estão em `p`, e
      `settings_file() == p / "settings.ini"`; `set_data_dir(None)` volta ao padrão (fixture autouse do `conftest.py` zera a pasta fixada).
    - `test_unusable_data_dir_falls_back_with_a_warning`: `p` é um arquivo / uma pasta sem escrita (`chmod`): nada é fixado e o aviso
      tem o caminho.
    - `test_settings_are_copied_once`: um `QSettings` padrão com `ui/theme=light` (XDG temporário do conftest); o primeiro
      `open_settings` copia, o segundo não sobrescreve uma chave mudada depois.
    - `test_copying_the_folder_takes_the_settings`: `config.yaml` com `paths.data: data` e `ui/theme=light` gravado em
      `data/settings.ini`; a pasta inteira copiada (`shutil.copytree`) para outro lugar, `load_config(<cópia>/config.yaml)` →
      `set_data_dir` → `open_settings` lê `light` do arquivo da cópia, não do original.
    - `test_reload_with_another_data_dir_tells_to_restart`: `restart_notices` devolve o texto do R2.7 e nada quando a pasta é a mesma.

## Fora de escopo

- Criar o `config.yaml` no checkout pela primeira execução ("Criar config…" segue em `~/.config/qe-studio/`): outra spec, se o usuário
  quiser.
- Mover o log e o cache para `paths.data`: são cache (decisão 2).
- Trocar a pasta de dados com o Lain aberto: só ao reiniciar (R2.7).
- Uma instalação não editável (`uv tool install .` sem `--editable`) não acha o checkout: o README diz para usar `--config`,
  `$QE_STUDIO_CONFIG` ou `~/.config/qe-studio/config.yaml` nesse caso.

## Decisões assumidas (confirmar na revisão)

1. **`./config.yaml` continua antes do checkout.** Um `config.yaml` na pasta onde o terminal está vence o do checkout; "sempre" do
   pedido vale para qualquer pasta sem `config.yaml` próprio. A alternativa (checkout primeiro) impediria testar um config de outra pasta
   sem `--config`.
2. **O que é "configuração":** o `QSettings` e o `data_dir()`. O log e o QSS compilado ficam em `~/.cache/qe-studio` (são refeitos), e a
   `.lain/` fica na raiz (spec 48).
3. **Migração só do `QSettings`.** O `data_dir()` antigo não é copiado: nesta máquina ele está vazio; um `roots/<hash>` antigo continua
   onde está (o Lain não o acha mais com `paths.data` definida; mover à mão).
4. **Nome do arquivo:** `settings.ini` (formato INI do Qt, o mesmo do `QE Studio.conf` de hoje no Linux).
5. **Variável `QE_STUDIO_NO_CHECKOUT_CONFIG`** só para testes e para quem não quer o passo novo; segue o prefixo antigo de propósito
   (`CLAUDE.md`, "Old internal names").
6. **Relativo ao `config.yaml`**, não ao `cwd`: é o que faz a pasta copiada funcionar em qualquer lugar.

## Notas de implementação

- Novos: `ui/restart_notice.py` (novo); `tests/test_data_dir.py` (novo).
- Alterados: `core/config.py` (`checkout_dir`, passo do `find_config`, `PathsConfig.data`, resolução relativa em `parse_config`);
  `core/appdirs.py` (`default_data_dir`, `set_data_dir`, `settings_file`); `core/project_data.py:113` (`legacy` em `default_data_dir()`);
  `ui/app.py` (ordem da partida, `open_settings` com a cópia única); `ui/help_controller.py` (linha do "Sobre"); `ui/main_window.py:43,425`
  (import e chamada, sem linha nova); `tests/conftest.py` (variável e fixture que zera `set_data_dir`); os dois `config.example.yaml`;
  `.gitignore`.
- Limites: `core/config.py` 430 → cerca de 465; `ui/main_window.py` fica em 449/450.
- O `ui/` não ganha chamada de disco: a criação e o teste de escrita da pasta ficam em `core/appdirs.py`; o `QSettings` lê o arquivo
  sozinho.
- Documentação ao implementar: `README.md` (ordem de busca com o checkout; troca de `README.md:48-49`; seção nova "Dados portáteis" com
  `paths.data`); cabeçalho dos `config.example.yaml`; `CLAUDE.md`, seção "Config" (a ordem de busca ganha o checkout) e "Where state lives"
  (o `QSettings` pode estar em `paths.data`).
- i18n: textos novos em `_()`, depois `scripts/i18n.py update`, tradução e `compile`.

## Critérios de aceite e testes

- [ ] Sem `paths.data` e com o `config.yaml` no `cwd`, nada muda: `test_config.py`, `test_first_run.py`, `test_language.py` e
      `test_i18n_closing.py` passam sem alteração de expectativa (só o `test_search_order` ganha os passos novos).
- [ ] `lain` aberto de `/tmp` lê o `config.yaml` do checkout, idioma incluído (`test_search_order`, `test_language.py`; passo manual: `cd /tmp
      && lain` abre em inglês com a raiz do config).
- [ ] A suíte inteira passa nesta máquina com `/home/m/Projetos/Lain/config.yaml` presente (variável do `conftest.py`).
- [ ] `paths.data` relativa ao config, expandida, vazia = `None` (`test_relative_data_is_relative_to_the_config_file`).
- [ ] `QSettings`, `lain.lock` e `roots/` vão para a pasta (`test_set_data_dir_moves_lock_and_fallback`); cópia única do `QSettings`
      antigo (`test_settings_are_copied_once`); pasta copiada leva o estado (`test_copying_the_folder_takes_the_settings`).
- [ ] Pasta inutilizável: aviso e lugares padrão (`test_unusable_data_dir_falls_back_with_a_warning`).
- [ ] Recarregar com outra pasta avisa que muda ao reiniciar (`test_reload_with_another_data_dir_tells_to_restart`).
- [ ] `ruff check`, `ruff format --check`, `pyright`, `test_architecture.py`, `scripts/i18n.py check` e a suíte
      `-m "not realdata and not perf"` verdes.
