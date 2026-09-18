#!/usr/bin/env python3
"""卡牌库 API 服务:封装 LanceDB 向量检索 + 过滤 + 分页。

启动: python3 web/serve.py [--port 8103]
接口:
  GET /api/search?q=&mode=vector|fts&colors=W,B&cmc_min=&cmc_max=&type=&rarity=
      &commander=1&keyword=&page=1&page_size=60&sort=rel|edhrec|cmc_asc|cmc_desc|name
  GET /api/card/{oracle_id}
  GET /api/meta
"""
import argparse
import json
import os
import re
import urllib.request

import lancedb
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastembed import TextEmbedding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(ROOT, "data", "vectordb")
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

app = FastAPI(title="MTG CN Card DB")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = lancedb.connect(DB_DIR)
tbl = db.open_table("cards")
_model = None


def model():
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model


LIST_COLS = ["oracle_id", "name_en", "name_zh", "type_line_en", "type_line_zh",
             "cmc", "mana_cost", "colors", "color_identity", "rarity", "layout",
             "is_dfc", "edhrec_rank", "image_url", "power", "toughness",
             "set_code", "released_at", "commander_legal", "sf_tags", "keywords"]


# ---------------- 拼音首字母检索 ----------------
SLANG_FILE = os.path.join(ROOT, "data", "slang.txt")
_slang_map = None
_slang_mtime = 0.0


