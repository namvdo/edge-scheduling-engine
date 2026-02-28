import json
import logging
import asyncio
import math
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import time
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        
        for d in disconnected:
            self.disconnect(d)

manager = ConnectionManager()

# Global state to track forced spikes from UI
spike_state = {
    "active": False,
    "node": None,
    "end_time": 0
}

# Currently, we simulate reading from the Raft/DDPG log. 
# In a full integration, this would tail `node1.log` or connect via ZMQ/gRPC.
async def log_generator():
    demo_logs = [
        {"type": "RAFT", "level": "INFO", "msg": "[RU-1] Broadcast AppendEntries (Heartbeat)", "node": "RU-1", "ts": None},
        {"type": "RAFT", "level": "INFO", "msg": "← RU-2: Ack Term 452 (2ms)", "node": "RU-2", "ts": None},
        {"type": "RAFT", "level": "INFO", "msg": "← DU-Core: Ack Term 452 (4ms)", "node": "DU-Core", "ts": None},
        {"type": "RAFT", "level": "WARN", "msg": "x CU-East: Timeout Error > 50ms", "node": "CU-East", "ts": None},
        {"type": "SCHED", "level": "INFO", "msg": "Scheduler dynamically adjusted DL PRB allocation for DU-Core.", "node": "DU-Core", "ts": None},
        {"type": "SCHED", "level": "CRIT", "msg": "RU-2 latency spiked > 50ms. DDPG penalizing state reward.", "node": "RU-2", "ts": None},
    ]
    
    tp = 400
    lat = 12
    util = 60
    
    while True:
        await asyncio.sleep(1.0)
        
        ts = time.strftime('%H:%M:%S')
        
        # 1. Generate live metric data drift
        tp = tp + random.uniform(-10, 15)
        lat = max(2.0, lat + random.uniform(-2, 2.5))
        util = max(10.0, min(99.0, util + random.uniform(-5, 5)))
        
        # Dynamic TDD (e.g., DDPG agent output changing over time)
        dl_percent = 50 + int(math.sin(time.time() / 10) * 30 + random.uniform(-5, 5))
        dl_percent = max(10, min(90, dl_percent))
        ul_percent = 100 - dl_percent

        # Node-specific resource allocation (Compute, Storage Buffer, Spectrum)
        nodes = ["RU-1", "RU-2", "RU-3", "RU-4", "DU-1", "DU-Core", "CU-East", "CU-West"]
        node_metrics = []
        for n in nodes:
            # Check if there is a manual UI spike commanded
            is_manual_spike = spike_state["active"] and time.time() < spike_state["end_time"] and spike_state["node"] == n
            if is_manual_spike:
                base_compute = 99
                storage = int(random.uniform(90, 100)) # buffer floods
            else:
                # Normal operations
                is_congested = random.random() > 0.85
                base_compute = int(random.uniform(75, 99)) if is_congested else int(random.uniform(20, 65))
                storage = int(random.uniform(10, 80))
            
            # CU-East is typically higher load in the demo
            if n == "CU-East" and not is_manual_spike:
                base_compute = max(60, base_compute + int(random.uniform(10, 30)))
                
            node_metrics.append({
                "name": n,
                "compute": min(99, base_compute),
                "storage": storage,      # representation of buffer fill
                "spectrum": int(random.uniform(50, 400))     # allocated PRBs / bandwidth
            })
            
        # Network Slicing (Bandwidth partitioning)
        slices = [
            {"name": "eMBB", "value": int(random.uniform(40, 60))},
            {"name": "URLLC", "value": int(random.uniform(20, 35))},
            {"name": "mMTC", "value": int(random.uniform(5, 15))}
        ]

        metrics = {
            "type": "METRICS",
            "time": int(time.time() % 100),
            "throughput": tp,
            "latency": lat,
            "utilization": util,
            "users": int(300 + random.uniform(-10, 20)),
            "tdd_dl": dl_percent,
            "tdd_ul": ul_percent,
            "node_allocations": node_metrics,
            "slice_allocation": slices
        }
        await manager.broadcast(json.dumps(metrics))

        # 2. Generate random log events
        if random.random() > 0.6:
            log_event = random.choice(demo_logs).copy()
            log_event["ts"] = ts
            await manager.broadcast(json.dumps(log_event))


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(log_generator())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "INJECT_SPIKE":
                    spike_state["active"] = True
                    spike_state["node"] = msg.get("node", "RU-1")
                    spike_state["end_time"] = time.time() + 15  # Spike lasts 15 seconds
                    print(f"Server received SPIKE command for {spike_state['node']}")
                    
                    # Log the injection
                    await manager.broadcast(json.dumps({
                        "type": "SCHED",
                        "level": "CRIT",
                        "msg": f"USER OVERRIDE: 500% WORKLOAD SPIKE INJECTED AT {spike_state['node']}!",
                        "node": spike_state['node'],
                        "ts": time.strftime('%H:%M:%S')
                    }))
            except Exception as e:
                print("Error parsing websocket message:", e)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
