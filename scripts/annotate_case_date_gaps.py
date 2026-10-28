#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
annotate_case_date_gaps.py — 给「决定日未知」的案例补上**为什么未知**

问题：
    23 条案例 decisionDate 为 null，卡片只显示「决定日未知（待核验）」。
    读者无法分辨这是「机构未公布」「链接指错」还是「我们没查」——
    三种情况的可靠性含义完全不同，混成一个「未知」等于把工作量藏起来。

做法：
    依据 scripts/probe_case_dates.py 的探测结果（data/case_date_probe.json），
    给每条缺口写入 recordLevel.dateGap，含三项：
      · reason     —— 分类原因：source-is-index-page / source-gone / source-blocked /
                      page-has-no-date / upstream-uncertain
      · upstreamDate —— 上游数据集里记的日期（原样保留，**明确标注口径未核实**，不充作决定日）
      · evidence   —— 探测到的事实（HTTP 状态、页面标题、命中片段）

纪律：
    · 绝不因为「上游有个日期」就把 decisionDate 填上——那正是当年导入时判为不可靠而置空的东西；
    · 只在 recordLevel 增加说明字段，不动 decisionDate、不动 status；
    · 幂等：已写过 dateGap 的跳过（--force 可重写）。

用法：python scripts/annotate_case_date_gaps.py [--dry-run]
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "records" / "cases_aviation_data.json"
PROBE = ROOT / "data" / "case_date_probe.json"
UPSTREAM = ROOT / ".scratch" / "upstream_cases.json"
TODAY = date.today().isoformat()

# 探测结果 → 原因分类。逐条人工判读，不靠规则猜。
REASONS = {
    "AVA-ES-ADP-A-004": ("source-blocked",
        "AEPD 返回「Acceso Bloqueado」（反爬拦截），决定书 PS-00319-2022 正文取不到"),
    "AVA-FR-ADP-A-001": ("source-blocked",
        "Legifrance 返回 Cloudflare 人机校验页（Just a moment...），取不到 CNILTEXT000045372972 正文"),
    "AVA-DE-ADP-A-001": ("source-is-index-page",
        "链接指向 BfDI 英文首页，非该案决定页"),
    "AVA-IT-ADP-A-003": ("page-has-no-date",
        "noyb 页面为投诉通报，日期 2024-12-19 为**投诉提起日**，非监管决定日；罚额为「最高可达」的估算，非已决金额"),
    "AVA-SE-ADP-A-001": ("page-has-no-date",
        "EDPB 存档的决定书 PDF 可读，但页面内可检索到的日期为 GDPR 生效日与文件编号，决定落款日需逐页定位"),
    "AVA-TR-ADP-A-001": ("page-has-no-date",
        "KVKK 页面返回站点导航模板，决定正文未随 HTML 下发（疑前端异步加载）"),
    "AVA-TR-ADP-A-002": ("page-has-no-date",
        "同上：KVKK 页面仅返回导航模板"),
    "AVA-US-ADP-A-002": ("source-blocked",
        "transportation.gov 返回 Access Denied（403），取不到 DOT Order 2023-6-3"),
    "AVA-US-ADP-A-003": ("source-gone",
        "FTC 该案页面现返回「Page Not Found」，案卷已改版或改址"),
    "AVA-US-ADP-A-004": ("source-gone",
        "FTC 该新闻稿页面现返回「Page Not Found」"),
    "AVA-US-ADP-C-001": ("page-has-no-date",
        "Courthouse News 的判决书 PDF 可读，但检索到的 2019-06-18 是其中引用的**先例**日期，非本案裁判日"),
    "AVA-US-ADP-C-002": ("page-has-no-date",
        "Bloomberg Law 页面为报道，日期属报道日；起诉状与立案日需回法院记录（CourtListener/PACER）"),
    "AVA-NO-ADP-A-001": ("source-gone",
        "Datatilsynet 该新闻页现返回 404"),
    "AVA-NL-ADP-A-001": ("source-gone",
        "autoriteitpersoonsgegevens.nl 该页连接超时/拒绝，未能取到"),
    "AVA-HU-ADP-A-001": ("page-has-no-date",
        "dmp.hu 为律所分析文章，页面日期（2025-04-22）是**文章发布日**，非 NAIH 决定日"),
    "AVA-CH-ADP-A-001": ("source-is-index-page",
        "链接指向 EDÖB 决定汇编栏目页，非该案决定页；页面本身还报错"),
    "AVA-KR-ADP-A-001": ("source-is-index-page",
        "链接指向 PIPC 英文首页，非该案决定页"),
    "AVA-IN-ADP-A-001": ("source-is-index-page",
        "链接指向 MeitY 首页。注：DPBI 系印度数据保护委员会，其决定未必在 MeitY 站发布"),
    "AVA-AT-ADP-A-001": ("source-is-index-page",
        "链接指向奥地利 DSB 首页，非该案决定页"),
    "AVA-PT-ADP-A-001": ("source-is-index-page",
        "链接指向 CNPD 首页，非该案决定页"),
    "AVA-IE-ADP-A-001": ("source-is-index-page",
        "链接指向 DPC 首页；页内最新新闻日（2026-10）与本决定无关"),
    "AVA-PL-ADP-A-001": ("source-is-index-page",
        "链接指向 UODO 英文首页，非该案决定页"),
    "AVA-DK-ADP-A-001": ("source-is-index-page",
        "链接指向丹麦 Datatilsynet 首页（丹麦语），非该案决定页"),
}


