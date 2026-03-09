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

config_state = {
    "ru": 5,
    "du": 5,
    "cu": 1,
    "max_ues": 250
}

# Currently, we simulate reading from the Raft/DDPG log. 
# In a full integration, this would tail `node1.log` or connect via ZMQ/gRPC.
async def log_generator():
    demo_logs_templates = [
        {"type": "RAFT", "level": "INFO", "msg": "[{n1}] Broadcast AppendEntries (Heartbeat)", "node": "{n1}"},
        {"type": "RAFT", "level": "INFO", "msg": "← {n2}: Ack Term {term} ({latency}ms)", "node": "{n2}"},
        {"type": "RAFT", "level": "WARN", "msg": "x {n3}: Timeout Error > 50ms", "node": "{n3}"},
        {"type": "SCHED", "level": "INFO", "msg": "Scheduler dynamically adjusted DL PRB allocation for {n2}.", "node": "{n2}"},
        {"type": "SCHED", "level": "CRIT", "msg": "{n_last} latency spiked > 50ms. DDPG penalizing state reward.", "node": "{n_last}"},
    ]
    
    tp = 400
    lat = 12
    util = 60
    
    # RAFT state counters — increment over time
    raft_term = 450
    raft_log_index = 18900
    raft_leader = "DU-1"   # start with DU-1 as the initial leader
    term_timer = 0  # seconds until next election
    
    # Slice type distribution: probability that a UE belongs to each slice
    # These are base probabilities — they shift with UE count
    SLICE_PROFILES = {
        "eMBB":  {"prob": 0.60, "bw_per_ue": 1.0,  "desc": "video/streaming"},
        "URLLC": {"prob": 0.25, "bw_per_ue": 0.5,  "desc": "low-latency control"},
        "mMTC":  {"prob": 0.15, "bw_per_ue": 0.05, "desc": "IoT sensors"},
    }
    
    while True:
        await asyncio.sleep(1.0)
        
        ts = time.strftime('%H:%M:%S')
        
        # Load factor: normalized to default 250 UEs
        max_ues = config_state["max_ues"]
        ue_load_factor = max_ues / 250.0
        
        # Simulate active UE count (85-100% of max are active at any time)
        active_ues = int(max_ues * random.uniform(0.85, 1.0))
        
        # 1. Generate live metric data drift — scaled by UE load
        tp = tp + random.uniform(-10, 15) * ue_load_factor
        tp = max(50, tp)  # floor
        lat = max(2.0, lat + random.uniform(-2, 2.5) * ue_load_factor)
        # Utilization base shifts up with more UEs
        util_base_shift = (ue_load_factor - 1.0) * 20  # +20% util per 2x UEs
        util = max(10.0, min(99.0, util + random.uniform(-5, 5) + util_base_shift * 0.1))
        
        # ---- RAFT Term & Log Index (increment over time) ----
        term_timer += 1
        num_dus = config_state["du"]
        # Build DU list for election purposes
        du_nodes = [f"DU-{i+1}" for i in range(num_dus)]
        # New election roughly every 30-60 seconds
        new_election = term_timer >= random.randint(30, 60)
        if new_election:
            raft_term += 1
            term_timer = 0
            old_leader = raft_leader
            # Re-elect: pick any DU, weighted so leader changes most of the time
            candidates = [d for d in du_nodes if d != old_leader] or du_nodes
            raft_leader = random.choice(candidates)
            # Broadcast a dedicated election log event
            await manager.broadcast(json.dumps({
                "type": "RAFT",
                "level": "INFO",
                "msg": f"[ELECTION] Term {raft_term}: {raft_leader} won election. Previous leader: {old_leader}",
                "node": raft_leader,
                "ts": ts
            }))
        # Ensure leader is always a valid DU (e.g. if DU count changed)
        if raft_leader not in du_nodes:
            raft_leader = du_nodes[0]
        # Log index grows with each scheduling decision (proportional to active UEs)
        raft_log_index += random.randint(1, max(1, active_ues // 50))
        
        # Dynamic TDD (e.g., DDPG agent output changing over time)
        dl_percent = 50 + int(math.sin(time.time() / 10) * 30 + random.uniform(-5, 5))
        dl_percent = max(10, min(90, dl_percent))
        ul_percent = 100 - dl_percent

        # Node-specific resource allocation (Compute, Storage Buffer, Spectrum)
        nodes = []
        for i in range(config_state["ru"]):
            nodes.append(f"RU-{i+1}")
        for i in range(config_state["du"]):
            nodes.append(f"DU-{i+1}")
        nodes.append("CU-Core")
            
        node_metrics = []
        # Per-node UE pressure: distribute UEs across RUs
        num_rus = config_state["ru"]
        ues_per_ru = max_ues / max(1, num_rus)
        node_ue_pressure = min(1.0, ues_per_ru / 250.0)  # 0..1 pressure scale
        
        for i, n in enumerate(nodes):
            # Check if there is a manual UI spike commanded
            is_manual_spike = spike_state["active"] and time.time() < spike_state["end_time"] and spike_state["node"] == n
            if is_manual_spike:
                base_compute = 99
                storage = int(random.uniform(90, 100)) # buffer floods
            else:
                # Normal operations — scaled by UE load
                is_congested = random.random() > (0.95 - 0.3 * ue_load_factor)  # more UEs → more congestion
                # Base compute range shifts up with UE pressure
                low_base = int(20 + 35 * node_ue_pressure)  # 20..55
                high_base = int(65 + 30 * node_ue_pressure)  # 65..95
                base_compute = int(random.uniform(75, 99)) if is_congested else int(random.uniform(low_base, high_base))
                storage = int(random.uniform(10, 80) * ue_load_factor)
            
            # The last node is typically higher load in the demo
            if i == len(nodes) - 1 and not is_manual_spike:
                base_compute = max(60, base_compute + int(random.uniform(10, 30)))
                
            node_metrics.append({
                "name": n,
                "compute": min(99, base_compute),
                "storage": min(100, storage),      # representation of buffer fill
                "spectrum": int(random.uniform(50, 400) * ue_load_factor)     # allocated PRBs / bandwidth
            })
            
        # ---- Dynamic Network Slicing (UE-driven demand model) ----
        # Step 1: Distribute active UEs across slice types
        #   With more UEs, mMTC proportion grows (IoT scales massively)
        #   eMBB proportion slightly decreases as network gets crowded
        mmtc_boost = min(0.15, (ue_load_factor - 1.0) * 0.05)  # mMTC grows with scale
        embb_prob  = max(0.35, SLICE_PROFILES["eMBB"]["prob"] - mmtc_boost)
        urllc_prob = SLICE_PROFILES["URLLC"]["prob"]
        mmtc_prob  = 1.0 - embb_prob - urllc_prob  # remainder goes to mMTC
        
        embb_ues  = int(active_ues * embb_prob  * random.uniform(0.9, 1.1))
        urllc_ues = int(active_ues * urllc_prob * random.uniform(0.9, 1.1))
        mmtc_ues  = active_ues - embb_ues - urllc_ues  # remainder
        
        # Step 2: Calculate bandwidth demand per slice
        #   Each UE type consumes different bandwidth:
        #   eMBB:  1.0 unit per UE (heavy: video, large downloads)
        #   URLLC: 0.5 unit per UE (medium: small but frequent & guaranteed)
        #   mMTC:  0.05 unit per UE (tiny: sensor pings, status updates)
        embb_demand  = embb_ues  * SLICE_PROFILES["eMBB"]["bw_per_ue"]  * random.uniform(0.8, 1.2)
        urllc_demand = urllc_ues * SLICE_PROFILES["URLLC"]["bw_per_ue"] * random.uniform(0.8, 1.2)
        mmtc_demand  = mmtc_ues  * SLICE_PROFILES["mMTC"]["bw_per_ue"]  * random.uniform(0.8, 1.2)
        
        # Step 3: Normalize to percentage (total = 100%)
        total_demand = embb_demand + urllc_demand + mmtc_demand
        if total_demand > 0:
            embb_pct  = int(embb_demand  / total_demand * 100)
            urllc_pct = int(urllc_demand / total_demand * 100)
            mmtc_pct  = 100 - embb_pct - urllc_pct  # ensure they sum to 100
        else:
            embb_pct, urllc_pct, mmtc_pct = 50, 30, 20
        
        slices = [
            {"name": "eMBB",  "value": embb_pct,  "ues": embb_ues},
            {"name": "URLLC", "value": urllc_pct, "ues": urllc_ues},
            {"name": "mMTC",  "value": mmtc_pct,  "ues": mmtc_ues},
        ]

        metrics = {
            "type": "METRICS",
            "time": int(time.time() % 100),
            "throughput": tp,
            "latency": lat,
            "utilization": util,
            "users": active_ues,
            "raft_term": raft_term,
            "raft_log_index": raft_log_index,
            "raft_leader": raft_leader,
            "tdd_dl": dl_percent,
            "tdd_ul": ul_percent,
            "node_allocations": node_metrics,
            "slice_allocation": slices
        }
        await manager.broadcast(json.dumps(metrics))

        # 2. Generate random log events
        if random.random() > 0.6:
            tmpl = random.choice(demo_logs_templates)
            n1 = nodes[0]
            n2 = nodes[min(1, len(nodes)-1)]
            n3 = nodes[min(2, len(nodes)-1)]
            n_l = nodes[-1]
            log_event = {
                "type": tmpl["type"],
                "level": tmpl["level"],
                "msg": tmpl["msg"].format(n1=n1, n2=n2, n3=n3, n_last=n_l, term=raft_term, latency=random.randint(1, 8)),
                "node": tmpl["node"].format(n1=n1, n2=n2, n3=n3, n_last=n_l, term=raft_term, latency=0),
                "ts": ts
            }
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
                elif msg.get("type") == "UPDATE_CONFIG":
                    config_state["ru"] = msg.get("ru", 5)
                    config_state["du"] = msg.get("du", 5)
                    config_state["max_ues"] = msg.get("max_ues", 250)
                    print(f"Applied new global configuration: {config_state['ru']} RUs, {config_state['du']} DUs, {config_state['max_ues']} max UEs")
                    
                    # Log the config update
                    await manager.broadcast(json.dumps({
                        "type": "SYS",
                        "level": "INFO",
                        "msg": f"SYSTEM RECONFIG: Set cluster size to {config_state['ru']} RUs, {config_state['du']} DUs, max {config_state['max_ues']} UEs.",
                        "node": "SYS",
                        "ts": time.strftime('%H:%M:%S')
                    }))
            except Exception as e:
                print("Error parsing websocket message:", e)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
