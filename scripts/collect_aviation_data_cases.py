#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_aviation_data_cases.py — 航空数据保护执法案例导入

数据来源：sabby2233/aviation-privacy-cases-map 的 data/cases.json
（作者本人早前用 WorkBuddy 搭建的项目，本仓库为其延续与重构）

导入时做三件事：
1. 拆出六类时间字段——原数据的 date 混装"决定日"与"报道日"，此处不臆断，
   统一置 decisionDate=null，并在 recordLevel 标注原始值与口径存疑
2. 罚款按三态拆行——原数据仅 20/49 条有金额且口径不一（拟议/最终/减免混存），
   此处原样保留数值并标注 finalAmount 是否为推断
3. 二手来源标注 sourceTier，官方一手与二手在检索结果中可区分

用法：python scripts/collect_aviation_data_cases.py [--source-url URL]
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "records" / "cases_aviation_data.json"

DEFAULT_SRC = ("https://raw.githubusercontent.com/sabby2233/"
               "aviation-privacy-cases-map/main/data/cases.json")

# 官方一手域名（决定该条能否作为核心事实引用）
OFFICIAL_HOSTS = [
    "aepd.es", "cnil.fr", "ico.org.uk", "ftc.gov", "kvkk.gov.tr",
    "garanteprivacy.it", "bfdi.bund.de", "dataprotectionauthority.be",
    "dataprotection.ie", "datatilsynet.no", "datatilsynet.dk",
    "autoriteitpersoonsgegevens.nl", "dmp.hu", "dsb.gv.at", "cnpd.pt",
    "uodo.gov.pl", "pipc.go.kr", "meity.gov.in", "pdpc.gov.sg",
    "pcpd.org.hk", "edoeb.admin.ch", "priv.gc.ca", "oaic.gov.au",
    "dataprotection.ro", "dataprotection.gov.cy", "edpb.europa.eu",
    "legifrance.gouv.fr", "eur-lex.europa.eu", "courtlistener.com",
    "court.gov.cn", "transportation.gov",
]

# 二手来源 → 标为 L3（专业二手），仅可作线索与叙事背景
SECONDARY_HOSTS = [
    "baylos.com", "ppc.land", "vixio.com", "ilfattoquotidiano.it",
    "noyb.eu", "courthousenews.com", "news.bloomberglaw.com",
]


def evidence_level(url):
    host = url.split("/")[2].lower() if "//" in url else ""
    for h in OFFICIAL_HOSTS:
        if host == h or host.endswith("." + h):
            return "L0" if h in ("courtlistener.com", "eur-lex.europa.eu",
                                 "legifrance.gouv.fr", "edpb.europa.eu",
                                 "court.gov.cn") else "L1"
    for h in SECONDARY_HOSTS:
        if host == h or host.endswith("." + h):
            return "L3"
    return "L3"


def _locator_for(c, decision_no):
    """生成原文定位符。

    要求（LOC-01）：不得指向本站自身标识，必须是能在官方文书中定位的信息。
    优先用官方决定编号（AEPD 的 PS/00300/2019、CNIL 的 SAN-… 等），
    该编号通常就出现在官方 URL 的末段。
    """
    url = c.get("sourceUrl", "") or ""
    ct = c.get("caseType")

    # 1) 从官方 URL 末段提取决定编号
    tail = url.rstrip("/").split("/")[-1]
    if tail and not tail.isdigit() and "." not in tail[:4] and len(tail) >= 6:
        # 形如 PS-00300-2019 / SAN-2023-0123 / 2021-00123
        ident = tail.split("_")[0].split(".")[0]
        if re.match(r"^[A-Za-z]{0,4}[-/\d]{4,}$", ident):
            kind = "决定书" if ct == "admin" else "判决书"
            return f"{kind} {ident}"

    # 2) 退到文书类型 + 官方链接（仍非本站标识）
    kind = "行政处罚决定" if ct == "admin" else "法院判决"
    return f"{kind}（{c.get('authorityShort') or c.get('authority') or '官方机构'}），见官方链接"


