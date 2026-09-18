#!/usr/bin/env python3
"""AI 卡牌元数据管线:LLM 为每张卡生成结构化元数据。

输出的 6 个字段:
  - ai_desc          40-60 字功能定位(嵌入核心,P0 保留)
  - ai_deck_role     卡组角色枚举 (P1, 取代 ai_synergy)
  - ai_strategy      策略主题枚举 (P1)
  - ai_countermeta   {answers: 克的, weak_to: 怕的} (P1)
  - ai_phase         early/mid/late/any (P2)
  - ai_theme_keywords 用户口里的中文联想词 (P2)
另保留 ai_tags/ai_synergy(占位,展示用,不嵌向量)

供应商可配置(默认智谱 GLM-4-Flash 免费档):data/raw/.llm_config.json
  {"base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
   "api_key": "xxx.xxx", "model": "glm-4-flash"}

- 批量:每次调用处理 5 张卡(JSON 数组输出)
- 失败批次自动降级为单张重试,单张也失败标记 ok=false
- 并发:10 线程;429/5xx 指数退避
- 断点:结果增量追加到 data/tags.jsonl,重跑自动跳过已完成
- 范围:仅指挥官赛制合法的卡(衍生物/插画牌/UN 系列不花钱)
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

BATCH = 5
WORKERS = 10

DEFAULT_CFG = {
    "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "",
    "model": "glm-4-flash",
}
cfg = {**DEFAULT_CFG, **(json.load(open(CONFIG)) if os.path.exists(CONFIG) else {})}
if not cfg["api_key"]:
    sys.exit("缺少 API key: 写入 " + CONFIG)

# ============== 枚举与归一化 ==============

DECK_ROLES = {
    "ramp", "card_advantage", "removal", "wincon", "protection",
    "combo", "tutor", "card_selection", "recursion", "mana_rock",
    "token", "finisher", "counter", "draw_engine", "threat",
}
# 归一化:常见近义词 / 中文 → 英文枚举
ROLE_ALIAS = {
    "加速": "ramp", "产费": "ramp", "mana": "ramp", "ramp_mana": "ramp",
    "过牌": "card_advantage", "抓牌": "card_advantage", "draw": "card_advantage",
    "抽牌": "card_advantage", "card_draw": "card_advantage", "手牌优势": "card_advantage",
    "去除": "removal", "解": "removal", "杀": "removal", "点杀": "removal",
    "扫场": "removal", "board_wipe": "removal", "destroy": "removal",
    "致胜": "wincon", "赢": "wincon", "kill": "wincon",
    "保护": "protection", "盾": "protection", "indestructible": "protection",
    "组合技": "combo", "combo_piece": "combo", "连携": "combo",
    "导师": "tutor", "检索": "tutor", "搜寻": "tutor", "search": "tutor",
    "筛选": "card_selection", "占卜": "card_selection", "loot": "card_selection",
    "挖坟": "recursion", "复生": "recursion", "坟场": "recursion",
    "法术力石": "mana_rock", "mana_sink": "mana_rock",
    "铺场": "token", "衍生物": "token", "token_gen": "token",
    "终结": "finisher", "闭锁": "finisher",
    "反击": "counter", "反制": "counter", "counter_spell": "counter",
    "抓牌引擎": "draw_engine", "draw_eng": "draw_engine",
    "威胁": "threat", "tempo": "threat",
}

STRATEGIES = {
    "tokens", "aristocrats", "reanimator", "voltron", "lifegain", "mill",
    "control", "combo", "stax", "spellslinger", "+1+1_counters", "sacrifice",
    "blink", "flicker", "treasures", "artifact", "enchantress", "graveyard",
    "burn", "anthem", "evasion",
}
STRATEGY_ALIAS = {
    "token": "tokens", "衍生物": "tokens",
    "贵族": "aristocrats", "aristrocrats": "aristocrats", "sac": "sacrifice",
    "reanimate": "reanimator", "复生": "reanimator", "挖坟": "reanimator",
    "指挥官杀": "voltron", "voltron_": "voltron", "武装": "voltron",
    "回血": "lifegain", "life": "lifegain", "lifegain_": "lifegain",
    "磨牌": "mill", "磨库": "mill",
    "控制": "control", "控": "control",
    "组合技": "combo",
    "stax_": "stax", "锁": "stax", "锁控": "stax",
    "法术狂": "spellslinger", "spells": "spellslinger",
    "指示物": "+1+1_counters", "counters": "+1+1_counters",
    "牺牲": "sacrifice",
    "闪现": "blink", "blink_": "blink",
    "闪烁": "flicker",
    "珍宝": "treasures", "treasure": "treasures",
    "神器": "artifact", "artifact_": "artifact",
    "结界": "enchantress", "enchant": "enchantress",
    "坟场": "graveyard",
    "burn_": "burn", "烧": "burn", "直伤": "burn",
    "增益": "anthem", "lord": "anthem",
    "穿透": "evasion", "踢脸": "evasion",
}

COUNTER_TYPES = {
    # 这张卡能克什么
    "hexproof", "evasion", "planeswalker", "artifact", "enchantment",
    "graveyard", "commander", "token", "aristocrat", "flyer",
    "indestructible", "high_cost_threat", "tapped_creature",
}
COUNTER_WEAK = {
    # 这张卡怕什么
    "mass_removal", "counter_spell", "graveyard_hate", "artifact_hate",
    "enchantment_hate", "flyer", "trample", "lifegain", "hexproof",
    "indestructible", "protection_from_color", "tutor_hate",
}
COUNTER_ALIAS = {
    "神:护": "hexproof", "不灭": "indestructible",
    "鹏洛客": "planeswalker", "planeswalkers": "planeswalker", "旅法": "planeswalker",
    "飞行": "flyer", "飞兵": "flyer", "flying": "flyer",
    "神器": "artifact", "结界": "enchantment", "坟场": "graveyard",
    "指挥官": "commander", "主将": "commander",
    "衍生物": "token", "贵族": "aristocrat",
    "穿透": "evasion", "踢脸": "evasion",
    "大生物": "high_cost_threat", "高费威胁": "high_cost_threat",
    "横置": "tapped_creature",
    "扫场": "mass_removal", "清场": "mass_removal", "wipe": "mass_removal",
    "反击": "counter_spell", "counterspell": "counter_spell", "反制": "counter_spell",
    "坟场仇恨": "graveyard_hate", "挖坟克": "graveyard_hate",
    "神器克": "artifact_hate", "神器破坏": "artifact_hate",
    "结界克": "enchantment_hate", "结界破坏": "enchantment_hate",
    "穿透生物": "trample", "践踏": "trample",
    "回血": "lifegain",
    "有色保护": "protection_from_color",
    "导师克": "tutor_hate", "反导师": "tutor_hate",
}

PHASES = {"early", "mid", "late", "any"}
PHASE_ALIAS = {
    "前期": "early", "早期": "early", "起手": "early", "turn_1_3": "early",
    "中期": "mid", "中盘": "mid", "turn_4_6": "mid",
    "后期": "late", "终盘": "late", "turn_7_plus": "late",
    "任意": "any", "通用": "any", "all": "any",
}


def _norm(val, allowed, alias):
    """把任意字符串/枚举归一化成 allowed 集合内的元素;不在集合内返回 None。"""
    if val is None:
        return None
    if isinstance(val, list):
        val = val[0] if val else None
    if not isinstance(val, str):
        return None
    s = val.strip().lower().replace(" ", "_").replace("-", "_")
    if s in allowed:
        return s
    if s in alias:
        return alias[s]
    # 中文别名
    for cn, en in alias.items():
        if not cn.isalpha() and cn in val:
            return en
    return None


def _norm_list(values, allowed, alias, max_n=3):
    """list 字段归一化去重,保留最多 max_n 个。"""
    if not isinstance(values, list):
        return []
    seen = []
    for v in values:
        n = _norm(v, allowed, alias)
        if n and n not in seen:
            seen.append(n)
        if len(seen) >= max_n:
            break
    return seen


def _norm_str(v, max_len=200):
    if not isinstance(v, str):
        return ""
    v = re.sub(r"\s+", " ", v).strip()
    return v[:max_len]


def _norm_countermeta(v):
    if not isinstance(v, dict):
        return {"answers": [], "weak_to": []}
    return {
        "answers": _norm_list(v.get("answers"), COUNTER_TYPES, COUNTER_ALIAS, 3),
        "weak_to": _norm_list(v.get("weak_to"), COUNTER_WEAK, COUNTER_ALIAS, 3),
    }


SYSTEM = """你是万智牌(Magic: The Gathering)指挥官(EDH)赛制专家。
为玩家给出的每张卡生成结构化元数据,严格以 JSON 数组返回(无 markdown 代码块,无解释)。

