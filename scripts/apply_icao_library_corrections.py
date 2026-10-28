#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_icao_library_corrections.py — 用图书馆 2024-04-09 ICAO 包核出的结果更正站内记录

核验前提（重要，避免误判）：
    库内 ICAO 附件的版次**普遍比站内旧**（站内版次取自 2026-10-22 ICAO Store 实抓）。
    因此这批文件**不能用来升级版次**；它的用途是三种：
      ① 独立第二来源的**复核**（站内说第 N 版，第二来源能对上 → 提升可信度）；
      ② 官方中文译本封面给出的**中文标准名**（L1，优于原有的公众号相册 L3）；
      ③ 版权页给出的**英文/中文版各自 ISBN**（同一附件不同语言版本 ISBN 不同，
         站内原来只记一个，无法说明是哪一语言的版本）。

本脚本只做「有实证的更正」，不做「看起来更合理」的改写。
每条更正都写清楚：改了哪个字段、依据哪个文件的哪一页、原文怎么写。

用法：python scripts/apply_icao_library_corrections.py [--dry-run]
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REC = ROOT / "data" / "records" / "icao_documents.json"
EXTRACT = ROOT / "data" / "verify" / "icao_library_extract.json"
OUT = ROOT / "data" / "icao_library_verification.json"

SRC = "ICAO-LIB-2024"
TODAY = date.today().isoformat()

# ── 逐条更正 ──────────────────────────────────────────────
# 只列「库内原件与站内断言不一致、且站内确属有误」的项。
# 站内比库内新的（如 Annex 1 14版 vs 库内 13版）不是错误，不在此列。
CORRECTIONS = [
    {
        "recordId": "AVA-ICAO-STD-ANNEX-17",
        "field": "titleZh",
        "old": "保安：保护国际民用航空免遭非法干扰行为",
        "new": "安保 — 保护国际民用航空免遭非法干扰行为",
        "basis": "附件17 第十一版（2020年3月）中文版封面 p.3：「附件17 — 安保 保护国际民用航空免遭非法干扰行为」；"
                 "版权页 p.4：「附件17 —《安保 — 保护国际民用航空免遭非法干扰行为》」",
        "note": "第十版（2017年4月）中文封面仍作「保安」，第十一版起改为「安保」。"
                "站内原值「保安」来自微信公众号相册（L3 二手），本次以官方中文译本（L1）更正。",
        "evidenceLevel": "L1",
        "locator": "中文版 11th ed PDF p.3 封面、p.4 版权页",
    },
    {
        "recordId": "AVA-ICAO-STD-ANNEX-18",
        "field": "titleZh",
        "old": "危险品的安全航空运输",
        "new": "危险物品的安全航空运输",
        "basis": "附件18 第四版（2011年7月）中文版封面 p.3 载「危险物品的安全航空运输」",
        "note": "站内原值省作「危险品」，官方中文译本用全称「危险物品」。",
        "evidenceLevel": "L1",
        "locator": "中文版 4th ed PDF p.3 封面",
    },
    {
        "recordId": "AVA-ICAO-STD-ANNEX-19",
        "field": "isbn",
        "old": "978-92-9275-818-9",
        "new": None,          # 见下方 isbnByLanguage，此字段改由分语言结构承载
        "basis": "英文版第二版版权页 p.4：ISBN 978-92-9249-965-5；中文版第二版版权页 p.4：ISBN 978-92-9249-983-9",
        "note": "站内原记 978-92-9275-818-9，与第二版英文/中文版权页均不符（疑为第 3 版 ISBN）。"
                "同一附件不同语言版本的 ISBN 不同，单值字段无法表达，改为按语言分列。",
        "evidenceLevel": "L1",
        "locator": "英文版 2nd ed p.4 版权页；中文版 2nd ed p.4 版权页",
        "isbnByLanguage": {"en": "978-92-9249-965-5", "zh": "978-92-9249-983-9"},
    },
]

