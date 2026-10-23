#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_icao_docs.py — 把用户提供的 ICAO Doc（PANS 与手册）导入 icao_documents.json

收录纪律（与 Annex 记录一致）：
  1. 只写可从版权页 / 修订记录页逐字核对的事实，不转述正文；
  2. **正文与 PDF 一律不入库**（SARPs 与 PANS 受版权保护，不得印刷分发）；
  3. 版次与修订分开记：版次是出版，修订才是效力；未生效的修订必须单独标出；
  4. 已被取代的版次照收，但 status 写 superseded 并留 revisionLog —— 库里留着
     旧版是为了让读者知道自己手上那本处在什么位置，不是当作现行文本。

本批四份（2026-10-23 逐份读版权页核实）：
  Doc 8400  9th Ed 2016，含 Amd 33/34，缺 Amd 35
  Doc 8126  7th Ed 2022，含 Amd 1（2024-07-30）
  Doc 9760  4th Ed 2020 —— 已由 5th Ed 2025 取代
  Doc 8168-3 1st Ed 2018，含 Amd 1/2/3；Amd 4 待 2026-11-26 适用

附带修正：18 条 Annex 记录的 status 原为 "in_force"，不在 record_id.STATUSES 词表内，
前端 statusLabel() 无从映射，筛选项里会直接露出英文原值。统一改为 "effective"。

用法：python scripts/import_icao_docs.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "records" / "icao_documents.json"

TODAY = "2026-10-23"

STORE = "https://store.icao.int/en/"


def A(field, value, source_id, locator, level="L1", previous=None):
    a = {
        "field": field,
        "value": value,
        "sourceId": source_id,
        "locator": locator,
        "evidenceLevel": level,
        "verifiedAt": TODAY,
    }
    if previous is not None:
        a["previousValue"] = previous
    return a


