# Instalação

## Requisitos

- **Python ≥ 3.11** e [uv](https://docs.astral.sh/uv/) (gerenciador de ambiente usado pelo projeto).
- `rsync` (≥ 3.1) e `ssh` no `PATH` — necessários só para falar com o cluster.
- Linux é o alvo principal (o app também tem caminhos para Windows no ssh/askpass).

## Script de instalação

O `install.sh` executa os passos da próxima seção em ordem e pergunta sempre que há uma escolha a fazer. As
perguntas e mensagens são em inglês. No Linux, rode num terminal. No Windows, rode no **Git Bash**, que vem com o
[Git for Windows](https://git-scm.com/download/win):

```bash
curl -fsSL https://raw.githubusercontent.com/Mariano17omega/Lain/main/install.sh | bash
# ou, de um clone:  bash install.sh
```

1. Verifica `git`, `ssh` e `rsync` (só o `git` é obrigatório) e instala o uv se ele faltar.
2. Clona o repositório (pasta padrão `~/Lain`) ou, se o Lain já estiver lá, oferece um `git pull`.
3. Copia o `config.example.yaml` para `config.yaml` e preenche com as suas respostas:

    | Chave | Padrão |
    |---|---|
    | `paths.local_root` | `LUCCI` na sua pasta Documentos: `~/Documentos/LUCCI` num Linux em português, `~/Documents/LUCCI` em inglês e no Windows (criada, depois de perguntar, se não existir) |
    | `paths.remote_root` | `~/LUCCI` |
    | `paths.xcrysden_path` | o que `$XCRYSDEN_TOPDIR` ou o `xcrysden` do `PATH` indicam; senão você digita o caminho ou deixa em branco |
    | `paths.data` | em branco (o lugar padrão do sistema) |
    | `cluster.host`, `cluster.user` | obrigatórios |
    | `cluster.port` | `22` |
    | `cluster.auth` | `key` |
    | `cluster.key_path` | `~/.ssh/id_ed25519` |
    | `jobs.myemail` | em branco (pulado) |

4. Oferece criar a chave ssh, copiá-la para o cluster e fazer um login, que faz o ssh confiar na host key do cluster
   (veja [Conexão SSH](ssh.md)). Cada passo pergunta antes, e o comando de um passo pulado aparece no final.
5. Roda `uv tool install --editable --force .` e, no Linux, oferece a entrada no menu de aplicativos.

Um `config.yaml` que já existe só muda se você confirmar, e o antigo fica em `config.yaml.bak`. Para responder às
perguntas de novo depois: `bash install.sh --config-only`. No login por senha, o script nunca pede a senha: o Lain a
lê de `QE_STUDIO_SSH_PASSWORD`. `local_root`, `key_path` e `xcrysden_path` precisam ser caminhos completos (começando
por `/` ou `~`, ou por uma letra de unidade no Windows): o Lain leria um caminho relativo a partir da pasta onde roda.

## Passo a passo

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # se ainda não tem o uv
source ~/.bashrc
git clone git@github.com:Mariano17omega/Lain.git && cd Lain
cp config.example.yaml config.yaml                 # depois edite (veja Configuração)
uv tool install --editable .                       # instala o comando `lain`
lain                                               # ou: lain --config /caminho/config.yaml
```

Opções de linha de comando: `--config PATH` (arquivo de configuração) e `--verbose` (log em `debug` também no
terminal).

### Instalação editável (padrão)

A instalação é **editável**: mudanças no código valem sem reinstalar (use `--force` depois de mudar dependências ou
*entry points*). De qualquer pasta, o `lain` lê o `config.yaml` da raiz do repositório, a menos que a pasta atual
tenha um `config.yaml` próprio — veja a [ordem de busca](config.md).

### Instalação não editável (opcional)

```bash
uv tool install .
```

Não há repositório de onde ler o config: deixe-o em `~/.config/qe-studio/config.yaml`, aponte `$QE_STUDIO_CONFIG`
para ele ou use `--config`. Mudanças no código só valem após reinstalar.

### Sem instalar (desenvolvimento)

```bash
uv sync && uv run lain
```

Roda direto do ambiente do repositório; é o que se usa para desenvolver e testar.

## Integração com o desktop (opcional)

Para o gerenciador de janelas mostrar o ícone e o menu de aplicativos listar o Lain:

```bash
uv run python scripts/install_desktop.py              # em ~/.local/share
uv run python scripts/install_desktop.py --prefix DIR # ou em outro diretório
```

Nada é instalado se você não rodar isso. Precisa do comando `lain` no `PATH`.

## XCrySDen (opcional)

"Abrir com XCrysDen" usa o [XCrySDen](http://www.xcrysden.org/) externo. Informe a pasta de instalação (ou o script
`xcrysden`) em `paths.xcrysden_path` — veja [Configuração](config.md).

## Primeira execução

Sem nenhum `config.yaml`, o Lain abre num estado de boas-vindas que explica onde colocar o arquivo. Veja o
[Início rápido](quickstart.md).
