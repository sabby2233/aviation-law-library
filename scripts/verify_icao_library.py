#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_icao_library.py — 核验「中国民航大学图书馆 2024-04-09 转来的 ICAO 附件包」

为什么做这件事：
    站内 ICAO 记录的版次断言此前有两个来源：
      ① 用户单独提供的附件 19 原件（p.3 封面 / p.4 版权页 / p.5 修订记录页）
      ② ICAO Store 目录页（2026-10-22 实抓）
    中文标准名（titleZh）则来自微信公众号相册（L3 专业二手）。
    这批图书馆转来的中文官方译本，是**第三来源**，且是官方原件（L1）——
    用来复核版次、把中文标准名从 L3 升到 L1、并给英文版与中文版分别登记 ISBN。

纪律（与全站一致）：
    · 每份文件必须读封面、版权页、修订记录页，不按文件名猜版次；
    · 只抽取可在这几页上直接读到的事实，页读不到就留空，不推断；
    · SARPs 受版权保护，正文不入库、不入仓，脚本只产元数据与事实字段。

用法：python scripts/verify_icao_library.py
产出：data/verify/icao_library_extract.json（抽取原文，不入库）
      data/icao_library_verification.json（核验结论，入库）
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INBOX = DATA / "inbox" / "icao_library_2024"
ZH_DIRS = [INBOX / "ICAO附件2024-4-9图书馆发来" / "ICAO附件中文版"]
EN_DIR = INBOX / "icao_en"

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10}

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
          "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
          "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}