def build_docs():
    """四份文档的记录定义。值全部取自 2026-10-23 实读的 PDF 页面。"""
    docs = []

    # ── Doc 8400 ────────────────────────────────────────────────────
    sid = "ICAO-DOC-8400"
    loc_cover = "Doc 8400 PDF 第 1 页封面"
    loc_copy = "Doc 8400 PDF 第 4 页版权页"
    loc_amd = "Doc 8400 PDF 第 5 页 Record of Amendments"
    docs.append({
        "recordId": "AVA-ICAO-STD-DOC-8400",
        "title": "ICAO Abbreviations and Codes (PANS-ABC)",
        "titleZh": "国际民航组织缩略语和代码",
        "summary": (
            "ICAO《航空导航服务程序——缩略语和代码》（PANS-ABC）第 9 版（2016，88 页），"
            "2016-11-10 起取代旧版；本件含 Amendment 33（2018-11-08）与 34（2024-11-28），"
            "未含 2025-11-27 适用的 Amendment 35。本站只存元数据与官方链接，不收录正文。"
        ),
        "topics": ["definitions", "air-traffic", "flight-ops"],
        "status": "effective",
        "publicationDate": "2016",
        "publicationPrecision": "year",
        "effectiveDate": "2016-11-10",
        "citationString": "Doc 8400",
        "canonicalKey": "icao:doc:8400",
        "sourceUrl": STORE + "procedures-for-air-navigation-services-pans-icao-abbreviations-and-codes-doc-8400",
        "icaoKind": "文件（PANS）",
        "edition": "Ninth Edition, 2016",
        "editionDate": "2016",
        "latestAmendment": "34（2024-11-28）",
        "amendmentDate": "2024-11-28",
        "adoptedDate": None,
        "citationFull": "ICAO Doc 8400, Procedures for Air Navigation Services — ICAO Abbreviations and Codes (PANS-ABC), Ninth Edition, 2016",
        "note": (
            "PDF 共 88 页，与 ICAO 产品目录所载页数一致。"
            "缩略语表是航空情报与电报文本的编码基础，与 Annex 10 第 II 卷 3.7、"
            "Annex 15 1.3.4 及 5.2.6（NOTAM 代码）互为引用关系。"
            "修订记录页只到「34 28/11/24」，因此本件落后现行修订一个号。"
        ),
        "assertions": [
            A("icao_number", "Doc 8400", sid, loc_cover),
            A("title", "ICAO Abbreviations and Codes (PANS-ABC)", sid, loc_cover),
            A("title_zh", "国际民航组织缩略语和代码", sid, loc_cover),
            A("edition", "Ninth Edition, 2016", sid, loc_cover),
            A("supersedes_date", "2016-11-10", sid,
              loc_cover + "；原文「This edition supersedes, on 10 November 2016」"),
            A("order_number", "8400", sid, loc_copy),
            A("isbn", "978-92-9258-089-6（印刷版）/ 978-92-9275-355-9（电子版）", sid, loc_copy),
            A("pages", "88", sid, loc_copy + "；与 ICAO 产品目录所载 88 pp 一致"),
            A("amendment_included",
              "Amd 1–32 已并入本版；另含 Amd 33（2018-11-08）、Amd 34（2024-11-28）",
              sid, loc_amd + "：1-32 Incorporated in this Edition；33 8/11/18；34 28/11/24"),
            A("amendment_missing", "Amd 35（2025-11-27 适用）未含", "ICAO-CAT-8400",
              "ICAO 产品与服务目录 2025 年第 9 号增补：Doc 8400 Amendment 35 (27/11/25)"),
            A("amendment_pending", "Amd 36 预定 2026-11-26 适用", "ICAO-RESELLER-8400",
              "Accuris 与 AFE 标准经销商目录均列为 Amendment 36 – 26/11/26；"
              "非 ICAO 官方发布，待官方目录确认", level="L3"),
            A("language", "en（另有 A/C/F/R/S 五种正式文本）", sid, loc_copy),
        ],
    })

    # ── Doc 8126 ────────────────────────────────────────────────────
    sid = "ICAO-DOC-8126"
    loc_cover = "Doc 8126 PDF 第 1 页封面"
    loc_copy = "Doc 8126 PDF 第 4 页版权页"
    loc_amd = "Doc 8126 PDF 第 5 页 Record of Amendments"
    docs.append({
        "recordId": "AVA-ICAO-STD-DOC-8126",
        "title": "Aeronautical Information Services Manual",
        "titleZh": "航空情报服务手册",
        "summary": (
            "ICAO《航空情报服务手册》第 7 版（2022，716 页），含 Amendment 1（2024-07-30）。"
            "Annex 15 与 PANS-AIM（Doc 10066）的操作层实施细则，"
            "说明从「产品式 AIS」转向「数据式 AIM」的具体做法。本站只存元数据与官方链接。"
        ),
        "topics": ["air-traffic", "flight-ops", "definitions"],
        "status": "effective",
        "publicationDate": "2022",
        "publicationPrecision": "year",
        "effectiveDate": None,
        "citationString": "Doc 8126",
        "canonicalKey": "icao:doc:8126",
        "sourceUrl": STORE + "aeronautical-information-services-manual-doc-8126",
        "icaoKind": "手册",
        "edition": "Seventh Edition, 2022",
        "editionDate": "2022",
        "latestAmendment": "1（2024-07-30）",
        "amendmentDate": "2024-07-30",
        "adoptedDate": None,
        "citationFull": "ICAO Doc 8126, Aeronautical Information Services Manual, Seventh Edition, 2022",
        "note": (
            "PDF 共 716 页。本件修订记录页只有一条 Amd 1（30/07/24），"
            "未载后续修订；ICAO 官方目录本次未能访问（Cloudflare 拦截），"
            "故「是否为最新修订」未获独立确认，引用前请自行核 Store 页。"
            "手册本身不具 SARPs 效力，条文要求仍以 Annex 15 为准。"
        ),
        "assertions": [
            A("icao_number", "Doc 8126", sid, loc_cover),
            A("title", "Aeronautical Information Services Manual", sid, loc_cover),
            A("title_zh", "航空情报服务手册", sid, loc_cover),
            A("edition", "Seventh Edition, 2022", sid, loc_cover),
            A("order_number", "8126", sid, loc_copy),
            A("isbn", "978-92-9265-643-0（印刷版）/ 978-92-9275-531-7（电子版）", sid, loc_copy),
            A("pages", "716", sid, "PDF 页数（文件实读）"),
            A("amendment_included", "Amendment 1（2024-07-30）已并入", sid,
              loc_amd + "：No. 1，Date 30/07/24"),
            A("language", "en（另有 A/C/F/R/S 五种正式文本）", sid, loc_copy),
        ],
    })

    # ── Doc 9760 ────────────────────────────────────────────────────
    sid = "ICAO-DOC-9760"
    loc_cover = "Doc 9760 PDF 第 1 页封面"
    loc_copy = "Doc 9760 PDF 第 4 页版权页"
    docs.append({
        "recordId": "AVA-ICAO-STD-DOC-9760",
        "title": "Airworthiness Manual",
        "titleZh": "适航手册",
        "summary": (
            "ICAO《适航手册》第四版（2020，420 页），已被第五版（2025，448 页）取代，"
            "本条按历史版本保存。手册为 Annex 8 的实施指导材料，"
            "供各国建立适航检查机构与持续适航体系参考。本站只存元数据与官方链接。"
        ),
        "topics": ["airworthiness", "certification"],
        "status": "superseded",
        "publicationDate": "2020",
        "publicationPrecision": "year",
        "effectiveDate": None,
        "citationString": "Doc 9760",
        "canonicalKey": "icao:doc:9760",
        "sourceUrl": STORE + "airworthiness-manual-doc-9760",
        "icaoKind": "手册",
        "edition": "Fourth Edition, 2020（已被 Fifth Edition, 2025 取代）",
        "editionDate": "2020",
        "latestAmendment": None,
        "amendmentDate": None,
        "adoptedDate": None,
        "citationFull": "ICAO Doc 9760, Airworthiness Manual, Fourth Edition, 2020",
        "note": (
            "PDF 共 420 页，修订记录页为空（第 4 版未附修订）。"
            "第五版 2025 已出版（448 页，ISBN 978-92-9275-840-0，Order No. 9760），"
            "本条不得作为现行文本引用；涉及 eVTOL 适航审定的论述应改用第五版或直接引 Annex 8。"
        ),
        "revisionLog": [{
            "oldStatus": "effective",
            "newStatus": "superseded",
            "date": "2025",
            "reason": "ICAO 出版第五版（5th Edition, 2025，448 页），第四版随之被取代",
            "reasonSource": "ICAO Store 产品页（Airworthiness Manual, 5th Edition, 2025）；"
                            "2025 年产品与服务目录第 10 号增补",
            "sourceId": "ICAO-STORE-9760",
            "note": "ICAO 未在公开页面给出取代的确切适用日，此处只记到年，不臆造具体日期",
        }],
        "assertions": [
            A("icao_number", "Doc 9760", sid, loc_cover),
            A("title", "Airworthiness Manual", sid, loc_cover),
            A("title_zh", "适航手册", sid, loc_cover),
            A("edition", "Fourth Edition, 2020", sid, loc_cover),
            A("order_number", "9760", sid, loc_copy),
            A("isbn", "978-92-9265-135-0", sid, loc_copy),
            A("pages", "420", sid, "PDF 页数（文件实读）"),
            A("edition_history", "第一版 2001；第三版 2014；第四版 2020", sid,
              loc_copy + "；原文「First edition, 2001 / Third edition, 2014 / Fourth edition, 2020」"),
            A("superseded_by", "Fifth Edition, 2025（448 页，ISBN 978-92-9275-840-0）",
              "ICAO-STORE-9760",
              "ICAO Store 产品页：Edition 5th Edition, 2025；SKU DOC-09760-005-01"),
            A("language", "en（另有 A/C/F/R/S 五种正式文本）", sid, loc_copy),
        ],
    })

    # ── Doc 8168 第 III 卷 ──────────────────────────────────────────
    sid = "ICAO-DOC-8168-3"
    loc_cover = "Doc 8168 第 III 卷 PDF 第 1 页封面"
    loc_copy = "Doc 8168 第 III 卷 PDF 第 4 页版权页"
    loc_amd = "Doc 8168 第 III 卷 PDF 第 5 页 Record of Amendments"
    docs.append({
        "recordId": "AVA-ICAO-STD-DOC-8168-3",
        "title": "Aircraft Operating Procedures (PANS-OPS, Volume III)",
        "titleZh": "航空器运行程序（第 III 卷）",
        "summary": (
            "ICAO《航空导航服务程序——航空器运行》第 III 卷《航空器运行程序》第一版（2018），"
            "2018-08-28 经理事会主席批准、2018-11-08 起适用；含 Amendment 1（2021-11-04）、"
            "2（2022-11-03）、3（2024-11-28），Amendment 4 待 2026-11-26 适用。"
            "本站只存元数据与官方链接，不收录正文。"
        ),
        "topics": ["flight-ops", "air-traffic"],
        "status": "effective",
        "publicationDate": "2018",
        "publicationPrecision": "year",
        "effectiveDate": "2018-11-08",
        "citationString": "Doc 8168-3",
        "canonicalKey": "icao:doc:8168-3",
        "sourceUrl": STORE + "procedures-for-air-navigation-services-pans-aircraft-operations-volume-iii-aircraft-operating-procedures-doc-8168",
        "icaoKind": "文件（PANS）",
        "edition": "First Edition, 2018",
        "editionDate": "2018",
        "latestAmendment": "3（2024-11-28）",
        "amendmentDate": "2024-11-28",
        "adoptedDate": "2018-08-28",
        "citationFull": "ICAO Doc 8168, Procedures for Air Navigation Services — Aircraft Operations, Volume III — Aircraft Operating Procedures, First Edition, 2018",
        "note": (
            "第一卷《飞行程序》、第二卷《目视和仪表飞行程序设计》、第三卷《航空器运行程序》"
            "分属三卷，引注须写明卷次。第三卷内容原属第一卷，2018 年独立成卷，"
            "故 2018 年之前的文献不会出现「Vol III」这一引法。"
            "PDF 共 138 页，官方目录所载为 122 pp（印刷页与 PDF 页口径不同）。"
        ),
        "assertions": [
            A("icao_number", "Doc 8168-3", sid, loc_cover),
            A("title", "Aircraft Operating Procedures (PANS-OPS Volume III)", sid, loc_cover),
            A("title_zh", "航空器运行程序（第 III 卷）", sid, loc_cover),
            A("edition", "First Edition, 2018", sid, loc_cover),
            A("approved_date", "2018-08-28", sid,
              loc_cover + "；原文「approved by the President of the Council ... on 28 August 2018」"),
            A("applicable_date", "2018-11-08", sid,
              loc_cover + "；原文「becomes applicable on 8 November 2018」"),
            A("order_number", "8168-3", sid, loc_copy),
            A("isbn", "978-92-9258-601-0（印刷版）/ 978-92-9275-452-5（电子版）", sid, loc_copy),
            A("amendment_included",
              "Amd 1（2021-11-04）、Amd 2（2022-11-03）、Amd 3（2024-11-28）",
              sid, loc_amd + "：1 4/11/21；2 3/11/22；3 28/11/24"),
            A("amendment_pending", "Amd 4 预定 2026-11-26 适用", "ICAO-RESELLER-8168-3",
              "Accuris 标准经销商目录：ICAO 8168 VOL III AMD 4，Published 11/26/2026；"
              "非 ICAO 官方发布，待官方目录确认", level="L3"),
            A("language", "en（另有 A/C/F/R/S 五种正式文本）", sid, loc_copy),
        ],
    })

    return docs


