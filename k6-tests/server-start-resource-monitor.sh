#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/ecoassistant"
RESULT_DIR="$HOME/load-test-results/$(date +%F_%H-%M-%S)"
mkdir -p "$RESULT_DIR"

cd "$PROJECT_DIR"

echo "Result dir: $RESULT_DIR"

(
  while true; do
    {
      echo "===== $(date -Is) ====="
      echo "--- docker compose ps ---"
      docker compose ps
      echo
      echo "--- docker stats --no-stream ---"
      docker stats --no-stream
      echo
      echo "--- free -h ---"
      free -h
      echo
      echo "--- df -h / /opt/ecoassistant ---"
      df -h / /opt/ecoassistant || true
      echo
    } >> "$RESULT_DIR/resource_monitor.log" 2>&1
    sleep 5
  done
) &

echo $! > "$RESULT_DIR/resource_monitor.pid"
ln -sfn "$RESULT_DIR" "$HOME/load-test-results/latest"

echo "Resource monitor started."
echo "PID: $(cat "$RESULT_DIR/resource_monitor.pid")"
echo "Log: $RESULT_DIR/resource_monitor.log"
echo "To stop: bash $(pwd)/k6-tests/server-stop-resource-monitor.sh"
