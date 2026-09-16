#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ] || [ ! -d node_modules ]; then
  echo '请先按 README 安装 Python 与 npm 依赖。' >&2
  exit 1
fi
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8016 &
backend_pid=$!
.venv/bin/uvicorn backend.camera_ingress:app --host 0.0.0.0 --port 500 &
camera_pid=$!
npm run dev -- --host 0.0.0.0 --port 5176 --strictPort &
frontend_pid=$!
cleanup() { kill "$backend_pid" "$camera_pid" "$frontend_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
wait "$backend_pid" "$camera_pid" "$frontend_pid"
