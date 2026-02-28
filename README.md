# Edge Scheduling Engine - 5G/6G Distributed Systems Final Project

This project implements core distributed systems concepts including consensus algorithms, deep reinforcement learning, big data analytics, and microservice architectures. 

## Major Components

1. **Custom Raft Consensus (`services/scheduler/cluster`)**
   A custom, dependency-free implementation of the Raft consensus algorithm. Redundant Edge Scheduler nodes dynamically elect a Leader, maintain heartbeats, and replicate network scheduling decisions to an internal distributed log for fault tolerance.
2. **DDPG Reinforcement Learning Agent (`services/scheduler/ml`)**
   A PyTorch Actor-Critic neural network that predicts optimal Downlink/Uplink TDD splits in real-time. It learns to minimize UE buffer starvation and maximize throughput across dynamic network conditions.
3. **Stateful 5G Base Station Simulator (`services/basestation-sim`)**
   A stateful, physics-based simulator modeling UE mobility (random walk), Path Loss mapping to SINR/CQI, and Poisson-distributed packet traffic. It dynamically drains 5G buffers by mathematical transmission capacity upon receiving Scheduler PRB allocations.
4. **Big Data PySpark Analytics (`services/analytics`)**
   A data pipeline that ingests gigabytes of centralized telemetry JSONL logs. It utilizes Apache Spark to execute tumbling time-window aggregations, isolating throughput demands per 5G network slice (eMBB, URLLC, mMTC). 
5. **Global Cloud Orchestrator (`services/cloud-orchestrator`)**
   A slow-loop orchestrator that reads historical PySpark analytics to detect slice starvation. It deploys new Quality of Service weights downward to the fast-loop Edge Schedulers via gRPC `UpdateSlicePolicy` hooks.
6. **React Dashboard Interface (`frontend`)**
   Features a live animated SVG Network Topology map, real-time DDPG training monitors, scrolling RAFT consensus logs, and responsive Recharts for bandwidth capabilities.

---

## Getting Started

### Prerequisites

* Python 3.12+
* Docker & Docker Compose (for Microservices deployment)
* Java 11+ (for PySpark)

### Native Setup (Development & Testing)

1. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Generate gRPC Protocol Buffers:**
   ```bash
   ./tools/gen_protos.sh
   # On Windows: .\tools\gen_protos.ps1
   ```

### Running the System (Native Local Execution)

1. **Start a 3-Node Raft Cluster (Terminal 1):**
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=.
   ./test_raft.sh
   ```
   *(This boots 3 scheduler nodes locally, holding a Raft election.)*

2. **Start the Stateful Base Station Simulator (Terminal 2):**
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=.:./gen
   python services/basestation-sim/client.py
   ```
   *(You will see UEs moving, buffers filling, and the DDPG agent actively draining them.)*

3. **Run Big Data PySpark Analytics (Terminal 3):**
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=.
   python services/analytics/spark_job.py
   ```
   *(Parses logs and creates `slice_stats.csv` inside `data/output/`)*

4. **Start the Global Cloud Orchestrator (Terminal 4):**
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=.:./gen
   python services/cloud-orchestrator/orchestrator.py
   ```

---

## Running in Docker (Microservices Orchestration)

To deploy the entire test suite inside isolated networking namespaces via Docker Compose:

```bash
docker-compose up --build -d
```
*Note: Make sure your local Docker daemon supports standard user bridging or configure the daemon appropriately. Once deployed, you can use `docker logs -f [container-name]` to view the Raft cluster formations and base station metrics.*

---

## Testing & Auditing

The project uses `pytest` to definitively validate the complex mathematical algorithms and Raft state boundaries.

1. **Run the Automated Test Suite:**
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=.:./gen
   pytest tests/
   ```

2. **Test Coverage Includes:**
   * `test_raft_node.py`: Asserts single-node instant election, and validates `LEADER` vs `FOLLOWER` log rejection patterns.
   * `test_simulator.py`: Asserts UE mobility boundaries, strict distance-to-CQI signal constraints, and floating-point accuracy of TDD packet byte drains.

---

## Viewing The Dashboard 

The Web App acts as the Visual Command Center. To start the Vite developer server:

```bash
cd frontend/
npm install
npm run dev
```

Open your browser to `http://localhost:5173`. You will see the animated 6G Network Topology map, the DDPG Agent monitor, and live Raft logging components.