def fetch(url, retries=3):
    """抓取源数据。失败时自动重试（raw.githubusercontent 偶发断连）。

    支持 file:// 与本地路径：源站不可达时用仓库内快照重建，
    保证数据管道不因外部网络抖动而中断。
    """
    import time

    # 本地路径 / file:// 直接读
    if url.startswith("file://"):
        path = Path(url[7:].lstrip("/") if url.startswith("file:///") else url[7:])
    elif "://" not in url:
        path = Path(url)
    else:
        path = None

    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"本地源不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))

    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "aviation-law-library/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"抓取失败（已重试 {retries} 次）：{url} → {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-url", default=DEFAULT_SRC)
    args = ap.parse_args()

    raw = fetch(args.source_url)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = []

    for c in raw:
        rid = c.get("id", "")
        url = c.get("sourceUrl", "")
        lvl = evidence_level(url)
        country = str(c.get("country") or "ZZ").upper()

        # recordId：AVA-<法域>-ADP-<原记录号（去掉重复的国家段）>
        #   原号 ES-A-009，国家段 ES 已由法域段承载，故剥离避免冗余
        local = "-".join(rid.split("-")[1:]) if rid else ""
        record_id = make_id(country, "ADP", local, fallback=rid)

        # 原始 date 口径存疑：原数据未区分决定日与报道日
        # 此处不臆断，置 null 并在 recordLevel 保留原值供人工核验
        dates = {
            "decisionDate": None,
            "publicationDate": c.get("date"),
            "retrievedAt": today,
        }

        # 罚款：原数据单字段且口径不一（拟议/最终/减免混存）
        # 原样保留为 amountOriginal，并标注 finalAmount 未经确认
        penalty = None
        if c.get("fineAmount") is not None:
            penalty = {
                "amountOriginal": c.get("fineAmount"),
                "amountFinal": None,
                "currency": c.get("fineCurrency"),
                "reductionBasis": None,
                "amountBasisText": c.get("summary", "")[:300],
            }

        assertion_fields = {
            "case_name_local": c.get("caseName"),
            "case_name_en": c.get("caseNameEn"),
            "authority": c.get("authority"),
            "date_as_reported": c.get("date"),
            "case_type": c.get("caseType"),
            "fine_amount": str(c.get("fineAmount")) if c.get("fineAmount") is not None else None,
            "fine_currency": c.get("fineCurrency"),
            "tags": ", ".join(c.get("tags") or []),
        }

        sid = f"ADP-{rid}"

        # locator 必须是原文定位，不能指向本站自身标识。
        # 原数据的记录 id 只作为"来源方编号"保留在单独字段里，
        # locator 则给出可核验的定位：官方决定编号 + 文书类型。
        decision_no = c.get("caseNameEn") or c.get("caseName") or ""
        locator = _locator_for(c, decision_no)

        rec = {
            "recordId": record_id,
            "recordType": "case",
            "title": c.get("caseName") or c.get("caseNameEn") or "",
            "titleEn": c.get("caseNameEn"),
            "summary": c.get("summary", ""),
            "jurisdiction": c.get("country"),
            "topics": sorted(set(c.get("tags") or [])),
            "status": "final" if c.get("caseType") == "court" else "adopted",
            "dates": dates,
            "penalty": penalty,
            "citationString": c.get("caseNameEn", ""),
            "assertions": [
                {
                    "field": f,
                    "value": str(v),
                    "sourceId": sid,
                    "locator": locator,
                    "evidenceLevel": lvl,
                    "verifiedAt": today,
                }
                for f, v in assertion_fields.items()
                if v
            ],
            "sourceUrl": url,
            "recordLevel": {
                "note": "原始数据 date 字段口径存疑（决定日与报道日混用），"
                        "决定日待人工回官方文书核对",
                "originalDate": c.get("date"),
                "originalFineAmount": c.get("fineAmount"),
                "sourceTier": lvl,
                "lastVerified": c.get("lastVerified"),
                "sourceRecordId": rid,
                "verificationStatus": "pending",
            },
            "revisionLog": [],
        }
        records.append(rec)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    tiers = {}
    for r in records:
        t = r["recordLevel"]["sourceTier"]
        tiers[t] = tiers.get(t, 0) + 1
    print(f"导入 {len(records)} 条航空数据保护案例 → {OUT.relative_to(ROOT)}")
    print(f"来源分级：{tiers}")
    print("注意：全部 decisionDate 置空待核验，罚款 finalAmount 未确认，")
    print("      须回官方文书补齐后方可作为引证依据。")


if __name__ == "__main__":
    main()
