#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MYSQL_PORT="${JOB_SEARCH_MYSQL_PORT:-3307}"
MYSQL_PID_FILE="$ROOT/data/runtime/mysql/mysql.pid"
KAFKA_BIN_DIR="/opt/homebrew/opt/kafka/bin"

if [ -f "$MYSQL_PID_FILE" ]; then
  MYSQL_PID="$(cat "$MYSQL_PID_FILE" 2>/dev/null || true)"
  if [ -n "$MYSQL_PID" ] && kill -0 "$MYSQL_PID" >/dev/null 2>&1; then
    kill "$MYSQL_PID" >/dev/null 2>&1 || true
    sleep 2
  fi
fi

if lsof -iTCP:"$MYSQL_PORT" -sTCP:LISTEN -nP >/dev/null 2>&1; then
  mysqladmin -h127.0.0.1 -P"$MYSQL_PORT" -uroot shutdown >/dev/null 2>&1 || true
fi

if lsof -iTCP:9092 -sTCP:LISTEN -nP >/dev/null 2>&1; then
  pkill -f "kafka.Kafka $ROOT/infra/kafka/server.properties" >/dev/null 2>&1 || true
  sleep 2
  "$KAFKA_BIN_DIR/kafka-server-stop" >/dev/null 2>&1 || true
fi
