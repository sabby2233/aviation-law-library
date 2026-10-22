#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize_caac_text.py — 给没取到全文的规章写明原因

为什么要单独一步：39 条规章取不到正文，不是「抓取失败」，
而是源本身没有可供机器读取的条文文本（无附件、附件是二进制 .doc、
PDF 是扫描件或字体缺 Unicode 映射、附件其实是表格附录）。
不写清楚，读者会以为本站漏抓了；写清楚，才是「如实标注」。
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_caac_fulltext import (  # noqa: E402
    fetch, decode_html, find_attachment, extract_pdf, extract_doc, content_div_text,
)

SRC = Path(__file__).resolve().parent.parent / "data" / "records" / "regulations_cn_caac.json"


def diagnose(url):
    try:
        h = decode_html(fetch(url, binary=True, referer="https://www.caac.gov.cn/"))
    except Exception as e:                       # noqa: BLE001
        return f"页面取不到（{type(e).__name__}）"
    att = find_attachment(h, url)
    if not att:
        page = content_div_text(h)
        if len(page) > 1500:
            return "页面正文块长度异常，未取"
        return "该页无正文附件（仅部长令与链接）"
    if re.search(r"\.pdf(\?|$)", att, re.I):
        try:
            raw = fetch(att, binary=True, referer=url)
        except Exception as e:                   # noqa: BLE001
            return f"附件取不到（{type(e).__name__}）"
        txt, _ = extract_pdf(raw)
        if len(txt) < 50:
            return "附件 PDF 无可抽取文字层（扫描件或字体缺 Unicode 映射）"
        if re.search(r"申请书|表格|附\s*件\s*一|附录\s*A", txt[:400]):
            return "附件为表格或附录，非条文正文"
        return "附件 PDF 抽取内容非条文"
    # doc / docx / wps
    try:
        raw = fetch(att, binary=True, referer=url)
    except Exception as e:                       # noqa: BLE001
        return f"附件取不到（{type(e).__name__}）"
    txt = extract_doc(raw)
    if len(txt) > 200:
        return "附件为 Word，抽取未通过条文校验"
    if raw[:4] == b"\xd0\xcf\x11\xe0":
        return "附件为二进制 .doc（Word 97），本机无解析器"
    return "附件为 Word 文档，本机无可用解析器"


def main():
    records = json.loads(SRC.read_text(encoding="utf-8"))
    todo = [r for r in records if not r.get("fullText")]
    print(f"待标注 {len(todo)} 条", flush=True)
    for i, r in enumerate(todo, 1):
        reason = diagnose(r.get("sourceUrl") or "")
        rl = r.setdefault("recordLevel", {})
        rl["textStatus"] = reason
        rl["fullTextNote"] = "本页未收录条文正文，理由见「正文状态」；点官方原文链接可自行查阅。"
        print(f"  [{i}/{len(todo)}] {r['recordId']:22} {reason}", flush=True)
    SRC.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    got = sum(1 for r in records if r.get("fullText"))
    print(f"\n完成：全文 {got} / {len(records)} 条，其余 {len(records) - got} 条已标注原因")


if __name__ == "__main__":
    main()
