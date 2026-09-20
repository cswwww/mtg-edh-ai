#!/usr/bin/env python3
"""AI 卡牌元数据管线:LLM 为每张卡生成 ai_desc(一句话功能定位)。

最终定稿:只保留 ai_desc 一个 AI 字段(其他结构化维度交给 Scryfall Tagger + tagdict.txt)。

供应商可配置:data/raw/.llm_config.json
  {"base_url": "...", "api_key": "...", "model": "glm-4-flash"}

- 批量:每批 8 张卡(JSON 输出)
- 失败批次降级为单张重试,失败标 ok=false
- 并发:12 线程;429/5xx 指数退避
- 断点:增量写 data/tags.jsonl,重跑自动跳过已完成
- 范围:仅指挥官赛制合法的卡
- 用法: python3 scripts/tag_cards.py [本轮最大批次数]
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "cards.jsonl")
OUT = os.path.join(ROOT, "data", "tags.jsonl")
CONFIG = os.path.join(ROOT, "data", "raw", ".llm_config.json")

BATCH = 8
WORKERS = 12

DEFAULT_CFG = {
    "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "",
    "model": "glm-4-flash",
}
cfg = {**DEFAULT_CFG, **(json.load(open(CONFIG)) if os.path.exists(CONFIG) else {})}
if not cfg["api_key"]:
    sys.exit("缺少 API key: 写入 " + CONFIG)

SYSTEM = """你是万智牌(Magic: The Gathering)指挥官(EDH)赛制专家,正在为一位正在组牌/选牌的牌手写一句实战点评,
让 ta 看完就知道这张卡在 EDH 里能干嘛、值不值得放进自己的套牌。

为每张卡生成一条 desc,严格以 JSON 对象返回(无 markdown 代码块,无解释):

{"id": <1-indexed 序号>,
 "desc": "30-80 字简体中文实战点评"}

desc 必须包含 oracle 里没有写的信息,至少命中以下两条:
- 实战价值定位(EDH 必备 / 常见 / 小众 / 几乎没人放)
- 适合的套牌类型、节奏(开 1-2 回合加速 / 中盘去除 / 终结 / 防守)或常见主题(部族 / 套牌引擎 / 坟场 / 牌库挖掘)
- 典型配合卡或思路关键词(配合 / 适合 / X 思路 / X 主题 / X 引擎 / 终结)
- 什么时候用、什么时候别用的判断

desc 严禁:
- 把 oracle 句子逐句翻译(例:oracle "Whenever X, do Y" 严禁写 "每当 X 时,做 Y")
- 复制 oracle 句式("在 X 步骤开始时..."、"如果你这样做..."、"你可以...")
- 用费用符号 {X} 复述机制
- 写"这张卡是 X 类型的卡"这种不增加信息的废话

自检:把 oracle text 删掉,只看 desc 还能知道这张卡做什么 —— 如果做不到,就是没写好。

长度:30-80 字。oracle 简单时可以很短但不准凑字数,oracle 复杂时可以稍长但不准堆砌规则。

示例(合格):

Sol Ring(神器,费用 {1},oracle "{T}: Add {C}{C}.")
→ desc: "一费神器,横一次产两点无色法术力,EDH 第一加速件,几乎所有指挥官套牌必放,ban 讨论桌上的常客。"

Swords to Plowshares(瞬间,费用 {W},oracle "Exile target creature. Its controller gains life equal to its power.")
→ desc: "一费白色瞬间,放逐任意生物,对手按力量回血。EDH 最强单体去除之一,白/白多色套牌几乎必放。"

Cyclonic Rift(瞬间,费用 {1}{U},含 overload {6}{U})
→ desc: "蓝色瞬间双形态卡,小用弹一个威胁,过载清场扫光对手所有永久物。后者让它成为 EDH 最强清场之一,几乎所有蓝色套牌都放。"

Avenger of Zendikar(生物,进场触发 + landfall)
→ desc: "进场按地数产植物衍生物,每次地落植物全体 +1/+1。铺场/地落思路的经典终结,中期一波平推,也是植物主题套牌的轴心。"

