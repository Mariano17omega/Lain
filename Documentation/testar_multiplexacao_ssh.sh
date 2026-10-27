#!/usr/bin/env bash
# Testa se o cluster aceita multiplexar o ssh (ControlMaster).
# Edite apenas a linha CLUSTER abaixo. O resultado vai para o arquivo de texto indicado no fim da execução.
# Só roda comandos inofensivos (true, sleep) e fecha o mestre ao terminar. Autenticação: chave, sem senha.

CLUSTER="usuario@IP_DO_CLUSTER"   # <-- edite aqui

# ---------------------------------------------------------------------------------------------

SAIDA="$(dirname "$(readlink -f "$0")")/resultado_multiplexacao_ssh_$(date +%Y%m%d_%H%M%S).txt"
SOCKET="/tmp/lain-mux-%C"
BASE=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15)
MUX=(-o "ControlPath=$SOCKET")

if [[ "$CLUSTER" == "USUARIO@IP_DO_CLUSTER" ]]; then
    echo "Edite a variável CLUSTER no início de $0 antes de rodar." >&2
    exit 1
fi

{
echo "Teste de multiplexação ssh: $(date -Is)"
echo "Destino: $CLUSTER"
echo "ssh local: $(ssh -V 2>&1)"
echo

echo "=== 1. Abrir o mestre (ControlMaster=yes, ControlPersist=120) ==="
ssh "${BASE[@]}" "${MUX[@]}" -o ControlMaster=yes -o ControlPersist=120 "$CLUSTER" true
echo "código de saída: $?"
echo

echo "=== 2. Conferir o mestre (-O check) ==="
ssh -O check "${MUX[@]}" "$CLUSTER" 2>&1
echo "código de saída: $?"
echo

echo "=== 3. Tempo de um comando pelo mestre ==="
( time ssh "${BASE[@]}" "${MUX[@]}" "$CLUSTER" true ) 2>&1
echo

echo "=== 3b. Tempo de um comando SEM multiplexação (comparação) ==="
( time ssh "${BASE[@]}" -o ControlMaster=no -o ControlPath=none "$CLUSTER" true ) 2>&1
echo

for N in 3 12; do
    echo "=== 4. $N sessões simultâneas pelo mestre (limite MaxSessions) ==="
    falhas=0
    pids=()
    for i in $(seq 1 "$N"); do
        ssh "${BASE[@]}" "${MUX[@]}" "$CLUSTER" 'sleep 3' 2>&1 &
        pids+=($!)
    done
    for p in "${pids[@]}"; do
        wait "$p" || falhas=$((falhas + 1))
    done
    echo "sessões com falha: $falhas de $N"
    echo
done

echo "=== 5. Fechar o mestre (-O exit) ==="
ssh -O exit "${MUX[@]}" "$CLUSTER" 2>&1
echo "código de saída: $?"
echo

echo "=== Como ler ==="
echo "1 e 2 sem erro, 3 bem mais rápido que 3b e 4 com 0 falhas: o cluster aceita."
echo "Falhas no 4 com 'Session open refused by peer' ou 'administratively prohibited': MaxSessions baixo."
echo "Falha no 1 ou 2: o ssh local ou o ssh_config bloqueia, ou o host não é conhecido (known_hosts)."
} > "$SAIDA" 2>&1

echo "Pronto. Resultado em: $SAIDA"
