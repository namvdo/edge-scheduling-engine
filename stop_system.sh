#!/bin/bash

echo "====================================================="
echo "  Stopping 6G Edge Scheduling Engine & Dashboard"
echo "====================================================="

# Kill scheduler nodes
echo "[1/5] Stopping Raft Scheduler Nodes..."
pkill -f "services/scheduler/server.py" 2>/dev/null

# Kill simulator
echo "[2/5] Stopping Base Station Simulator..."
pkill -f "services/basestation-sim/client.py" 2>/dev/null

# Kill orchestrator
echo "[3/5] Stopping Cloud Orchestrator..."
pkill -f "services/cloud-orchestrator/orchestrator.py" 2>/dev/null

# Kill API server
echo "[4/5] Stopping WebSocket API (port 8000)..."
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Kill frontend
echo "[5/5] Stopping React Dashboard (port 5173)..."
lsof -ti:5173 | xargs kill -9 2>/dev/null

echo "====================================================="
echo " All services stopped."
echo "====================================================="
