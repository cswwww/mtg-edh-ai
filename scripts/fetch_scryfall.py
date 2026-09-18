#!/usr/bin/env python3
"""下载 Scryfall Bulk Data 并转为 jsonl.gz。

- 通过 api.scryfall.com/bulk-data 发现最新下载地址(文件名带时间戳,不固定)
- oracle_cards / all_cards:JSON 数组 -> 逐行 jsonl.gz(流式解析,不占大内存)
- oracle_tags:本身就是 jsonl,直接转存
- 输出: data/raw/{oracle-cards,all-cards,oracle-tags}.jsonl.gz
- 原子写入(.tmp 完成后改名),失败自动恢复旧文件
"""
import gzip
import json
import os
import shutil
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
UA = {"User-Agent": "mtg-edh-ai-local-db/1.0 (personal research)"}

WANT = {
    "oracle_cards": ("oracle-cards.jsonl.gz", True),
    "all_cards": ("all-cards.jsonl.gz", True),
    "oracle_tags": ("oracle-tags.jsonl.gz", False),
}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def download(url, dest_gz, is_json_array):
    """下载并转换,先写临时文件再原子替换。"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gz")
    tmp.close()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r, \
                gzip.open(tmp.name, "wt", encoding="utf-8") as out:
            if not is_json_array:
                shutil.copyfileobj(r, out, 1024 * 1024)
            else:
                dec = json.JSONDecoder()
                buf = ""
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    buf += chunk.decode("utf-8")
                    while True:
                        buf = buf.lstrip()
                        if not buf:
                            break
                        if buf[0] in "[,":
                            buf = buf[1:]
                            continue
                        if buf[0] == "]":
                            buf = ""
                            break
                        obj, end = dec.raw_decode(buf)
                        out.write(json.dumps(obj, ensure_ascii=False) + "\n")
                        buf = buf[end:]
        shutil.move(tmp.name, dest_gz)
        print(f"OK {os.path.basename(dest_gz)} <- {url}", flush=True)
    except Exception:
        os.unlink(tmp.name)
        raise


def main():
    os.makedirs(RAW, exist_ok=True)
    bulk = get_json("https://api.scryfall.com/bulk-data")
    found = {d["type"]: d["download_uri"] for d in bulk.get("data") or []}
    fail = 0
    for btype, (fname, is_arr) in WANT.items():
        url = found.get(btype)
        dest = os.path.join(RAW, fname)
        if not url:
            print(f"SKIP {btype}: bulk-data 中未找到", flush=True)
            fail += 1
            continue
        bak = dest + ".bak"
        if os.path.exists(dest):
            shutil.copy2(dest, bak)  # 备份旧文件,失败可回滚
        try:
            download(url, dest, is_arr)
        except Exception as e:
            if os.path.exists(bak):  # 恢复旧文件
                shutil.move(bak, dest)
            print(f"FAIL {btype}: {e}", flush=True)
            fail += 1
        else:
            if os.path.exists(bak):
                os.unlink(bak)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
