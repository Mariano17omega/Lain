# SSH connection

Lain talks to the cluster through your system's `ssh` and `rsync`, always **non-interactively**, with no terminal.

## With a key (`auth: key`, recommended)

No password to store or type. One-time setup:

```bash
ssh-keygen -t ed25519                  # skip if ~/.ssh/id_ed25519 already exists (never overwrite it)
ssh-copy-id -i ~/.ssh/id_ed25519.pub -p 22 your_user@cluster.example.org
ssh -i ~/.ssh/id_ed25519 your_user@cluster.example.org   # must log in without asking for the cluster password
```

The last command also records the cluster in `~/.ssh/known_hosts` — **required**: Lain forces
`StrictHostKeyChecking=yes` and never accepts unknown host keys.

```yaml
paths:
  local_root: ~/qe_simulations
  remote_root: /home/your_user/qe_simulations
cluster:
  host: cluster.example.org
  port: 22
  user: your_user
  auth: key
  key_path: ~/.ssh/id_ed25519
  connect_timeout: 10
```

If the key has a passphrase, load it first (ssh runs with no terminal):

```bash
eval "$(ssh-agent -s)"     # only if no agent is running
ssh-add ~/.ssh/id_ed25519
lain
```

With `auth: key` Lain passes `-o BatchMode=yes -i <key_path> -o IdentitiesOnly=yes`.

## With a password (`auth: password`)

`host`, `user` and `remote_root` are required. The password reaches Lain in one of three ways:

1. **Typed when asked** (simplest): with the variable unset, Lain asks ("Senha do cluster") at the first sync and
   keeps it **in memory only** for the session.
2. **Environment variable** named by `password_env` (`QE_STUDIO_SSH_PASSWORD`): `export … && lain`.
3. **`password:` in the config** (plain text; discouraged, with a warning).

The password reaches ssh through `SSH_ASKPASS` (`qe-studio-askpass`) in the child process environment — **never** on a
command line or in the log; `sshpass` is not needed.

## One connection for many actions

With `cluster.multiplex: true`, the first call becomes an OpenSSH *master* (`ControlMaster=auto`,
`ControlPersist=120`) and the next ones (queue, listings, submit, cancel, delete, rsync) reuse the channel with no new
login, until 120 s without use. Sockets live in a folder of your own (`0700`, checked on every call); each Lain has
its own masters and stops only those (`ssh -O stop`). `multiplex: false` turns it off.

## Test outside Lain

```bash
ssh -p 22 -i ~/.ssh/id_ed25519 your_user@cluster.example.org
```

If this fails too, the problem is the credential, not the app. *Cluster ▸ Testar conexão* checks reachability.

## "Authentication refused by the cluster"

ssh reached the cluster and it said no (host and port are right). Check, in order:

- `user` is your real login (not the `seu_usuario` placeholder of the example).
- `auth` is exactly `key` or `password`, appears once, and does not contain the password.
- `key`: `key_path` exists and its public key is in `~/.ssh/authorized_keys` on the cluster; a passphrase key must be
  in `ssh-agent`.
- `password`: the variable named by `password_env` exists in the environment that started Lain (an app launched from
  the desktop menu does not see a variable exported in another terminal).
- Lain reads the config you think: the `session: config=` line of the log says which one.
