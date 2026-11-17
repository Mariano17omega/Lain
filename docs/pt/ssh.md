# Conexão SSH

O Lain fala com o cluster pelo `ssh` e `rsync` do seu sistema. Sempre de forma **não interativa**, sem terminal.

## Com chave (`auth: key`, recomendado)

Sem senha para guardar ou digitar. Configuração única:

```bash
ssh-keygen -t ed25519                  # pule se ~/.ssh/id_ed25519 já existe (nunca sobrescreva)
ssh-copy-id -i ~/.ssh/id_ed25519.pub -p 22 seu_usuario@cluster.exemplo.org
ssh -i ~/.ssh/id_ed25519 seu_usuario@cluster.exemplo.org   # deve entrar sem pedir a senha do cluster
```

O último comando também grava o cluster em `~/.ssh/known_hosts` — **obrigatório**: o Lain força
`StrictHostKeyChecking=yes` e nunca aceita chaves de host desconhecidas.

```yaml
paths:
  local_root: ~/qe_simulations
  remote_root: /home/seu_usuario/qe_simulations
cluster:
  host: cluster.exemplo.org
  port: 22
  user: seu_usuario
  auth: key
  key_path: ~/.ssh/id_ed25519
  connect_timeout: 10
```

Se a chave tem *passphrase*, carregue-a antes (o ssh roda sem terminal):

```bash
eval "$(ssh-agent -s)"     # só se nenhum agente roda
ssh-add ~/.ssh/id_ed25519
lain
```

Com `auth: key` o Lain passa `-o BatchMode=yes -i <key_path> -o IdentitiesOnly=yes`.

## Com senha (`auth: password`)

`host`, `user` e `remote_root` são obrigatórios. A senha chega ao Lain por um de três caminhos:

1. **Digitada quando pedida** (mais simples): com a variável não definida, o Lain pergunta ("Senha do cluster") no
   primeiro sync e a guarda **só na memória** da sessão.
2. **Variável de ambiente** nomeada em `password_env` (`QE_STUDIO_SSH_PASSWORD`): `export … && lain`.
3. **`password:` no config** (texto puro; desencorajado, com aviso).

A senha chega ao ssh por `SSH_ASKPASS` (`qe-studio-askpass`) no ambiente do processo filho — **nunca** na linha de
comando nem no log; `sshpass` não é necessário.

## O que o instalador faz e como desfazer

### O que o `install.sh` altera

O passo de ssh nunca pede nem guarda sua senha: você a digita para o próprio `ssh`. Cada ação pergunta antes, e o padrão
é não. Um passo pulado aparece no final, para você rodar depois.

Com `auth: key`, são três perguntas:

1. **Criar a chave**, só se não houver uma em `cluster.key_path`. Roda `ssh-keygen -t ed25519`. Uma chave que já existe é
   usada como está.
2. **Copiar a chave pública para o cluster.** Roda `ssh-copy-id`, ou um comando `ssh` equivalente no Git Bash, que não tem
   `ssh-copy-id`. Uma linha é acrescentada ao `~/.ssh/authorized_keys` do cluster, e as que já existem não mudam.
3. **Testar o login**, com `ssh ... true`, que não faz nada no cluster.

Com `auth: password`, é uma pergunta: um login de teste, em que você digita a senha.

Nos dois casos, o primeiro login faz o `ssh` perguntar se você confia no cluster, e a resposta fica no
`~/.ssh/known_hosts`. O Lain precisa disso, pois recusa servidores desconhecidos.

| Onde | O que muda | Quando |
|---|---|---|
| Seu computador | `~/.ssh/id_ed25519` e `~/.ssh/id_ed25519.pub` | Se você aceitou criar a chave |
| Seu computador | Uma linha no `~/.ssh/known_hosts` | No primeiro login |
| Seu computador | `cluster.auth` e `cluster.key_path` no `config.yaml` | Nas perguntas de configuração |
| Cluster | Uma linha no `~/.ssh/authorized_keys` | Se você aceitou copiar a chave |

O login sem senha funciona porque as duas metades se encontram: o cluster tem a chave pública e seu computador prova que
tem a privada. Basta remover uma das metades para o `ssh` voltar a pedir a senha.

### Fazer o mesmo à mão

Troque o usuário, o host e a porta pelos seus:

```bash
# 1. Crie a chave. Pule se o arquivo já existe: nunca sobrescreva uma chave.
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# 2. Copie a chave pública para o cluster. Ele pede a senha do cluster.
ssh-copy-id -i ~/.ssh/id_ed25519.pub -p 22 seu_usuario@cluster.exemplo.org

# No Git Bash, que não tem ssh-copy-id:
ssh -p 22 seu_usuario@cluster.exemplo.org \
  'umask 077; mkdir -p ~/.ssh && echo >> ~/.ssh/authorized_keys && cat >> ~/.ssh/authorized_keys' < ~/.ssh/id_ed25519.pub

# 3. Teste usando só essa chave. Não deve pedir a senha do cluster.
ssh -p 22 -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes seu_usuario@cluster.exemplo.org true
```

