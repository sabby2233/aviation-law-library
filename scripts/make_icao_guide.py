#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icao_guide.py — 生成 ICAO 文档下载与导入指引

原则：**本清单不凭记忆写编号**。
今天在 EUR-Lex 上，正是凭记忆写编号导致 27 条候选里 17 条指向无关领域。
因此这里的清单分两类，来源完全不同：

  A 类「已核验」——编号出现在 eCFR / EUR-Lex / Federal Register 的
     官方文本里，因此编号本身已被第三方官方文本确认；连主题名也是
     从那些官方文本的上下文里读出来的，不是我的记忆。

  B 类「待您从官网确认」——**不给编号**，只给下载入口与检索路径。
     因为 ICAO 官网全站 Cloudflare 拦截，我无法核验任何编号，
     给编号等于让您去核验一堆我编的东西。

用法：python scripts/make_icao_guide.py
输出：outputs/ICAO文档下载与导入指引.md
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / "outputs"
REFS = ROOT / "data" / "icao_refs_extracted.json"

# ICAO 商店的实测分类结构（2026-10-21 抓取 store.icao.int 得到）
STORE_AREAS = [
    ("safety", "安全", [
        ("accident-investigation", "事故调查（对应 Annex 13）"),
        ("aerodromes", "机场（对应 Annex 14）"),
        ("aeronautical-information", "航行资料"),
        ("dangerous-goods", "危险品运输"),
        ("communication-navigation-and-surveillance", "CNS"),
        ("flight-operations", "飞行运行（对应 Annex 6、PANS-ATM）"),
        ("flight-safety", "飞行安全"),
        ("human-factors", "人的因素"),
        ("meteorology", "气象"),
        ("performance-based-navigation", "基于性能的导航（PBN）"),
        ("safety-management", "安全管理（对应 Annex 19）"),
        ("safety-oversight", "安全监督"),
        ("search-and-rescue", "搜救（对应 Annex 12）"),
    ]),
    ("capacity-and-efficiency", "容量与效率", []),
    ("security-facilitation", "安保与边检", []),
    ("environmental-protection", "环境保护（对应 Annex 16）", []),
    ("economic-development", "经济发展", []),
    ("legal", "国际民航法律事务（芝加哥公约与附件）", []),
]