每个元素格式:
{"id": <1-indexed 序号>,
 "desc": "40-60 字简体中文功能定位",
 "deck_role": [...],   // 0-3 个,从候选枚举中选
 "strategy": [...],    // 0-3 个,从候选枚举中选
 "countermeta": {"answers": [...], "weak_to": [...]},
 "phase": "early|mid|late|any",
 "theme_keywords": [...]  // 0-5 个简体中文短语,描述牌该怎么用,可能出现的用户口里的俗称/联想词
}

desc 要求:
- 不要逐句翻译规则文本
- 写这张卡在 EDH 实战中做什么、有什么价值、适合什么节奏
- 例如"一费神器,横置产两点无色法术力,几乎适合所有指挥官套牌,帮助提前两回合拍出指挥官或大型威胁。"

deck_role 候选(选 0-3 个最贴切的):
ramp / card_advantage / removal / wincon / protection / combo /
tutor / card_selection / recursion / mana_rock / token / finisher /
counter / draw_engine / threat
- ramp: 法术力加速(横置产费、找地)
- card_advantage: 抓牌 / 抽牌 / 过牌
- removal: 去除 / 消灭 / 弹回 / 放逐目标
- wincon: 终结手段(直接造成伤害/磨牌库/同步生命等)
- protection: 保护生物或自己(辟邪/不灭/防止伤害)
- combo: 组合技组件
- tutor: 从牌库搜寻
- card_selection: 手牌筛选(占卜、loot)
- recursion: 坟场利用(挖回、生物回收)
- mana_rock: 法术力资源(石头/结界型产费)
- token: 铺场/造衍生物
- finisher: 终结技 / 拍出来就锁定局面
- counter: 反击咒语
- draw_engine: 持续抓牌引擎(每回合/每次触发都抓)
- threat: 战场威胁(自己拍下后对手必须应对)

