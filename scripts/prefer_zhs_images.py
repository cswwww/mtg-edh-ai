#!/usr/bin/env python3
"""把卡图优先换成中文版本(原地更新 cards.jsonl 与向量库,不重新嵌入)。

优先级与 build_cards.py 一致:
  1. mtgch 任一印张的 /zhs/ 卡图
  2. Scryfall 简中印张图
  3. 保持现状(英文图)

- cards.jsonl: 只改 image_url 字段,先写 .tmp 再替换
- 向量库: 用 merge_insert 按 oracle_id 只更新 image_url 列,向量不动
- 已有中文图的卡跳过;算不出候选的卡保持原样
"""
import glob
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")
DB_DIR = os.path.join(ROOT, "data", "vectordb")
RAW = os.path.join(ROOT, "data", "raw")

# 印张级中文图索引
prints = defaultdict(list)
for f in glob.glob(os.path.join(RAW, "mtgch_sets", "*.json")):
    d = json.load(open(f))
    for c in d["items"]:
        prints[c["oracle_id"]].append(c)
zhs = json.load(open(os.path.join(RAW, "scryfall_zhs.json")))


def preferred(oid, cur):
    """返回更好的卡图 URL 或 None(保持现状)。"""
    if cur and "/zhs/" in cur:
        return None  # 已是中文图
    p = next((x["image_url"] for x in prints.get(oid, [])
              if x.get("image_url") and "/zhs/" in x["image_url"]), None)
    if p:
        return p
    zimg = (zhs.get(oid) or {}).get("image")
    if zimg and zimg != cur:
        return zimg
    return None


records = []
updates = {}
n_changed = 0
with open(CARDS, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        better = preferred(r["oracle_id"], r.get("image_url"))
        if better:
            updates[r["oracle_id"]] = better
            r["image_url"] = better
            n_changed += 1
        records.append(r)

if not updates:
    print("无需更新,所有可换的卡都已是中文图")
    raise SystemExit(0)

tmp = CARDS + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
os.replace(tmp, CARDS)
print(f"cards.jsonl 更新 {n_changed} 张")

import lancedb
db = lancedb.connect(DB_DIR)
tbl = db.open_table("cards")
batch = [{"oracle_id": k, "image_url": v} for k, v in updates.items()]
for i in range(0, len(batch), 1000):
    tbl.merge_insert("oracle_id").when_matched_update_all().execute(batch[i:i + 1000])
print(f"向量库 image_url 列已同步({tbl.count_rows()} 行不变,仅更新字段)")
