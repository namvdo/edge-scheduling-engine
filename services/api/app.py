import json
import logging
import asyncio
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
        
        metrics = {
            "type": "METRICS",
            "time": int(time.time() % 100),
            "throughput": tp,
            "latency": lat,
            "utilization": util,
            "users": int(300 + random.uniform(-10, 20))
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
            # Handle incoming commands if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)
