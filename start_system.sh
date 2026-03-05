#!/bin/bash

echo "====================================================="
echo "  Starting 6G Edge Scheduling Engine & Dashboard"
echo "====================================================="

# Clean up any stale processes from previous runs
cleanup_stale() {
    echo "[0/6] Cleaning up stale processes..."

    # Kill any existing scheduler nodes
    pkill -f "services/scheduler/server.py" 2>/dev/null

    # Kill existing simulator
    pkill -f "services/basestation-sim/client.py" 2>/dev/null

    # Kill existing orchestrator
    pkill -f "services/cloud-orchestrator/orchestrator.py" 2>/dev/null

    # Kill any uvicorn on port 8000
    lsof -ti:8000 | xargs kill -9 2>/dev/null

    # Kill frontend dev server on port 5173
    lsof -ti:5173 | xargs kill -9 2>/dev/null

    sleep 1
}

cleanup_stale

# Activate virtual environment
source .venv/bin/activate
export PYTHONPATH=.:./gen

NUM_NODES=${1:-5}

if [ "$NUM_NODES" -ne 3 ] && [ "$NUM_NODES" -ne 5 ] && [ "$NUM_NODES" -ne 9 ]; then
    echo "Error: Number of nodes must be 3, 5, or 9."
    exit 1
fi

if [ "$NUM_NODES" -eq 3 ]; then
    TOLERATE=1
elif [ "$NUM_NODES" -eq 5 ]; then
    TOLERATE=2
elif [ "$NUM_NODES" -eq 9 ]; then
    TOLERATE=4
fi

echo "[1/6] Starting Raft Consensus Cluster ($NUM_NODES Nodes, can tolerate $TOLERATE failures)..."

PIDS=""
for i in $(seq 1 $NUM_NODES); do
    PEERS=""
    for j in $(seq 1 $NUM_NODES); do
        if [ "$i" -ne "$j" ]; then
            if [ -z "$PEERS" ]; then
                PEERS="node$j"
            else
                PEERS="$PEERS,node$j"
            fi
        fi
    done
    PORT=$((50050 + i))
    RAFT_PORT=$((50060 + i))
    python services/scheduler/server.py --id node$i --peers $PEERS --port $PORT --raft-port $RAFT_PORT > node$i.log 2>&1 &
    PIDS="$PIDS $!"
done

# Give the cluster a moment to elect a leader
sleep 5

echo "[2/6] Starting Stateful 5G Base Station Simulator..."
python services/basestation-sim/client.py > simulator.log 2>&1 &
P4=$!

echo "[3/6] Starting Distributed PySpark Analytics (Background)..."
# We run spark job periodically or as a daemon in a real setting, here we just echo it
# python services/analytics/spark_job.py > analytics.log 2>&1 &
echo "      (Skipping PySpark batch job for real-time visualization)"

echo "[4/6] Starting Global Cloud Orchestrator..."
python services/cloud-orchestrator/orchestrator.py > orchestrator.log 2>&1 &
P5=$!

echo "[5/6] Starting Live Metrics WebSocket API..."
uvicorn services.api.app:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
P6=$!

echo "[6/6] Starting React Visual Dashboard..."
cd frontend
npm run dev > frontend.log 2>&1 &
P7=$!

echo "====================================================="
echo " System is fully online! "
echo " Dashboard available at: http://localhost:5173"
echo " Monitoring backend logs... Press [CTRL+C] to stop."
echo "====================================================="

# Function to clean up background processes on exit
cleanup() {
    echo ""
    echo "Shutting down all microservices..."
    kill $PIDS $P4 $P5 $P6 $P7 2>/dev/null
    exit 0
}

trap cleanup INT TERM

wait
