#!/usr/bin/env python3
"""v2 prompt 试跑:挑 2-3 张典型卡单条跑,对比新旧 ai_desc,不动 tags.jsonl。"""
import sys
import json

sys.path.insert(0, "scripts")
import tag_cards as tc  # noqa: E402  # 复用 SYSTEM/card_text/parse_batch_result/call_llm

SAMPLES = ["Sol Ring", "Cyclonic Rift", "Craterhoof Behemoth"]
cards_map = {json.loads(l)["name_en"]: json.loads(l) for l in open("data/cards.jsonl")}
samples = [cards_map[n] for n in SAMPLES if n in cards_map]
if not samples:
    sys.exit(f"未找到样本卡: {SAMPLES}")

print(f"model={tc.cfg['model']}  base={tc.cfg['base_url']}")
print(f"样本: {[s['name_en'] for s in samples]}\n")

for r in samples:
    print("=" * 72)
    print(f"CARD: {r['name_en']} / {r.get('name_zh', '')}")
    print(f"费用: {r.get('mana_cost') or '无'}  类型: {(r.get('type_line_en') or '').splitlines()[0]}")
    ot = (r.get("oracle_text_en") or "").replace("\n", " / ")
    print(f"oracle: {ot}")
    print(f"旧 ai_desc: {r.get('ai_desc') or '(空)'}")
    print("--- v2 ---")
    user_prompt = "请为以下万智牌卡牌生成一句话功能定位:\n\n" + tc.card_text(1, r)
    raw = tc.call_llm(user_prompt, max_tokens=400)
    parsed = tc.parse_batch_result(raw, [r])
    new_desc = parsed.get(r["oracle_id"], {}).get("ai_desc")
    if not new_desc:
        print(f"new_desc: <解析失败>  原始输出片段: {(raw or '')[:200]!r}")
    else:
        print(f"new_desc: {new_desc}")
    print()