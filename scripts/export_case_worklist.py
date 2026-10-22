#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_case_worklist.py — 生成 49 条案例的人工核验清单

用途：把库里"待核验"的案例变成一份**可直接在网络中检索与回填**的工作表。

每条给出四重检索线索（任一即可定位官方文书）：
  1. 决定编号 / 案卷号（如 AEPD 的 PS-00300-2019、FTC 的 2023074）
  2. 案件名（原文 + 英文）
  3. 监管机关全称
  4. 当前来源链接及其**实测可达状态**

同时输出 CSV，供回填核验结果（决定日 / 最终罚款额 / 官方链接 / 备注）。

用法：python scripts/export_case_worklist.py
输出：outputs/案例核验清单.md
      outputs/案例核验回填表.csv
      data/case_url_check.json（链接可达性实测结果）
"""

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "records" / "cases_aviation_data.json"
CHECK = ROOT / "data" / "case_url_check.json"
OUT_DIR = ROOT.parent / "outputs"

# 监管机关 → 官方决定库的检索入口与检索技巧
AUTHORITY_GUIDE = {
    "Agencia Española de Protección de Datos (AEPD)": (
        "https://www.aepd.es/documento/（决定库）",
        "决定编号 PS/XXXXX-YYYY 可直接拼 URL："
        "`https://www.aepd.es/documento/ps-XXXXX-YYYY.pdf`；"
        "站内搜 `PS-00300-2019`，或 Google `site:aepd.es PS-00300-2019`"),
    "Information Commissioner's Office (ICO)": (
        "https://ico.org.uk/action-weve-taken/enforcement/",
        "ICO 改版后路径常变；用案件名在 enforcement 页搜，"
        "或 Google `site:ico.org.uk <案件名>`；决定号在决定书页脚"),
    "Federal Trade Commission (FTC)": (
        "https://www.ftc.gov/legal-library/browse/cases-proceedings",
        "FTC 有**案卷号**（如 2023074），最可靠："
        "`site:ftc.gov 2023074`；或在 Cases & Proceedings 按案卷号搜"),
    "Kişisel Verileri Koruma Kurumu (KVKK)": (
        "https://www.kvkk.gov.tr/EN/Anonymous/Decision",
        "土耳其 KVKK 决定库有编号，搜案件名或公告日期"),
    "Commission nationale de l'informatique et des libertés (CNIL)": (
        "https://www.cnil.fr/fr/sanctions",
        "CNIL 制裁决定库按年分页；搜 `CNIL <案件名>`"),
    "Datatilsynet (挪威)": (
        "https://www.datatilsynet.no/",
        "挪威 DPA 决定库；搜案件名"),
    "Ufficio Garante per la protezione dei dati personali (Garante)": (
        "https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/####",
        "Garante 决定书编号形如 **152/2026**（provvedimento n. 152/2026），"
        "直接搜 `provvedimento 152/2026`"),
    "Dataprotection Authority (BE)": (
        "https://www.dataprotectionauthority.be/citizen",
        "比利时 APD 决定库；搜案件名或日期"),
    "Bundesbeauftragte für den Datenschutz (BfDI)": (
        "https://www.bfdi.bund.de/",
        "德国 BfDI 决定库；搜案件名"),
    "European Data Protection Board (EDPB)": (
        "https://www.edpb.europa.eu/",
        "EDPB 决定书有文号，搜案件名"),
    "Court of Justice of the European Union (CJEU)": (
        "https://curia.europa.eu/",
        "**CJEU 有 ECLI 标识符**（如 ECLI:EU:C:2019:817）——"
        "这在法学引注上是标准格式，比 URL 可靠；"
        "curia.europa.eu 搜案号即可"),
    "U.S. Court of Appeals / District Court": (
        "https://www.courtlistener.com/",
        "**CourtListener 免费且可检索**，优于商业站；"
        "按案号或当事人名搜，可得判决书 PDF"),
    "Dataprotection Commission (CY)": (
        "https://www.dataprotection.gov.cy/",
        "塞浦路斯委员会决定库"),
    "Datatilsynet (DK)": (
        "https://www.datatilsynet.dk/",
        "丹麦 DPA 决定库"),
    "Dataprotection Commission (RO)": (
        "https://www.dataprotection.ro/",
        "罗马尼亚 ANSPDCP 决定库"),
}

# 域名 → 官方站点，供失效链接重定向
HOST_OFFICIAL = {
    "www.aepd.es": "https://www.aepd.es/",
    "ico.org.uk": "https://ico.org.uk/",
    "www.ftc.gov": "https://www.ftc.gov/",
    "www.cnil.fr": "https://www.cnil.fr/",
    "www.legifrance.gouv.fr": "https://www.legifrance.gouv.fr/",
    "www.garanteprivacy.it": "https://www.garanteprivacy.it/",
    "www.datatilsynet.no": "https://www.datatilsynet.no/",
    "www.edoeb.admin.ch": "https://www.edoeb.admin.ch/",
    "noyb.eu": "https://noyb.eu/",
    "baylos.com": "（二手律所简报——须换官方一手）",
    "ppc.land": "（二手媒体——须换官方一手）",
    "vixio.com": "（二手——须换官方一手）",
    "courthousenews.com": "（二手媒体——须换官方一手）",
    "news.bloomberglaw.com": "（二手媒体——须换官方一手）",
    "ilfattoquotidiano.it": "（二手媒体——须换官方一手）",
}


def decision_no(case):
    """从 locator 或 URL 中抽决定编号 / 案卷号。"""
    loc = (case.get("assertions") or [{}])[0].get("locator", "")
    m = re.search(r"(?:决定书|判决|决定编号|case|案卷号)\s*[:：]?\s*([A-Za-z0-9\-\/\.]+)",
                  loc, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"/([A-Za-z]{2,10}-\d{3,6}-\d{4})", case.get("sourceUrl", ""))
    if m:
        return m.group(1)
    m = re.search(r"(\d{7})", case.get("sourceUrl", ""))
    if m:
        return m.group(1)
    return ""


def main():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    checks = {}
    if CHECK.exists():
        checks = {c["id"]: c for c in json.loads(CHECK.read_text(encoding="utf-8"))}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / "案例核验清单.md"
    csv_path = OUT_DIR / "案例核验回填表.csv"

    # ── CSV（供回填）──────────────────────────────────────
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "recordId", "法域", "监管机关", "决定编号/案卷号",
            "案件名（原文）", "案件名（英文）", "案由标签",
            "原库日期(口径待核)", "原库罚款额", "币种", "最终额是否已确认",
            "当前来源链接", "链接实测状态", "来源等级",
            "★需填_决定日", "★需填_最终罚款额", "★需填_官方一手链接", "★备注",
        ])
        for c in cases:
            a = {x["field"]: x["value"] for x in (c.get("assertions") or [])}
            pen = c.get("penalty") or {}
            chk = checks.get(c["recordId"], {})
            w.writerow([
                c["recordId"],
                c.get("jurisdiction", ""),
                a.get("authority", ""),
                decision_no(c),
                c.get("title", ""),
                c.get("titleEn", ""),
                ", ".join(c.get("topics") or []),
                (c.get("recordLevel") or {}).get("originalDate", ""),
                pen.get("amountOriginal", ""),
                pen.get("currency", ""),
                "否" if pen.get("amountFinal") is None and pen.get("amountOriginal") else "是",
                c.get("sourceUrl", ""),
                chk.get("status", "未测"),
                (c.get("recordLevel") or {}).get("sourceTier", ""),
                "", "", "", "",
            ])

    # ── Markdown（按机关分组）──────────────────────────────
    by_auth = {}
    for c in cases:
        a = {x["field"]: x["value"] for x in (c.get("assertions") or [])}
        by_auth.setdefault(a.get("authority", "（未标注）"), []).append(c)

    lines = [
        "# 49 条案例 · 人工核验清单",
        "",
        "> 本清单用于把库中「待核验」的案例转成可引用的记录。",
        "> 每条给出**四重检索线索**：决定编号 / 案卷号、案件名（中英）、监管机关、当前链接及其实测状态。",
        "",
        "## 每条需要核验什么",
        "",
        "| 项 | 说明 | 依据 |",
        "|---|---|---|",
        "| **决定日** | DPA 或法院作出决定的日期 | 原库 `date` 字段混装「决定日」与「报道日」，论文引用必须区分 |",
        "| **最终罚款额** | 是否减免、减免依据 | 原库拟议额/最终额/减免额混存；AENA 案摘要称 200,000 减至 160,000，字段却存 200,000 |",
        "| **官方一手链接** | 换成监管机构或法院的原始文书 | 25 条链接实测已失效或属二手来源 |",
        "",
        "## 链接实测总览",
        "",
    ]

    st = {}
    for c in cases:
        s = checks.get(c["recordId"], {}).get("status", "未测")
        st[s] = st.get(s, 0) + 1
    lines.append("| 状态 | 条数 | 含义 |")
    lines.append("|---|---|---|")
    mean = {
        "200": "链接有效，可直接打开原文",
        "HTTP 404": "页面已迁移或删除，需按决定编号重新定位",
        "HTTP 403": "网站拒绝程序访问（需人工浏览器打开）",
        "HTTP 503": "网站临时不可用，可稍后重试",
        "URLError": "域名或连接失败，可能已改域名",
        "202": "异步返回（可能是 JS 挑战页）",
        "ConnectionAbortedError": "连接被中断",
        "未测": "未检测",
    }
    for k, v in sorted(st.items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{k}` | {v} | {mean.get(k, '—')} |")
    lines.append("")

    lines += [
        "**注意**：`403 / 503 / URLError` 多为网站对自动程序的限制，",
        "**用浏览器人工打开往往正常**——请以人工访问结果为准，不要据此判定文书不存在。",
        "",
        "---",
        "",
    ]

    for auth, items in sorted(by_auth.items(), key=lambda kv: -len(kv[1])):
        entry = AUTHORITY_GUIDE.get(auth)
        lines += [f"## {auth}（{len(items)} 条）", ""]
        if entry:
            lines += [f"- 决定库：{entry[0]}", f"- 检索技巧：{entry[1]}", ""]
        else:
            hosts = {checks.get(c["recordId"], {}).get("host", "") for c in items}
            for h in hosts:
                if h in HOST_OFFICIAL:
                    lines.append(f"- 官方站点：{HOST_OFFICIAL[h]}")
            lines.append("")

        lines += [
            "| recordId | 决定编号 / 案卷号 | 案件名 | 原库日期 | 罚款 | 链接 | 状态 |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in items:
            a = {x["field"]: x["value"] for x in (c.get("assertions") or [])}
            pen = c.get("penalty") or {}
            chk = checks.get(c["recordId"], {})
            amt = ""
            if pen.get("amountOriginal"):
                amt = f"{pen.get('amountOriginal')} {pen.get('currency') or ''}"
                if pen.get("amountFinal") is None:
                    amt += "（拟议）"
            lines.append(
                f"| `{c['recordId']}` | {decision_no(c) or '—'} | "
                f"{c.get('title', '')[:44]} | "
                f"{(c.get('recordLevel') or {}).get('originalDate', '')} | "
                f"{amt or '—'} | [{chk.get('host', '')[:18]}]({c.get('sourceUrl', '')}) | "
                f"`{chk.get('status', '未测')}` |"
            )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"核验清单 → {md_path}")
    print(f"  {len(cases)} 条，按 {len(by_auth)} 个监管机关分组")
    print(f"  链接实测：{dict(sorted(st.items(), key=lambda kv: -kv[1]))}")
    print(f"回填表   → {csv_path}")
    print("  列：recordId / 决定编号 / 案件名 / ★决定日 / ★最终罚款额 / ★官方链接 / ★备注")


if __name__ == "__main__":
    main()