# Miika: RAN Scheduler Simulator

## QUICKSTART

Linux:
```bash
cd <project-folder>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export PYTHONPATH=src
python -m ran_scheduler.main --scenario normal --ticks 20 --users 200 --base-requests-per-tick 200 --log-dir logs
```




Windows Powershell
```bash
cd <project-folder>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:PYTHONPATH="src"
python -m ran_scheduler.main --scenario normal --ticks 20 --users 200 --base-requests-per-tick 200 --log-dir logs
```


straight in the file if you want this way
```bash
export PYTHONPATH=src
python src/ran_scheduler/main.py --scenario normal --ticks 20 --users 200 --base-requests-per-tick 200 --log-dir logs
```
(powershell)
```bash
$env:PYTHONPATH="src"
python src/ran_scheduler/main.py --scenario normal --ticks 20 --users 200 --base-requests-per-tick 200 --log-dir logs
```


## Here's more detailed if you wanna check. (all below with Linux)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
python -c "import ran_scheduler; print('OK', ran_scheduler.__file__)"
python -m ran_scheduler.main --scenario normal --ticks 20 --users 200 --base-requests-per-tick 200 --log-dir logs
python -m ran_scheduler.main --scenario rush --ticks 100 --users 400 --base-requests-per-tick 400 --log-dir logs_rush
head -n 5 logs_rush/requests_kpi.csv
grep -iE "qos|blocked|granted" -m 1 logs_rush/requests_kpi.csv
```

## Monitoring (Prometheus + Grafana)

1) Start stack:

```bash
docker compose -f monitoring/docker-compose.yml up -d
```

2) Run simulator with prometheus exporter:

```bash
python -m ran_scheduler.main --scenario rush --ticks 5000 --users 300 --base-requests-per-tick 300 \
  --prometheus --prometheus-port 8000 --log-dir logs_metrics

docker compose -f monitoring/docker-compose.yml up -d
docker compose -f monitoring/docker-compose.yml ps

curl -s http://127.0.0.1:3000/api/health
curl -s http://127.0.0.1:9090/-/ready
```

Grafana: http://localhost:3000 (default login admin/admin)
Prometheus: http://localhost:9090

## Batch analytics

```bash
python spark_jobs/analyze_demand_patterns.py --input logs/requests_kpi.csv --output reports/demand_patterns.json
```


## Cloud and Datacenter things

You need:
- Docker + docker compose
- OpenSSL (for cert generation)


From repo root

```bash
cd cloud/inc9

#generate CA, server certs, client certs
bash certs/generate_certs.sh

#Start multi-region stack
docker compose -f docker-compose.multiregion.yml up -d --build

#Follow logs
docker compose -f docker-compose.multiregion.yml logs -f ran-eu
```

Expected:

- `scheduler-eu` listens on `https://localhost:18443` (host port)
- `scheduler-us` listens on `https://localhost:28443`
-agents run a short simulation and write logs to `cloud/inc9/out/logs_*`

Stop:

```bash
docker compose -f docker-compose.multiregion.yml down
```

## 2) “Secure tunnel” detail

Implement secure RAN <-> scheduler communication using mTLS:

-A local CA signs both server and client certs
-Scheduler requires a valid client cert (RAN agent)
-Client verifies the scheduler cert chain

so this demonstrates secure connectivity between edge RAN and a cloud scheduler.

## 3) Cloud deployment (free tier)

This repo is containerized, so you can deploy it to **any** free-tier VM:
1.AWS EC2 Free Tier (Ubuntu). 2.GCP Compute Engine free tier regions. 3.Azure VM free tier

### Minimal approach

Create 2 small VMs in two regions (or two different cloud regions). On each VM:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin openssl
git clone <your_repo>
cd <your_repo>/cloud/inc9
bash certs/generate_certs.sh
docker compose -f docker-compose.single-region.yml up -d --build
```


## Benchmark + caching

```bash
python benchmarks/benchmark_sim.py --ticks 100 --users 1000 --req-per-tick 1000 --log-dir logs_bench
```

Redis cache:

```bash
docker run --rm -p 6379:6379 redis:7
python benchmarks/benchmark_sim.py --redis-url redis://localhost:6379/0
```



also you can check this way...

```bash
docker run --rm -p 6379:6379 --name ran-redis redis:7
```
other terminal:
```bash
redis-cli -p 6379 ping
source .venv/bin/activate
export PYTHONPATH=src
python benchmarks/benchmark_sim.py \
  --ticks 100 --users 1000 --req-per-tick 1000 \
  --log-dir logs_bench_redis \
  --redis-url redis://127.0.0.1:6379/0
redis-cli -p 6379 info stats | egrep "keyspace_hits|keyspace_misses"
```
(you can change cache time for example to 600s in benchmarks --> benchmark_sim.py)
