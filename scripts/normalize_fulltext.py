#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_fulltext.py — 统一全文与摘要的关系

规则（只改有 fullText 的记录）：
    summary      = fullText 前 SUMMARY_CHARS 字符   ← 卡片显示 + 检索索引都取它
    charCount    = fullText 全长
    summaryKind  = verbatim（全文不超过 SUMMARY_CHARS）/ verbatim-excerpt（被截断）

为什么摘要也要截到固定长度：检索词由 summary 抽取（build_browse.terms_of），
若把 438,201 字的欧盟条例整篇塞进索引，browse.json 会从 7MB 涨到几十 MB，
首屏直接不可用。2,000 字覆盖了绝大多数条文的全部长度，
个别长文的剩余部分在详情页可读，但不在检索窗口内——
这个边界必须写在 README 里，不能让人以为全文都能搜到。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "data" / "records"
SUMMARY_CHARS = 2000


def fix_cjk_spaces(t):
    """去掉汉字之间的空格。

    PDF 抽取常把每个汉字之间塞一个空格（「中 华 人 民 共 和 国」），
    这既难读，也会让条文号匹配失效。此处只动汉字之间的空格，
    英文词与数字之间的空格保留。
    """
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"(?<=[一-鿿]) +(?=[一-鿿])", "", t)
    return t


def main():
    total = changed = 0
    for p in sorted(RECORDS.glob("*.json")):
        if ".bak" in p.name:
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        n = 0
        for r in data:
            full = r.get("fullText")
            if not full:
                continue
            total += 1
            full = fix_cjk_spaces(full)
            r["fullText"] = full
            r["summary"] = full[:SUMMARY_CHARS]
            rl = r.setdefault("recordLevel", {})
            rl["charCount"] = len(full)
            rl["summaryChars"] = min(SUMMARY_CHARS, len(full))
            rl["summaryKind"] = "verbatim" if len(full) <= SUMMARY_CHARS else "verbatim-excerpt"
            n += 1
        if n:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += n
            print(f"{p.name}: {n} 条")
    print(f"\n共 {total} 条有全文（改动 {changed}）")


if __name__ == "__main__":
    main()
