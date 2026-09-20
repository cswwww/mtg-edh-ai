#!/usr/bin/env python3
"""迁移 cards.jsonl schema:清理 AI 历史死字段,只保留 ai_desc + ai_tags + ai_synergy。

死字段(全部 AI 新字段)会被删除:
  ai_deck_role, ai_strategy, ai_phase, ai_countermeta, ai_theme_keywords

用法: python3 scripts/migrate_cards_schema.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")

# 历史死字段(用户决定不再生产)
DEAD_FIELDS = ("ai_deck_role", "ai_strategy", "ai_phase",
               "ai_countermeta", "ai_theme_keywords")


def main():
    tmp = CARDS + ".tmp"
    n = 0
    n_cleaned = 0
    with open(CARDS, encoding="utf-8") as fin, open(tmp, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            n += 1
            changed = False
            # 删死字段
            for dead in DEAD_FIELDS:
                if dead in r:
                    del r[dead]; changed = True
            # 补 3 个核心 AI 字段兜底
            if "ai_desc" not in r:
                r["ai_desc"] = ""; changed = True
            if "ai_tags" not in r or not isinstance(r["ai_tags"], list):
                r["ai_tags"] = r.get("ai_tags") if isinstance(r.get("ai_tags"), list) else []; changed = True
            if "ai_synergy" not in r or not isinstance(r["ai_synergy"], list):
                r["ai_synergy"] = r.get("ai_synergy") if isinstance(r.get("ai_synergy"), list) else []; changed = True
            if changed:
                n_cleaned += 1
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, CARDS)
    print(f"迁移完成: {n} 张卡, {n_cleaned} 张动了字段")
    print(f"已删死字段: {', '.join(DEAD_FIELDS)}")


if __name__ == "__main__":
    main()