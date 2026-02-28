#!/bin/bash

echo "====================================================="
echo "  Starting 6G Edge Scheduling Engine & Dashboard"
echo "====================================================="

# Activate virtual environment
source .venv/bin/activate
export PYTHONPATH=.:./gen

echo "[1/5] Starting Raft Consensus Cluster (3 Nodes)..."
python services/scheduler/server.py --id node1 --peers node2,node3 --port 50051 --raft-port 50061 > node1.log 2>&1 &
P1=$!
python services/scheduler/server.py --id node2 --peers node1,node3 --port 50052 --raft-port 50062 > node2.log 2>&1 &
P2=$!
python services/scheduler/server.py --id node3 --peers node1,node2 --port 50053 --raft-port 50063 > node3.log 2>&1 &
P3=$!

# Give the cluster a moment to elect a leader
sleep 5

echo "[2/5] Starting Stateful 5G Base Station Simulator..."
python services/basestation-sim/client.py > simulator.log 2>&1 &
P4=$!

echo "[3/5] Starting Distributed PySpark Analytics (Background)..."
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
    kill $P1 $P2 $P3 $P4 $P5 $P6 $P7 2>/dev/null
    exit 0
}

trap cleanup INT TERM

wait
