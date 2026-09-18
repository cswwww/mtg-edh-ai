#!/bin/bash
# 启动前端 dev server;后端 API(8103)由 vite.config.js 的插件自动拉起并随其关闭
cd "$(dirname "$0")"
if [ $# -eq 0 ]; then
  exec npx vite --port 7100 --strictPort
else
  exec npx vite "$@"
fi
