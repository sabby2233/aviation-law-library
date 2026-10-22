#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_federal_register.py — 美国联邦公报航空法规采集

信源：Federal Register Public API（https://www.federalregister.gov/api/v1/）
实测：航空相关文档 3777 条；支持按机构 + 文档类型 + 关键词精确过滤；
每条含 publication_date / effective_on / citation(文号) / html_url（全文）/
agencies / type，是机器可读的最可靠航空法规源之一。

特点：无需 API Key，无需登录，是本项目最重要的法规类信源。
输出：data/records/regulations_us.json
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "records" / "regulations_us.json"

API = "https://www.federalregister.gov/api/v1/documents.json"
UA = "aviation-law-library/1.0 (research; contact via repository issues)"

# 只取与航空直接相关的机构
AVIATION_AGENCIES = [
    "federal-aviation-administration",
    "transportation-department",
    "aviation-safety-organization",
    "national-transportation-safety-board",
]

# 文档类型：正式规则、拟议规则、通知（公告类）
DOC_TYPES = ["RULE", "PRORULE", "NOTICE"]

# 关键词：航空业务词。命中即视为航空相关（与 FR 的全文索引配合）
KEYWORDS = [
    "air carrier", "airline", "aircraft", "aviation", "airport",
    "airworthiness", "unmanned", "drone", "pilot", "flight crew",
    "passenger", "airspace", "helicopter", "eVTOL",
]

FIELDS = [
    "title", "publication_date", "effective_on", "html_url", "pdf_url",
    "agencies", "citation", "type", "document_number", "action",
    "abstract", "regulation_id_numbers", "docket_ids", "topics",
    "cfr_references", "start_page", "end_page", "volume", "page_length",
]

PAGE_SIZE = 100
MAX_PAGES = 12          # 单次运行上限，控制请求量
REQUEST_DELAY = 1.1     # 秒，遵守礼貌抓取


def fetch(params):
    url = API + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def build_query(agency, doc_type, keyword, newest_first=True):
    """构造 FR API 查询参数。

    注意：FR 的数组条件键名必须写成 conditions[xxx][]，
    这里的 key 已是完整键名，不要再套一层 f'conditions[{k}]'，
    否则会拼出 conditions[type[]] 这种畸形键导致 HTTP 400。
    """
    params = {
        "per_page": PAGE_SIZE,
        "order": "newest" if newest_first else "oldest",
        "conditions[agencies][]": agency,
        "conditions[type][]": doc_type,
        "conditions[term]": keyword,
    }
    for f in FIELDS:
        params["fields[]"] = params.get("fields[]", [])
        params["fields[]"].append(f)
    return params