def upstream_date_map():
    """上游 cases.json 的 date 字段。原样取用，仅作为线索。"""
    if not UPSTREAM.exists():
        return {}
    up = json.loads(UPSTREAM.read_text(encoding="utf-8"))
    up = up if isinstance(up, list) else up.get("cases", [])
    m = {}
    for x in up:
        p = str(x.get("id", "")).split("-")
        if len(p) == 3:
            m[f"AVA-{p[0]}-ADP-{p[1]}-{p[2]}"] = {
                "date": x.get("date"), "lastVerified": x.get("lastVerified")}
    return m


def main():
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    data = json.loads(CASES.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    probe = {x["recordId"]: x for x in json.loads(PROBE.read_text(encoding="utf-8"))}
    upd = upstream_date_map()

    n = 0
    for r in recs:
        rid = r["recordId"]
        if (r.get("dates") or {}).get("decisionDate"):
            continue
        rl = r.setdefault("recordLevel", {})
        if rl.get("dateGap") and not force:
            continue
        reason, detail = REASONS.get(rid, ("unclassified", "未分类"))
        p = probe.get(rid, {})
        up = upd.get(rid, {})
        rl["dateGap"] = {
            "annotatedAt": TODAY,
            "reason": reason,
            "detail": detail,
            "probeStatus": p.get("status"),
            "probeBytes": p.get("bytes"),
            "upstreamDate": up.get("date"),
            "upstreamDateCaveat": (
                "上游数据集记录的日期，其口径（决定日／公布日／报道日）未经核实，"
                "故不写入 decisionDate；仅作后续核查线索保留。"
                if up.get("date") else None),
            "upstreamLastVerified": up.get("lastVerified"),
            "nextStep": (
                "需按案号回监管机构决定库定位决定书正文，或回法院记录（PACER/CourtListener）取裁判日"
                if reason in ("source-is-index-page", "source-gone")
                else "需换用可直接取文的通道（官方 PDF 直链、公开镜像或书面申请）"
            ),
        }
        n += 1

    if not dry:
        from jsonio import save_json
        save_json(CASES, data)
    print(f"{'试跑' if dry else '已写入'}：为 {n} 条缺口补注 dateGap")
    from collections import Counter
    c = Counter(v[0] for v in REASONS.values())
    for k, v in c.most_common():
        print(f"  {k:24s} {v} 条")


if __name__ == "__main__":
    main()
