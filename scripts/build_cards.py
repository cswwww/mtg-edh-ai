#!/usr/bin/env python3
"""三源合并:mtgch 中文数据 + mtgch 详情(双面卡) + Scryfall(zhs 印张/英文基准)
生成统一卡牌库 data/cards.jsonl(oracle 级别)。
"""
import gzip
import html
import json
import os
import re
import glob
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "cards.jsonl")

SETS = {s["code"]: s for s in json.load(open(os.path.join(RAW, "sets.json")))}
ZHS = json.load(open(os.path.join(RAW, "scryfall_zhs.json")))
EN_TEXT = json.load(open(os.path.join(RAW, "scryfall_en_text.json")))


def clean_html(s):
    """mtgch HTML -> 纯文本,保留 {X} 法术力符号。"""
    if not s:
        return None
    s = re.sub(r'<i class="ms[^"]*"[^>]*>\s*<i class="sr-only">([^<]*)</i>\s*</i>',
               r"\1", s)
    s = re.sub(r'<i class="sr-only">([^<]*)</i>', r"\1", s)
    s = re.sub(r"</p>\s*<p>", "\n", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>|<p>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s or None


def clean_zh_type(t):
    if not t:
        return None
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip() or None


def _pt(fo):
    p, t = fo.get("power"), fo.get("toughness")
    if p is not None and t is not None:
        return f"{p}/{t}"
    return fo.get("loyalty") or fo.get("defense")


def name_initials(zh):
    """中文名 -> 拼音首字母(如 罗堰妖精 -> lyyj),供首字母搜索。"""
    if not zh:
        return ""
    from pypinyin import lazy_pinyin, Style
    return "".join(ch for ch in lazy_pinyin(zh, style=Style.INITIALS, strict=False)
                   if ch.isalpha()).lower()


def main():
    # ---------- 1. mtgch view=1 按 oracle 分组 ----------
    by_oracle = defaultdict(list)
    for f in glob.glob(os.path.join(RAW, "mtgch_sets", "*.json")):
        d = json.load(open(f))
        for c in d["items"]:
            by_oracle[c["oracle_id"]].append(c)

    def rep_key(c):
        s = SETS.get(c["set"], {})
        return (bool(c.get("display_name_zh")), s.get("released_at") or "")

    # ---------- 2. Scryfall oracle_cards ----------
    sf = {}
    with gzip.open(os.path.join(RAW, "oracle-cards.jsonl.gz"), "rt") as f:
        for line in f:
            c = json.loads(line)
            sf[c["oracle_id"]] = c

    # ---------- 3. mtgch 详情 ----------
    details = {}
    for f in glob.glob(os.path.join(RAW, "mtgch_details", "*.json")):
        d = json.load(open(f))
        details[d["oracle_id"]] = d

    records = []
    n_zh = n_zh_text = n_faces_detail = n_faces_zhs = 0
    for oid, prints in by_oracle.items():
        prints.sort(key=rep_key, reverse=True)
        best = prints[0]
        s = sf.get(oid)
        z = ZHS.get(oid)
        d = details.get(oid)

        set_codes = sorted({p["set"] for p in prints})
        # 卡图优先级: 中文卡图(mtgh zhs 代理) > Scryfall 简中印张图 > 英文兜底
        zhs_img = next((p["image_url"] for p in prints
                        if p.get("image_url") and "/zhs/" in p["image_url"]), None)
        rec = {
            "oracle_id": oid,
            "name_en": (s or {}).get("name") or best.get("display_name"),
            "name_zh": best.get("display_name_zh") or (z or {}).get("name"),
            "name_py": name_initials(best.get("display_name_zh") or (z or {}).get("name")),
            "layout": (s or {}).get("layout"),
            "is_dfc": bool(best.get("is_double_faced")),
            "cmc": (s or {}).get("cmc"),
            "colors": (s or {}).get("colors"),
            "color_identity": (s or {}).get("color_identity"),
            "keywords": (s or {}).get("keywords") or [],
            "mana_cost": (s or {}).get("mana_cost"),
            "type_line_en": (s or {}).get("type_line"),
            "type_line_zh": clean_zh_type(best.get("display_type_line"))
                            or ((z or {}).get("faces") or [{}])[0].get("type"),
            "oracle_text_en": (s or {}).get("oracle_text") or EN_TEXT.get(oid),
            "oracle_text_zh": clean_html(best.get("oracle_text_html"))
                              or ((z or {}).get("faces") or [{}])[0].get("text"),
            "flavor_text_zh": clean_html(best.get("flavor_text_html"))
                              or ((z or {}).get("faces") or [{}])[0].get("flavor"),
            "power": (s or {}).get("power"),
            "toughness": (s or {}).get("toughness"),
            "loyalty": (s or {}).get("loyalty"),
            "defense": (s or {}).get("defense"),
            "produced_mana": (s or {}).get("produced_mana"),
            "legalities": (s or {}).get("legalities"),
            "edhrec_rank": (s or {}).get("edhrec_rank"),
            "prices": (s or {}).get("prices"),
            "rarity": best.get("rarity"),
            "set_code": best.get("set"),
            "collector_number": best.get("collector_number"),
            "released_at": SETS.get(best["set"], {}).get("released_at"),
            "image_url": zhs_img or (z or {}).get("image") or best.get("image_url"),
            "art_crop": best.get("art_crop"),
            "all_sets": set_codes,
            "faces": [],
            # AI 结构化元数据: 由 tag_cards.py 写入 tags.jsonl, merge_ai_tags.py 合入
            # 这些字段在 build_cards.py 阶段先以空值占位,保证下游管线 schema 稳定
            "ai_desc": "",                       # 40-60 字功能定位(嵌入核心)
            "ai_tags": [],                       # 历史遗留(展示用,不再生产)
            "ai_synergy": [],                    # 历史遗留(展示用,不再生产)
        }

        sf_faces = ((s or {}).get("card_faces")) or []
        if rec["is_dfc"]:
            zh_names_v1 = {of.get("face_name"): of.get("display_name_zh")
                           for of in best.get("other_faces") or []}
            if best.get("display_name_zh"):
                zh_names_v1[None] = best["display_name_zh"]  # 正面
            if d:
                n_faces_detail += 1
                face_objs = [d] + list(d.get("other_faces") or [])
                zfaces = ((z or {}).get("faces")) or []
                seen_f = set()
                idx = 0
                for fo in face_objs:
                    fn = fo.get("face_name")
                    if not fn or fn in seen_f:
                        continue
                    seen_f.add(fn)
                    zf = zfaces[idx] if idx < len(zfaces) else {}
                    rec["faces"].append({
                        "name_en": fn,
                        "name_zh": zh_names_v1.get(fn) or zf.get("name")
                                  or fo.get("atomic_translated_name") or fo.get("zhs_face_name"),
                        "type_en": fo.get("type_line"),
                        "type_zh": fo.get("atomic_translated_type") or fo.get("zhs_type_line")
                                   or zf.get("type"),
                        "text_en": fo.get("oracle_text"),
                        "text_zh": fo.get("atomic_translated_text") or fo.get("zhs_text")
                                   or zf.get("text"),
                        "mana_cost": fo.get("mana_cost"),
                        "pt": fo.get("power_toughness_loyalty_defense") or _pt(fo),
                        "image": (fo.get("image_uris") or {}).get("normal") or zf.get("image"),
                    })
                    idx += 1
            elif z and z.get("faces"):
                # 无 mtgch 详情:用 Scryfall zhs 印张 + 英文卡面
                n_faces_zhs += 1
                for i, zf in enumerate(z["faces"]):
                    sf_f = sf_faces[i] if i < len(sf_faces) else {}
                    rec["faces"].append({
                        "name_en": sf_f.get("name") or zf.get("name"),
                        "name_zh": zf.get("name"),
                        "type_en": sf_f.get("type_line"),
                        "type_zh": zf.get("type"),
                        "text_en": sf_f.get("oracle_text"),
                        "text_zh": zf.get("text"),
                        "mana_cost": sf_f.get("mana_cost"),
                        "pt": _pt(sf_f) if sf_f else None,
                        "image": zf.get("image"),
                    })
            else:
                for i, sf_f in enumerate(sf_faces):
                    ofs = best.get("other_faces") or []
                    of1 = best if i == 0 else (ofs[i - 1] if i - 1 < len(ofs) else {})
                    rec["faces"].append({
                        "name_en": sf_f.get("name"),
                        "name_zh": zh_names_v1.get(sf_f.get("name"))
                                  or (of1 or {}).get("display_name_zh"),
                        "type_en": sf_f.get("type_line"),
                        "type_zh": (of1 or {}).get("display_type_line"),
                        "text_en": sf_f.get("oracle_text"),
                        "text_zh": None,
                        "mana_cost": sf_f.get("mana_cost"),
                        "pt": _pt(sf_f),
                        "image": (of1 or {}).get("image_url"),
                    })

        if rec["name_zh"]:
            n_zh += 1
        if rec["oracle_text_zh"] or any(fc.get("text_zh") for fc in rec["faces"]):
            n_zh_text += 1
        records.append(rec)

    records.sort(key=lambda r: (r["name_en"] or ""))
    with open(OUT, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(records)
    print(f"oracle records: {n}")
    print(f"with zh name: {n_zh} ({n_zh/n:.1%})")
    print(f"with zh text: {n_zh_text} ({n_zh_text/n:.1%})")
    print(f"dfc faces from detail: {n_faces_detail}, from zhs prints: {n_faces_zhs}")


if __name__ == "__main__":
    main()
