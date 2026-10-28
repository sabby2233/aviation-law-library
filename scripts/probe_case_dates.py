#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_case_dates.py — 探测未核案例的官方页面，看决定日能否直接读出

背景：
    49 条案例里 23 条 decisionDate 为 null。导入脚本当年的处理是：
    上游 cases.json 的 date 字段「混装决定日与报道日」，无法判定口径，
    于是统一置空（见 collect_aviation_data_cases.py 顶部说明）。
    这导致卡片上 23 条显示「决定日未知（待核验）」。

本脚本不写库，只做探测与取证：
    对每条缺口，抓官方页面（curl 通道，WebFetch 在本机被代理拦），
    在页面文本里搜「决定日 / 落款日 / 判决日」这类日期标记，
    把命中的上下文原样打印出来，供人工判断该日期是决定日还是报道日。

用法：python scripts/probe_case_dates.py [recordId ...]
产出：data/case_date_probe.json（探测原始证据，不入库）
"""

import json
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.parse as up
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "records" / "cases_aviation_data.json"
OUT = ROOT / "data" / "case_date_probe.json"

# 日期标记。多语言覆盖：英/德/法/西/荷/葡/瑞典/土耳其/匈/韩
DATE_HINT = re.compile(
    r"(decision\s+date|date\s+of\s+decision|decided\s+on|dated|décision\s+du|"
    r"entscheidung\s+vom|besluit\s+van|decisão\s+de|beslut\s+datum|karar\s+tarihi|"
    r"határozat\s+kelte|의결일|결정일|决定日期|判决日期|日期|datum|fecha|data)",
    re.I)

# 各种写法里的日期：2023-01-31 / 31.01.2023 / 31/01/2023 / January 31, 2023 / 31 January 2023
DATE_PAT = re.compile(
    r"(\d{4}-\d{2}-\d{2})|(\d{1,2}[./]\d{1,2}[./]\d{4})|"
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4})|"
    r"((?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},?\s+\d{4})", re.I)


def fetch(url, timeout=45):
    """用 curl 取页面。WebFetch 在本机走代理被拦，curl 直连正常。"""
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "--insecure",
             "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
             url],
            capture_output=True, timeout=timeout + 10)
        return r.stdout
    except Exception:
        return b""


def pdf_text(raw):
    """PDF 就用 pdfplumber 抽；抽不出说明是扫描件，如实报。"""
    try:
        import pdfplumber
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(raw)
            p = f.name
        with pdfplumber.open(p) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages[:8])
    except Exception as e:
        return f"[PDF_EXTRACT_FAILED: {e}]"


def html_text(raw):
    t = raw.decode("utf-8", "ignore")
    if "<html" not in t.lower() and "<!doctype" not in t.lower():
        return ""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;?", " ", t)
    return re.sub(r"\s+", " ", t)


def snippets(text, width=110):
    """把命中的日期连同上下文切出来——只看日期本身无法判断是决定日还是报道日。"""
    out = []
    for m in DATE_HINT.finditer(text):
        s = max(0, m.start() - width)
        e = min(len(text), m.end() + width)
        frag = re.sub(r"\s+", " ", text[s:e]).strip()
        dates = DATE_PAT.findall(frag)
        if dates:
            out.append({"hint": m.group(0), "context": frag[:260],
                        "dates": [next(x for x in d if x) for d in dates][:4]})
        if len(out) >= 6:
            break
    return out


def main():
    ids = [a for a in sys.argv[1:] if not a.startswith("-")]
    data = json.loads(CASES.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    targets = [r for r in recs if not (r.get("dates") or {}).get("decisionDate")]
    if ids:
        targets = [r for r in targets if r["recordId"] in ids]

    results = []
    for r in targets:
        url = r.get("sourceUrl") or ""
        print(f"\n── {r['recordId']}  {url[:80]}")
        raw = fetch(url)
        if not raw:
            print("   ✗ 取不到（超时/拒绝）")
            results.append({"recordId": r["recordId"], "url": url, "status": "fetch_failed"})
            continue
        is_pdf = raw[:5] == b"%PDF-" or raw[:1024].lower().find(b"%pdf") >= 0
        text = pdf_text(raw) if is_pdf else html_text(raw)
        if not text:
            print(f"   ✗ 取到 {len(raw)} 字节但无可解析文本（可能是 JS 渲染或扫描件）")
            results.append({"recordId": r["recordId"], "url": url,
                            "status": "no_text", "bytes": len(raw), "isPdf": is_pdf})
            continue
        sn = snippets(text)
        print(f"   ✓ {len(raw):,} 字节｜{'PDF' if is_pdf else 'HTML'}｜命中日期标记 {len(sn)} 处")
        for s in sn[:3]:
            print(f"     [{s['hint']}] {s['context'][:150]}")
        results.append({"recordId": r["recordId"], "url": url, "status": "ok",
                        "isPdf": is_pdf, "bytes": len(raw),
                        "snippets": sn, "textHead": text[:600]})

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    ok = sum(1 for x in results if x["status"] == "ok")
    print(f"\n探测 {len(results)} 条：可读文本 {ok} 条，取不到/无文本 {len(results) - ok} 条 → {OUT.name}")


if __name__ == "__main__":
    main()
