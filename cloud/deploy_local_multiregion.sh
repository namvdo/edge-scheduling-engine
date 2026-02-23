#!/usr/bin/env bash
set -euo pipefail

#this simulate multi-datacenter locally by running 2 stacks
#This is a local helper

echo "Starting monitoring stack (Prometheus + Grafana) using host networking..."
docker compose -f monitoring/docker-compose.yml up -d

echo "Run two simulators in two terminals with different LOG_DIR and prometheus ports:"
echo "  REGION=eu LOG_DIR=logs-eu python -m ran_scheduler.main --scenario rush --prometheus --prometheus-port 8000 --log-dir logs-eu"
echo "  REGION=us LOG_DIR=logs-us python -m ran_scheduler.main --scenario rush --prometheus --prometheus-port 8001 --log-dir logs-us"
echo ""
echo "Then in prometheus, add another target localhost:8001 if you want both regions scraped."
