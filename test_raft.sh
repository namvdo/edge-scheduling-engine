#!/bin/bash
export CONSENSUS_ENABLED=true

NUM_NODES=${1:-5}

if [ "$NUM_NODES" -ne 3 ] && [ "$NUM_NODES" -ne 5 ] && [ "$NUM_NODES" -ne 9 ]; then
    echo "Error: Number of nodes must be 3, 5, or 9."
    exit 1
fi

RAFT_PEERS=""
for i in $(seq 1 $NUM_NODES); do
    if [ -z "$RAFT_PEERS" ]; then
        RAFT_PEERS="localhost:5006$i"
    else
        RAFT_PEERS="$RAFT_PEERS,localhost:5006$i"
    fi
done
export RAFT_PEERS

PIDS=()
for i in $(seq 1 $NUM_NODES); do
    export NODE_ID=scheduler-$i
    export SCHEDULER_PORT=$((50050 + i))
    export RAFT_PORT=$((50060 + i))
    export RAFT_ADDRESS=localhost:$RAFT_PORT
    PYTHONUNBUFFERED=1 .venv/bin/python services/scheduler/server.py > node$i.log 2>&1 &
    PIDS+=($!)
done

echo "Started $NUM_NODES nodes. PIDs: ${PIDS[*]}"
sleep 5

echo "Killing Node 1 (${PIDS[0]}) to trigger re-election..."
kill -9 ${PIDS[0]}

sleep 5

echo "Shutting down remaining nodes..."
for i in $(seq 1 $((NUM_NODES-1))); do
    kill -9 ${PIDS[$i]} 2>/dev/null
done
echo "Done"