反例(不合格):
oracle "{T}: Add {C}{C}." → desc: "横置此神器,添加两点无色法术力。"
(问题:完全是 oracle 的中文翻译,没有实战价值、节奏、配合等任何增量信息。碰到 oracle 短的卡,要主动写出"为什么所有人都放"这种专家点评,而不是把 oracle 翻成中文。)
"""


def card_text(i, r):
    """把一张卡压成 LLM 友好文本。"""
    lines = [f"{i}. 名称: {r['name_en']}" + (f" / {r['name_zh']}" if r.get("name_zh") else "")]
    t = r.get("type_line_en") or r.get("type_line_zh") or ""
    lines.append(f"   类型: {t}  费用: {r.get('mana_cost') or '无'}  颜色: {''.join(r.get('color_identity') or []) or '无色'}")
    if r.get("power"):
        lines.append(f"   攻防: {r['power']}/{r['toughness']}")
    if r.get("keywords"):
        lines.append(f"   关键词: {', '.join(r['keywords'])}")
    if r.get("sf_tags"):
        lines.append(f"   社区标签: {', '.join(r['sf_tags'][:10])}")
    if r.get("faces"):
        for fc in r["faces"]:
            fn = fc.get("name_en") or ""
            ft = (fc.get("text_en") or "").replace("\n", " ")
            lines.append(f"   面[{fn}]: {ft}")
    else:
        ot = (r.get("oracle_text_en") or "").replace("\n", " ")
        lines.append(f"   规则: {ot}")
    return "\n".join(lines)


def call_llm(prompt, max_tokens=1500, retries=5):
    # 不带 response_format=json_object:该模式在 GLM-4-Flash + 多卡批量下会卡死
    # LLM 会自动输出 markdown ```json ... ``` 块,由 parse_batch_result 兜底提取
    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(cfg["base_url"], data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                d = json.loads(resp.read())
            return d["choices"][0]["message"]["content"]  # 返回原始字符串
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(min(2 ** i * 2, 30))
                continue
            return None
        except Exception:
            time.sleep(min(2 ** i * 2, 30))
    return None


def _extract_json_payload(content):
    """从 LLM 输出中提取 JSON 列表,支持多种包装:
    - 顶层 dict {"cards":[...]} / {"data":[...]} / 顶层 list
    - markdown ```json ... ``` 代码块
    - 直接 [{...}, {...}]
    返回 list[dict] 或 None(永不抛异常)
    """
    if content is None:
        return None
    s = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    if not s.strip():
        return None
    # 1) markdown 代码块 ```json ... ```
    for pat in (r"```json\s*([\s\S]+?)```", r"```\s*([\s\S]+?)```"):
        for m in re.finditer(pat, s):
            try:
                parsed = json.loads(m.group(1).strip())
                items = _as_items(parsed)
                if items:
                    return items
            except Exception:
                continue
    # 2) 找 JSON 数组的起始位置 (用 raw_decode 容错前缀文本)
    for i, ch in enumerate(s):
        if ch in "[{":
            try:
                parsed, _ = json.JSONDecoder().raw_decode(s, i)
                items = _as_items(parsed)
                if items:
                    return items
            except Exception:
                continue
    return None


def _as_items(parsed):
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for k in ("cards", "data", "results", "items"):
            if isinstance(parsed.get(k), list):
                return parsed[k]
        if len(parsed) == 1:
            v = list(parsed.values())[0]
            if isinstance(v, list):
                return v
        # 单条记录(只有 desc) → 包成 list
        if "desc" in parsed:
            return [parsed]
    return None


def parse_batch_result(content, batch):
    """content: LLM 原始输出(字符串或已解析对象);返回 {oracle_id: {ai_desc, ok}}"""
    items = _extract_json_payload(content) if content else None
    if not items:
        return {}
    out = {}
    for it in items:
        try:
            idx = it.get("id")
            if not isinstance(idx, int):
                continue
            card = batch[idx - 1]
            desc = it.get("desc")
            if not isinstance(desc, str):
                continue
            desc = re.sub(r"\s+", " ", desc).strip()[:200]
            if len(desc) < 10:
                continue
            out[card["oracle_id"]] = {"ai_desc": desc, "ok": True}
        except Exception:
            continue
    return out


def process_batch(batch_list):
    prompt = "请为以下万智牌卡牌生成一句话功能定位:\n\n" + "\n\n".join(
        card_text(i + 1, r) for i, r in enumerate(batch_list))
    content = call_llm(prompt)
    results = parse_batch_result(content, batch_list) if content else {}
    missing = [c for c in batch_list if c["oracle_id"] not in results]
    if missing and content is not None:
        # 部分缺失:对缺失的单张重试一次
        for c in missing:
            p = "请为以下万智牌卡牌生成一句话功能定位:\n\n" + card_text(1, c)
            single = call_llm(p, max_tokens=300)
            r = parse_batch_result(single, [c]) if single else {}
            if r:
                results.update(r)
    for c in batch_list:
        if c["oracle_id"] not in results:
            results[c["oracle_id"]] = {"ai_desc": "", "ok": False}
    return results


def main():
    max_batches = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    records = [json.loads(l) for l in open(CARDS)]
    records = [r for r in records if (r.get("legalities") or {}).get("commander") == "legal"]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try:
                d = json.loads(l)
                # 已有 ai_desc 且 ok=true 视为完成
                if d.get("ok") and d.get("ai_desc"):
                    done.add(d["oracle_id"])
            except Exception:
                pass
    pending = [r for r in records if r["oracle_id"] not in done]
    batches = [pending[i:i + BATCH] for i in range(0, len(pending), BATCH)]
    print(f"model={cfg['model']} total={len(records)} done={len(done)} pending={len(pending)} batches={len(batches)}", flush=True)

    import threading
    out = open(OUT, "a")
    lock = threading.Lock()
    t0 = time.time()
    processed = 0

    def run(b):
        nonlocal processed
        res = process_batch(b)
        with lock:
            for oid, r in res.items():
                out.write(json.dumps({"oracle_id": oid, **r}, ensure_ascii=False) + "\n")
            out.flush()
            processed += len(b)
            el = time.time() - t0
            rate = processed / max(el, 1)
            print(f"{processed}/{len(pending)} {rate:.1f}/s eta {((len(pending)-processed)/max(rate,0.1))/60:.0f}min", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, batches[:max_batches]))

    remaining = len(pending) - processed
    print(f"batch done: processed={processed} remaining~={remaining}", flush=True)
    sys.exit(0 if remaining <= 0 else 2)


if __name__ == "__main__":
    main()