Depois, defina `auth: key` e `key_path` no `config.yaml`, como em [Com chave](#com-chave-auth-key-recomendado).

### Voltar a usar senha

Funciona do mesmo jeito se a chave foi configurada pelo instalador ou à mão. **Renomear a chave no seu computador basta, e
não mexe no cluster.**

**Com o `uninstall.sh`:** quando o Lain entra com chave, o script explica a mudança e pergunta se deve renomeá-la (padrão
não). Ele nunca se conecta ao cluster e nunca apaga a chave.

**À mão:**

```bash
ssh-add -d ~/.ssh/id_ed25519     # só se a chave estiver carregada no ssh-agent
mv ~/.ssh/id_ed25519     ~/.ssh/id_ed25519.lain-disabled
mv ~/.ssh/id_ed25519.pub ~/.ssh/id_ed25519.pub.lain-disabled
ssh -p 22 seu_usuario@cluster.exemplo.org   # deve pedir sua senha
```

Se você continuar usando o Lain, defina também `auth: password` no `config.yaml` (veja [Com senha](#com-senha-auth-password)).

Antes de renomear:

- Confirme que você sabe a senha do cluster. Se ela não funcionar, renomeie a chave de volta para entrar de novo.
- Tudo o que usa essa chave (GitHub, outros servidores) para de funcionar até você renomeá-la de volta.
- Se outra chave sua também estiver autorizada no cluster, o `ssh` pode continuar entrando sem senha.

Para usar a chave de novo, renomeie de volta:

```bash
mv ~/.ssh/id_ed25519.lain-disabled     ~/.ssh/id_ed25519
mv ~/.ssh/id_ed25519.pub.lain-disabled ~/.ssh/id_ed25519.pub
```

### Outras coisas que você pode desfazer

**Esquecer a identidade do cluster** no seu computador. O Lain vai recusar o cluster até você entrar uma vez à mão:

```bash
ssh-keygen -R cluster.exemplo.org            # porta 22
ssh-keygen -R '[cluster.exemplo.org]:2222'   # qualquer outra porta
```

**Apagar a chave de vez**, só se tiver certeza de que nada mais a usa. Não dá para desfazer:

```bash
rm ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
```

**Tirar a chave pública do cluster.** Isso não é necessário para voltar à senha: a linha não tem efeito sem a chave
privada. Nem o Lain nem seus scripts fazem isso. Se quiser removê-la, faça à mão e com cuidado: em muitos clusters esse
arquivo também guarda a chave que os nós usam entre si para MPI e para a fila de jobs, e uma edição errada pode parar seus
jobs ou deixar você sem acesso. Mantenha uma sessão aberta enquanto edita e, na dúvida, fale com o administrador do
cluster.

```bash
cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak   # no cluster, antes de tudo
```

Depois, abra o `~/.ssh/authorized_keys` num editor e apague só a linha idêntica ao seu `id_ed25519.pub`.

## Uma conexão para várias ações

Com `cluster.multiplex: true`, a primeira chamada vira um *master* OpenSSH (`ControlMaster=auto`,
`ControlPersist=120`) e as seguintes (fila, listagens, submeter, cancelar, apagar, rsync) reutilizam o canal, sem novo
login, até 120 s sem uso. Os sockets ficam numa pasta sua (`0700`, verificada a cada chamada); cada Lain tem seus
masters e só fecha os próprios (`ssh -O stop`). `multiplex: false` desliga.

## Teste fora do Lain

```bash
ssh -p 22 -i ~/.ssh/id_ed25519 seu_usuario@cluster.exemplo.org
```

Se falha aqui, o problema é a credencial, não o app. O menu *Cluster ▸ Testar conexão* confere o alcance.

## "Autenticação recusada pelo cluster"

O ssh chegou ao cluster e ele disse não (host/porta estão certos). Confira, em ordem:

- `user` é seu login real (não o `seu_usuario` do exemplo).
- `auth` é exatamente `key` ou `password`, aparece uma vez e não contém a senha.
- `key`: `key_path` existe e a chave pública está em `~/.ssh/authorized_keys` no cluster; chave com *passphrase*
  precisa estar no `ssh-agent`.
- `password`: a variável de `password_env` existe no ambiente que iniciou o Lain (app aberto pelo menu do desktop não
  vê variáveis exportadas em outro terminal).
- O Lain lê o config que você pensa: a linha `session: config=` do log diz qual.
