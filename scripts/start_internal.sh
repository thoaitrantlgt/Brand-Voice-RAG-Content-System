#!/usr/bin/env bash
set -euo pipefail

CONTENTOS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTENTOS_RUNTIME="$CONTENTOS_ROOT/.runtime"
CONTENTOS_LOGS="$CONTENTOS_RUNTIME/logs"
CONTENTOS_PID_FILE="$CONTENTOS_RUNTIME/processes.env"
CONTENTOS_BACKEND_PYTHON="$CONTENTOS_ROOT/backend/.venv/bin/python"
CONTENTOS_MODEL_CLI="$CONTENTOS_RUNTIME/model-venv/bin/transformers"
CONTENTOS_STANDALONE="$CONTENTOS_ROOT/frontend/.next/standalone"
CONTENTOS_NGROK_CLI="$CONTENTOS_RUNTIME/ngrok"
CONTENTOS_NGROK_CONFIG="$CONTENTOS_RUNTIME/ngrok.yml"

mkdir -p "$CONTENTOS_LOGS"

if [[ ! -x "$CONTENTOS_BACKEND_PYTHON" ]]; then
  echo "Missing backend venv: $CONTENTOS_BACKEND_PYTHON" >&2
  exit 1
fi
if [[ ! -x "$CONTENTOS_MODEL_CLI" ]]; then
  echo "Missing model runtime: $CONTENTOS_MODEL_CLI" >&2
  exit 1
fi
if [[ ! -f "$CONTENTOS_STANDALONE/server.js" ]]; then
  echo "Missing frontend build. Run npm run build in frontend first." >&2
  exit 1
fi
if [[ -f "$CONTENTOS_PID_FILE" ]]; then
  while IFS='=' read -r CONTENTOS_NAME CONTENTOS_PID; do
    if [[ "$CONTENTOS_PID" =~ ^[0-9]+$ ]] && kill -0 "$CONTENTOS_PID" 2>/dev/null; then
      echo "ContentOS is already running ($CONTENTOS_NAME pid $CONTENTOS_PID)." >&2
      exit 1
    fi
  done < "$CONTENTOS_PID_FILE"
fi

CONTENTOS_NODE="$(command -v node || true)"
if [[ -z "$CONTENTOS_NODE" ]] || [[ "${CONTENTOS_NODE##*/}" == "" ]]; then
  echo "Node.js is not installed." >&2
  exit 1
fi
CONTENTOS_NODE_MAJOR="$($CONTENTOS_NODE -p 'process.versions.node.split(".")[0]')"
if (( CONTENTOS_NODE_MAJOR < 22 )); then
  CONTENTOS_NODE_CANDIDATE="$(find /usr/local/nvm/versions/node -path '*/v22*/bin/node' -type f 2>/dev/null | sort -V | tail -n 1)"
  if [[ -z "$CONTENTOS_NODE_CANDIDATE" ]]; then
    echo "Node.js 22+ is required." >&2
    exit 1
  fi
  CONTENTOS_NODE="$CONTENTOS_NODE_CANDIDATE"
fi

cp -a "$CONTENTOS_ROOT/frontend/.next/static" "$CONTENTOS_STANDALONE/.next/"
cp -a "$CONTENTOS_ROOT/frontend/public" "$CONTENTOS_STANDALONE/"

wait_for_url() {
  local CONTENTOS_URL="$1"
  local CONTENTOS_LABEL="$2"
  local CONTENTOS_LOG="$3"
  local CONTENTOS_ATTEMPTS="${4:-120}"
  for CONTENTOS_ATTEMPT in $(seq 1 "$CONTENTOS_ATTEMPTS"); do
    if curl -fsS "$CONTENTOS_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "$CONTENTOS_LABEL did not become ready. Last log lines:" >&2
  tail -n 40 "$CONTENTOS_LOG" >&2 || true
  return 1
}

cleanup_on_error() {
  for CONTENTOS_PID in "${CONTENTOS_NGROK_PID:-}" "${CONTENTOS_FRONTEND_PID:-}" "${CONTENTOS_WORKER_PID:-}" "${CONTENTOS_API_PID:-}" "${CONTENTOS_MODEL_PID:-}"; do
    if [[ "$CONTENTOS_PID" =~ ^[0-9]+$ ]]; then
      kill "$CONTENTOS_PID" 2>/dev/null || true
    fi
  done
}
trap cleanup_on_error ERR INT TERM