def to_record(d):
    """按 icao_documents.json 既有 schema 组装一条记录。

    摘要与注释走前端的 esc()，不解析 Markdown——写进去的 ** 会原样显示成星号，
    因此在这里统一剥掉强调标记（正文本身没有这种语法）。
    """
    def plain(s):
        return s.replace("**", "") if isinstance(s, str) else s

    return {
        "recordId": d["recordId"],
        "recordType": "standard",
        "title": d["title"],
        "titleEn": d["title"],
        "summary": plain(d["summary"]),
        "jurisdiction": "ICAO",
        "topics": d["topics"],
        "status": d["status"],
        "dates": {
            "publicationDate": d["publicationDate"],
            "effectiveDate": d["effectiveDate"],
            "retrievedAt": TODAY,
            "publicationDatePrecision": d["publicationPrecision"],
            "publicationDateBasis": "edition",
        },
        "citationString": d["citationString"],
        "sourceUrl": d["sourceUrl"],
        "recordLevel": {
            "icaoNumber": d["citationString"],
            "icaoKind": d["icaoKind"],
            "canonicalKey": d["canonicalKey"],
            "titleZh": d["titleZh"],
            "subVolumes": None,
            "edition": d["edition"],
            "editionDate": d["editionDate"],
            "adoptedDate": d["adoptedDate"],
            "amendmentDate": d["amendmentDate"],
            "latestAmendment": d["latestAmendment"],
            "language": "en",
            "publisher": "International Civil Aviation Organization",
            "isFreeAccess": False,
            "acquiredFrom": plain("用户提供的官方 PDF（本机保存，不入库）"),
            "acquiredDate": TODAY,
            "hasLocalPdf": False,
            "sourceTier": "L1",
            "verificationStatus": "verified",
            "retrievalChannel": "用户提供 PDF，程序读取封面、版权页、修订记录页",
            "editionCheckedAt": TODAY,
            "editionSource": d["sourceUrl"] + "（2026-10-23 实访 200）",
            "citationStringFull": d["citationFull"],
            "note": plain(d["note"]),
            "linkNote": ("链接指向 ICAO Store 产品页（境外付费商店，部分网络环境可能无法直连）；"
                         "本站不收录正文，需阅读请购买、到官方 eLibrary 查阅或使用本机授权副本。"),
        },
        "revisionLog": d.get("revisionLog", []),
        "assertions": d["assertions"],
    }


def main():
    if not TARGET.exists():
        print(f"[FATAL] 找不到 {TARGET}", file=sys.stderr)
        return 2
    records = json.loads(TARGET.read_text(encoding="utf-8"))
    by_id = {r["recordId"]: i for i, r in enumerate(records)}

    new_docs = build_docs()
    added = updated = 0
    for d in new_docs:
        rec = to_record(d)
        if rec["recordId"] in by_id:
            records[by_id[rec["recordId"]]] = rec
            updated += 1
        else:
            records.append(rec)
            added += 1

    # 状态词表对齐：in_force 不在 record_id.STATUSES 内，前端无从映射
    fixed = []
    for r in records:
        if r.get("status") == "in_force":
            r["status"] = "effective"
            fixed.append(r["recordId"])

    records.sort(key=lambda r: r["recordId"])
    TARGET.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"新增 {added} 条、覆盖 {updated} 条；现有 {len(records)} 条")
    print(f"状态归一 in_force → effective：{len(fixed)} 条")
    for r in fixed[:3]:
        print(f"  例：{r}")


if __name__ == "__main__":
    sys.exit(main())