# ── 第二来源复核（库内版次与站内一致 → 记一次独立确认，不改数据）────
CONFIRMED = [
    ("AVA-ICAO-STD-ANNEX-4", "11th Edition, 2009", "附件4 第十一版 2009年7月 / AN 04 Eleventh Edition, July 2009"),
    ("AVA-ICAO-STD-ANNEX-5", "5th Edition, 2010", "附件5 第五版 2010年7月 / AN 05 Fifth Edition, July 2010"),
    ("AVA-ICAO-STD-ANNEX-7", "6th Edition, 2012", "附件7 第六版 2012年7月 / AN 07 Sixth Edition, July 2012"),
    ("AVA-ICAO-STD-ANNEX-11", "15th Edition, 2018", "附件11 第十五版 2018年7月 / AN 11 Fifteenth Edition, July 2018"),
    ("AVA-ICAO-STD-ANNEX-15", "16th Edition, 2018", "附件15 第十六版 2018年7月 / AN 15 Sixteenth Edition, July 2018"),
    ("AVA-ICAO-STD-ANNEX-18", "4th Edition, 2011", "附件18 第四版 2011年7月 / AN 18 Fourth Edition, July 2011"),
    ("AVA-ICAO-STD-ANNEX-19", "2nd Ed, 2016-07", "附件19 第二版 2016年7月 / AN 19 Second Edition, July 2016，封面载「自2019-11-07起取代所有以前版本」"),
]

# ── 库内版本落后于站内（不是错误，记录以免日后误当"新版本"）────
BEHIND = [
    ("Ann 1", "14th Edition, 2022", "库内最新为 13th 2020-07"),
    ("Ann 2", "11th Edition, 2024", "库内为 10th 2005-07 + 第1–9号修订（.rar）"),
    ("Ann 3", "21st Edition, 2025", "库内为 20th 2018-07"),
    ("Ann 6", "Part I 12th 2022-07", "库内 Part I 11th 2018-07"),
    ("Ann 8", "13th Edition, 2022", "库内 12th 2018-07"),
    ("Ann 9", "17th Edition, 2025", "库内 15th 2017-10"),
    ("Ann 10", "Vol I 8th 2023-07", "库内 Vol I 7th 2018-07；库内无 Vol VI"),
    ("Ann 12", "9th Edition, 2024", "库内 8th 2004-07（含第1–17号修订，第18号修订 2007-11-22）"),
    ("Ann 13", "13th Edition, 2024", "库内 12th 2020-07"),
    ("Ann 14", "Vol I 9th 2022-07 / Vol II 5th 2020-07", "库内 Vol I 8th 2018-07 / Vol II 5th 2020-07（Vol II 一致）"),
    ("Ann 16", "Vol I 8th 2017-07 (Amd 15) / Vol IV 2nd 2023-07", "库内 Vol I 8th 2017-07 / Vol IV 1st 2018-10"),
    ("Ann 17", "12th Edition, 2022", "库内 11th 2020-03"),
]


