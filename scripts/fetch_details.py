#!/usr/bin/env python3
"""抓取需要详情的卡牌(双面卡/正文缺失卡),带断点续传,4 线程。

用法: python3 fetch_details.py [每轮最大请求数]
"""
import json
import os
import sys
import time
import glob
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE = "https://mtgch.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw", "mtgch_details")
os.makedirs(RAW_DIR, exist_ok=True)
UA = {"User-Agent": "mtg-edh-ai-local-db/1.0 (personal research)"}


def get_json(url, retries=6):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(45)
            else:
                time.sleep(2 ** i)
        except Exception:
            time.sleep(2 ** i)
    return None


def fetch(item):
    oid, code, num = item
    safe = f"{code}__{num.replace('/', '_')}"
    path = os.path.join(RAW_DIR, f"{safe}.json")
    if os.path.exists(path):
        return True
    d = get_json(f"{BASE}/api/v1/card/{code}/{urllib.parse.quote(num, safe='')}/")
    if d is None:
        print(f"FAIL {code}/{num}", flush=True)
        return False
    json.dump(d, open(path, "w"))
    time.sleep(0.5)
    return True


def main():
    max_calls = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    todo = set()
    for f in glob.glob(os.path.join(ROOT, "data/raw/mtgch_sets/*.json")):
        d = json.load(open(f))
        for c in d["items"]:
            if c.get("is_double_faced"):
                todo.add((c["oracle_id"], c["set"], c["collector_number"]))
            elif not (c.get("oracle_text_html") or "").strip() and c.get("display_type_line") not in (None, "牌"):
                todo.add((c["oracle_id"], c["set"], c["collector_number"]))
    todo = sorted(todo)
    remaining = [t for t in todo
                 if not os.path.exists(os.path.join(RAW_DIR, f"{t[1]}__{t[2].replace('/', '_')}.json"))]
    print(f"total={len(todo)} remaining={len(remaining)}", flush=True)

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=2) as ex:
        for ok in ex.map(fetch, remaining[:max_calls]):
            done += 1
            if done % 100 == 0:
                el = time.time() - t0
                print(f"{done} done {el:.0f}s", flush=True)
    left = len(remaining) - done
    print(f"batch done: fetched={done} remaining~={left}", flush=True)
    sys.exit(0 if left <= 0 else 2)


if __name__ == "__main__":
    main()
