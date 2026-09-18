#!/usr/bin/env python3
"""把 Scryfall Tagger 标签并入 cards.jsonl 的 sf_tags 字段。

- 输入: data/raw/oracle-tags.jsonl.gz (Scryfall bulk)
- 过滤: 去掉 cycle-* 系列归属类标签(对功能检索是噪声)
- 输出: 原地更新 data/cards.jsonl
"""
import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")
TAGS = os.path.join(ROOT, "data", "raw", "oracle-tags.jsonl.gz")

# oracle_id -> set(tag label)
tag_map = {}
n_tags = 0
with gzip.open(TAGS, "rt") as f:
    for line in f:
        d = json.loads(line)
        label = (d.get("label") or "").strip()
        if not label or label.startswith("cycle-"):
            continue
        for t in d.get("taggings") or []:
            oid = t.get("oracle_id")
            if oid:
                tag_map.setdefault(oid, set()).add(label)
                n_tags += 1

records = [json.loads(l) for l in open(CARDS)]
n_hit = 0
for r in records:
    tags = sorted(tag_map.get(r["oracle_id"], set()))
    r["sf_tags"] = tags
    if tags:
        n_hit += 1

with open(CARDS, "w") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"tags total: {len(tag_map)} oracles, {n_tags} taggings")
print(f"cards with tags: {n_hit}/{len(records)}")