def to_record(doc, agency):
    """FR 文档 → 本站记录格式"""
    agencies = [a.get("name") for a in (doc.get("agencies") or []) if a.get("name")]
    # 归一：DOT 下属的 FAA 名称在 FR 里可能是 "Transportation Department"
    if "Federal Aviation Administration" in agencies:
        authority = "Federal Aviation Administration (FAA)"
    else:
        authority = agencies[0] if agencies else "U.S. Federal Register"

    doc_type = (doc.get("type") or "").upper()
    record_type = {
        "RULE": "legislation",
        "PRORULE": "legislation",
        "NOTICE": "policy",
    }.get(doc_type, "legislation")

    # recordId：AVA-US-<类型>-<年份>-<序号>，永久标识，永不复用、永不重编
    #
    # FR 的 document_number 有三种历史格式，必须分别处理：
    #   1) "2026-21422"  —— 四位年 + 序号（1994 年后）
    #   2) "00-22564"    —— 两位年 + 序号（2000 年前后，年份需补全为 4 位）
    #   3) "93-31907"    —— 两位年 + 序号（1994 年前后）
    # 直接按 "-" 切分会把两位年份当成不完整的四位年，故须按长度判断。
    # 序号统一补零到 6 位，避免不同原始长度相撞（如 0083 与 83）。
    doc_num = doc.get("document_number") or "000000"
    pub = (doc.get("publication_date") or "")[:4]
    parts = doc_num.split("-")
    head = parts[0] if parts else ""

    if len(head) == 4 and head.isdigit():
        year = head
        seq = parts[1] if len(parts) > 1 else ""
    elif len(head) == 2 and head.isdigit():
        # 两位年份：1993-1999 → 1990+xx；2000-2009 → 2000+xx
        yy = int(head)
        year = f"19{yy:02d}" if yy >= 90 else f"20{yy:02d}"
        seq = parts[1] if len(parts) > 1 else ""
    else:
        year = pub if pub.isdigit() else "0000"
        seq = "".join(ch for ch in doc_num if ch.isdigit())

    seq = (seq + "000000")[:6]
    type_code = {"RULE": "R", "PRORULE": "P", "NOTICE": "N"}.get(doc_type, "X")
    # recordId：AVA-US-FR-<文种>-<年份>-<序号>
    #   文种段（RULE/PRORULE/NOTICE → R/P/N）保留在标识符内，
    #   因为同一 document_number 在不同文种下是不同文书。
    rid = make_id("US", "FR", f"{type_code}-{year}-{seq}")

    dates = {
        "publicationDate": doc.get("publication_date"),
        "effectiveDate": doc.get("effective_on"),
        "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    cfr = doc.get("cfr_references") or []
    topics = [t.lower() for t in (doc.get("topics") or [])]

    # CFR 引用：FR 返回对象数组 [{title, part, chapter}]，需转成 "14 CFR 93" 形式
    cfr_texts = []
    for c in cfr:
        if isinstance(c, dict):
            t, p = c.get("title"), c.get("part")
            if t and p:
                cfr_texts.append(f"{t} CFR {p}")
            elif t:
                cfr_texts.append(f"{t} CFR")
        elif isinstance(c, str):
            cfr_texts.append(c)

    # 主题标签：从 FR 官方 topics + 关键词命中推导
    tagset = set(topics)
    kw = (doc.get("title") or "").lower()
    if "unmanned" in kw or "drone" in kw or "remote id" in kw:
        tagset.add("uav")
    if "airworthiness" in kw or "type certif" in kw:
        tagset.add("airworthiness")
    if "privacy" in kw or "personal data" in kw:
        tagset.add("data-protection")
    if "safety" in kw or "accident" in kw:
        tagset.add("safety")

    summary = (doc.get("abstract") or "").strip()
    if not summary:
        action = (doc.get("action") or "").strip()
        summary = action[:400] if action else ""

    assertion_fields = {
        "publication_date": doc.get("publication_date"),
        "effective_date": doc.get("effective_on"),
        "citation": doc.get("citation"),
        "document_number": doc_num,
        "agency": authority,
        "cfr_references": ", ".join(cfr_texts[:12]) if cfr_texts else None,
        "docket_ids": ", ".join(doc.get("docket_ids") or []) or None,
        "action": (doc.get("action") or "").strip()[:500] or None,
    }

    return {
        "recordId": rid,
        "recordType": record_type,
        "title": (doc.get("title") or "").strip(),
        "summary": summary,
        "jurisdiction": "US",
        "topics": sorted(tagset),
        "status": "not_yet_effective" if doc_type == "PRORULE" else "adopted",
        "dates": {k: v for k, v in dates.items() if v},
        "citationString": doc.get("citation") or "",
        "assertions": [
            {
                "field": f,
                "value": str(v),
                "sourceId": f"FR-{doc.get('document_number')}",
                "locator": "document metadata",
                "evidenceLevel": "L0",
                "verifiedAt": dates["retrievedAt"],
            }
            for f, v in assertion_fields.items()
            if v
        ],
        "sourceUrl": doc.get("html_url"),
        "pdfUrl": doc.get("pdf_url"),
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    records = []
    total_calls = 0

    for agency in AVIATION_AGENCIES:
        for doc_type in DOC_TYPES:
            for keyword in KEYWORDS:
                if total_calls >= MAX_PAGES:
                    break
                params = build_query(agency, doc_type, keyword)
                params["page"] = 1
                try:
                    data = fetch(params)
                except Exception as e:
                    print(f"  [warn] {agency}/{doc_type}/{keyword}: {e}")
                    total_calls += 1
                    time.sleep(REQUEST_DELAY)
                    continue
                total_calls += 1

                for doc in data.get("results", []):
                    num = doc.get("document_number")
                    if not num or num in seen:
                        continue
                    seen.add(num)
                    rec = to_record(doc, agency)
                    rec["sourceUrl"] = doc.get("html_url")
                    records.append(rec)

                print(f"  {agency:<38} {doc_type:<8} {keyword:<16} → 本次 {len(data.get('results', []))} 条")
                time.sleep(REQUEST_DELAY)

    # 排序：公布日倒序
    records.sort(key=lambda r: (r.get("dates", {}).get("publicationDate") or ""), reverse=True)

    with OUT.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\n完成：{len(records)} 条唯一记录 → {OUT.relative_to(ROOT)}")
    print(f"请求次数 {total_calls}，覆盖机构 {len(AVIATION_AGENCIES)}，类型 {len(DOC_TYPES)}，关键词 {len(KEYWORDS)}")


if __name__ == "__main__":
    main()
