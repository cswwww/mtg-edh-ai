#!/usr/bin/env python3
"""从 Scryfall all_cards 提取中文(zhs)印张索引,按 oracle_id 归并。

输出 data/raw/scryfall_zhs.json:
{ oracle_id: {
    "name": 中文全名("A // B"),
    "faces": [{name, type, text, flavor, image}]  # 单面卡只有一项
    "image": 正面图,
    "set_code": ..., "collector_number": ...
} }
同时输出 data/raw/scryfall_en_text.json: { oracle_id: oracle_text } 作为英文兜底。
"""
import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

zhs = {}
en_text = {}


def face_from(cf):
    return {
        "name": cf.get("printed_name"),
        "type": cf.get("printed_type_line"),
        "text": cf.get("printed_text"),
        "flavor": cf.get("flavor_text"),
        "image": (cf.get("image_uris") or {}).get("normal"),
    }


with gzip.open(os.path.join(RAW, "all-cards.jsonl.gz"), "rt") as f:
    for line in f:
        c = json.loads(line)
        if c.get("object") != "card":
            continue
        oid = c.get("oracle_id")
        if not oid:
            continue
        if c.get("lang") == "zhs" and oid not in zhs:
            rec = {"set_code": c.get("set"), "collector_number": c.get("collector_number")}
            if c.get("card_faces"):
                rec["name"] = " // ".join(
                    cf.get("printed_name") or "" for cf in c["card_faces"])
                rec["faces"] = [face_from(cf) for cf in c["card_faces"]]
                rec["image"] = (c.get("image_uris") or {}).get("normal") \
                    or rec["faces"][0].get("image")
            else:
                rec["name"] = c.get("printed_name")
                rec["faces"] = [{
                    "name": c.get("printed_name"),
                    "type": c.get("printed_type_line"),
                    "text": c.get("printed_text"),
                    "flavor": c.get("flavor_text"),
                    "image": (c.get("image_uris") or {}).get("normal"),
                }]
                rec["image"] = (c.get("image_uris") or {}).get("normal")
            zhs[oid] = rec
        elif c.get("lang") == "en" and oid not in en_text:
            en_text[oid] = c.get("oracle_text")

json.dump(zhs, open(os.path.join(RAW, "scryfall_zhs.json"), "w"), ensure_ascii=False)
json.dump(en_text, open(os.path.join(RAW, "scryfall_en_text.json"), "w"), ensure_ascii=False)
print("zhs oracles:", len(zhs), " en text oracles:", len(en_text))
