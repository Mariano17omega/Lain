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
