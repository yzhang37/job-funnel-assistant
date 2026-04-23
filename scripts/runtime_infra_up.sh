#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MYSQL_PORT="${JOB_SEARCH_MYSQL_PORT:-3307}"
MYSQL_DATA_DIR="$ROOT/data/runtime/mysql/data"
MYSQL_SOCKET="$ROOT/data/runtime/mysql/mysql.sock"
MYSQL_CONFIG="$ROOT/infra/mysql/my.cnf"
MYSQL_LOG_DIR="$ROOT/data/runtime/logs"
KAFKA_CONFIG="$ROOT/infra/kafka/server.properties"
KAFKA_LOG_DIR="$ROOT/data/runtime/logs"
KAFKA_DATA_DIR="$ROOT/data/runtime/kafka/kraft-combined-logs"
KAFKA_BIN_DIR="/opt/homebrew/opt/kafka/bin"

mkdir -p "$MYSQL_DATA_DIR" "$MYSQL_LOG_DIR" "$KAFKA_DATA_DIR"

if ! lsof -iTCP:"$MYSQL_PORT" -sTCP:LISTEN -nP >/dev/null 2>&1; then
  if [ ! -d "$MYSQL_DATA_DIR/mysql" ]; then
    mysqld --initialize-insecure \
      --basedir=/opt/anaconda3 \
      --datadir="$MYSQL_DATA_DIR" \
      --plugin-dir=/opt/anaconda3/lib/plugin \
      --lc-messages-dir=/opt/anaconda3/pkgs/mysql-8.4.0-h065ec36_2/share/mysql \
      >"$MYSQL_LOG_DIR/mysql-init.out" 2>"$MYSQL_LOG_DIR/mysql-init.err"
  fi

  mysqld --defaults-file="$MYSQL_CONFIG" --daemonize \
    >"$MYSQL_LOG_DIR/mysql-server.out" 2>&1

  for _ in $(seq 1 30); do
    if mysqladmin ping -h127.0.0.1 -P"$MYSQL_PORT" --silent >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  mysql -h127.0.0.1 -P"$MYSQL_PORT" -uroot <<'SQL'
CREATE DATABASE IF NOT EXISTS job_funnel_runtime CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'jobsearch'@'127.0.0.1' IDENTIFIED BY 'jobsearch';
CREATE USER IF NOT EXISTS 'jobsearch'@'localhost' IDENTIFIED BY 'jobsearch';
GRANT ALL PRIVILEGES ON job_funnel_runtime.* TO 'jobsearch'@'127.0.0.1';
GRANT ALL PRIVILEGES ON job_funnel_runtime.* TO 'jobsearch'@'localhost';
FLUSH PRIVILEGES;
SQL
fi

if ! lsof -iTCP:9092 -sTCP:LISTEN -nP >/dev/null 2>&1; then
  if [ ! -f "$KAFKA_DATA_DIR/meta.properties" ]; then
    KAFKA_CLUSTER_ID="$("$KAFKA_BIN_DIR/kafka-storage" random-uuid)"
    "$KAFKA_BIN_DIR/kafka-storage" format \
      --standalone \
      --cluster-id "$KAFKA_CLUSTER_ID" \
      -c "$KAFKA_CONFIG"
  fi

  "$KAFKA_BIN_DIR/kafka-server-start" -daemon "$KAFKA_CONFIG"

  for _ in $(seq 1 30); do
    if "$KAFKA_BIN_DIR/kafka-topics" --bootstrap-server 127.0.0.1:9092 --list >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

echo "MySQL listening on 127.0.0.1:$MYSQL_PORT"
echo "Kafka listening on 127.0.0.1:9092"