(
  cd "$CONTENTOS_ROOT"
  nohup env PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
    "$CONTENTOS_MODEL_CLI" serve Qwen/Qwen3.5-2B \
    --host 127.0.0.1 --port 8001 --device cuda:0 --dtype bfloat16 \
    --reasoning off --chat-template-kwargs '{"enable_thinking":false}' \
    --log-level warning > "$CONTENTOS_LOGS/model.log" 2>&1 &
  echo $!
) > "$CONTENTOS_RUNTIME/model.pid"
CONTENTOS_MODEL_PID="$(<"$CONTENTOS_RUNTIME/model.pid")"
wait_for_url "http://127.0.0.1:8001/health" "Model server" "$CONTENTOS_LOGS/model.log" 180

(
  cd "$CONTENTOS_ROOT/backend"
  nohup env DEBUG=false CREWAI_TRACING_ENABLED=false AUTH_ENABLED=false ALLOW_INSECURE_AUTH=true \
    "$CONTENTOS_BACKEND_PYTHON" run.py > "$CONTENTOS_LOGS/api.log" 2>&1 &
  echo $!
) > "$CONTENTOS_RUNTIME/api.pid"
CONTENTOS_API_PID="$(<"$CONTENTOS_RUNTIME/api.pid")"
wait_for_url "http://127.0.0.1:8000/health" "API" "$CONTENTOS_LOGS/api.log" 120

(
  cd "$CONTENTOS_ROOT/backend"
  nohup env DEBUG=false CREWAI_TRACING_ENABLED=false AUTH_ENABLED=false ALLOW_INSECURE_AUTH=true \
    "$CONTENTOS_BACKEND_PYTHON" worker.py > "$CONTENTOS_LOGS/worker.log" 2>&1 &
  echo $!
) > "$CONTENTOS_RUNTIME/worker.pid"
CONTENTOS_WORKER_PID="$(<"$CONTENTOS_RUNTIME/worker.pid")"

(
  cd "$CONTENTOS_STANDALONE"
  nohup env HOSTNAME=0.0.0.0 PORT=3000 \
    "$CONTENTOS_NODE" server.js > "$CONTENTOS_LOGS/frontend.log" 2>&1 &
  echo $!
) > "$CONTENTOS_RUNTIME/frontend.pid"
CONTENTOS_FRONTEND_PID="$(<"$CONTENTOS_RUNTIME/frontend.pid")"
wait_for_url "http://127.0.0.1:3000" "Frontend" "$CONTENTOS_LOGS/frontend.log" 60
wait_for_url "http://127.0.0.1:3000/ready" "Complete stack" "$CONTENTOS_LOGS/api.log" 60

CONTENTOS_PUBLIC_URL=""
if [[ -x "$CONTENTOS_NGROK_CLI" && -f "$CONTENTOS_NGROK_CONFIG" ]]; then
  (
    cd "$CONTENTOS_ROOT"
    nohup "$CONTENTOS_NGROK_CLI" http 3000 \
      --config "$CONTENTOS_NGROK_CONFIG" \
      --log "$CONTENTOS_LOGS/ngrok.log" --log-format json --log-level info \
      >/dev/null 2>&1 &
    echo $!
  ) > "$CONTENTOS_RUNTIME/ngrok.pid"
  CONTENTOS_NGROK_PID="$(<"$CONTENTOS_RUNTIME/ngrok.pid")"
  wait_for_url "http://127.0.0.1:4040/api/tunnels" "ngrok" "$CONTENTOS_LOGS/ngrok.log" 60
  CONTENTOS_PUBLIC_URL="$(
    curl -fsS "http://127.0.0.1:4040/api/tunnels" \
      | "$CONTENTOS_BACKEND_PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["tunnels"][0]["public_url"])'
  )"
fi

{
  printf 'model=%s\n' "$CONTENTOS_MODEL_PID"
  printf 'api=%s\n' "$CONTENTOS_API_PID"
  printf 'worker=%s\n' "$CONTENTOS_WORKER_PID"
  printf 'frontend=%s\n' "$CONTENTOS_FRONTEND_PID"
  if [[ "${CONTENTOS_NGROK_PID:-}" =~ ^[0-9]+$ ]]; then
    printf 'ngrok=%s\n' "$CONTENTOS_NGROK_PID"
  fi
} > "$CONTENTOS_PID_FILE"
trap - ERR INT TERM

echo "ContentOS started"
echo "Web:   http://127.0.0.1:3000"
if [[ -n "$CONTENTOS_PUBLIC_URL" ]]; then
  echo "Public: $CONTENTOS_PUBLIC_URL"
fi
echo "Ready: http://127.0.0.1:3000/ready"
echo "Logs:  $CONTENTOS_LOGS"
