#!/usr/bin/env python3
"""把 AI 生成的结构化元数据(data/tags.jsonl)合并进 data/cards.jsonl。

- 输入: data/tags.jsonl(LLM 输出,可能含重复行和未完成标记)
- 去重: 同一 oracle_id 保留最后一行;只保留完整的(ai_desc 非空且 ok=true)
- 输出: 原地更新 cards.jsonl,合并以下字段:
    ai_desc, ai_deck_role, ai_strategy, ai_countermeta, ai_phase,
    ai_theme_keywords, ai_tags, ai_synergy
- 安全: 只增改 AI 字段,不动其他数据;cards.jsonl 先写 .tmp 再替换
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")
TAGS = os.path.join(ROOT, "data", "tags.jsonl")

EMPTY_COUNTER = {"answers": [], "weak_to": []}
# tags.jsonl 中拿到的 key → cards.jsonl 中要写入的 key
KEYS_TO_MERGE = (
    "ai_desc", "ai_deck_role", "ai_strategy",
    "ai_countermeta", "ai_phase", "ai_theme_keywords",
    "ai_tags", "ai_synergy",
)

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
            # 跳过失败占位行(没有任何 ai_desc 内容)
            if not d.get("ok", True) and not d.get("ai_desc"):
                continue
            # 跳过未升级的旧 schema(只有 ai_tags/ai_desc,没有新字段)
            has_new_schema = (
                d.get("ai_deck_role") is not None
                or d.get("ai_countermeta") is not None
                or d.get("ai_phase") is not None
            )
            if not has_new_schema:
                continue
            # 字段兜底
            d.setdefault("ai_desc", "")
            d.setdefault("ai_deck_role", [])
            d.setdefault("ai_strategy", [])
            d.setdefault("ai_countermeta", EMPTY_COUNTER)
            d.setdefault("ai_phase", "any")
            d.setdefault("ai_theme_keywords", [])
            d.setdefault("ai_tags", [])
            d.setdefault("ai_synergy", [])
            # countermeta 字段兜底
            cm = d["ai_countermeta"]
            if not isinstance(cm, dict):
                cm = EMPTY_COUNTER
            cm.setdefault("answers", [])
            cm.setdefault("weak_to", [])
            d["ai_countermeta"] = cm
            tag_map[oid] = d
print(f"tags.jsonl 行数={n_lines}, 有效 oracle(含新 schema)={len(tag_map)}")

records = []
n_hit = 0
with open(CARDS, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        t = tag_map.get(r.get("oracle_id"))
        if t:
            for k in KEYS_TO_MERGE:
                v = t.get(k)
                # ai_desc 空字符串保留空(老字段旧值会被覆盖)
                if k == "ai_desc":
                    r[k] = v if isinstance(v, str) else ""
                else:
                    r[k] = v if v else (r.get(k) if isinstance(r.get(k), (list, dict)) else ([] if isinstance(r.get(k), list) or k != "ai_countermeta" else EMPTY_COUNTER))
            n_hit += 1
        records.append(r)

tmp = CARDS + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
os.replace(tmp, CARDS)
print(f"合并完成: {n_hit}/{len(records)} 张卡带 AI 元数据")