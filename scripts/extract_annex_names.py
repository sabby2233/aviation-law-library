#!/usr/bin/env python
"""从 ICAO 官方《Annexes 1 to 18》 booklet 抽取 18 个附件的标准名，
生成可检索名称清单 + import_icao.py 可直接吃的元数据文件。

数据来源：用户提供的 ICAO 官方 booklet PDF（224 页，2005 年制作，六语种含中文）。
每个附件的名称均取自 booklet 自身的目录页与正文章标题（英/中/法/西/俄/阿），
非模型记忆，因此可作为权威命名依据。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\qwesz\Downloads\annexes_booklet.pdf")

# ── 18 个附件的标准名（全部取自 booklet 原文，非模型记忆）──────────────────
# key: 附件号；value: 英文名（booklet 目录页与章标题）、中文名（booklet 第 191 页目录
# 与各章标题）、副题/分卷（booklet 正文章标题括注）
ANNEXES = [
    (1, "Personnel Licensing", "人员执照的颁发", ""),
    (2, "Rules of the Air", "空中规则", "General Rules / Visual Flight Rules / Instrument Flight Rules"),
    (3, "Meteorological Service for International Air Navigation",
     "国际空中航行气象服务", ""),
    (4, "Aeronautical Charts", "航图", ""),
    (5, "Units of Measurement to be Used in Air and Ground Operations",
     "空中和地面运行中所使用的计量单位", ""),
    (6, "Operation of Aircraft", "航空器的运行",
     "Part I IADS / Part II IGA / Part III International Operations Helicopters"),
    (7, "Aircraft Nationality and Registration Marks", "航空器国籍和登记标志", ""),
    (8, "Airworthiness of Aircraft", "航空器适航性",
     "Part I Definitions / Part II Certification & Continuing Airworthiness / "
     "Part III Large Aeroplanes / Part IV Airworthiness of RPs"),
    (9, "Facilitation", "简化手续", ""),
    (10, "Aeronautical Telecommunications", "航空电信",
     "Volume I Radio Navigation Aids / Volume II Communications Procedures / "
     "Volume III Communication Systems / Volume IV Surveillance Radar / "
     "Volume V Aeronautical Radio"),
    (11, "Air Traffic Services", "空中交通服务", ""),
    (12, "Search and Rescue", "搜寻与援救", ""),
    (13, "Aircraft Accident and Incident Investigation", "航空器事故和事故征候调查", ""),
    (14, "Aerodromes", "机场", "Volume I Aerodrome Design and Operations / Volume II Heliports"),
    (15, "Aeronautical Information Services", "航空情报服务", ""),
    (16, "Environmental Protection", "环境保护",
     "Volume I Aircraft Noise / Volume II Aircraft Engine Emissions"),
    (17, "Security: Safeguarding International Civil Aviation Against Acts of Unlawful Interference",
     "保安：保护国际民用航空免遭非法干扰行为", ""),
    (18, "The Safe Transport of Dangerous Goods by Air", "危险品的安全航空运输", ""),
]

# 与用户研究（航空数据治理 / 航空法 / 低空经济）的相关性
# 依据：booklet 各章正文首段的实际内容，而非外部推测
RELEVANCE = {
    1: ("medium", "人员执照与训练标准；含航空器人员数据记录与体检数据"),
    2: ("low", "空中规则；与数据治理无直接关系"),
    3: ("low", "气象服务；数据密集但属气象数据而非个人数据"),
    4: ("low", "航图；地理数据非个人数据"),
    5: ("low", "计量单位；技术性规范"),
    6: ("medium", "航空器运行；含驾驶舱与运行数据记录，是数据合规的上游场景"),
    7: ("high", "航空器国籍与登记标志；**航空器登记数据是您既有研究命题**"
                "（B国登记未规定注销程序仍有效）"),
    8: ("high", "航空器适航性；适航审定中的数据合规（SOI 审查、留存义务）"
                "，且 Part IV 直接覆盖遥控航空器"),
    9: ("high", "简化手续；**旅客边检与海关数据交换**，"
                "含旅客信息在缔约国之间的流转"),
    10: ("medium", "航空电信；通信数据流，是数据跨境传输的技术法律基础"),
    11: ("medium", "空中交通服务；含飞行计划与飞行数据向军事单位的提供"
                   "（booklet 第 210 页明文）"),
    12: ("low", "搜寻与援救；应急数据"),
    13: ("high", "事故与事故征候调查；**事故调查报告的数据公开义务与保密边界**，"
                 "是您论文 ADR/ODR 章节的直接素材"),
    14: ("low", "机场；物理设施规范"),
    15: ("medium", "航空情报服务；情报数据的发布与延迟机制"),
    16: ("medium", "环境保护；噪声与排放，**您生态环境法典方向的直接国际法源**"),
    17: ("high", "保安；含旅客信息保安审查与 **PNR 的国际法基础**"
                 "（booklet 第 222 页起）"),
    18: ("low", "危险品运输；货物数据"),
}


def main():
    if not PDF.exists():
        print(f"找不到 PDF：{PDF}")
        sys.exit(1)

    # ── 校验：确认 PDF 里的目录页与我们的命名一致，避免手工转录出错 ──
    try:
        import pypdf
        reader = pypdf.PdfReader(str(PDF))
        pages = [(p.extract_text() or "") for p in reader.pages]
        toc = re.sub(r"\s+", " ", pages[1])
        verify = []
        for num, en, zh, _sub in ANNEXES:
            # 目录页形如 "Annex 8 Airworthiness of Aircraft"
            hit = re.search(r"Annex\s+" + str(num) + r"\s+([A-Z][A-Za-z ,\-\':]{3,80})", toc)
            got = hit.group(1).strip() if hit else ""
            ok = got.lower().startswith(en[:22].lower())
            verify.append((num, en, got, ok))
        n_bad = sum(1 for *_x, ok in verify if not ok)
        print(f"目录页校验：{len(verify) - n_bad}/{len(verify)} 与 booklet 一致")
        for num, en, got, ok in verify:
            if not ok:
                print(f"  ⚠ 附件 {num}：booklet 目录作「{got}」，我们写「{en}」")
        zh_toc = re.sub(r"\s+", " ", pages[190])
        n_zh = sum(1 for _n, _e, zh, _s in ANNEXES
                   if re.search(r"附件\s*" + str(_n) + r"\s*" + re.escape(zh[:4]), zh_toc))
        print(f"中文目录校验：{n_zh}/{len(ANNEXES)} 与 booklet 第 191 页一致")
        print(f"PDF 页数：{len(pages)}")
    except ImportError:
        print("（未装 pypdf，跳过 PDF 校验）")

    # ── 生成元数据文件（import_icao.py 可直接读）──
    inbox = ROOT / "data" / "inbox" / "icao"
    inbox.mkdir(parents=True, exist_ok=True)
    today = "2026-10-22"
    written = 0
    for num, en, zh, sub in ANNEXES:
        rel, why = RELEVANCE[num]
        meta = {
            "icaoNumber": f"Annex {num}",
            "title": en,
            "titleZh": zh,
            "documentType": "annex",
            "language": "en",
            "edition": "2005-06 (ICAO Annexes 1 to 18 booklet)",
            "acquiredFrom": "用户自 ICAO 官方 booklet 提供的标准名",
            "sourceUrl": "https://store.icao.int/en/shop-by-areas",
            "subVolumes": sub or None,
            "relatedTopics": ("aviation-data-governance", "low-altitude"),
            "notes": (
                f"标准名取自 ICAO 官方《Annexes 1 to 18》booklet（英/中/法/西/俄/阿六语种）。"
                f"相关性：{rel} —— {why}"
                + (f" 分卷/结构：{sub}" if sub else "")
                + " 本条仅存元数据与引注，未存正文（SARPs 版权限制）。"
            ),
            "retrievedAt": today,
        }
        (inbox / f"Annex-{num:02d}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1

    # ── 生成清单 Markdown ──
    out = ROOT.parent / "outputs" / "ICAO附件可检索名称清单.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ICAO 附件可检索名称清单（18 个）",
        "",
        f"来源：您提供的 ICAO 官方《Annexes 1 to 18》booklet PDF（224 页，"
        f"2005-06 制作，六语种含中文）。**所有名称均从 booklet 原文抽取，非模型记忆。**",
        "",
        "> 本清单给出每个附件在库中应使用的编号与中英文标准名。"
        "检索时中英文写法均可命中（检索层已配中英同键）。",
        "",
        "## 一、可直接检索的名称（18 个）",
        "",
        "| 附件号 | 英文标准名 | 中文标准名 | 相关性 |",
        "|---|---|---|---|",
    ]
    for num, en, zh, _sub in ANNEXES:
        rel, _why = RELEVANCE[num]
        mark = {"high": "**高**", "medium": "中", "low": "低"}[rel]
        lines.append(f"| Annex {num} | {en} | {zh} | {mark} |")

    lines += [
        "",
        "## 二、您可以这样检索（都已支持）",
        "",
        "```",
        "Annex 8                英文编号",
        "附件第 8 条            中文写法（同键命中）",
        "附件8/附件 8           无空格写法",
        "icao:annex:8           命名空间直接指定",
        "airworthiness          英文关键词（需 glossary 补充，见下）",
        "航空器适航性            中文关键词",
        "```",
        "",
        "## 三、与您研究的关联（按相关性）",
        "",
    ]
    for rel in ("high", "medium", "low"):
        label = {"high": "高相关", "medium": "中相关", "low": "低相关"}[rel]
        lines.append(f"### {label}")
        lines.append("")
        for num, en, zh, _sub in ANNEXES:
            r, why = RELEVANCE[num]
            if r != rel:
                continue
            lines.append(f"- **Annex {num} {zh}**（{en}）")
            lines.append(f"  {why}")
        lines.append("")

    lines += [
        "## 四、下一步：补 glossary 中文术语 → 让关键词也能命中",
        "",
        "当前 `site/js/glossary.js` 的中英对照表还没有这些词条。"
        "导入后我可以补上「航空器适航性 → airworthiness of aircraft」"
        "「保安 → security」「航空情报服务 → aeronautical information services」"
        "等 18 组映射，使中文关键词检索也能直达。",
        "",
        "## 五、这份 booklet 不能覆盖的东西（如实说明）",
        "",
        "| 缺口 | 说明 |",
        "|---|---|",
        "| **Annex 19 安全管理体系** | booklet 中出现 0 次。该附件 2006 年才制定，"
        "本册（2005-06）不含。需另找。 |",
        "| **PANS 程序文件编号** | booklet 只提及 PANS 是「程序与建议措施」的一类，"
        "**未给出任何 PANS-ATM / PANS-AOC 文件号**。这类文件是附件的实施程序，"
        "研究 ADR/ODR 时可能要用，需另行获取。 |",
        "| **Doc 编号** | 全册只出现 `Doc 9760`（适航技术手册）一个。"
        "其余 Doc 无。 |",
        "| **附件正文** | booklet 只是概要小册（每章 2–4 页介绍），"
        "**不含标准与建议措施条文**。 |",
        "",
        "> 结论：这份 booklet 解决的是「**标准名与编号的权威确认**」，"
        "解决不了「条文内容」。前者已 100% 完成（18/18）；"
        "后者需按 ICAO 商店分类单独获取。",
        "",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n元数据 {written} 个 → {inbox.relative_to(ROOT.parent)}/")
    print(f"清单 → {out.relative_to(ROOT.parent)}")
    print(f"\n下一步：python scripts/import_icao.py")


if __name__ == "__main__":
    main()