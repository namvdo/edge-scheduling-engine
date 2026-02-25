Remove-Item -Recurse -Force gen -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force gen | Out-Null
New-Item -ItemType File -Force gen\__init__.py | Out-Null

python -m grpc_tools.protoc -I proto `
  --python_out=gen `
  --grpc_python_out=gen `
  proto/telemetry.proto proto/scheduler.proto proto/health.proto

Write-Host " Protos generated into ./gen"
