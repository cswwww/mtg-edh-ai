#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/.mtg-edh-ai-web.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "没有找到 Web 服务 PID 文件，服务可能未运行"
  exit 0
fi

pid="$(<"$PID_FILE")"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  echo "PID 文件内容无效: $PID_FILE" >&2
  exit 1
fi

if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "Web 服务未运行，已清理过期 PID 文件"
  exit 0
fi

process_tree() {
  local parent="$1"
  local child
  while IFS= read -r child; do
    [[ -n "$child" ]] && process_tree "$child"
  done < <(ps -axo pid=,ppid= | awk -v parent="$parent" '$2 == parent { print $1 }')
  printf '%s\n' "$parent"
}

processes="$(process_tree "$pid")"
while IFS= read -r process; do
  [[ -n "$process" ]] && kill -TERM "$process" 2>/dev/null || true
done <<<"$processes"

for _ in {1..10}; do
  running=false
  while IFS= read -r process; do
    if [[ -n "$process" ]] && kill -0 "$process" 2>/dev/null; then
      running=true
      break
    fi
  done <<<"$processes"
  [[ "$running" == false ]] && break
  sleep 1
done

if [[ "$running" == true ]]; then
  while IFS= read -r process; do
    [[ -n "$process" ]] && kill -KILL "$process" 2>/dev/null || true
  done <<<"$processes"
fi

rm -f "$PID_FILE"
echo "Web 服务已停止"
