# resource-scheduling-network

## Week 1 Prakash task, he has done following : 

Base station simulator streaming telemetry

Scheduler gRPC server receiving it

Scheduler returning decisions + dynamic TDD

Client printing decisions, server logging scheduling epochs


# How to run :

python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Generate protos
.\tools\gen_protos.ps1

# Terminal 1
python services/scheduler/server.py

# Terminal 2
python services/basestation-sim/client.py