def slang_map():
    """黑话词典,从 data/slang.txt 懒加载;文件变了自动重读(无需重启)。"""
    global _slang_map, _slang_mtime
    try:
        mtime = os.path.getmtime(SLANG_FILE)
    except OSError:
        mtime = 0.0
    if _slang_map is None or mtime != _slang_mtime:
        m = {}
        if os.path.exists(SLANG_FILE):
            with open(SLANG_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    m[k.strip()] = v.strip()
        _slang_map = m
        _slang_mtime = mtime
    return _slang_map


def expand_query(q):
    """把查询里的黑话展开成描述性短语,供向量嵌入。

    返回 (扩展后文本, 命中的展开值列表);无命中时原样返回。
    长词优先:若「单向扫场」命中,则不再叠加其短子词「扫场」的展开,避免语义被稀释。
    """
    m = slang_map()
    keys = [k for k in m if k in q]
    keys = [k for k in keys if not any(k != o and k in o for o in keys)]
    extras = [m[k] for k in keys]
    return (q + " " + " ".join(extras)) if extras else q, extras


# ---------------- 标签筛选 ----------------
_tag_index = None
_ai_tag_counts = None
_sf_tag_counts = None


def tag_index():
    """{tag: set(oracle_id)},ai_tags + sf_tags 倒排索引,懒加载自 cards.jsonl。
    分别统计两类词频:筛选条只展示 Scryfall Tagger 社区标签(人工策划、准确),
    AI 标签保留在详情页展示并参与语义嵌入。"""
    global _tag_index, _ai_tag_counts, _sf_tag_counts
    if _tag_index is None:
        idx = {}
        ai_counts = {}
        sf_counts = {}
        with open(os.path.join(ROOT, "data", "cards.jsonl"), encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                ai = set(c.get("ai_tags") or [])
                sf = set(c.get("sf_tags") or [])
                for t in ai:
                    ai_counts[t] = ai_counts.get(t, 0) + 1
                for t in sf:
                    sf_counts[t] = sf_counts.get(t, 0) + 1
                for t in ai | sf:
                    idx.setdefault(t, set()).add(c["oracle_id"])
        _tag_index = idx
        _ai_tag_counts = ai_counts
        _sf_tag_counts = sf_counts
    return _tag_index


# ---------------- Tagger 标签中英对照 ----------------
TAGDICT_FILE = os.path.join(ROOT, "data", "tagdict.txt")
_tagdict = None
_tagdict_mtime = 0.0


def tagdict():
    """{英文标签: 中文},从 data/tagdict.txt 懒加载;文件变了自动重读。"""
    global _tagdict, _tagdict_mtime
    try:
        mtime = os.path.getmtime(TAGDICT_FILE)
    except OSError:
        mtime = 0.0
    if _tagdict is None or mtime != _tagdict_mtime:
        m = {}
        if os.path.exists(TAGDICT_FILE):
            with open(TAGDICT_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    m[k.strip()] = v.strip()
        _tagdict = m
        _tagdict_mtime = mtime
    return _tagdict


@app.get("/api/tagdict")
def tagdict_get():
    return {"items": [{"key": k, "value": v} for k, v in tagdict().items()]}


@app.put("/api/tagdict")
def tagdict_put(body: dict):
    items = body.get("items")
    if not isinstance(items, list):
        raise HTTPException(400, "items 必须是数组")
    lines = ["# Scryfall Tagger 标签中英对照",
             "# 每行一条:英文标签=中文,界面优先显示中文;未收录的标签原样显示英文",
             "# 保存后立即生效,无需重启"]
    seen = set()
    for it in items:
        k = str(it.get("key") or "").strip()
        v = str(it.get("value") or "").strip()
        if not k or not v or k in seen or "=" in k:
            continue
        seen.add(k)
        lines.append(f"{k}={v}")
    tmp = TAGDICT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, TAGDICT_FILE)
    tagdict()  # 立即重载
    return {"ok": True, "count": len(seen)}


@app.get("/api/slang")
def slang_get():
    return {"items": [{"key": k, "value": v} for k, v in slang_map().items()]}


@app.put("/api/slang")
def slang_put(body: dict):
    items = body.get("items")
    if not isinstance(items, list):
        raise HTTPException(400, "items 必须是数组")
    lines = ["# MTG 语义搜索黑话词典",
             "# 每行一条:黑话=展开描述(向量搜索时自动把黑话展开成描述再嵌入)",
             "# 以 # 开头的行是注释;保存后立即生效,无需重启"]
    seen = set()
    for it in items:
        k = str(it.get("key") or "").strip()
        v = str(it.get("value") or "").strip()
        if not k or not v or k in seen or "=" in k:
            continue
        seen.add(k)
        lines.append(f"{k}={v}")
    tmp = SLANG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, SLANG_FILE)
    slang_map()  # 立即重载
    return {"ok": True, "count": len(seen)}

_py_index = None


def pinyin_index():
    """[(name_py, oracle_id, edhrec_rank)],懒加载自 cards.jsonl。"""
    global _py_index
    if _py_index is None:
        idx = []
        with open(os.path.join(ROOT, "data", "cards.jsonl"), encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                if c.get("name_py"):
                    idx.append((c["name_py"], c["oracle_id"],
                                c.get("edhrec_rank") or 9_999_999))
        _py_index = idx
    return _py_index


def pinyin_hits(q):
    """中文牌名拼音首字母匹配:完全匹配 > 前缀 > 包含,各按 EDHREC 排名截断。"""
    s = "".join((q or "").lower().split())
    if not (2 <= len(s) <= 15) or not s.isalpha() or not s.isascii():
        return []
    exact, starts, contains = [], [], []
    for py, oid, rk in pinyin_index():
        if py == s:
            exact.append((rk, oid))
        elif py.startswith(s):
            starts.append((rk, oid))
        elif s in py:
            contains.append((rk, oid))
    exact.sort()
    starts.sort()
    contains.sort()
    return [oid for _, oid in exact[:30] + starts[:60] + contains[:60]]


# ---------------- 卡名模糊检索 ----------------
import difflib
import re as _re_name

_name_idx = None


def _norm_name(s):
    """小写 + 去掉非字母数字汉字,便于子串/模糊比较。"""
    return _re_name.sub(r"[^a-z0-9一-鿿]", "", (s or "").lower())


def name_index():
    """[(norm_en, norm_zh, en_tokens, oid, edhrec_rank)],懒加载自 cards.jsonl。"""
    global _name_idx
    if _name_idx is None:
        idx = []
        with open(os.path.join(ROOT, "data", "cards.jsonl"), encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                ne = _norm_name(c.get("name_en"))
                nz = _norm_name(c.get("name_zh"))
                toks = tuple(t for t in _re_name.split(r"[^a-z0-9]+", (c.get("name_en") or "").lower()) if t)
                idx.append((ne, nz, toks, c["oracle_id"],
                            c.get("edhrec_rank") or 9_999_999))
        _name_idx = idx
    return _name_idx


def name_hits(q, limit=80):
    """卡名三层匹配:精确/子串 > 英文分词前缀 > 模糊纠错(difflib)。"""
    s = _norm_name(q)
    if len(s) < 2:
        return []
    q_toks = tuple(t for t in _re_name.split(r"[^a-z0-9]+", q.lower()) if t)
    exact, subs, prefix = [], [], []
    fuzzy_pool = []
    for ne, nz, toks, oid, rk in name_index():
        hit_e, hit_z = s in ne, s in nz
        if hit_e or hit_z:
            if s == ne or s == nz:
                exact.append((rk, oid))
            else:
                pos = min([p for p in (ne.find(s), nz.find(s)) if p >= 0])
                subs.append((pos, rk, oid))
        elif q_toks and toks and len(q_toks) <= len(toks) and all(
                any(t.startswith(qt) for t in toks) for qt in q_toks):
            # 每个查询词都是某个名字词的前缀: "llan sen" -> Llanowar Sentinel
            prefix.append((rk, oid))
        else:
            fuzzy_pool.append((ne, oid))
            if nz:
                fuzzy_pool.append((nz, oid))
    exact.sort()
    subs.sort()
    prefix.sort()
    out = [oid for _, oid in exact[:20]]
    out += [oid for _, _, oid in subs[:40]]
    out += [oid for _, oid in prefix[:40]]
    # 模糊纠错:只在前两层没填满时跑(省时间),difflib 扫全库
    if len(out) < limit and fuzzy_pool:
        # 中文短词容错率低(3 字错 1 字约 0.67), cutoff 放宽;英文保持 0.72
        cutoff = 0.6 if any('一' <= ch <= '鿿' for ch in s) else 0.72
        close = difflib.get_close_matches(s, [n for n, _ in fuzzy_pool],
                                          n=limit, cutoff=cutoff)
        ratio = {n: difflib.SequenceMatcher(None, s, n).ratio() for n in close}
        ranked = sorted(((ratio[n], oid) for n, oid in fuzzy_pool if n in ratio),
                        reverse=True)
        out += [oid for _, oid in ranked[:limit - len(out)]]
    seen, uniq = set(), []
    for oid in out:
        if oid not in seen:
            seen.add(oid)
            uniq.append(oid)
        if len(uniq) >= limit:
            break
    return uniq


def build_where(colors, cmc_min, cmc_max, type_, rarity, commander, keyword, dfc, ci_mode="",
                color_field="ci", color_mode="within", cmc_sel="",
                cc_colors="", cc_colorless=0, cc_multi=0, cc_exclude=0, cc_partial=0,
                ci_colors="", ci_colorless=0):
    w = []
    if commander:
        w.append("commander_legal = 'legal'")
    ALL_C = "WUBRG"

    # ---- 卡牌颜色(cc):默认精确匹配;不含未选=子集;部分匹配=交集;无=包含无色牌 ----
    sel = [c for c in (cc_colors or "").upper() if c in ALL_C]
    if cc_multi:
        w.append("colors LIKE '% %'")  # 至少两个颜色
    if sel or cc_colorless:
        like = lambda f, c: f"{f} LIKE '%{c}%'"
        if cc_exclude:
            # 牌面色 ⊆ 所选:未选的色都不能出现
            cond = " AND ".join(f"NOT {like('colors', c)}" for c in ALL_C if c not in sel)
            if cc_colorless and cond:
                cond = f"(colors = '' OR {cond})"
        elif cc_partial:
            cond = " OR ".join(like('colors', c) for c in sel)
            if cc_colorless:
                cond = (f"({cond}) OR colors = ''") if cond else "colors = ''"
        else:
            # 精确匹配:colors 为排序空格拼接
            exact = " ".join(sorted(sel))
            cond = f"colors = '{exact}'"
            if cc_colorless:
                cond = f"(colors = '{exact}' OR colors = '')" if exact else "colors = ''"
        if cond:
            w.append(f"({cond})")

    # ---- 指挥官标识色(ci):标识色 ⊆ 所选(组牌约束);无色单独勾选 ----
    cis = [c for c in (ci_colors or "").upper() if c in ALL_C]
    if cis or ci_colorless:
        cond = " AND ".join(f"color_identity NOT LIKE '%{c}%'" for c in ALL_C if c not in cis)
        if ci_colorless and cond:
            cond = f"(color_identity = '' OR {cond})"
        if cond:
            w.append(f"({cond})")
    if cmc_sel.strip():
        vals = sorted({int(x) for x in cmc_sel.split(",") if x.strip().isdigit()})
        if vals:
            exact = [v for v in vals if v < 11]
            conds = []
            if exact:
                conds.append("cmc IN (" + ", ".join(map(str, exact)) + ")")
            if 11 in vals:
                conds.append("cmc >= 11")
            if conds:
                w.append("(" + " OR ".join(conds) + ")")
    if cmc_min is not None:
        w.append(f"cmc >= {float(cmc_min)}")
    if cmc_max is not None:
        w.append(f"cmc <= {float(cmc_max)}")
    if type_:
        # 多选为交集:牌必须同时属于所有选中类型(如 生物+神器 = 神器生物)。
        # 按英文类别行匹配(中文 LIKE 会把"法术"误中"法术师")
        ZH2EN = {"生物": "Creature", "法术": "Sorcery", "瞬间": "Instant",
                 "结界": "Enchantment", "神器": "Artifact", "地": "Land",
                 "鹏洛客": "Planeswalker"}
        for t in type_.split(","):
            t = t.strip().replace("'", "")
            if not t:
                continue
            en = ZH2EN.get(t, t)
            w.append(f"type_line_en LIKE '%{en}%'")
    if rarity:
        rs = [r.strip().replace("'", "") for r in rarity.split(",") if r.strip()]
        if len(rs) == 1:
            w.append(f"rarity = '{rs[0]}'")
        elif rs:
            w.append("rarity IN (" + ", ".join(f"'{r}'" for r in rs) + ")")
    if keyword:
        k = keyword.replace("'", "")
        w.append(f"array_contains(keywords, '{k}')")
    if dfc == "0":
        w.append("is_dfc = false")
    elif dfc == "1":
        w.append("is_dfc = true")
    return " AND ".join(w)


# 主搜索栏"分词直接搜类型":主类型/超类型的中英对照(副类别从 /api/types 数据动态取)
TYPE_ZH2EN = {"生物": "Creature", "法术": "Sorcery", "瞬间": "Instant", "结界": "Enchantment",
              "神器": "Artifact", "地": "Land", "鹏洛客": "Planeswalker",
              "战役": "Battle", "亲缘": "Kindred", "诡局": "Conspiracy", "地城": "Dungeon",
              "异象": "Phenomenon", "时空": "Plane", "邪计": "Scheme", "先锋": "Vanguard",
              "传奇": "Legendary", "基本": "Basic", "雪": "Snow", "持续": "Ongoing", "世界": "World"}


def map_type_tokens(q):
    """搜索词映射为类型 token(中文、英文、大小写均可),返回 token 列表;
    任一无法映射返回 None(回退语义搜索)。支持空格分词与中文连写切分
    ("传奇 人类"、"传奇人类"、"legendary human" 等效)。"""
    raw = q.strip()
    if not raw:
        return None
    subs = {s["t"]: s.get("zh") for s in all_types()["subtypes"]}
    zh2en = dict(TYPE_ZH2EN)
    for en, zh in subs.items():
        if zh:
            zh2en.setdefault(zh, en)

    # 路径一:整串贪心切分(支持中文连写,如"传奇人类"→传奇+人类)
    segs, i = [], 0
    names = sorted(zh2en.keys(), key=len, reverse=True)
    while i < len(raw):
        for n in names:
            if raw.startswith(n, i):
                segs.append(zh2en[n])
                i += len(n)
                break
        else:
            segs = None
            break
    if segs and len(segs) >= 2:
        return segs

    # 路径二:空格/逗号分词,逐词映射(中英文均可)
    toks = [t for t in re.split(r"[\s,，、]+", raw) if t]
    if len(toks) < 2:
        return None
    mapped = []
    for tok in toks:
        if tok in zh2en:
            mapped.append(zh2en[tok])
            continue
        tl = tok.lower()
        hit = next((en for en, zh in subs.items()
                    if en.lower() == tl or (zh and zh == tok)), None)
        if hit is None:
            hit = next((en for en in TYPE_ZH2EN.values() if en.lower() == tl), None)
        if hit is None:
            return None
        mapped.append(hit)
    return mapped


@app.get("/api/search")
def search(
    q: str = "",
    mode: str = "vector",          # vector | fts | none
    cmc_min: float = None,
    cmc_max: float = None,
    type_: str = Query("", alias="type"),
    rarity: str = "",
    commander: int = 0,
    keyword: str = "",
    dfc: str = "",
    # 卡牌颜色:默认精确;cc_exclude=不含未选(子集);cc_partial=部分匹配(交集)
    cc_colors: str = "",          # 牌面色多选,如 "W,U"
    cc_colorless: int = 0,        # 无(把无色牌也算进来)
    cc_multi: int = 0,            # 必须多色
    cc_exclude: int = 0,
    cc_partial: int = 0,
    # 指挥官标识色:标识色 ⊆ 所选
    ci_colors: str = "",
    ci_colorless: int = 0,
    tags: str = "",               # 标签筛选,逗号分隔,多选语义由 tag_mode 决定
    tag_mode: str = "and",        # and=交集(同时命中) | or=并集(命中任一)
    cmc_sel: str = "",            # 总法术力多选,逗号分隔,11 表示 11+
    max_dist: float = 0.55,   # 向量语义相关度阈值(cosine 距离,越小越相关)
    sort: str = "rel",
    page: int = 1,
    page_size: int = 60,
):
    type_direct = None
    if q.strip():
        m = map_type_tokens(q)
        if m:
            # 全部分词都映射为类型:走类型交集精确搜索,语义向量置空
            type_direct = m
            exist = [x.strip() for x in type_.split(",") if x.strip()]
            type_ = ",".join(exist + m)
            q = ""

    where = build_where("", cmc_min, cmc_max, type_, rarity, commander, keyword, dfc, "",
                        cmc_sel=cmc_sel,
                        cc_colors=cc_colors, cc_colorless=cc_colorless,
                        cc_multi=cc_multi, cc_exclude=cc_exclude, cc_partial=cc_partial,
                        ci_colors=ci_colors, ci_colorless=ci_colorless)
    page = max(1, page)
    page_size = min(200, max(1, page_size))

    # ---- 标签过滤:and=同时命中所有选中标签(交集);or=命中任一(并集) ----
    if tags.strip():
        sel = [t.strip() for t in tags.split(",") if t.strip()]
        idx = tag_index()
        if tag_mode == "or":
            oids = set()
            for t in sel:
                oids |= idx.get(t, set())
        else:
            oids = None
            for t in sel:
                s = idx.get(t, set())
                oids = s if oids is None else (oids & s)
                if not oids:
                    break
        if not oids:
            return {"total": 0, "page": page, "page_size": page_size, "items": []}
        id_list = ", ".join(f"'{o}'" for o in oids)
        where = (where + " AND " if where else "") + f"oracle_id IN ({id_list})"

    # ---- 混合检索:向量 + FTS 两路召回,RRF 融合(仅相关性排序时) ----
    if mode == "vector" and q.strip() and sort == "rel":
        eq, extras = expand_query(q)
        qv = next(iter(model().embed([eq])))
        vq = tbl.search(qv).metric("cosine").distance_range(
            upper_bound=min(1.0, max(0.05, max_dist)))
        if where:
            vq = vq.where(where)
        vrows = vq.limit(150).to_list()

        meta_rows = {r["oracle_id"]: r for r in vrows}
        scores = {}
        for rank, r in enumerate(vrows):
            scores[r["oracle_id"]] = scores.get(r["oracle_id"], 0.0) + 1.0 / (60 + rank + 1)
        try:
            fq = tbl.search(q, query_type="fts")
            if where:
                fq = fq.where(where)
            for rank, r in enumerate(fq.limit(150).to_list()):
                oid = r["oracle_id"]
                scores[oid] = scores.get(oid, 0.0) + 1.0 / (60 + rank + 1)
                if oid not in meta_rows:
                    r.pop("_distance", None)
                    meta_rows[oid] = r
        except Exception:
            pass  # FTS 路失败时退化为纯向量        # 拼音首字母路:纯字母短串(如 ygj -> 阳光戒)按中文名首字母召回
        py_ids = pinyin_hits(q)
        if py_ids:
            fetched = {}
            missing = [o for o in py_ids if o not in meta_rows]
            if missing:
                try:
                    id_list = ", ".join(f"'{o}'" for o in missing)
                    for r in (tbl.search()
                              .where(f"oracle_id IN ({id_list})")
                              .limit(len(missing)).to_list()):
                        r.pop("vector", None)
                        r.pop("card", None)
                        r.pop("text", None)
                        fetched[r["oracle_id"]] = r
                except Exception:
                    fetched = {}
            for rank, oid in enumerate(py_ids):
                row = meta_rows.get(oid) or fetched.get(oid)
                if row is None:
                    continue
                # 首字母命中是给确定性匹配,权重远高于语义路
                scores[oid] = scores.get(oid, 0.0) + 1.0 / (10 + rank + 1)
                meta_rows[oid] = row

        # 标签召回路:黑话展开文本中出现的 Tagger 标签名(支持多词标签如
        # "draw engine",英文按词边界匹配),把该标签下的全部卡直接注入召回
        # (向量召回对"单向/不对称"这类抽象限定词区分力弱,真卡常被挤出
        # top150,只能靠这条路拉回来),按标签内热度(edhrec rank)给 RRF
        # 基础分,交给短语加分排序。
        # 只认纯英文标签:中文标签多为 AI 标注噪声(生物/手牌/清场这类
        # 泛词会污染召回),且带空格等脏数据。
        if extras:
            idx = tag_index()
            eq_l = eq.lower()
            matched = [t for t in idx
                       if len(t) >= 3 and t == t.strip() and t.isascii()
                       and re.search(r"(?<![a-z0-9-])" + re.escape(t.lower())
                                     + r"(?![a-z0-9-])", eq_l) is not None]
            for tag in matched:
                tag_oids = idx[tag]
                missing = [o for o in tag_oids if o not in meta_rows]
                if missing:
                    try:
                        cond = "oracle_id IN (" + ", ".join(f"'{o}'" for o in missing) + ")"
                        if where:
                            cond = where + " AND " + cond
                        for r in (tbl.search().where(cond)
                                  .limit(len(missing)).to_list()):
                            r.pop("vector", None)
                            r.pop("card", None)
                            meta_rows[r["oracle_id"]] = r
                    except Exception:
                        pass
                for rank, oid in enumerate(tag_oids):
                    if oid in meta_rows:
                        # 0.5 主体分:命中的黑话对应某个 Tagger 概念时,
                        # 带该标签的卡应整体压过只靠向量/短语分的泛匹配卡;
                        # 1/(30+rank) 按标签内热度(edhrec)细分先后
                        scores[oid] = (scores.get(oid, 0.0) + 0.5
                                       + 1.0 / (30 + rank + 1))

        # 黑话展开的确定性加分:卡片嵌入文本命中的展开短语越多,排得越前。
        # 解决"轮子"混入群体弃牌卡的问题——两者都含"弃掉手牌",
        # 但只有真 wheel 卡同时命中"抓七张/wheel/重抽"。
        if extras:
            toks = [t for v in extras for t in v.split() if len(t) >= 2]
            if toks:
                for oid, row in meta_rows.items():
                    txt = row.get("text") or ""
                    hits = sum(1 for t in toks if t in txt)
                    if hits:
                        scores[oid] = scores.get(oid, 0.0) + 0.05 * min(hits, 3)

        fused = sorted(scores, key=scores.get, reverse=True)
        total = len(fused)
        page_ids = fused[(page - 1) * page_size: page * page_size]
        rows = [meta_rows[oid] for oid in page_ids]
        for r in rows:
            r.pop("vector", None)
            r.pop("card", None)
            r.pop("text", None)
        return {"total": total, "page": page, "page_size": page_size,
                "items": rows, "hybrid": True}

    # 卡名模式:拼音首字母 + 三层卡名匹配(子串/前缀/模糊),FTS 殿后
    if mode == "fts" and q.strip():
        ordered_ids = pinyin_hits(q)
        have = set(ordered_ids)
        for oid in name_hits(q):
            if oid not in have:
                have.add(oid)
                ordered_ids.append(oid)
        if ordered_ids:
            id_list = ", ".join(f"'{o}'" for o in ordered_ids)
            cond = (where + " AND " if where else "") + f"oracle_id IN ({id_list})"
            nm_rows = {r["oracle_id"]: r
                       for r in tbl.search().where(cond).limit(len(ordered_ids)).to_list()}
            fq = tbl.search(q, query_type="fts")
            if where:
                fq = fq.where(where)
            seen, merged = set(), []
            for oid in ordered_ids:
                r = nm_rows.get(oid)
                if r:
                    merged.append(r)
                    seen.add(oid)
            if not merged:
                # 名字完全没命中时,用 FTS 兜底(规则文本里的词)
                for r in fq.limit(50).to_list():
                    if r["oracle_id"] not in seen:
                        merged.append(r)
                        seen.add(r["oracle_id"])
            for r in merged:
                r.pop("vector", None)
                r.pop("card", None)
                r.pop("text", None)
            return {"total": len(merged), "page": page, "page_size": page_size,
                    "items": merged[(page - 1) * page_size: page * page_size]}

    if mode == "vector" and q.strip():
        qv = next(iter(model().embed([expand_query(q)[0]])))
        query = tbl.search(qv).metric("cosine").distance_range(
            upper_bound=min(1.0, max(0.05, max_dist)))
    elif mode == "fts" and q.strip():
        query = tbl.search(q, query_type="fts")
    else:
        query = tbl.search().select(LIST_COLS)

    if where:
        query = query.where(where)

    # 排序:相关性优先时,向量搜索保持 cosine 距离;其余情况显式排序
    if sort == "edhrec":
        query = query.order_by([{"column_name": "edhrec_rank"}])
    elif sort == "cmc_asc":
        query = query.order_by([{"column_name": "cmc"}])
    elif sort == "cmc_desc":
        query = query.order_by([{"column_name": "cmc", "descending": True}])
    elif sort == "name":
        query = query.order_by([{"column_name": "name_en"}])
    elif not (mode == "vector" and q.strip()):
        query = query.order_by([{"column_name": "edhrec_rank"}]).select(LIST_COLS)

    total = query.limit(100000).to_arrow().num_rows
    rows = (query.limit(page_size).offset((page - 1) * page_size)
            .to_list())
    for r in rows:
        r.pop("vector", None)
        r.pop("card", None)
        r.pop("text", None)
    return {"total": total, "page": page, "page_size": page_size, "items": rows,
            "type_direct": type_direct}


@app.get("/api/card/{oracle_id}")
def card_detail(oracle_id: str):
    rows = (tbl.search().where(f"oracle_id = '{oracle_id}'").limit(1).to_list())
    if not rows:
        raise HTTPException(404, "card not found")
    card = json.loads(rows[0]["card"])
    # 从 image_url 提取 Scryfall ID,供 MTGStand 等外链使用
    m = _re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        card.get("image_url") or "")
    card["sf_id"] = m.group(1) if m else None
    return card


# ---------------- EDHREC 主将使用率 ----------------
import functools
import re as _re
import time as _time

EDHREC_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
CACHE_DIR = os.path.join(ROOT, "data", "raw", "edhrec_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 7 * 86400  # 7 天

_name_img_map = None


def name_image_map():
    """英文名 -> 卡图 URL(含双面卡正面名索引),懒加载一次。
    直接读 cards.jsonl 建映射,避免依赖 LanceDB 查询语义。"""
    global _name_img_map
    if _name_img_map is None:
        m = {}
        path = os.path.join(ROOT, "data", "cards.jsonl")
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    c = json.loads(line)
                except Exception:
                    continue
                n, img = c.get("name_en"), c.get("image_url")
                if n and img:
                    m.setdefault(n, img)
                    m.setdefault(n.split("//")[0].strip(), img)
        _name_img_map = m
    return _name_img_map


def edhrec_slug(name: str) -> str:
    name = name.split("//")[0]          # 双面卡取正面
    name = name.replace("Æ", "Ae").replace("æ", "ae")
    name = name.lower()
    name = name.replace("&", " and ")
    name = name.replace("'", "").replace("’", "")
    name = _re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return name


def fetch_edhrec(slug: str):
    """抓取 EDHREC 单卡页并解析;结果落盘缓存"""
    cache = os.path.join(CACHE_DIR, slug + ".json")
    if os.path.exists(cache) and _time.time() - os.path.getmtime(cache) < CACHE_TTL:
        result = json.load(open(cache))
        # 旧缓存/异常缓存补卡图字段(包括被写成了 null 的)
        if result.get("commanders") and any(not c.get("image_url") for c in result["commanders"]):
            imgs = name_image_map()
            for c in result["commanders"]:
                if not c.get("image_url"):
                    n = c.get("name") or ""
                    c["image_url"] = imgs.get(n) or imgs.get(n.split("//")[0].strip())
            json.dump(result, open(cache, "w"), ensure_ascii=False)
        return result
    url = f"https://edhrec.com/cards/{slug}"
    req = urllib.request.Request(url, headers=EDHREC_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return None
    m = _re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                   html, _re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
        jd = d["props"]["pageProps"]["data"]["container"]["json_dict"]
        card = jd.get("card") or {}
        commanders = []
        for lst in jd.get("cardlists") or []:
            if isinstance(lst, dict) and lst.get("tag") == "topcommanders":
                for cv in (lst.get("cardviews") or []):
                    nd, pd = cv.get("num_decks") or 0, cv.get("potential_decks") or 0
                    commanders.append({
                        "name": cv.get("name"),
                        "slug": cv.get("slug"),
                        "num_decks": nd,
                        "potential_decks": pd,
                        "pct": round(nd / pd, 4) if pd else None,
                    })
        result = {
            "name": card.get("name"),
            "num_decks": card.get("num_decks"),
            "potential_decks": card.get("potential_decks"),
            "commanders": commanders,
        }
        imgs = name_image_map()
        for c in commanders:
            c["image_url"] = imgs.get(c.get("name") or "")
        json.dump(result, open(cache, "w"), ensure_ascii=False)
        return result
    except Exception:
        return None


@app.get("/api/edhrec/{oracle_id}")
def edhrec_top_commanders(oracle_id: str):
    rows = (tbl.search().where(f"oracle_id = '{oracle_id}'")
            .limit(1).to_list())
    if not rows:
        raise HTTPException(404, "card not found")
    name = rows[0].get("name_en") or ""
    slug = edhrec_slug(name)
    data = fetch_edhrec(slug)
    if not data:
        raise HTTPException(404, "EDHREC 暂无此卡数据")
    return data


# ---------------- MTGStocks 价格历史外链 ----------------
MS_CACHE_DIR = os.path.join(ROOT, "data", "raw", "mtgstocks_cache")
os.makedirs(MS_CACHE_DIR, exist_ok=True)
MS_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def fetch_mtgstocks_url(name: str):
    """按卡名调 MTGStocks autocomplete,返回 (prints页URL, print_id);优先精确同名。"""
    import urllib.parse
    q = urllib.parse.quote(name)
    try:
        req = urllib.request.Request(
            f"https://api.mtgstocks.com/search/autocomplete/{q}", headers=MS_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None, None
    if not isinstance(data, list) or not data:
        return None, None
    low = name.lower()
    pick = next((p for p in data if (p.get("name") or "").lower() == low),
                data[0])
    slug = pick.get("slug") or ""
    pid = int(slug.split("-")[0]) if slug.split("-")[0].isdigit() else None
    url = f"https://www.mtgstocks.com/prints/{slug}" if slug else None
    return url, pid


def fetch_mtgstocks_prices(pid: int):
    """取 TCGplayer 价格历史,按月降采样(每月最后一个点),返回 {series, updated}。"""
    try:
        req = urllib.request.Request(
            f"https://api.mtgstocks.com/prints/{pid}/prices/tcgplayer",
            headers=MS_UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    series = {}
    for key in ("avg", "market"):
        pts = data.get(key) or []
        # 按月分桶,保留每月最后一点;全量 ~5200 点降到 ~170 点
        buckets = {}
        for ts, p in pts:
            if p is None:
                continue
            buckets[_time.strftime("%Y-%m", _time.gmtime(ts / 1000))] = [ts, p]
        series[key] = list(buckets.values())
    return {"series": series, "updated": int(_time.time())}


MS_PRICE_TTL = 6 * 3600  # 价格 6 小时内走缓存,避免频繁打外部 API


@app.get("/api/mtgstocks/{oracle_id}")
def mtgstocks_link(oracle_id: str):
    rows = (tbl.search().where(f"oracle_id = '{oracle_id}'")
            .limit(1).to_list())
    if not rows:
        raise HTTPException(404, "card not found")
    cache = os.path.join(MS_CACHE_DIR, f"{oracle_id}.json")
    now = _time.time()
    if os.path.exists(cache):
        try:
            cached = json.load(open(cache, encoding="utf-8"))
        except Exception:
            cached = None
        if cached:
            # url 是永久缓存;价格在 TTL 内直接复用
            if (cached.get("prices") and
                    now - cached["prices"].get("updated", 0) < MS_PRICE_TTL):
                return cached
            if cached.get("print_id"):
                prices = fetch_mtgstocks_prices(cached["print_id"])
                if prices:
                    cached["prices"] = prices
                    json.dump(cached, open(cache, "w", encoding="utf-8"),
                              ensure_ascii=False)
                return cached
    name = (rows[0].get("name_en") or "").split("//")[0].strip()
    url, pid = fetch_mtgstocks_url(name) if name else (None, None)
    result = {"url": url, "print_id": pid}
    if pid:
        prices = fetch_mtgstocks_prices(pid)
        if prices:
            result["prices"] = prices
    try:
        json.dump(result, open(cache, "w", encoding="utf-8"),
                  ensure_ascii=False)
    except Exception:
        pass
    return result


# ---------------- 版本卡图(悬浮预览用) ----------------
PRINT_IMG_CACHE = os.path.join(ROOT, "data", "raw", "print_img_cache")
os.makedirs(PRINT_IMG_CACHE, exist_ok=True)
SF_UA = {"User-Agent": "mtg-edh-ai-card-browser/1.0", "Accept": "*/*"}


def fetch_print_image(oracle_id: str, set_code: str):
    """按 oracle_id + set_code 查 Scryfall 该版本的卡图,优先中文(mtgch)。"""
    import urllib.parse
    q = urllib.parse.quote(f"oracleid:{oracle_id} set:{set_code}")
    try:
        req = urllib.request.Request(
            f"https://api.scryfall.com/cards/search?q={q}&unique=prints",
            headers=SF_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    cards = (data.get("data") or []) if isinstance(data, dict) else []
    if not cards:
        return None
    c = cards[0]
    # 双面卡取正面图
    img = (c.get("image_uris") or {}).get("normal")
    if not img and c.get("card_faces"):
        img = (c["card_faces"][0].get("image_uris") or {}).get("normal")
    if not img:
        return None
    # 换 mtgch 中文图床(webp,若该版本有中文图),否则保留 Scryfall 原图
    zhs = img.split("?")[0].replace("https://cards.scryfall.io/normal/",
                                     "https://images.mtgch.com/zhs/normal/")
    if zhs.endswith(".jpg"):
        zhs = zhs[:-4] + ".webp"
    try:
        req2 = urllib.request.Request(zhs, method="HEAD", headers=SF_UA)
        with urllib.request.urlopen(req2, timeout=6) as r2:
            if r2.status == 200:
                return zhs
    except Exception:
        pass
    return img


@app.get("/api/print_image/{oracle_id}/{set_code}")
def print_image(oracle_id: str, set_code: str):
    set_code = set_code.upper()
    cache = os.path.join(PRINT_IMG_CACHE, f"{oracle_id}_{set_code}.json")
    if os.path.exists(cache):
        try:
            return json.load(open(cache, encoding="utf-8"))
        except Exception:
            pass
    img = fetch_print_image(oracle_id, set_code)
    result = {"image": img}
    try:
        json.dump(result, open(cache, "w", encoding="utf-8"),
                  ensure_ascii=False)
    except Exception:
        pass
    return result


@app.get("/api/meta")
def meta():
    import pyarrow.compute as pc
    t = tbl.search().limit(100000).to_arrow()
    t = t.select(["commander_legal", "color_identity", "cmc", "rarity"])
    legal = pc.equal(t["commander_legal"], "legal")
    n_legal = pc.sum(legal).as_py()
    ci = t["color_identity"].to_pylist()
    dist = {}
    for s in ci:
        key = "".join(sorted((s or "").split())) or "C"
        dist[key] = dist.get(key, 0) + 1
    top = dict(sorted(dist.items(), key=lambda kv: -kv[1])[:12])
    tag_index()  # 确保词频已加载
    # 筛选条只展示 Scryfall Tagger 社区标签(人工策划、准确),按频率取前 100;
    # 排除纯文本模式的元标签(对组牌无意义)
    TAG_META_NOISE = {"alliteration", "intervening if clause", "unique type line",
                      "namesake spell", "virtual vanilla"}
    top_tags = sorted(
        ({"tag": t, "n": n, "zh": tagdict().get(t)} for t, n in _sf_tag_counts.items()
         if n >= 20 and t not in TAG_META_NOISE),
        key=lambda x: -x["n"])[:100]
    return {"total": tbl.count_rows(), "commander_legal": n_legal,
            "color_identity_top": top, "sets": set_name_map(),
            "top_tags": top_tags, "tagdict": tagdict()}


@app.get("/api/types")
def all_types():
    """完整类型清单:15 种主类型 + 超类型 + 副类别(带卡数与中英对照)。
    中英对照通过同一张卡的 en/zh 类型行按位置对齐,多数投票得出。"""
    global _all_types
    if _all_types is None:
        t = (tbl.search().limit(100000).to_arrow()
             .select(["type_line_en", "type_line_zh"]))
        counts = {}
        votes = {}   # en -> {zh: n}
        for en, zh in zip(t["type_line_en"].to_pylist(),
                          t["type_line_zh"].to_pylist()):
            if not en or "—" not in en:
                continue
            subs = [s.strip() for s in en.split("—", 1)[1].split()
                    if s.strip().isalpha()]
            for s in subs:
                counts[s] = counts.get(s, 0) + 1
            if zh and "～" in zh:
                # 中文行格式:传奇生物～人类／浪客(超类型连写,副类别以 ／ 分隔)
                zsubs = [s.strip() for s in zh.split("～", 1)[1].split("／") if s.strip()]
                if len(zsubs) == len(subs):
                    for e, z in zip(subs, zsubs):
                        v = votes.setdefault(e, {})
                        v[z] = v.get(z, 0) + 1
        zh_map = {e: max(v.items(), key=lambda kv: kv[1])[0]
                  for e, v in votes.items() if v}
        subs = [{"t": s, "n": n, "zh": zh_map.get(s)}
                for s, n in counts.items() if n >= 8]
        subs.sort(key=lambda x: -x["n"])
        _all_types = {"subtypes": subs[:500]}
    return _all_types


_all_types = None


@app.get("/api/tags")
def tags(q: str = "", limit: int = 60):
    """全库标签模糊搜索:只搜英文 Tagger 规范标签(人工策划、准确),
    支持前缀/包含/词首/中文翻译四种命中,按命中强度与卡数排序。"""
    idx = tag_index()
    td = tagdict()
    pool = [t for t in idx if t.isascii() and t == t.strip() and len(t) >= 3]
    ql = q.strip().lower()
    if not ql:
        return {"items": []}

    def score(t):
        zh = (td.get(t) or "").lower()
        if t.startswith(ql):
            return 3
        if ql in t or ql in zh:
            return 2
        if any(w.startswith(ql) for w in t.split("-")):
            return 1
        return 0

    hits = [(score(t), len(idx[t]), t) for t in pool]
    hits = [h for h in hits if h[0] > 0]
    hits.sort(key=lambda x: (-x[0], -x[1]))
    return {"items": [{"tag": t, "n": n, "zh": td.get(t)}
                      for _, n, t in hits[:min(200, max(1, limit))]]}


_sets_map = None


def set_name_map():
    """{set_code: name} 懒加载,供前端版本链接提示。"""
    global _sets_map
    if _sets_map is None:
        try:
            sets = json.load(open(os.path.join(ROOT, "data", "raw", "sets.json")))
            _sets_map = {s["code"].upper(): s.get("name") or s["code"]
                         for s in sets}
        except Exception:
            _sets_map = {}
    return _sets_map


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8103)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
