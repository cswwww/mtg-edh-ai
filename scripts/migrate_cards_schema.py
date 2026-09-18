#!/usr/bin/env python3
"""迁移 cards.jsonl schema:给每张卡加新 AI 字段默认值(保留旧 ai_desc/ai_tags/ai_synergy)。

执行后,每行都保证 8 个 AI 字段完整(空值或旧值):
  ai_desc, ai_tags, ai_synergy,
  ai_deck_role=[], ai_strategy=[], ai_countermeta={answers:[], weak_to:[]},
  ai_phase='any', ai_theme_keywords=[]

用法: python3 scripts/migrate_cards_schema.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")

EMPTY_COUNTER = {"answers": [], "weak_to": []}


def main():
    tmp = CARDS + ".tmp"
    n = 0
    n_filled = 0
    with open(CARDS, encoding="utf-8") as fin, open(tmp, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            n += 1
            changed = False
            # 旧字段补默认
            if "ai_desc" not in r:
                r["ai_desc"] = ""; changed = True
            if "ai_tags" not in r or not isinstance(r["ai_tags"], list):
                r["ai_tags"] = [] if not isinstance(r.get("ai_tags"), list) else r["ai_tags"]; changed = True
            if "ai_synergy" not in r or not isinstance(r["ai_synergy"], list):
                r["ai_synergy"] = [] if not isinstance(r.get("ai_synergy"), list) else r["ai_synergy"]; changed = True
            # 新字段补默认
            if "ai_deck_role" not in r or r["ai_deck_role"] is None:
                r["ai_deck_role"] = []; changed = True
            if "ai_strategy" not in r or r["ai_strategy"] is None:
                r["ai_strategy"] = []; changed = True
            if "ai_countermeta" not in r or not isinstance(r["ai_countermeta"], dict):
                r["ai_countermeta"] = EMPTY_COUNTER; changed = True
            else:
                cm = r["ai_countermeta"]
                cm.setdefault("answers", [])
                cm.setdefault("weak_to", [])
            if "ai_phase" not in r or not r["ai_phase"]:
                r["ai_phase"] = "any"; changed = True
            if "ai_theme_keywords" not in r or r["ai_theme_keywords"] is None:
                r["ai_theme_keywords"] = []; changed = True
            if changed:
                n_filled += 1
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, CARDS)
    print(f"迁移完成: {n} 张卡, {n_filled} 张补了新字段")


if __name__ == "__main__":
    main()