#!/usr/bin/env bash
# 一键更新 MTG 数据快照并重建本地库。
#
# 流程: 备份 -> Scryfall bulk 下载 -> mtgch 增量抓取 -> 重建 cards.jsonl
#       -> 合并 sf_tags -> 合并 AI 标签 -> 重建向量库
#
# 安全性:
#   - 更新前自动备份 cards.jsonl / tags.jsonl 到 data/backup/<时间戳>/
#   - AI 标签源头 data/tags.jsonl 全程只读,不会被覆盖
#   - 重建 cards.jsonl 后会把 AI 标签按 oracle_id 合并回去,不会丢
#   - 向量库(data/vectordb)是从 cards.jsonl 全量再生的,删掉重建不影响任何源数据
#   - EDHREC 缓存(7 天 TTL)保留,新卡会自动抓取
#
# 注意: 打标签任务(tag_cards.py)运行期间不要执行本脚本,
#       否则 tags.jsonl 正在写入的行可能被读到一半(虽然不致命)。
# 用法: bash scripts/update_data.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PY=python3

ts=$(date +%Y%m%d-%H%M%S)
bk="data/backup/$ts"
mkdir -p "$bk"
echo "== 0. 备份到 $bk"
cp data/cards.jsonl "$bk/cards.jsonl"
cp data/tags.jsonl "$bk/tags.jsonl" 2>/dev/null || true

echo "== 1. 下载 Scryfall Bulk(oracle-cards / all-cards / oracle-tags)"
$PY scripts/fetch_scryfall.py || { echo "Scryfall 下载失败,已自动回滚旧文件,退出"; exit 1; }

echo "== 2. 刷新 mtgch 系列列表并增量抓取缺失系列"
curl -s -H "User-Agent: mtg-edh-ai-local-db/1.0" \
  https://mtgch.com/api/v1/sets/ -o data/raw/sets.json.new \
  && mv data/raw/sets.json.new data/raw/sets.json
for i in 1 2 3 4 5 6 7 8 9 10; do
  $PY scripts/fetch_mtgch.py 500 && break
  echo "   (还有剩余系列,再来一轮)"
  sleep 5
done

echo "== 3. 抓取双面卡/缺正文卡详情(断点续传)"
for i in 1 2 3; do
  $PY scripts/fetch_details.py 2000 && break
  echo "   (还有剩余详情,再来一轮)"
  sleep 5
done

echo "== 4. 提取 Scryfall 中文印张索引"
$PY scripts/extract_zhs.py || exit 1

echo "== 5. 三源合并,重建 data/cards.jsonl"
$PY scripts/build_cards.py || exit 1

echo "== 6. 合并 Scryfall Tagger 标签(sf_tags)"
$PY scripts/merge_tags.py || exit 1

echo "== 7. 合并 AI 标签(ai_tags/ai_synergy/ai_desc)—— tags.jsonl 只读,不会丢"
$PY scripts/merge_ai_tags.py || exit 1

echo "== 8. 重建向量库(从 cards.jsonl 全量再生,删掉旧的重建是安全的)"
rm -rf data/vectordb
$PY scripts/build_vector_db.py || exit 1

echo "== 完成 ✓"
echo "   卡片数: $(wc -l < data/cards.jsonl)"
echo "   带AI标签: $(grep -c '"ai_tags": \[' data/cards.jsonl || true)"
echo "   备份在: $bk"
echo "   重启后端生效: cd web && npm run dev"
