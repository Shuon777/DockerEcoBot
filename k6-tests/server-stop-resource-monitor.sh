#!/usr/bin/env bash
set -euo pipefail

LATEST="$HOME/load-test-results/latest"
PID_FILE="$LATEST/resource_monitor.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "PID file not found: $PID_FILE"
  exit 1
fi

PID="$(cat "$PID_FILE")"
kill "$PID" || true
echo "Stopped resource monitor PID=$PID"
echo "Results: $LATEST"
