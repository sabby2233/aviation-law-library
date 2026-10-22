#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_sources.py — 从记录中的断言反推来源登记表

来源登记表是「每个字段值都能回溯到一份可核对材料」的载体。
记录里每条断言都挂 sourceId，本脚本把这些 sourceId 汇总成登记表，
并写入 URL、机构、证据等级、检索方式、检索式、检索日期。

关键纪律：**证据等级必须从断言派生，不得按文件名硬编码。**
此前把 cases_aviation_data.json 整文件硬编码为 L1，与记录内的 L0/L1/L3 冲突，
导致 12/49 条的登记等级与实际不符，一手来源占比被高估。

用法：python scripts/build_sources.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 等级由严到宽：取该来源下所有断言中最严格的一个
LEVEL_ORDER = ["L0", "L1", "L2", "L3", "L4", "L5"]

# 官方机构（用于 source 记录的 authority 与 documentType 兜底）
KNOWN_AUTHORITIES = {
    "federal-register": ("Federal Register (U.S.)", "US", "regulation"),
    "aviation-data-cases": ("各国数据保护机构（DPA）与法院", "", "enforcement_decision"),
}


def stricter(a, b):
    """取两个等级中更严格的一个。"""
    if not a:
        return b
    if not b:
        return a
    return a if LEVEL_ORDER.index(a) <= LEVEL_ORDER.index(b) else b


def main():
    rec_dir = DATA / "records"
    sources = {}
    skipped = []

    for p in sorted(rec_dir.glob("*.json")):
        with p.open(encoding="utf-8") as f:
            records = json.load(f)
        for r in records:
            for a in r.get("assertions", []):
                sid = a.get("sourceId")
                if not sid:
                    continue
                if sid in sources:
                    # 已登记：等级取更严格者，并补充可能缺失的字段
                    cur = sources[sid]
                    cur["evidenceLevel"] = stricter(cur.get("evidenceLevel"),
                                                  a.get("evidenceLevel"))
                    if not cur.get("retrievedAt") and a.get("verifiedAt"):
                        cur["retrievedAt"] = a["verifiedAt"]
                    continue

                # 机构名优先取断言中的 authority 字段；缺失时按来源特征兜底
                authority = _authority_of(r)
                if not authority:
                    authority = ("Federal Register (U.S. Office of the Federal Register)"
                                 if "federalregister.gov" in (r.get("sourceUrl") or "")
                                 else "未标注（须回原文核验）")

                sources[sid] = {
                    "sourceId": sid,
                    "url": r.get("sourceUrl", ""),
                    "authority": authority,
                    "jurisdiction": r.get("jurisdiction", ""),
                    "documentType": _doc_type_of(r),
                    "documentNo": r.get("citationString", ""),
                    # 等级从断言派生，不硬编码
                    "evidenceLevel": a.get("evidenceLevel", "L3"),
                    "retrievedAt": a.get("verifiedAt")
                    or r.get("dates", {}).get("retrievedAt")
                    or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "retrievalChannel": _channel_of(r),
                    "retrievalQuery": _query_of(r),
                    "language": _lang_of(r),
                    "title": r.get("title", ""),
                    # 核验状态：API 抓取即已核对官方元数据；人工录入须逐条核验
                    "verificationStatus": _verification_status(r),
                    "locatorScheme": _locator_scheme(r),
                    # 存档与永久标识：目前无快照，故显式标注状态
                    "snapshotUrl": None,
                    "archiveStatus": "not-archived",
                }

    out = DATA / "sources"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "registry.json"
    with target.open("w", encoding="utf-8") as f:
        json.dump(list(sources.values()), f, ensure_ascii=False, indent=2)

    # 分级统计
    dist = {}
    for s in sources.values():
        dist[s["evidenceLevel"]] = dist.get(s["evidenceLevel"], 0) + 1
    print(f"来源登记表：{len(sources)} 条 → {target.relative_to(ROOT)}")
    print(f"等级分布（由断言派生）：{dict(sorted(dist.items()))}")
    if skipped:
        print(f"\n[warn] {len(skipped)} 条断言因缺登记规则被跳过")


def _authority_of(r):
    for a in r.get("assertions", []):
        if a.get("field") == "authority" and a.get("value"):
            return a["value"]
    return ""


def _doc_type_of(r):
    rt = r.get("recordType")
    return {
        "legislation": "regulation",
        "case": "enforcement_decision",
        "standard": "standard",
        "guidance": "guidance",
        "policy": "policy",
    }.get(rt, "other")


def _host_of(r):
    url = r.get("sourceUrl", "") or ""
    if "//" not in url:
        return ""
    return url.split("//", 1)[1].split("/", 1)[0].lower()


# 官方域名 → (检索渠道, 检索式说明, 语言, 定位方案)
# 单一真源：新增采集源时在此登记，判定逻辑不散落在各函数里
SOURCE_PROFILES = {
    "federalregister.gov": (
        "api",
        "https://www.federalregister.gov/api/v1/documents.json "
        "?conditions[agencies][]=federal-aviation-administration",
        "en", "fr-citation",
    ),
    "ecfr.gov": (
        "api",
        "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-14.xml?part=N",
        "en", "cfr-section",
    ),
    "caac.gov.cn": (
        "api",
        "https://www.caac.gov.cn/was5/web/search?channelid=269689&searchword=&perpage=20",
        "zh", "ccar-number",
    ),
    "lexcom.12348.gov.cn": (
        "api",
        "https://lexcom.12348.gov.cn/api/law/chinese/page?current=1&size=100",
        "zh", "platform-record-id",
    ),
    "publications.europa.eu": (
        "cellar",
        "http://publications.europa.eu/resource/celex/{CELEX}.ENG "
        "(Accept: application/xml;notice=object)",
        "en", "celex-id",
    ),
    "store.icao.int": (
        "user-provided",
        "用户自 ICAO 官网下载后导入（程序无法访问 icao.int）",
        "en", "icao-number",
    ),
    "eur-lex.europa.eu": (
        "cellar",
        "http://publications.europa.eu/resource/celex/{CELEX}.ENG",
        "en", "celex-id",
    ),
}


def _profile_of(r):
    """按来源域名取检索档案；未登记的域名返回 None（视为人工录入）。"""
    host = _host_of(r)
    for dom, prof in SOURCE_PROFILES.items():
        if host == dom or host.endswith("." + dom):
            return prof
    return None


def _channel_of(r):
    prof = _profile_of(r)
    return prof[0] if prof else "manual"


def _query_of(r):
    prof = _profile_of(r)
    if prof:
        return prof[1]
    return "CMS GDPR Enforcement Tracker / 各 DPA 官网 / CourtListener"


def _lang_of(r):
    prof = _profile_of(r)
    return prof[2] if prof else "zh"


def _verification_status(r):
    """核验状态。

    官方接口程序化抓取：元数据由官方系统直接给出，视为 verified
    人工录入：数据源自用户早前仓库，决定日与金额口径均待核验，视为 pending
    """
    prof = _profile_of(r)
    if prof:
        return "verified"
    return (r.get("recordLevel") or {}).get("verificationStatus", "pending")


def _locator_scheme(r):
    """定位方案：声明本库的 locator 用什么制度定位原文。"""
    prof = _profile_of(r)
    if prof:
        return prof[3]
    if r.get("recordType") == "case":
        return "decision-number+date"
    return None


if __name__ == "__main__":
    main()
