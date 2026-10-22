#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_eurlex_fulltext.py — 给 EUR-Lex 记录补全文

EUR-Lex 的正文在 Cellar 的 XHTML 里，collect_eurlex.py 只用它取过条文标题，
正文本身没存。欧盟官方公报文本依 2011/833/EU 决定可自由再利用（注明来源即可），
故可全文收录。

用法：
    python scripts/collect_eurlex_fulltext.py
    python scripts/collect_eurlex_fulltext.py --limit 1
"""

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_eurlex import cellar  # noqa: E402  复用同一取数通道（含 .ENG 后缀处理）

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "records" / "regulations_eu_eurlex.json"
PREVIEW = 600


def body_text(xhtml):
    """从 EUR-Lex XHTML 抽正文。

    只保留这三类段落：条文号（oj-ti-art）、条文标题（oj-sti-art）、正文（oj-normal）。
    页头页脚的导航、目录、脚注链接一律不要——脚注在 <p class="oj-note">，
    属于编辑性注释，不属于法规正文。
    """
    xhtml = re.sub(r"<script.*?</script>", " ", xhtml, flags=re.S | re.I)
    xhtml = re.sub(r"<style.*?</style>", " ", xhtml, flags=re.S | re.I)
    paras = re.findall(
        r'<p[^>]*class="(?:oj-ti-art|oj-sti-art|oj-normal|oj-ti-section-\d)"[^>]*>(.*?)</p>',
        xhtml, re.S | re.I)
    out = []
    for p in paras:
        t = re.sub(r"<[^>]+>", "", p)
        t = html.unescape(t).replace("\u00a0", " ")
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            out.append(t)
    return "\n".join(out).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    records = json.loads(SRC.read_text(encoding="utf-8"))
    todo = [r for r in records if args.force or not r.get("fullText")]
    if args.limit:
        todo = todo[:args.limit]
    print(f"待补全文 {len(todo)} / {len(records)} 条", flush=True)

    for i, rec in enumerate(todo, 1):
        celex = (rec.get("recordLevel") or {}).get("celex") or ""
        try:
            xhtml = cellar(celex, "application/xhtml+xml").decode("utf-8", "ignore")
            text = body_text(xhtml)
            if len(text) < 200:
                print(f"  [{i}] {celex} 正文过短（{len(text)}），跳过", flush=True)
                continue
            rec["fullText"] = text
            rec["summary"] = text[:PREVIEW]
            rl = rec.setdefault("recordLevel", {})
            rl["charCount"] = len(text)
            rl["textSource"] = "EUR-Lex Cellar XHTML 正文段"
            rl["fullTextNote"] = ("官方公报文本，依 2011/833/EU 决定可再利用；"
                                  "仅取条文段落，不含编辑性脚注。")
            print(f"  [{i}/{len(todo)}] {celex} {len(text):,} 字", flush=True)
        except Exception as e:              # noqa: BLE001
            print(f"  [{i}] {celex} 失败：{type(e).__name__} {e}", flush=True)
        time.sleep(1.0)

    SRC.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    got = [r for r in records if r.get("fullText")]
    tot = sum(len(r.get("fullText") or "") for r in got)
    print(f"\n完成：已有全文 {len(got)} / {len(records)} 条，合计 {tot:,} 字符")


if __name__ == "__main__":
    main()