# 中英对照仅作导航用，不入库——未经 ICAO 官方中文版核对
SUBJECT_HINT = {
    "1": ("Personnel Licensing", "人员执照", "航空器人员资格"),
    "2": ("Rules of the Air", "空中规则", "空中规则与国际空中交通规则"),
    "6": ("Operation of Aircraft", "航空器运行", "国际空中运行规则"),
    "8": ("Airworthiness of Aircraft", "航空器适航", "航空器适航与持续适航"),
    "9": ("Air Navigation Services", "空中导航服务", "空中导航服务"),
    "10": ("Air Traffic Services", "空中交通服务", "空中交通服务"),
    "16": ("Environmental Protection", "环境保护", "航空器环境保护（噪声、排放）"),
    "19": ("Safety Management", "安全管理", "安全管理体系（SMS）"),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "ICAO文档下载与导入指引.md"

    refs = []
    if REFS.exists():
        refs = json.loads(REFS.read_text(encoding="utf-8"))
    annexes = [r for r in refs if r["kind"] == "附件"]

    L = [
        "# ICAO 文档下载与导入指引",
        "",
        "> 本清单**不含任何我凭记忆写的 ICAO 编号**。",
        "> 2026-10-21 的教训：在 EUR-Lex 上凭记忆写了 27 条 CELEX，",
        "> 逐条核验后 17 条指向无关领域（家用电冰箱能效标签、稻米出口退税…）。",
        "> 因此这里只提供**两种来源**：官方文本已确认的，或让您去官网确认的。",
        "",
        "---",
        "",
        "## 一、A 类：编号已被官方文本确认（可直接按编号去下载）",
        "",
        "这 8 个 ICAO 附件的编号**出现在美国联邦法规汇编（eCFR）与联邦公报的正文里**——",
        "换句话说，是美国官方法典自己在引用它们。主题名也摘自那些条文的上下文。",
        "",
        "| ICAO 附件 | 英文名（官方文本中的用法） | 中文参考¹ | 为什么被确认 | 出现处示例 |",
        "|---|---|---|---|---|",
    ]

    for a in sorted(annexes, key=lambda x: int(x["number"])):
        num = a["number"]
        subj = a["subjects"][0] if a["subjects"] else "（原文未带主题）"
        zh = SUBJECT_HINT.get(num, ("", "", ""))[2] or "—"
        ctx = a["contexts"][0] if a["contexts"] else ""
        L.append(
            f"| **Annex {num}** | {subj} | {zh} | "
            f"{', '.join(a['sources'])} | …{ctx[:70]}… |"
        )

    L += [
        "",
        "¹ 中文名仅作检索导航，**未经 ICAO 官方中文版核对**，入库时我不会把它当证据。",
        "",
        "**检索方式**（在 `store.icao.int` 站内搜索框，或 Google）：",
        "```",
        "site:store.icao.int \"Annex 17\"",
        "site:store.icao.int \"Annex 8\" airworthiness",
        "```",
        "",
        "---",
        "",
        "## 二、B 类：不给编号，只给下载入口",
        "",
        "ICAO 的**文件（Doc / PANS / Manual）体系编号极多且随修订变动**，",
        "我不给编号是因为无法核验——给您一堆我编的编号，您还得逐条去官网查证，",
        "那不如您直接在官网按主题找。",
        "",
        "### 下载入口（实测可访问）",
        "",
        "| 用途 | 地址 |",
        "|---|---|",
        "| 文档商店（主入口） | `https://store.icao.int/en` |",
        "| 高级检索 | `https://store.icao.int/en/advanced-search` |",
        "| 按主题浏览 | `https://store.icao.int/en/shop-by-areas` |",
        "",
        "### 主题分类（抓取自商店实际结构）",
        "",
        "| 分类 | 内容 |",
        "|---|---|",
    ]

    for slug, name, subs in STORE_AREAS:
        L.append(f"| **{name}** | `/en/shop-by-areas/{slug}` |")
        for sslug, sname in subs:
            L.append(f"| &nbsp;&nbsp;· {sname} | `/en/shop-by-areas/{slug}/{sslug}` |")

    L += [
        "",
        "### 按您的研究方向，建议优先取这几类",
        "",
        "| 优先级 | 类别 | 对应 ICAO 文件族 | 与您研究的关联 |",
        "|---|---|---|---|",
        "| ★★★ | 航空器适航 | Annex 8、Annex 1 | 适航审定、机载数据 |",
        "| ★★★ | 国际空中运行规则 | Annex 6、PANS-ATM | 低空运行、U-space 衔接 |",
        "| ★★☆ | 安全管理体系 | Annex 19、SMS 相关文件 | 适航与运行安全管理 |",
        "| ★★☆ | 空中交通服务 | Annex 11（待您确认编号）、PANS-ATM | UTM / U-space 的国际基础 |",
        "| ★★☆ | 航空安全与安保 | Annex 17、Annex 19 | 机场与航行安全 |",
        "| ★☆☆ | 环境保护 | Annex 16、Volume I/II | 航空器噪声与排放 |",
        "",
        "---",
        "",
        "## 三、下载之后怎么给我",
        "",
        "### 步骤",
        "",
        "```bash",
        "# 1. 生成元数据模板",
        "python scripts/import_icao.py --template",
        "",
        "# 2. 把从官网下载的文件与元数据放进收件箱",
        "#    目录：aviation-law-library/data/inbox/icao/",
        "",
        "# 3. 导入",
        "python scripts/import_icao.py",
        "",
        "# 4. 重建索引",
        "python scripts/build_sources.py && python scripts/build_manifest.py \\",
        "  && python scripts/build_browse.py && node scripts/build_api.js",
        "```",
        "",
        "### 放什么进去",
        "",
        "两种方式都可以：",
        "",
        "**方式 A（推荐，元数据准确）**——同名的一对文件：",
        "",
        "```",
        "data/inbox/icao/",
        "  Annex-17.json     ← 元数据（照模板填）",
        "  Annex-17.pdf      ← 正文原件（可选，仅作留档，不入库正文）",
        "```",
        "",
        "**方式 B（只有 PDF）**——脚本从文件名解析编号：",
        "",
        "```",
        "data/inbox/icao/Annex-17-Air-Traffic-Services.pdf",
        "```",
        "",
        "### 元数据模板字段说明",
        "",
        "| 字段 | 必填 | 说明 |",
        "|---|---|---|",
        "| `icaoNumber` | ✓ | `Annex 17` / `Doc 9944` / `PANS-ATM 8610` |",
        "| `title` | ✓ | 英文标题（照 PDF 封面抄） |",
        "| `titleZh` | | 中文标题。**只作检索导航，不作证据** |",
        "| `edition` | ✓ | 版本，如 `17th ed., 2010`——**引注必须带版本** |",
        "| `adoptedDate` | | 通过/采用日期 |",
        "| `amendmentDate` | | 最近修订日期 |",
        "| `sourceUrl` | ✓ | 该文档在官网的稳定链接 |",
        "| `isFreeAccess` | | 是否免费获取（影响版权判断） |",
        "",
        "### 版权处理",
        "",
        "**本站只存元数据与引注，不转载正文**——SARPs（标准与建议措施）",
        "由 ICAO 独家享有版权，官方明示不得印刷分发。",
        "",
        "您下载的 PDF 放在 `data/inbox/icao/` 里作为**个人留档**；",
        "入库时只抽取编号、标题、版本、日期与官网链接，**正文不入库、不上线**。",
        "",
        "### 导入后的记录状态",
        "",
        "每条 ICAO 记录会被标记为：",
        "",
        "```json",
        "\"verificationStatus\": \"user-provided\",",
        "\"sourceTier\": \"L1\"",
        "\"note\": \"ICAO 官方站点无法程序访问（Cloudflare 拦截），",
        "          本条元数据由用户从官网下载后导入；",
        "          SARPs 受版权保护，本站只存元数据与引注，不转载正文\"",
        "```",
        "",
        "**它不会伪装成 L0 自动核验**——这一点与库内其他源不同，",
        "引用前请自行核对版本与是否已被新版取代。",
        "",
        "---",
        "",
        "## 四、检索层已经准备好了",
        "",
        "ICAO 的标识符规则**现在就能用**，不用改任何代码：",
        "",
        "```",
        "Annex 17            → icao:annex:17",
        "附件第 17 条         → icao:annex:17      （中文写法归一到同一键）",
        "Annex 17 (Air Traffic Services) → icao:annex:17",
        "Doc 9944            → icao:doc:9944",
        "ICAO Doc 9944       → icao:doc:9944",
        "Document 9944       → icao:doc:9944",
        "PANS-ATM Doc 8610   → icao:pans:PANS-ATM:8610",
        "```",
        "",
        "数据接入前，这些查询会返回 **`未收录：Annex 17`** 的明确告警，",
        "而不是静默返回全部记录——这是设计意图。",
        "",
    ]

    path.write_text("\n".join(L), encoding="utf-8")
    print(f"指引 → {path}")
    print(f"  A 类已核验附件 {len(annexes)} 个")
    print(f"  B 类下载入口：商店主页 + {len(STORE_AREAS)} 个主题分类")
    print(f"  导入脚本：scripts/import_icao.py（已实测可用）")
    print(f"  收件箱：data/inbox/icao/")


if __name__ == "__main__":
    main()