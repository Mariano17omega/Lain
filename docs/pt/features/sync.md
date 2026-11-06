# Sincronização

Menu *Cluster*: **Sincronizar pasta selecionada**, **Sincronizar tudo**, **Enviar ao cluster**, **Testar conexão** e
**Ver arquivos do cluster** ([modo cluster](../remote-mode.md)).

- **Baixar (pull)**: `rsync` em *dry run*, prévia (novos, atualizações, tamanhos, arquivos grandes) e só então a
  cópia, com diálogo de progresso cancelável. Conflitos perguntam arquivo a arquivo.
- **Enviar (push)**: só adiciona arquivos que o cluster não tem; nunca sobrescreve ou apaga; sempre com prévia.
- **Comparação**: `sync.checksum: true` compara conteúdo; `false`, data e tamanho.
- **Exclusões**: `sync.exclude` (`tmp/`, `*.save/`, `*.wfc*`…) mais as fixas (`.lain/`, `tmp_remote/`, `trash/` na raiz).
- Um LED mostra o alcance do cluster (`status_poll_seconds`); ao lado, seus jobs ("Executando: nome"). Clique para
  abrir a fila inteira (barras verde = rodando, âmbar = esperando; botão ✕ nos seus jobs em espera).

Detalhes e diagramas: [Modo remoto](../remote-mode.md). Código: `core/sync/`, `ui/cluster/`.
