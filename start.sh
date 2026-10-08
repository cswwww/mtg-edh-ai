#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/.mtg-edh-ai-web.pid"
LOG_FILE="$ROOT/.mtg-edh-ai-web.log"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(<"$PID_FILE")"
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "Web 服务已在运行 (PID $old_pid)"
    echo "浏览器打开: http://localhost:7100"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [[ ! -d "$ROOT/web/node_modules" ]]; then
  echo "未找到前端依赖，请先运行: cd \"$ROOT/web\" && npm install" >&2
  exit 1
fi

nohup bash "$ROOT/web/start.sh" >>"$LOG_FILE" 2>&1 </dev/null &
pid=$!
printf '%s\n' "$pid" >"$PID_FILE"

for _ in {1..10}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Web 服务启动失败，最近日志如下:" >&2
    tail -n 30 "$LOG_FILE" >&2
    exit 1
  fi
  sleep 1
done

echo "Web 服务已启动 (PID $pid)"
echo "浏览器打开: http://localhost:7100"
echo "日志文件: $LOG_FILE"
