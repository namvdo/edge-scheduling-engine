#!/bin/bash
export CONSENSUS_ENABLED=true
export RAFT_PEERS="localhost:50061,localhost:50062,localhost:50063"

# Node 1
export NODE_ID=scheduler-1
export SCHEDULER_PORT=50051
export RAFT_PORT=50061
export RAFT_ADDRESS=localhost:50061
PYTHONUNBUFFERED=1 .venv/bin/python services/scheduler/server.py > node1.log 2>&1 &
PID1=$!

# Node 2
export NODE_ID=scheduler-2
export SCHEDULER_PORT=50052
export RAFT_PORT=50062
export RAFT_ADDRESS=localhost:50062
PYTHONUNBUFFERED=1 .venv/bin/python services/scheduler/server.py > node2.log 2>&1 &
PID2=$!

# Node 3
export NODE_ID=scheduler-3
export SCHEDULER_PORT=50053
export RAFT_PORT=50063
export RAFT_ADDRESS=localhost:50063
PYTHONUNBUFFERED=1 .venv/bin/python services/scheduler/server.py > node3.log 2>&1 &
PID3=$!

echo "Started 3 nodes. PIDs: $PID1 $PID2 $PID3"
sleep 5

echo "Killing Node 1 ($PID1) to trigger re-election..."
kill -9 $PID1

sleep 5

echo "Shutting down remaining nodes..."
kill -9 $PID2 $PID3
echo "Done"
