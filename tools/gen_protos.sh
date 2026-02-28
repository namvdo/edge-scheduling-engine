#!/bin/bash
rm -rf gen
mkdir -p gen
touch gen/__init__.py

.venv/bin/python -m grpc_tools.protoc -I proto \
  --python_out=gen \
  --grpc_python_out=gen \
  proto/telemetry.proto proto/scheduler.proto proto/health.proto proto/raft.proto

echo "Protos generated into ./gen"