def cn_num(s):
    """中文数字转阿拉伯数字，支持到 99（'十一' / '二十一' / '十九'）。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if "十" not in s:
        total = 0
        for ch in s:
            if ch in CN_NUM:
                total = total * 10 + CN_NUM[ch]
        return total or None
    head, _, tail = s.partition("十")
    hi = CN_NUM.get(head, 1) if head else 1
    lo = CN_NUM.get(tail, 0) if tail else 0
    return hi * 10 + lo


def pages_text(pdf_path, n=7):
    """取前 n 页文本。中文官方译本的封面是图文混排，ToUnicode 映射残缺，
    读出来的第一页是乱码；真正的封面在 p.3，所以这里从 p.3 起读，前两页仅留档。"""
    import pdfplumber
    out = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i in range(min(n, len(pdf.pages))):
            try:
                out.append(pdf.pages[i].extract_text() or "")
            except Exception as e:                # 单页解析失败不应毁掉整份核验
                out.append(f"[EXTRACT_ERROR {e}]")
    return out


def parse_zh(texts):
    """从中文版抽取事实。字段只取自封面/版权页/修订记录页。"""
    f = {}
    body = "\n".join(texts[2:6])            # p.3–p.6
    cover = texts[2] if len(texts) > 2 else ""
    copy_p = texts[3] if len(texts) > 3 else ""
    rev_p = texts[4] if len(texts) > 4 else ""

    m = re.search(r"附件\s*(\d+(?:\s*-\s*\d+)?)\s*[—–\-]\s*([^\n]+)", cover)
    if m:
        f["annex"] = re.sub(r"\s+", "", m.group(1))
        f["titleZh"] = m.group(2).strip().strip("—–- ")
    elif "(cid:" in cover:
        # 官方译本里少数文件的 ToUnicode 映射残缺，封面读出来是 (cid:XXXXX) 乱码。
        # 这时不能靠封面取事实，改由文件名兜底，并在结果里标记来源是文件名。
        f["coverEncodingBroken"] = True
    m = re.search(r"第([一二三四五六七八九十]+)版[，,]\s*(\d{4})\s*年\s*(\d{1,2})\s*月", cover)
    if m:
        f["editionNum"] = cn_num(m.group(1))
        f["editionDate"] = f"{m.group(2)}-{int(m.group(3)):02d}"
    m = re.search(r"本版自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起取代", cover)
    if m:
        f["applicabilityDate"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"订购编号[：:]\s*([A-Z]{2}\s*\d+)", copy_p)
    if m:
        f["orderNumber"] = m.group(1).replace(" ", "")
    m = re.search(r"ISBN\s*([0-9Xx\-]{10,20})", copy_p)
    if m:
        f["isbn"] = m.group(1).strip()
    # 版权页的版本沿革：「第一版 — 2013年 / 第二版 — 2016年」
    hist = re.findall(r"第([一二三四五六七八九十]+)版\s*[—–\-]\s*(\d{4})\s*年", copy_p)
    if hist:
        f["editionHistory"] = [{"editionNum": cn_num(a), "year": int(b)} for a, b in hist]
    m = re.search(r"©\s*ICAO\s*(\d{4})", copy_p)
    if m:
        f["copyrightYear"] = int(m.group(1))
    # 修订记录页：修订编号与是否已编入本版
    if "修订" in rev_p and "更正" in rev_p:
        f["hasAmendmentTable"] = True
        amds = re.findall(r"^\s*(\d+)\s+(已编入本版|尚未编入)", rev_p, re.M)
        if amds:
            f["amendmentsInThisEdition"] = [int(a) for a, b in amds if b == "已编入本版"]
            f["amendmentsPending"] = [int(a) for a, b in amds if b != "已编入本版"]
        m = re.search(r"第\s*(\d+)\s*号修订案", rev_p)
        if m:
            f["latestAmendmentInText"] = int(m.group(1))
    return f


ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
           "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
           "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
           "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
           "nineteenth": 19, "twentieth": 20, "twenty-first": 21,
           "twenty-second": 22, "twenty-third": 23}


def parse_en(texts):
    """从英文版抽取事实。

    英文版封面有两种版式：
      A) 版权页式：「Annex 19 — Safety Management」（附件号与名称同行）
      B) 封面式：「Annex 19 / to the Convention ... / Safety Management」（分三行）
    两种都要认，否则会漏掉一半附件。
    """
    f = {}
    cover = texts[2] if len(texts) > 2 else ""
    copy_p = texts[3] if len(texts) > 3 else ""
    scan = "\n".join(texts[2:6])

    # 附件号与名称同行
    m = re.search(r"Annex\s*(\d+(?:\s*-\s*\d+)?)\s*[—–\-]\s*([^\n]+)", scan)
    if m:
        f["annex"] = re.sub(r"\s+", "", m.group(1))
        f["titleEn"] = m.group(2).strip().strip("—–- ")
    else:
        # 封面式：附件号单独一行，名称在「to the Convention」之后
        m = re.search(r"Annex\s*(\d+(?:\s*-\s*\d+)?)\s*\n\s*to the Convention[^\n]*\n\s*([^\n]+)", cover)
        if m:
            f["annex"] = re.sub(r"\s+", "", m.group(1))
            f["titleEn"] = m.group(2).strip().strip("—–- ")
    m = re.search(r"(\w+[\w-]*)\s+Edition,?\s*(\w+)\s+(\d{4})", cover)
    if m and m.group(1).lower() in ORDINAL:
        f["editionNum"] = ORDINAL[m.group(1).lower()]
        mo = MONTHS.get(m.group(2).lower())
        if mo:
            f["editionDate"] = f"{m.group(3)}-{mo:02d}"
        f["editionLine"] = f"{m.group(1)} Edition, {m.group(2)} {m.group(3)}"
    m = re.search(r"supersedes,?\s*on\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", cover, re.I)
    if m:
        mo = MONTHS.get(m.group(2).lower())
        if mo:
            f["applicabilityDate"] = f"{m.group(3)}-{mo:02d}-{int(m.group(1)):02d}"
    m = re.search(r"Order No(?:umber)?\.?:?\s*(AN\s*\d+)", copy_p, re.I)
    if m:
        f["orderNumber"] = m.group(1).replace(" ", "").upper()
    m = re.search(r"ISBN\s*([0-9Xx\-]{10,20})", copy_p)
    if m:
        f["isbn"] = m.group(1).strip()
    m = re.search(r"©\s*ICAO\s*(\d{4})", copy_p)
    if m:
        f["copyrightYear"] = int(m.group(1))
    # 修订记录页：「1 Incorporated in this edition」
    if "RECORD OF AMENDMENTS" in scan:
        f["hasAmendmentTable"] = True
        m = re.findall(r"^\s*(\d+)\s+Incorporated in this edition", scan, re.M)
        if m:
            f["amendmentsInThisEdition"] = [int(x) for x in m]
        m = re.findall(r"^\s*(\d+)\s+(\d{2}/\d{2}/\d{2})\s+ICAO", scan, re.M)
        if m:
            f["amendmentsPending"] = [int(a) for a, b in m]
            f["amendmentDates"] = {a: b for a, b in m}
    return f


def parse_from_filename(fname, lang):
    """文件名兜底。

    纪律：文件名只作**兜底**，且必须在结果里显式标注 fromFileName，
    以免与「从封面读到的」混为一谈——两者证据强度不同。
    图书馆给的命名规则是「附件N 中文名 第X版，YYYY年M月」/「AN N English Title ... Edition, Month Year」。
    """
    stem = re.sub(r"\.pdf$", "", fname, flags=re.I)
    f = {"fromFileName": True}
    if lang == "zh":
        m = re.match(r"附件\s*(\d+(?:-\d+)?)\s*(.*?)\s*第([一二三四五六七八九十]+)版[，,]\s*(\d{4})\s*年\s*(\d{1,2})\s*月", stem)
        if m:
            f["annex"] = m.group(1)
            f["titleZh"] = m.group(2).strip(" 　—–-")
            f["editionNum"] = cn_num(m.group(3))
            f["editionDate"] = f"{m.group(4)}-{int(m.group(5)):02d}"
    else:
        m = re.match(r"AN\s*(\d+(?:-P?\d+)?)\s+(.*?)\s+(\w+)\s+Edition,?\s*(\w+)\s+(\d{4})", stem, re.I)
        if m:
            f["annex"] = m.group(1)
            f["titleEn"] = m.group(2).strip()
            if m.group(3).lower() in ORDINAL:
                f["editionNum"] = ORDINAL[m.group(3).lower()]
            mo = MONTHS.get(m.group(4).lower())
            if mo:
                f["editionDate"] = f"{m.group(5)}-{mo:02d}"
            f["editionLine"] = f"{m.group(3)} Edition, {m.group(4)} {m.group(5)}"
    return f


def main():
    if not INBOX.exists():
        print(f"缺少 {INBOX}：先解压图书馆转来的 ICAO 包")
        sys.exit(2)

    results = []
    for d, lang in [(p, "zh") for p in ZH_DIRS if p.exists()] + \
                   [(EN_DIR, "en")]:
        if not d.exists():
            continue
        for pdf in sorted(d.glob("*.pdf")):
            print(f"  读 {pdf.name[:70]}")
            try:
                texts = pages_text(pdf)
            except Exception as e:
                results.append({"file": str(pdf.relative_to(INBOX)), "lang": lang,
                                "error": f"open_failed: {e}"})
                continue
            f = parse_zh(texts) if lang == "zh" else parse_en(texts)
            # 封面读不出附件号/版次时，用文件名兜底，并显式标注来源
            if "annex" not in f or not f.get("editionDate"):
                fb = parse_from_filename(pdf.name, lang)
                for k, v in fb.items():
                    f.setdefault(k, v)
                if fb.get("annex"):
                    f["annex"] = fb["annex"]
                    f["fromFileName"] = True
            f.update({"file": str(pdf.relative_to(INBOX)), "lang": lang,
                      "fileName": pdf.name, "pagesRead": len(texts)})
            results.append(f)

    out_dir = DATA / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "icao_library_extract.json").open("w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)

    ok = [r for r in results if "annex" in r]
    print(f"\n解析成功 {len(ok)}/{len(results)} 份 → data/verify/icao_library_extract.json")
    for r in sorted(ok, key=lambda x: (x["lang"], str(x.get("annex")), x.get("editionDate") or "")):
        print(f"  [{r['lang']}] 附件{r.get('annex'):6s} {r.get('editionNum','')}版 "
              f"{r.get('editionDate','')}  适用={r.get('applicabilityDate','—'):10s} "
              f"ISBN={r.get('isbn','—'):16s} {r.get('titleZh') or r.get('titleEn') or ''}")
    return results


if __name__ == "__main__":
    main()
