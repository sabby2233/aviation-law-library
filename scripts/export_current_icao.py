#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_current_icao.py — 把"核对过、且此刻现行"的 ICAO Annex 与 Doc 复制到桌面文件夹

为什么要有这个脚本，而不是手工拷：
  1. 文件名骗人是这批材料的高发问题（an10v1.pdf 实为 Vol VI、5801.pdf 实为
     Doc 8168 Vol II 第 6 版）。导出名必须由核验结论决定，不能沿用原名。
  2. "现行"要按适用日判，不按版次年份判：Annex 6 Part II 第 12 版 2026-08 出版，
     但适用日是 2026-11-26，所以在 2026-10-23 这天第 11 版仍现行。
  3. 必须排除 DRM 壳（2 页信封，正文加密在附件里），否则读者拷走也打不开。

用法：
  python scripts/export_current_icao.py --dry-run    # 只看计划
  python scripts/export_current_icao.py              # 实际复制
"""

import argparse
import shutil
import sys
from pathlib import Path

import pypdf

SRC = Path.home() / "Downloads"
DEST_NAME = "ICAO 现行文本（2026-10-23）"
CHECKED = "2026-10-23"

# (导出名主体, 源文件, 版次, 适用日, 修订状态, 备注)
ENTRIES = [
    ("Annex 01 人员执照的颁发 Personnel Licensing", "icao_annex_1_personnellicensing.pdf",
     "14th Ed, 2022", "2022-11-03", "Amd 1–179 已并入（末条 28/11/24）", ""),
    ("Annex 02 空中规则 Rules of the Air", "icao_annex_2_rulesoftheair.pdf",
     "11th Ed, 2024", "2024-11-28", "见文件内 (iii) 页", ""),
    ("Annex 03 国际空中航行气象服务 Meteorological Service", "an03_cons.pdf",
     "21st Ed, 2025", "2025-11-27", "Amd 1–82 已并入，另有 Corr 1（20/10/25）", "换版：库内原记 20th 2018，已按本件更正"),
    ("Annex 04 航图 Aeronautical Charts", "icao_annex_4_aeronauticalcharts.pdf",
     "11th Ed, 2009", "2009-11-19", "Amd 1–62 已并入（末条 28/11/24）", ""),
    ("Annex 05 计量单位 Units of Measurement", "icao_annex_5_unitsofmeasurementtobeusedinairandgroundoperations.pdf",
     "5th Ed, 2010", "2010-11-18", "见文件内 (iii) 页", ""),
    ("Annex 06-I 国际商业航空运输—飞机", "AN06_P1_cons.pdf",
     "12th Ed, 2022", "2022-11-03", "Amd 1–50 已并入（末条 27/11/25）", ""),
    ("Annex 06-II 国际通用航空—飞机", "icao_annex_6_operationofaircraftpartiiinternationalgeneralaviati.pdf",
     "11th Ed, 2022", "2022-11-03", "Amd 1–41 已并入（末条 28/11/24）", "第 12 版 2026-08 已出版，适用日 2026-11-26；在此之前本版仍现行"),
    ("Annex 06-III 国际运行—直升机", "an06_p3_cons.pdf",
     "11th Ed, 2022", "2022-11-03", "Amd 1–26 已并入（末条 27/11/25）", "第 12 版适用日 2026-11-26；在此之前本版仍现行"),
    ("Annex 07 航空器国籍和登记标志", "icao_annex_7_aircraftnationalityandregistrationmarks.pdf",
     "6th Ed, 2012", "2012-11-15", "Amd 1–7 已并入（末条 2/11/23）", ""),
    ("Annex 08 航空器适航性 Airworthiness of Aircraft", "an08_cons.pdf",
     "13th Ed, 2022", "2022-11-03", "见文件内 (iii) 页（另存 Amd 110 单行本）", ""),
    ("Annex 09 简化手续 Facilitation", "an09_cons.pdf",
     "17th Ed, 2025", "2025-07-11", "见文件内 (iii) 页", "PNR/API 旅客数据的国际法源，与数据治理主线直接相关"),
    ("Annex 10-I 无线电导航设备", "AN10_V1_cons.pdf",
     "8th Ed, 2023", "2023-11-02", "Amd 1–94 已并入（末条 27/11/25）", ""),
    ("Annex 10-II 通信程序（含 PANS 地位）", "AN10_V2_cons.pdf",
     "7th Ed, 2016", "2016-11-10", "见文件内 (iii) 页", ""),
    ("Annex 10-III 通信系统", "AN10_V3_cons.pdf",
     "2nd Ed, 2007", "2007-11-22", "见文件内 (iii) 页", "版次现行，但修订落后；文本层有损坏，部分页抽取为乱码"),
    ("Annex 10-IV 监视雷达与防撞系统", "icao_annex_10_aeronauticaltelecommunicationsvolumeiv-surveillanc.pdf",
     "5th Ed, 2014", "2014-11-13", "Amd 1–91 已并入（末条 3/11/22）", "第 6 版 2026-08 已出版，适用日 2026-11-26；在此之前本版仍现行"),
    ("Annex 10-V 航空无线电频谱利用", "AN10_V5_cons.pdf",
     "3rd Ed, 2013", "2013-11-14", "Amd 1–91 已并入（末条 27/11/25）", ""),
    ("Annex 11 空中交通服务 Air Traffic Services", "an11_cons.pdf",
     "15th Ed, 2018", "2018-11-08", "Amd 1–54 已并入（末条 27/11/25）", ""),
    ("Annex 12 搜寻与援救 Search and Rescue", "icao_annex_12_searchandrescue.pdf",
     "9th Ed, 2024", "2024-11-28", "见文件内 (iii) 页", ""),
    ("Annex 13 航空器事故和事故征候调查", "icao_annex_13_aircraftaccidentandincidentinvestigation.pdf",
     "13th Ed, 2024", "2024-11-28", "见文件内 (iii) 页", ""),
    ("Annex 14-I 机场设计与运行", "[722611283] an14_v1_cons corr3.pdf",
     "9th Ed, 2022", "2022-11-03", "含 Corrigendum 3；Amd 编号见 (iii) 页", "另有一份同版 352 页副本（无 Corr 3），未导出"),
    ("Annex 14-II 直升机场 Heliports", "AN14_V2_cons_en.pdf",
     "5th Ed, 2020", "2020-11-05", "Amd 1–10 已并入（末条 27/11/25）", "eVTOL 起降场直接参照本卷"),
    ("Annex 15 航空情报服务 Aeronautical Information Services", "an15_cons.pdf",
     "16th Ed, 2018", "2018-11-08", "Amd 1–44 已并入（末条 27/11/25）", "数据质量与数字交换要求的法源，配 Doc 10066 / 8126 使用"),
    ("Annex 16-I 航空器噪声 Aircraft Noise", "icao_annex_16_environmentalprotectionvolumei-aircraftnoise.pdf",
     "8th Ed, 2017", "2018-01-01", "见文件内 (iii) 页", ""),
    ("Annex 16-II 航空器发动机排放", "icao_annex_16_environmentalprotectionvolumeii-aircraftengineemis.pdf",
     "5th Ed, 2023", "2024-01-01", "见文件内 (iii) 页", ""),
    ("Annex 16-III 航空器 CO2 排放", "icao_annex_16_environmentalprotectionvolumeiii_co2.pdf",
     "1st Ed, 2017", "2017-01-01", "见文件内 (iii) 页", "第 2 版 2026-08 已出版，适用日 2026-11-26；在此之前本版仍现行"),
    ("Annex 16-IV CORSIA", "icao_annex_16_environmentalprotectionvolumeiv-corsia.pdf",
     "2nd Ed, 2023", "2024-01-01", "见文件内 (iii) 页", ""),
    ("Annex 17 保安：保护国际民用航空免遭非法干扰", "icao_annex_17_security.pdf",
     "12th Ed, 2022", "2022-11-18", "见文件内 (iii) 页", ""),
    ("Annex 18 危险品的安全航空运输", "icao_annex_18_thesafetransportofdangerousgoodsbyair.pdf",
     "4th Ed, 2011", "2011-11-17", "Amd 1–12 已并入（末条 12/11/15）", ""),
    ("Annex 19 安全管理 Safety Management", "icao_annex_19_second-edition.pdf",
     "2nd Ed, 2016", "2019-11-07", "含 Amd 1（见 (iii) 页）", "第 3 版 2025-11 已出版但 2026-11-26 才取代本版；截止核验日现行仍为第 2 版"),

    ("Doc 4444 空中交通管理 PANS-ATM", "4444_cons_en.pdf",
     "16th Ed, 2016", "2016-11-10", "含 Amd 1–13（Amd 13：27/11/25）", "英文合并本；另两份同版副本修订更旧，未导出。法文版另存。"),
    ("Doc 10066 航空情报管理 PANS-AIM", "10066_cons_en.pdf",
     "1st Ed, 2018", "2018-11-08", "含 Amd 1–4（Amd 4：27/11/25）", ""),
    ("Doc 8126 航空情报服务手册", "ICAO-Doc-8126-Aeronautical-Information-Services-Manual-7th-ed.-amdt.-1-2022.pdf",
     "7th Ed, 2022", "2022", "含 Amd 1（30/07/24）", "手册不具 SARPs 效力，条文要求以 Annex 15 为准"),
    ("Doc 8168-I 飞行程序 Flight Procedures", "icao_doc_8168_aircraftoperations.pdf",
     "6th Ed, 2018", "2018-11-08", "含 Amd 1–11（Amd 11：28/11/24）", ""),
    ("Doc 8168-II 目视和仪表飞行程序设计", "ICAO-Doc-8168-Aircraft-Operations-PANS-OPS-Volume-II-Construction-of-Visual-and-Instrument-Flight-Procedures-7th-ed.-2020.pdf",
     "7th Ed, 2020", "2020-11-05", "含 Amd 1–10 与 Corr 1–2；缺 Corr 5（2026-04-02）", "缺 Corrigendum 5（2026-04-02）"),
    ("Doc 8168-III 航空器运行程序", "ICAO-Doc-8168-Aircraft-Operations-PANS-OPS-Volume-III-Aircraft-Operating-Procedures-1st-ed.-amdt.-3-2018.pdf",
     "1st Ed, 2018", "2018-11-08", "含 Amd 1–3（Amd 3：28/11/24）；Amd 4 待 2026-11-26", "2018 年才从第 I 卷独立成卷，引注须写明卷次；Amd 4 待 2026-11-26"),
    ("Doc 8400 缩略语和代码 PANS-ABC", "8400_cons_en_2024.pdf",
     "9th Ed, 2016", "2016-11-10", "含 Amd 1–34；缺 Amd 35（27/11/25）", "缺 Amd 35（2025-11-27）；Amd 36 预定 2026-11-26 适用"),
    ("Doc 9981 机场 PANS-ADR", "9981_cons_en.pdf",
     "3rd Ed, 2020", "2020-11-05", "含 Amd 1–5（Amd 5：27/11/25 与 21/11/30 两批）", "Amd 5 分两批适用：一般条款 2025-11-27，障碍物评价章节 2030-11-21"),
    ("Doc 9868 培训 Training", "icao_doc_9868_training.pdf",
     "3rd Ed, 2020", "2020-11-05", "见文件内 (iii) 页", ""),
]

# 不导出，但要在清单里说明原因
EXCLUDED = [
    ("Annex 6 Part IV 遥控驾驶航空器系统（1st Ed, 2024）",
     "仅有 DRM 加密件（ICAO_AN_06Part04-1_EN_protected.pdf），正文在附件里加密，"
     "无任何可读副本；学校馆藏亦无此卷。RPAS 运行规则的关键一环，建议另行购买。"),
    ("Annex 10 Vol VI RPAS C2 链路（1st Ed, 2021）",
     "适用日 2026-11-26，尚未生效。文件（an10v1.pdf，36 页）已在手上，"
     "且 Part II 多章 ICAO 自标 To be developed，规则尚未成形。"),
    ("Doc 9760 适航手册（4th Ed, 2020）",
     "已被 5th Ed（2025，448 页）取代。手上只有第 4 版，不能当现行文本用。"),
    ("Doc 4444 法文版、Doc 8400 第 8 版（2010）、Doc 9868 第 2 版（2016）、"
     "Doc 8168-II 第 6 版（2014）",
     "均为旧版或非英文版，已有更好的替代件。"),
    ("annexes_booklet.pdf",
     "2005 年印制的附件目录小册，不是任何附件正文，版次信息早已过期。"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dest", default=str(Path.home() / "Desktop" / DEST_NAME))
    args = ap.parse_args()

    dest = Path(args.dest)
    plan, problems = [], []
    for name, src_name, ed, app, amd, note in ENTRIES:
        p = SRC / src_name
        if not p.exists():
            problems.append(f"缺文件：{src_name}")
            continue
        try:
            r = pypdf.PdfReader(p)
            pages = len(r.pages)
        except Exception as e:                      # noqa: BLE001
            problems.append(f"打不开：{src_name}（{type(e).__name__}）")
            continue
        if pages <= 3:
            problems.append(f"疑似 DRM 壳，跳过：{src_name}（{pages} 页）")
            continue
        out = dest / f"{name} — {ed}.pdf"
        plan.append((out, p, pages))

    print(f"目标目录：{dest}")
    print(f"计划导出 {len(plan)} 份")
    for out, p, pages in plan:
        print(f"  {out.name[:76]:76} {pages:>4}p  ← {p.name}")
    if problems:
        print("\n问题：")
        for x in problems:
            print("  !", x)

    if args.dry_run:
        print("\n（--dry-run，未复制）")
        return 0 if not problems else 1

    dest.mkdir(parents=True, exist_ok=True)
    for out, p, _ in plan:
        shutil.copy2(p, out)
    write_manifest(dest, plan)
    print(f"\n已复制到 {dest}")
    return 0 if not problems else 1


def write_manifest(dest, plan):
    lines = [
        "# ICAO 现行文本（核对日 2026-10-23）",
        "",
        f"共 {len(plan)} 份。全部为可读文本（非 DRM 加密），逐份核对过版次与适用日。",
        "",
        "**判定口径**：以「适用日」为准，不以版次年份为准。ICAO 的 Edition 年份是出版年，",
        "新版的适用日通常在出版后数月（多为 11 月），因此同一时点「最新版次」与「现行版次」",
        "可能不是同一个。例：Annex 6 第 II 部分第 12 版 2026-08 已出版，但 2026-11-26 才适用，",
        "所以本文件夹收的是仍在效力的第 11 版。",
        "",
        "| 文件 | 版次 | 适用日 | 修订状态 |",
        "|---|---|---|---|",
    ]
    for name, _, ed, app, amd, _ in ENTRIES:
        lines.append(f"| {name} | {ed} | {app} | {amd} |")

    notes = [(n, note) for n, _, _, _, _, note in ENTRIES if note]
    if notes:
        lines += ["", "## 逐条说明", ""]
        for n, note in notes:
            lines.append(f"- **{n}**：{note}")

    lines += ["", "## 未收入，及原因", ""]
    for n, why in EXCLUDED:
        lines.append(f"- **{n}**：{why}")

    lines += [
        "",
        "## 使用边界",
        "",
        "1. 这些是 ICAO 出版物，受著作权保护。SARPs 与 PANS 允许引用条款号并转述，",
        "   但不得整段复制、印刷分发或上传到公开站点。本文件夹仅供本人研究与写作引用。",
        "2. 引用时请同时写明**版次与适用日**，例如「Annex 6, Part II, 11th Edition (applicable 3 November 2022)」。",
        "   只写「Annex 6」会把不同部分、不同版次混在一起。",
        "3. 带分卷的附件必须写卷次：Annex 6 有四部分、Annex 10 有六卷、Annex 14 有两卷、Annex 16 有四卷。",
        "4. 本次核对的缺口（另需补充）：Annex 6 Part IV（RPAS）、Doc 9760 第 5 版、",
        "   Doc 8400 Amd 35、Doc 8168-II Corrigendum 5、Annex 10 Vol VI（2026-11-26 生效后）。",
    ]
    (dest / "清单与使用边界.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