strategy 候选(选 0-3 个最贴切的):
tokens / aristocrats / reanimator / voltron / lifegain / mill /
control / combo / stax / spellslinger / +1+1_counters / sacrifice /
blink / flicker / treasures / artifact / enchantress / graveyard /
burn / anthem / evasion
- tokens: 衍生物主题
- aristocrats: 牺牲生物触发收益
- reanimator: 复生大生物
- voltron: 给指挥官装武具/灵气冲锋
- lifegain: 大量回血
- mill: 磨牌库
- control: 控场
- combo: 组合技
- stax: 资源锁控
- spellslinger: 大量施放瞬间/法术
- +1+1_counters: 指示物增殖
- sacrifice: 牺牲作为费用/收益
- blink / flicker: 闪现/闪烁
- treasures: 珍宝产费
- artifact: 神器主题
- enchantress: 结界主题
- graveyard: 坟场坟堆
- burn: 直接伤害
- anthem: 群体增益
- evasion: 穿透踢脸

countermeta.answers 这张卡能克什么(选 0-3 个):
hexproof / evasion / planeswalker / artifact / enchantment / graveyard /
commander / token / aristocrat / flyer / indestructible /
high_cost_threat / tapped_creature

countermeta.weak_to 这张卡怕被什么克(选 0-3 个):
mass_removal / counter_spell / graveyard_hate / artifact_hate /
enchantment_hate / flyer / trample / lifegain / hexproof /
indestructible / protection_from_color / tutor_hate

phase 单值: early(早期/低费) / mid(中盘) / late(终盘/高费) / any(通用)

