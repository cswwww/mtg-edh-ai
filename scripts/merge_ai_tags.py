#!/usr/bin/env python3
"""把 AI 生成的一行话功能定位(data/tags.jsonl)合并进 data/cards.jsonl。

最终只合并 ai_desc(用户定稿:只保留 1 个 AI 字段)。

兼容:ai_tags / ai_synergy 字段也合入(展示用,历史遗留)。

- 输入: data/tags.jsonl(LLM 输出,可能含重复行和未完成标记)
- 去重: 同一 oracle_id 保留最后一行;只保留 ok=true 且 ai_desc 非空
- 输出: 原地更新 cards.jsonl;先写 .tmp 再替换
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")
TAGS = os.path.join(ROOT, "data", "tags.jsonl")

KEYS_TO_MERGE = ("ai_desc", "ai_tags", "ai_synergy")

# oracle_id -> 最后一行有效结果
tag_map = {}
n_lines = 0
if os.path.exists(TAGS):
    with open(TAGS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            oid = d.get("oracle_id")
            if not oid:
                continue
            if not d.get("ok", True) or not d.get("ai_desc"):
                continue  # 失败或空 desc,跳过
            tag_map[oid] = d
print(f"tags.jsonl 行数={n_lines}, 有效 oracle={len(tag_map)}")

records = []
n_hit = 0
with open(CARDS, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        t = tag_map.get(r.get("oracle_id"))
        if t:
            for k in KEYS_TO_MERGE:
                v = t.get(k)
                if v is not None:
                    if k == "ai_desc" and isinstance(v, str):
                        r[k] = v
                    elif k in ("ai_tags", "ai_synergy"):
                        r[k] = v if isinstance(v, list) else []
            n_hit += 1
        records.append(r)

tmp = CARDS + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
os.replace(tmp, CARDS)
print(f"合并完成: {n_hit}/{len(records)} 张卡带 ai_desc")