def main():
    dry = "--dry-run" in sys.argv
    data = json.loads(REC.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    by_id = {r["recordId"]: r for r in recs}

    applied, missing = [], []
    for c in CORRECTIONS:
        rec = by_id.get(c["recordId"])
        if not rec:
            missing.append(c["recordId"])
            continue
        rl = rec.setdefault("recordLevel", {})
        cur = rl.get(c["field"]) if c["field"] in rl else rec.get(c["field"])
        # 只在现值等于「旧值」时才改——避免覆盖此后别人做过的更正
        if str(cur or "") != str(c["old"] or ""):
            missing.append(f'{c["recordId"]}.{c["field"]}（现值「{cur}」≠ 记录中的旧值「{c["old"]}」）')
            continue
        if c["field"] == "isbn":
            # ISBN 改成分语言结构；原单值字段删除，避免两处说法并存
            rl.pop("isbn", None)
            rec.pop("isbn", None)
            rl["isbnByLanguage"] = c["isbnByLanguage"]
        else:
            rl[c["field"]] = c["new"]
            if c["field"] == "titleZh":
                rec["titleZh"] = c["new"]
        # 追加一条可审计的更正记录
        rl.setdefault("corrections", []).append({
            "correctedAt": TODAY,
            "field": c["field"],
            "from": c["old"],
            "to": c["new"] if c["field"] != "isbn" else c["isbnByLanguage"],
            "basis": c["basis"],
            "locator": c["locator"],
            "evidenceLevel": c["evidenceLevel"],
            "sourceId": SRC,
            "note": c["note"],
        })
        # 同步摘要里的中文名，否则会出现「中文名：安保」与「摘要：保安」自相矛盾
        if c["field"] == "titleZh":
            old_zh = c["old"].split("：")[0].split(":")[0].strip()
            new_zh = c["new"].split("—")[0].split("：")[0].strip()
            s = rec.get("summary") or ""
            if old_zh and old_zh in s:
                rec["summary"] = s.replace(old_zh, new_zh, 1)
            for a in rec.get("assertions") or []:
                if a.get("field") == "title_zh":
                    a["value"] = c["new"]
                    a["sourceId"] = SRC
                    a["locator"] = c["locator"]
                    a["evidenceLevel"] = "L1"
                    a["verifiedAt"] = TODAY
        applied.append(f'{c["recordId"]}.{c["field"]}')

    # 摘要与中文名对齐：独立成一遍，与「字段是否本次才改」解耦。
    # 否则首次只改了 titleZh、忘了摘要，二次运行又因现值≠旧值被跳过，
    # 站上就长期留下「中文名：安保」＋「摘要：保安」这种自相矛盾。
    synced = 0
    for c in CORRECTIONS:
        if c["field"] != "titleZh":
            continue
        rec = by_id.get(c["recordId"])
        if not rec:
            continue
        old_zh = c["old"].split("：")[0].split(":")[0].strip()
        new_zh = c["new"].split("—")[0].split("：")[0].strip()
        s = rec.get("summary") or ""
        if old_zh and old_zh in s:
            rec["summary"] = s.replace(old_zh, new_zh, 1)
            synced += 1
    if synced:
        print(f"  摘要中文名同步 {synced} 条")

    if not dry:
        from jsonio import save_json
        save_json(REC, data)
        report = {
            "verifiedAt": TODAY,
            "sourceId": SRC,
            "source": "中国民航大学图书馆 2024-04-09 转来的 ICAO 附件包（中文版 30 份 / 英文版 34 份）",
            "method": "逐份读 p.3 封面、p.4 版权页、p.5 修订记录页；不按文件名判版次",
            "conclusion": "库内版次普遍早于站内（站内取自 2026-10-22 ICAO Store 实抓），"
                          "因此本包不用于升级版次；用于三处更正与七处独立复核。",
            "corrections": CORRECTIONS,
            "secondSourceConfirmed": [
                {"recordId": r, "siteValue": s, "libraryValue": v, "locator": "该版 PDF p.3 封面 / p.4 版权页"}
                for r, s, v in CONFIRMED
            ],
            "libraryOlderThanSite": [
                {"annex": a, "siteValue": s, "libraryValue": v} for a, s, v in BEHIND
            ],
            "notIngested": "SARPs 与 PANS 受版权保护，中文/英文正文均只作本地核对之用，"
                           "不入库、不入仓、不随站点或仓库分发。",
        }
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
        print(f"已写入 {REC.relative_to(ROOT)} 与 {OUT.relative_to(ROOT)}")

    print(f"应用更正 {len(applied)} 项：")
    for x in applied:
        print("  ✓", x)
    if missing:
        print(f"跳过 {len(missing)} 项（现值不符或记录不存在）：")
        for x in missing:
            print("  ·", x)


if __name__ == "__main__":
    main()
