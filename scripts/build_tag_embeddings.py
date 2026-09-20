#!/usr/bin/env python3
"""构建 SF 标签语义嵌入,供 /api/tags/semantic 用。

每个标签的嵌入文本 = 标签英文名 + tagdict 中文翻译 + 标签下 EDHREC 热度前 N 张卡的
中文名 + ai_desc(被这些卡用来概括自身功能的一句话,语义信息密度最高)。

输出 data/tag_embeddings.npz,字段:
  tags      — 标签英文名数组(与 vecs 行序一致)
  zh        — tagdict 翻译数组
  counts    — 该标签下的卡数(用作频率加权和展示)
  vecs      — N x 384 float32 矩阵(paraphrase-multilingual-MiniLM-L12-v2)

可重复运行;cards.jsonl / tagdict.txt 任意一个 mtime 更新都会触发重建(由 serve.py 端
检测,本脚本无需关心)。离线一次性跑完缓存好,在线查询时只做一次矩阵乘法。

用法:
  python3 scripts/build_tag_embeddings.py
"""
import argparse
import json
import os
import re
import sys
import time

import numpy as np
from fastembed import TextEmbedding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")
TAGDICT = os.path.join(ROOT, "data", "tagdict.txt")
OUT = os.path.join(ROOT, "data", "tag_embeddings.npz")
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 跟 serve.py 保持一致的 SF 标签过滤规则:纯 ascii、非 cycle-归属类噪声、长度 ≥ 3。
# 见 merge_tags.py 和 serve.py:/api/tags。
_TAG_BAD = re.compile(r"^cycle-", re.I)
SAMPLE_PER_TAG = 30     # 每标签参与描述拼接的代表卡数
DESC_CHARS = 220        # 每张卡 ai_desc 截取长度,避免描述文本过长


def load_tagdict():
    m = {}
    if os.path.exists(TAGDICT):
        with open(TAGDICT, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                m[k.strip()] = v.strip()
    return m


def gather_sf_tags():
    """{tag: [(oracle_id, edhrec_rank, name_zh, name_en, ai_desc)]}"""
    tag_to_cards = {}
    with open(CARDS, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            sf = c.get("sf_tags") or []
            if not sf:
                continue
            rec = (
                c["oracle_id"],
                c.get("edhrec_rank") or 9_999_999,
                c.get("name_zh") or "",
                c.get("name_en") or "",
                (c.get("ai_desc") or "")[:DESC_CHARS],
            )
            for t in sf:
                if (not t.isascii()) or t != t.strip() or len(t) < 3:
                    continue
                if _TAG_BAD.match(t):
                    continue
                tag_to_cards.setdefault(t, []).append(rec)
    return tag_to_cards


def build_texts(tag_to_cards, td):
    """组装 (tag, zh, count, embed_text) 列表。"""
    out = []
    for tag, cards in tag_to_cards.items():
        cards.sort(key=lambda r: (r[1], r[0]))
        sample = cards[:SAMPLE_PER_TAG]
        zh = td.get(tag) or ""
        head = f"Tag: {tag}\n中文: {zh}" if zh else f"Tag: {tag}"
        # 卡名/desc 拼接:中文名在前,英文名在后便于双语模型对齐
        card_lines = []
        for _, _, nz, ne, desc in sample:
            name = (nz + " / " + ne) if nz else ne
            line = f"- {name}"
            if desc:
                line += f": {desc}"
            card_lines.append(line)
        text = head + "\n代表卡(EDHREC 热度):\n" + "\n".join(card_lines)
        out.append((tag, zh, len(cards), text))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--sample", type=int, default=SAMPLE_PER_TAG,
                    help="每个标签采样多少张代表卡拼进描述")
    args = ap.parse_args()

    t0 = time.time()
    print("loading SF tag -> cards ...")
    tag_to_cards = gather_sf_tags()
    td = load_tagdict()
    print(f"  {len(tag_to_cards)} SF tags")

    records = build_texts(tag_to_cards, td)
    print(f"building texts: {len(records)} ...")

    print(f"loading model: {args.model}")
    model = TextEmbedding(args.model)

    BATCH = 64
    vecs = np.zeros((len(records), 384), dtype=np.float32)
    for i in range(0, len(records), BATCH):
        chunk = [r[3] for r in records[i:i + BATCH]]
        emb = list(model.embed(chunk))
        for j, e in enumerate(emb):
            v = np.asarray(e, dtype=np.float32)
            v /= (np.linalg.norm(v) + 1e-9)  # 单位向量,cosine 直接 = 点积
            vecs[i + j] = v
        print(f"  embedded {min(i + BATCH, len(records))}/{len(records)}", flush=True)

    tags = np.array([r[0] for r in records])
    zh = np.array([r[1] for r in records])
    counts = np.array([r[2] for r in records], dtype=np.int32)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.savez_compressed(args.out, tags=tags, zh=zh, counts=counts, vecs=vecs)
    dt = time.time() - t0
    print(f"wrote {args.out} ({len(records)} tags, {vecs.nbytes / 1e6:.1f} MB vec, {dt:.1f}s)")


if __name__ == "__main__":
    main()