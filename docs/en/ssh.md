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

## What the installer does, and how to undo it

### What `install.sh` changes

Its ssh step never asks for your password or stores it: you type it to `ssh` itself. Each action asks first, and the
default answer is no. A step you skip is printed at the end, so you can run it later.

With `auth: key`, there are three questions:

1. **Create the key**, only if there is none at `cluster.key_path`. It runs `ssh-keygen -t ed25519`. A key that already
   exists is used as it is.
2. **Copy the public key to the cluster.** It runs `ssh-copy-id`, or an equivalent `ssh` command in Git Bash, which has
   no `ssh-copy-id`. One line is added to `~/.ssh/authorized_keys` on the cluster, and the lines already there do not
   change.
3. **Test the login**, with `ssh ... true`, which does nothing on the cluster.

With `auth: password`, there is one question: a test login, in which you type the password.

In both cases, the first login makes `ssh` ask whether you trust the cluster, and it records the answer in
`~/.ssh/known_hosts`. Lain needs that, as it refuses unknown hosts.

| Where | What changes | When |
|---|---|---|
| Your computer | `~/.ssh/id_ed25519` and `~/.ssh/id_ed25519.pub` | If you accepted creating the key |
| Your computer | One line in `~/.ssh/known_hosts` | At the first login |
| Your computer | `cluster.auth` and `cluster.key_path` in `config.yaml` | In the configuration questions |
| Cluster | One line in `~/.ssh/authorized_keys` | If you accepted copying the key |

The login without a password works because the two halves meet: the cluster has the public key, and your computer
proves it has the private one. Removing either half makes `ssh` ask for the password again.

### Doing the same by hand

Replace the user, the host and the port with yours:

```bash
# 1. Create the key. Skip this if the file exists: never overwrite a key.
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# 2. Copy the public key to the cluster. It asks for your cluster password.
ssh-copy-id -i ~/.ssh/id_ed25519.pub -p 22 your_user@cluster.example.org

# In Git Bash, which has no ssh-copy-id:
ssh -p 22 your_user@cluster.example.org \
  'umask 077; mkdir -p ~/.ssh && echo >> ~/.ssh/authorized_keys && cat >> ~/.ssh/authorized_keys' < ~/.ssh/id_ed25519.pub

# 3. Test it, using only this key. It must not ask for the cluster password.
ssh -p 22 -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes your_user@cluster.example.org true
```

Then set `auth: key` and `key_path` in `config.yaml`, as in [With a key](#with-a-key-auth-key-recommended).

### Going back to the password

This works the same whether the key was set up by the installer or by hand. **Renaming the key on your computer is
enough, and it does not touch the cluster.**

**With `uninstall.sh`:** when Lain logs in with a key, the script explains the change and asks whether to rename it
(default no). It never connects to the cluster and never deletes the key.

**By hand:**

```bash
ssh-add -d ~/.ssh/id_ed25519     # only if the key is loaded in ssh-agent
mv ~/.ssh/id_ed25519     ~/.ssh/id_ed25519.lain-disabled
mv ~/.ssh/id_ed25519.pub ~/.ssh/id_ed25519.pub.lain-disabled
ssh -p 22 your_user@cluster.example.org   # must ask for your password
```

If you keep using Lain, also set `auth: password` in `config.yaml` (see [With a password](#with-a-password-auth-password)).

Before you rename it:

- Be sure you know your cluster password. If it does not work, rename the key back to log in again.
- Anything else that uses this key (GitHub, other servers) stops working until you rename it back.
- If another key of yours is also authorized on the cluster, `ssh` may still log in without a password.

To use the key again, rename it back:

```bash
mv ~/.ssh/id_ed25519.lain-disabled     ~/.ssh/id_ed25519
mv ~/.ssh/id_ed25519.pub.lain-disabled ~/.ssh/id_ed25519.pub
```

### Other things you can undo

**Forget the cluster's identity** on your computer. Lain will refuse the cluster until you log in once by hand again:

```bash
ssh-keygen -R cluster.example.org            # port 22
ssh-keygen -R '[cluster.example.org]:2222'   # any other port
```

**Delete the key for good**, only if you are sure nothing else uses it. This cannot be undone:

```bash
rm ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
```

**Remove the public key from the cluster.** You do not need this to go back to the password: the line has no effect
without the private key. Neither Lain nor its scripts ever do this. If you want it gone, do it by hand and with care:
on many clusters this file also holds the key the nodes use to reach each other for MPI and the job queue, and a wrong
edit can stop your jobs or lock you out. Keep a session open while you edit, and ask the cluster's administrator if you
are not sure.

```bash
cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak   # on the cluster, first
```

Then open `~/.ssh/authorized_keys` in an editor and delete only the line identical to your `id_ed25519.pub`.

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
