#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 19 条 Annex 记录的 edition 字段从「2005-06 booklet」改为官方现行版次。

原字段记录的是用户所给 annexes_booklet.pdf 的印制年份，不是 Annex 本身的版次，
站上显示会造成「Annex 1 = 2005-06 版」的错误。基准：ICAO Store 2026-10-22 实抓。
booklet 信息保留到 bookletEdition，不丢来源。
"""
import json

P = "data/records/icao_documents.json"
CHECKED = "2026-10-22"
SRC = "https://store.icao.int/en/annexes（2026-10-22 实抓）"

# 号: (edition, editionDate, latestAmendment, note)
ED = {
    "Annex 1":  ("14th Edition, 2022", "2022-07", None, None),
    "Annex 2":  ("11th Edition, 2024", "2024-07", None, None),
    "Annex 3":  ("20th Edition, 2018", "2018-07", "Amd 80 (2021-11-04)", "Store 列表未单列，版次依 2018-07 第 20 版；修订号以官方核对为准"),
    "Annex 4":  ("11th Edition, 2009", "2009-07", "Amd 61 (2021-11-04)", None),
    "Annex 5":  ("5th Edition, 2010", "2010-07", None, None),
    "Annex 6":  ("Part I: 12th Ed, 2022-07 ｜ Part II: 12th Ed, 2026-08 ｜ Part III: 12th Ed, 2026-08",
                 "2026-08", None, "三部分版次不同步，Part II/III 于 2026-08 换版"),
    "Annex 7":  ("6th Edition, 2012", "2012-07", None, None),
    "Annex 8":  ("13th Edition, 2022", "2022-07", None, None),
    "Annex 9":  ("17th Edition, 2025", "2025-03", None, None),
    "Annex 10": ("Vol I: 8th Ed, 2023-07 ｜ Vol II: 7th Ed, 2016-07 (Amd 95, 2026-08) ｜ Vol III: 2nd Ed, 2007 (Amd 94, 2026-08) ｜ Vol IV: 6th Ed, 2026-08 ｜ Vol V: 3rd Ed, 2013-07 ｜ Vol VI: 1st Ed, 2021-07",
                 "2026-08", "Vol II Amd 95 / Vol III Amd 94（2026-08-03）",
                 "** Vol VI（RPAS C2 链路）1st Ed 2021-07 是两个渠道都缺的一卷 **"),
    "Annex 11": ("15th Edition, 2018", "2018-07", "Amd 55 (2026-08-03)", None),
    "Annex 12": ("9th Edition, 2024", "2024-07", None, None),
    "Annex 13": ("13th Edition, 2024", "2024-07", "Amd 20 (2026-08-03)", None),
    "Annex 14": ("Vol I: 9th Ed, 2022-07 ｜ Vol II: 5th Ed, 2020-07", "2022-07", None, None),
    "Annex 15": ("16th Edition, 2018", "2018-07", "Amd 45 (2026-08-03)", None),
    "Annex 16": ("Vol I: 8th Ed, 2017-07 (Amd 15) ｜ Vol II: 5th Ed, 2023-07 (Amd 12) ｜ Vol III: 2nd Ed, 2026-08 ｜ Vol IV: 2nd Ed, 2023-07 (Amd 2)",
                 "2026-08", "Vol I Amd 15 / Vol II Amd 12 / Vol IV Amd 2（2026-08-03）", None),
    "Annex 17": ("12th Edition, 2022", "2022-07", None, None),
    "Annex 18": ("4th Edition, 2011", "2011-07", None, None),
    "Annex 19": ("3rd Edition, 2025", "2025-11", None, "2025-11 换版（原 2nd Ed 2016-07）"),
}


def main():
    data = json.load(open(P, encoding="utf-8"))
    n = 0
    for r in data:
        rl = r.setdefault("recordLevel", {})
        k = rl.get("icaoNumber")
        if k not in ED:
            print("!! 未覆盖", k)
            continue
        ed, dt, amd, note = ED[k]
        # 保留 booklet 原始信息，改名不丢来源
        if rl.get("edition") and "booklet" in str(rl.get("edition")):
            rl["bookletEdition"] = rl["edition"]
        rl["edition"] = ed
        rl["editionDate"] = dt
        rl["latestAmendment"] = amd
        rl["editionCheckedAt"] = CHECKED
        rl["editionSource"] = SRC
        if note:
            rl["editionNote"] = note
        # 日期字段：补 publicationDate（版次年），不伪造具体日
        d = r.setdefault("dates", {})
        if not d.get("publicationDate") and dt:
            d["publicationDate"] = dt if len(dt) > 4 else dt
            d["publicationDatePrecision"] = "month"
            d["publicationDateBasis"] = "edition"
        # 注意：citationString 必须保持「Annex N」的规范写法——检索层靠它解析规范键，
        # 改成「ICAO Annex N, 14th Edition, 2022」会让 icao:annex:N 通道失配（实测命中 0）。
        rl["citationStringFull"] = f"ICAO {k}, {ed.split(' ｜ ')[0]}"
        n += 1
    out = json.dumps(data, ensure_ascii=False, indent=2)
    with open(P, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(out)
    print(f"更新 {n} 条")


if __name__ == "__main__":
    main()
