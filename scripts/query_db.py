#!/usr/bin/env python3
"""查询本地卡牌向量库。

用法:
  python3 query_db.py "中文或英文描述" [-n 10] [--colors BR] [--type 生物]
      [--cmc-max 3] [--commander] [--no-dfc] [--keyword 飞兵]

示例:
  python3 query_db.py "进场时从坟墓场回手的生物" -n 8 --colors B
  python3 query_db.py "draw cards when creatures die" --commander
"""
import argparse
import json
import os

import lancedb
from fastembed import TextEmbedding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(ROOT, "data", "vectordb")
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--colors", help="如 BR(黑红), 留空无色")
    ap.add_argument("--type", help="类型行关键词,如 生物 / Creature / 地")
    ap.add_argument("--cmc-max", type=float)
    ap.add_argument("--cmc-min", type=float)
    ap.add_argument("--commander", action="store_true", help="仅指挥官合法")
    ap.add_argument("--no-dfc", action="store_true")
    ap.add_argument("--keyword")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = ap.parse_args()

    model = TextEmbedding(MODEL_NAME)
    qv = next(iter(model.embed([args.query])))

    db = lancedb.connect(DB_DIR)
    tbl = db.open_table("cards")

    where = []
    if args.commander:
        where.append("commander_legal = 'legal'")
    if args.no_dfc:
        where.append("is_dfc = false")
    if args.colors is not None:
        # color_identity 为空格分隔字符串(如 "B R"),按单字母包含匹配
        for ch in args.colors.upper():
            where.append(f"color_identity LIKE '%{ch}%'")
    if args.cmc_max is not None:
        where.append(f"cmc <= {args.cmc_max}")
    if args.cmc_min is not None:
        where.append(f"cmc >= {args.cmc_min}")
    if args.type:
        t = args.type.replace("'", "")
        where.append(f"(type_line_en LIKE '%{t}%' OR type_line_zh LIKE '%{t}%')")
    if args.keyword:
        k = args.keyword.replace("'", "")
        where.append(f"array_contains(keywords, '{k}')")

    q = tbl.search(qv).metric("cosine").limit(args.n)
    if where:
        q = q.where(" AND ".join(where))
    res = q.to_list()

    cols = ["oracle_id", "name_zh", "name_en", "type_line_zh", "type_line_en",
            "cmc", "mana_cost", "colors", "commander_legal", "edhrec_rank",
            "image_url", "_distance"]
    for i, r in enumerate(res, 1):
        if args.json:
            print(json.dumps(r["card"], ensure_ascii=False))
            continue
        zh = r.get("name_zh") or ""
        en = r.get("name_en") or ""
        print(f"{i:2}. {zh} / {en}")
        print(f"    {r.get('type_line_zh') or r.get('type_line_en')}  "
              f"CMC {r.get('cmc')}  [{r.get('colors') or '无色'}]  "
              f"EDH {(r.get('edhrec_rank') or 0):>6}  d={r.get('_distance'):.3f}")


if __name__ == "__main__":
    main()
