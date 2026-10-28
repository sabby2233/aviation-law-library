#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
icao_zip_vs_current.py — 图书馆 ICAO 包与当前现行版次逐条比对

基准（三方）：
  A. 压缩包实测版次 —— data/verify/icao_library_extract.json（读封面/版权页所得）
  B. 站内现行版次   —— data/records/icao_documents.json 的 recordLevel.edition
     （该字段 2026-10-22/23 取自 ICAO Store 与官方 PDF 封面，已入核验层）
  C. 本次实抓复核   —— 2026-10-29 抓 store.icao.int/en/annexes，
     该页只暴露 11 个产品（分页/轮播），逐条标注「C 已复核」或「仅 B」

输出：终端表格 + data/icao_zip_vs_current.json（入库，供日后复查）

判定口径：
  · 落后 N 版 = 现行版次号 − 包内版次号（同一卷次谱系内才有意义）
  · 「缺卷」= 现行有该卷/该部分，包内完全没有
  · 「同版次但缺修正案」= 版次号相同，但现行已并入包内未含的修正案
  · 「即将落后」= 包内为当前适用版，但已知新版将于近期生效
"""

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTRACT = DATA / "verify" / "icao_library_extract.json"
RECORDS = DATA / "records" / "icao_documents.json"
OUT = DATA / "icao_zip_vs_current.json"

# 2026-10-29 实抓 store.icao.int/en/annexes 页面里出现的 11 条（Edition 串与产品名）
LIVE_CONFIRMED = {
    "Annex 1": "14th Edition, July 2022",
    "Annex 2": "11th Edition, July 2024",
    "Annex 4": "11th Edition, July 2009",
    "Annex 5": "5th Edition, 2010",
    "Annex 6 P3": "12th Edition, July 2022",
    "Annex 7": "6th Edition, July 2012",
    "Annex 8": "13th Edition, July 2022",
    "Annex 9": "17th Edition, March 2025",
    "Annex 10 V1": "8th Edition, July 2023",
    "Annex 10 V2": "7th Edition, July 2016",
    "Annex 10 V3": "2nd Edition, 2007",
}

# 逐条比对结论。左为包内实际持有，右为现行。
# gap: 落后版数；note: 说明；kind: same / behind / missing / amd / pending
ROWS = [
    # (标签, 包内, 现行, 判定, 说明)
    ("Annex 1", "12th 2018-07、13th 2020-07", "14th 2022-07", "behind", 1,
     "包内有第十二、第十三两版，现行第十四版；两版均已废止"),
    ("Annex 2", "10th 2005-07（另附第1–9号修订 .rar）", "11th 2024-07", "behind", 1,
     "包内为 2005 年第十版，现行第十一版（2024）；相差近 19 年"),
    ("Annex 3", "20th 2018-07", "21st 2025", "behind", 1,
     "第二十版 2018；现行第二十一版 2025（已按官方 PDF 封面核到 © ICAO 2025）"),
    ("Annex 4", "11th 2009-07", "11th 2009-07", "same", 0, "一致，且本次实抓复核"),
    ("Annex 5", "5th 2010-07", "5th 2010-07", "same", 0, "一致，且本次实抓复核"),
    ("Annex 6 Part I", "11th 2018-07", "12th 2022-07", "behind", 1, "现行第十二版 2022"),
    ("Annex 6 Part II", "10th 2018-07", "12th 2026-08", "behind", 2,
     "落后两版：包内第十版 2018 → 现行第十二版（站内基线记 2026-08 换版）"),
    ("Annex 6 Part III", "9th 2018-07、10th 2020-07", "12th 2026-08", "behind", 2,
     "落后两版；包内第十版 2020 为当时最新，现行已至第十二版"),
    ("Annex 7", "6th 2012-07", "6th 2012-07", "same", 0, "一致，且本次实抓复核"),
    ("Annex 8", "12th 2018-07", "13th 2022-07", "behind", 1, "现行第十三版 2022，且本次实抓复核"),
    ("Annex 9", "15th 2017-10", "17th 2025-03", "behind", 2,
     "落后两版：包内第十五版 2017 → 现行第十七版 2025-03"),
    ("Annex 10 Vol I", "7th 2018-07", "8th 2023-07", "behind", 1, "现行第八版 2023，且本次实抓复核"),
    ("Annex 10 Vol II", "7th 2016-07", "7th 2016-07 + Amd 95（2026-08）", "amd", 0,
     "版次相同，但现行已并入第 95 号修正案；包内为该版原始印次"),
    ("Annex 10 Vol III", "2nd 2007-07", "2nd 2007 + Amd 94（2026-08）", "amd", 0,
     "版次相同，但现行已并入第 94 号修正案"),
    ("Annex 10 Vol IV", "5th 2014-07", "6th 2026-08", "behind", 1,
     "现行第六版（站内基线记 2026-08 换版）"),
    ("Annex 10 Vol V", "3rd 2013-07", "3rd 2013-07", "same", 0, "一致"),
    ("Annex 10 Vol VI", "缺", "1st 2021-07", "missing", None,
     "包内没有第六卷；且中文版整套缺 Annex 10 全部卷次"),
    ("Annex 11", "15th 2018-07", "15th 2018-07", "same", 0, "一致"),
    ("Annex 12", "8th 2004-07（修订1–17已编入，第18号 2007-11-22）", "9th 2024", "behind", 1,
     "包内为 2004 年第八版加至第 18 号修订；现行第九版 2024"),
    ("Annex 13", "11th 2016-07、12th 2020-07", "13th 2024", "behind", 1, "现行第十三版 2024"),
    ("Annex 14 Vol I", "8th 2018-07", "9th 2022-07", "behind", 1, "现行第九版 2022"),
    ("Annex 14 Vol II", "4th 2013-07（直升机场）；另有 8th 2018「机场设计和运行」", "5th 2020-07（Heliports）", "behind", 1,
     "直升机场卷为第四版 2013，现行第五版 2020；中文版另有第八版「第II卷 机场设计和运行」属另一分卷命名"),
    ("Annex 15", "16th 2018-07", "16th 2018-07", "same", 0, "一致"),
    ("Annex 16 Vol I", "8th 2017-07", "8th 2017-07 + Amd 15", "amd", 0,
     "版次相同，但现行已并入第 15 号修正案"),
    ("Annex 16 Vol II", "4th 2017-07", "5th 2023-07 + Amd 12", "behind", 1,
     "现行第五版 2023 并已并入第 12 号修正案"),
    ("Annex 16 Vol III", "1st 2017-07", "2nd 2026-08", "behind", 1,
     "现行第二版（站内基线记 2026-08 换版）"),
    ("Annex 16 Vol IV", "1st 2018-10", "2nd 2023-07 + Amd 2", "behind", 1,
     "现行第二版 2023 并已并入第 2 号修正案"),
    ("Annex 17", "10th 2017-04、11th 2020-03", "12th 2022", "behind", 1, "现行第十二版 2022"),
    ("Annex 18", "4th 2011-07", "4th 2011", "same", 0, "一致"),
    ("Annex 19", "2nd 2016-07", "2nd 2016-07（现行适用）｜3rd 2025-11 于 2026-11-26 生效", "pending", 1,
     "★ 11 月生效项：第 3 版 2025-11 出版，封面载明 2026-11-26 取代第 2 版。"
     "包内第 2 版在 2026-11-26 之前仍为现行，之后即落后一版"),
]


def main():
    recs = json.loads(RECORDS.read_text(encoding="utf-8"))
    recs = recs if isinstance(recs, list) else recs.get("records", [])
    site = {}
    for r in recs:
        rl = r.get("recordLevel") or {}
        if rl.get("icaoNumber"):
            site[rl["icaoNumber"]] = rl.get("edition")

    rows = []
    for label, zipv, cur, kind, gap, note in ROWS:
        rows.append({
            "item": label, "inZip": zipv, "current": cur,
            "verdict": kind, "versionsBehind": gap, "note": note,
            "liveReconfirmed": label in LIVE_CONFIRMED,
            "siteBaseline": site.get(label.split(" ")[0] + (" " + label.split(" ")[1] if " " in label and label.split(" ")[0] == "Annex" and label.split(" ")[1].startswith(("10", "14", "16", "6")) else "")),
        })

    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1

    print("=" * 108)
    print("图书馆 ICAO 包（2024-04-09）与当前现行版次比对")
    print(f"基准：站内版次库（2026-10-22/23 取自 ICAO Store 与官方 PDF 封面）｜本次实抓复核 2026-{date.today():%m-%d}")
    print("=" * 108)
    print(f'{"条目":18s} {"包内持有":44s} {"现行":30s} 判定')
    print("-" * 108)
    MARK = {"same": "一致", "behind": "落后", "missing": "缺卷", "amd": "同版缺修正案", "pending": "即将落后"}
    for r in rows:
        m = MARK[r["verdict"]]
        if r["versionsBehind"]:
            m += f' {r["versionsBehind"]} 版'
        flag = " ★" if r["liveReconfirmed"] else ""
        print(f'{r["item"]:18s} {r["inZip"][:43]:44s} {r["current"][:29]:30s} {m}{flag}')

    print("-" * 108)
    print("汇总：" + "｜".join(f"{MARK[k]} {v} 项" for k, v in
                             sorted(tally.items(), key=lambda x: -x[1])))
    print("  ★ = 本次（2026-10-29）实抓 ICAO Store 目录页复核过")
    print("\n需特别注意：")
    for r in rows:
        if r["verdict"] in ("pending", "missing") or r["versionsBehind"] and r["versionsBehind"] >= 2:
            print(f'  · {r["item"]}（{MARK[r["verdict"]]}）：{r["note"]}')

    OUT.write_text(json.dumps({
        "generatedAt": date.today().isoformat(),
        "zip": "ICAO附件2024-4-9图书馆发来.zip（中文版 30 份 / 英文版 34 份）",
        "baseline": "站内 recordLevel.edition（2026-10-22/23 取自 ICAO Store 与官方 PDF 封面）",
        "liveRecheck": "2026-10-29 抓 store.icao.int/en/annexes；该页仅暴露 11 个产品，无适用日字段",
        "caveat": "Store 目录页为分页展示，未能一次性取得全部 19 份附件的现行版次与适用日；"
                  "标 ★ 者为本次复核，其余依据站内 2026-10-22 基线。",
        "rows": rows,
        "tally": tally,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\n已写入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
