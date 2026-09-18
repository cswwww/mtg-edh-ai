#!/usr/bin/env python3
"""从 mtgch.com 抓取全部系列卡牌数据(带断点续传)。

用法: python3 fetch_mtgch.py [每轮最大请求数]
"""
import json
import os
import sys
import time
import urllib.request

BASE = "https://mtgch.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw", "mtgch_sets")
SETS_FILE = os.path.join(ROOT, "data", "raw", "sets.json")
os.makedirs(RAW_DIR, exist_ok=True)

UA = {"User-Agent": "mtg-edh-ai-local-db/1.0 (personal research)"}


def get_json(url, retries=4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            wait = 2 ** i
            print(f"  retry {i+1}/{retries} {url}: {e}", flush=True)
            time.sleep(wait)
    return None


def main():
    max_calls = int(sys.argv[1]) if len(sys.argv) > 1 else 250

    if os.path.exists(SETS_FILE):
        sets = json.load(open(SETS_FILE))
    else:
        sets = get_json(f"{BASE}/api/v1/sets/")
        json.dump(sets, open(SETS_FILE, "w"))
    todo = [s for s in sets
            if not os.path.exists(os.path.join(RAW_DIR, f"{s['code']}.json"))]
    print(f"sets total={len(sets)} remaining={len(todo)}", flush=True)

    calls = 0
    t0 = time.time()
    for s in todo:
        if calls >= max_calls:
            break
        code = s["code"]
        d = get_json(f"{BASE}/api/v1/set/{code}/cards/?page_size=9999")
        calls += 1
        if d is None:
            print(f"FAIL {code}", flush=True)
            continue
        json.dump(d, open(os.path.join(RAW_DIR, f"{code}.json"), "w"))
        if calls % 25 == 0:
            el = time.time() - t0
            print(f"{calls} done, {el:.0f}s, eta {el/calls*(len(todo)-calls):.0f}s", flush=True)
        time.sleep(0.15)

    left = len(todo) - calls
    print(f"batch done: fetched={calls} remaining~={left}", flush=True)
    sys.exit(0 if left <= 0 else 2)  # exit 2 = 还有剩余,需要再跑一轮


if __name__ == "__main__":
    main()
