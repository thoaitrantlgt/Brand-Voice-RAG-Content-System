#!/usr/bin/env bash
set -euo pipefail

CONTENTOS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTENTOS_PID_FILE="$CONTENTOS_ROOT/.runtime/processes.env"

if [[ ! -f "$CONTENTOS_PID_FILE" ]]; then
  echo "No ContentOS process file found."
  exit 0
fi

while IFS='=' read -r CONTENTOS_NAME CONTENTOS_PID; do
  if [[ ! "$CONTENTOS_PID" =~ ^[0-9]+$ ]] || ! kill -0 "$CONTENTOS_PID" 2>/dev/null; then
    continue
  fi
  CONTENTOS_COMMAND="$(tr '\0' ' ' < "/proc/$CONTENTOS_PID/cmdline" 2>/dev/null || true)"
  CONTENTOS_CWD="$(readlink "/proc/$CONTENTOS_PID/cwd" 2>/dev/null || true)"
  if [[ "$CONTENTOS_COMMAND" != *"$CONTENTOS_ROOT"* ]] && [[ "$CONTENTOS_CWD" != "$CONTENTOS_ROOT"* ]]; then
    echo "Skipped $CONTENTOS_NAME pid $CONTENTOS_PID: process does not belong to this repo." >&2
    continue
  fi
  kill "$CONTENTOS_PID"
  echo "Stopped $CONTENTOS_NAME ($CONTENTOS_PID)"
done < <(tac "$CONTENTOS_PID_FILE")

mv "$CONTENTOS_PID_FILE" "$CONTENTOS_PID_FILE.stopped"