theme_keywords: 0-5 个简体中文短语,如"踢脸""加速""扫场""坟场""踢一脚""穿血"
- 用户用中文描述这张卡时可能用到的词
- 和你已有的 slang.txt(加速/扫场/铺场/过牌等)互补
- 偏口语和具体场景,如"踢一脚""无敌身板""清不掉""直接拍"

只输出 JSON 数组本身,不要 markdown 代码块,不要任何解释。"""


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


def call_llm(prompt, max_tokens=3000, retries=5):
    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(cfg["base_url"], data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                d = json.loads(resp.read())
            content = d["choices"][0]["message"]["content"]
            return json.loads(content)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(min(2 ** i * 2, 30))
                continue
            return None
        except Exception:
            time.sleep(min(2 ** i * 2, 30))
    return None


def parse_batch_result(content, batch):
    """content 应为 {"cards": [...]} 或顶层 list;返回 {oracle_id: result}"""
    items = None
    if isinstance(content, dict):
        for k in ("cards", "data", "results", "items"):
            if isinstance(content.get(k), list):
                items = content[k]
                break
        if items is None and len(content) == 1:
            v = list(content.values())[0]
            items = v if isinstance(v, list) else None
    elif isinstance(content, list):
        items = content
    if not items:
        return {}
    out = {}
    for it in items:
        try:
            idx = it.get("id")
            if not isinstance(idx, int):
                continue
            card = batch[idx - 1]
            # 解析各字段
            desc = _norm_str(it.get("desc"), 200)
            if len(desc) < 10:
                continue  # desc 太短,判为失败
            role = _norm_list(it.get("deck_role"), DECK_ROLES, ROLE_ALIAS, 3)
            strat = _norm_list(it.get("strategy"), STRATEGIES, STRATEGY_ALIAS, 3)
            cmeta = _norm_countermeta(it.get("countermeta"))
            phase_raw = it.get("phase")
            phase = _norm(phase_raw, PHASES, PHASE_ALIAS) or "any"
            kw = [str(k).strip() for k in (it.get("theme_keywords") or []) if isinstance(k, str)]
            kw = [k for k in kw if 1 <= len(k) <= 12][:5]
            out[card["oracle_id"]] = {
                "ai_desc": desc,
                "ai_deck_role": role,
                "ai_strategy": strat,
                "ai_countermeta": cmeta,
                "ai_phase": phase,
                "ai_theme_keywords": kw,
                "ok": True,
            }
        except Exception:
            continue
    return out


def process_batch(batch_list):
    prompt = "请为以下万智牌卡牌生成结构化元数据:\n\n" + "\n\n".join(
        card_text(i + 1, r) for i, r in enumerate(batch_list))
    content = call_llm(prompt)
    results = parse_batch_result(content, batch_list) if content else {}
    missing = [c for c in batch_list if c["oracle_id"] not in results]
    if missing and content is not None:
        # 部分缺失:对缺失的单张重试一次
        for c in missing:
            p = "请为以下万智牌卡牌生成结构化元数据:\n\n" + card_text(1, c)
            single = call_llm(p, max_tokens=800)
            r = parse_batch_result(single, [c]) if single else {}
            if r:
                results.update(r)
    for c in batch_list:
        if c["oracle_id"] not in results:
            results[c["oracle_id"]] = {
                "ai_desc": "", "ai_deck_role": [], "ai_strategy": [],
                "ai_countermeta": {"answers": [], "weak_to": []},
                "ai_phase": "any", "ai_theme_keywords": [],
                "ok": False,
            }
    return results


def main():
    max_batches = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    records = [json.loads(l) for l in open(CARDS)]
    # 只打指挥官赛制合法的卡
    records = [r for r in records if (r.get("legalities") or {}).get("commander") == "legal"]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try:
                d = json.loads(l)
                # 已有"完整 6 字段"输出视为已完成
                if d.get("ok") and d.get("ai_desc") and d.get("ai_deck_role") is not None \
                        and d.get("ai_strategy") is not None \
                        and d.get("ai_countermeta") is not None \
                        and d.get("ai_phase") is not None \
                        and d.get("ai_theme_keywords") is not None:
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