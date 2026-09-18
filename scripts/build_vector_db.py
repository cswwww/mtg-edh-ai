#!/usr/bin/env python3
"""构建 LanceDB 卡牌向量库。

- 输入: data/cards.jsonl
- 输出: data/vectordb/cards.lance
- 嵌入: paraphrase-multilingual-MiniLM-L12-v2 (384d, 中英双语)
- 同时保存全部结构化字段 + 原始 JSON,便于过滤与回取
"""
import json
import os

import lancedb
import numpy as np
import pyarrow as pa
from fastembed import TextEmbedding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "data", "cards.jsonl")
DB_DIR = os.environ.get("MTG_DB_DIR", os.path.join(ROOT, "data", "vectordb"))
TABLE = "cards"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BATCH = 512

os.makedirs(DB_DIR, exist_ok=True)


def embed_text(r):
    """组装用于嵌入的中英双语文本。"""
    parts = []
    name = " / ".join(x for x in [r.get("name_zh"), r.get("name_en")] if x)
    parts.append(name)
    tl = " | ".join(x for x in [r.get("type_line_zh"), r.get("type_line_en")] if x)
    if tl:
        parts.append(tl)
    if r.get("mana_cost"):
        parts.append(f"费用 {r['mana_cost']} 法术力值 {r.get('cmc')}")
    if r.get("keywords"):
        parts.append("关键词 " + ", ".join(r["keywords"]))
    if r.get("sf_tags"):
        parts.append("功能标签 " + ", ".join(r["sf_tags"]))
    # AI 功能定位是语义检索的核心:一句话说清这张卡是干什么的
    if r.get("ai_desc"):
        parts.append("功能定位: " + r["ai_desc"])
    # AI 结构化元数据(来自 tag_cards.py)
    # - deck_role / strategy / theme_keywords 进嵌入,提升"找这类卡"的召回
    # - countermeta / phase 是 meta 信息,不进嵌入(不影响"这张卡是什么")
    if r.get("ai_deck_role"):
        parts.append("卡组角色 " + " ".join(r["ai_deck_role"]))
    if r.get("ai_strategy"):
        parts.append("策略主题 " + " ".join(r["ai_strategy"]))
    if r.get("ai_theme_keywords"):
        parts.append("俗称联想 " + " ".join(r["ai_theme_keywords"]))
    if r.get("ai_tags"):
        parts.append("AI标签 " + ", ".join(r["ai_tags"]))

    def add_block(tag, zh, en):
        block = "\n".join(x for x in [zh, en] if x)
        if block:
            parts.append(f"[{tag}]\n{block}" if tag else block)

    if r["faces"]:
        for fc in r["faces"]:
            fn = " / ".join(x for x in [fc.get("name_zh"), fc.get("name_en")] if x)
            ft = " | ".join(x for x in [fc.get("type_zh"), fc.get("type_en")] if x)
            body = []
            if ft:
                body.append(ft)
            if fc.get("mana_cost"):
                body.append(f"费用 {fc['mana_cost']}")
            body += [x for x in [fc.get("text_zh"), fc.get("text_en")] if x]
            parts.append(f"【{fn}】\n" + "\n".join(body))
    else:
        add_block("", r.get("oracle_text_zh"), r.get("oracle_text_en"))
    return "\n".join(parts)


def main():
    records = [json.loads(l) for l in open(IN)]
    print(f"records: {len(records)}")

    texts = [embed_text(r) for r in records]
    model = TextEmbedding(MODEL_NAME)

    db = lancedb.connect(DB_DIR)
    tbl, start = None, 0
    done = False
    if TABLE in db.table_names():
        existing = db.open_table(TABLE)
        cnt = existing.count_rows()
        if cnt >= len(records):
            print("embeddings already complete")
            tbl, done = existing, True
        elif cnt > 0:
            print(f"resume from {cnt}")
            tbl, start = existing, cnt
        else:
            db.drop_table(TABLE)
    if tbl is None:
        schema = pa.schema([
            pa.field("vector", pa.list_(pa.float32(), 384)),
            pa.field("oracle_id", pa.string()),
            pa.field("name_en", pa.string()),
            pa.field("name_zh", pa.string()),
            pa.field("text", pa.string()),          # 嵌入用全文
            pa.field("colors", pa.string()),        # 如 "B R"
            pa.field("color_identity", pa.string()),
            pa.field("cmc", pa.float64()),
            pa.field("mana_cost", pa.string()),
            pa.field("type_line_en", pa.string()),
            pa.field("type_line_zh", pa.string()),
            pa.field("rarity", pa.string()),
            pa.field("layout", pa.string()),
            pa.field("is_dfc", pa.bool_()),
            pa.field("commander_legal", pa.string()),
            pa.field("edhrec_rank", pa.int64()),
            pa.field("keywords", pa.list_(pa.string())),
        pa.field("sf_tags", pa.list_(pa.string())),
            pa.field("power", pa.string()),
            pa.field("toughness", pa.string()),
            pa.field("set_code", pa.string()),
            pa.field("released_at", pa.string()),
            pa.field("image_url", pa.string()),
            pa.field("card", pa.string()),          # 完整原始 JSON
        ])
        tbl = db.create_table(TABLE, schema=schema)

    n = len(records)
    if not done:
        for i in range(start, n, BATCH):
            batch_recs = records[i:i + BATCH]
            vecs = list(model.embed(texts[i:i + BATCH]))
            rows = []
            for r, v, t in zip(batch_recs, vecs, texts[i:i + BATCH]):
                leg = r.get("legalities") or {}
                rows.append({
                    "vector": np.asarray(v, dtype=np.float32),
                    "oracle_id": r["oracle_id"],
                    "name_en": r.get("name_en"),
                    "name_zh": r.get("name_zh"),
                    "text": t,
                    "colors": " ".join(r.get("colors") or []),
                    "color_identity": " ".join(r.get("color_identity") or []),
                    "cmc": r.get("cmc"),
                    "mana_cost": r.get("mana_cost"),
                    "type_line_en": r.get("type_line_en"),
                    "type_line_zh": r.get("type_line_zh"),
                    "rarity": r.get("rarity"),
                    "layout": r.get("layout"),
                    "is_dfc": bool(r.get("is_dfc")),
                    "commander_legal": leg.get("commander"),
                    "edhrec_rank": r.get("edhrec_rank"),
                    "keywords": r.get("keywords") or [],
                    "sf_tags": r.get("sf_tags") or [],
                    "power": r.get("power"),
                    "toughness": r.get("toughness"),
                    "set_code": r.get("set_code"),
                    "released_at": r.get("released_at"),
                    "image_url": r.get("image_url"),
                    "card": json.dumps(r, ensure_ascii=False),
                })
            tbl.add(rows)
            print(f"{min(i + BATCH, n)}/{n}", flush=True)

    for fld in ("name_en", "name_zh", "text"):
        tbl.create_fts_index(fld, replace=True)
    print("done. rows:", tbl.count_rows())


if __name__ == "__main__":
    main()
