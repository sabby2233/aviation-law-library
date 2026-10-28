#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
annotate_case_evidence.py — 把「缺决定日」与「没有来源」区分开

问题（用户 2026-10-29 指出）：
    21 条案例卡片只写「决定日待核验」，读者容易读成「这条什么都没有、不可信」。
    实际情况完全相反：每条都有 62–202 字的具体摘要，且都登记了执法文书
    （documentType = enforcement_decision，题名精确到文号/企业）。
    缺的只是 decisionDate 一个字段，而不是整个案件没有依据。

    把两种情况混成一个「待核验」，等于自己贬低自己的数据——
    这正是「有二手来源支撑」与「什么都没有」被混为一谈的原因。

做法：
    给每条补 recordLevel.evidenceStatus，明确四件事：
      factSource      —— 事实依据哪份登记文书（ID/题名/类型/等级）
      summaryProvenance —— 摘要是中文转述而非逐字引用（这一条必须写，否则读者会当成原文）
      stillMissing    —— 只缺什么（决定日）
      recheck         —— 现在能不能回原文核对；不能的话，原因是什么

纪律：
    · 不因「有来源」就宣称数值已核——摘要里的罚款额、受影响人数未逐项复核，如实写明；
    · 不改 decisionDate；不改 sourceTier；
    · 幂等：已写过 evidenceStatus 的跳过（--force 重写）。

用法：python scripts/annotate_case_evidence.py [--dry-run] [--force]
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "records" / "cases_aviation_data.json"
REG = ROOT / "data" / "sources" / "registry.json"
TODAY = date.today().isoformat()

# 「原文现在为什么取不到」——沿用 dateGap 的实测结论，不重新猜
RECHECK_BLOCK = {
    "source-blocked": "官方站点反爬或人机校验，2026-10-29 实测取不到（换境外出口同样被挡）",
    "source-gone": "原链接已失效（404 / 站点改版），文书需重新定位",
    "source-is-index-page": "登记链接指向机构首页或栏目页，未直达文书，需站内另行定位",
    "page-has-no-date": "页面可读但未载决定日（多为报道或分析文章）",
    "lead-from-feed": "由信息流自动发现，尚未定位官方决定书",
}


def main():
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    data = json.loads(CASES.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    reg = {x["sourceId"]: x for x in json.loads(REG.read_text(encoding="utf-8"))}

    n = 0
    for r in recs:
        if (r.get("dates") or {}).get("decisionDate"):
            continue
        rl = r.setdefault("recordLevel", {})
        if rl.get("evidenceStatus") and not force:
            continue

        # 事实依据：取该记录断言里登记的第一个来源
        sids = [a.get("sourceId") for a in (r.get("assertions") or []) if a.get("sourceId")]
        src = reg.get(sids[0]) if sids else None
        gap = rl.get("dateGap") or {}
        reason = gap.get("reason") or "unclassified"

        evidence = {
            "annotatedAt": TODAY,
            "factSource": ({
                "sourceId": src.get("sourceId"),
                "documentType": src.get("documentType"),
                "title": src.get("title"),
                "authority": src.get("authority"),
                "evidenceLevel": src.get("evidenceLevel"),
                "url": src.get("url"),
            } if src else None),
            # 摘要来源必须按来源类型分别说清：
            #   信息流线索的摘要是英文原文搬运，不能说成「据文书整理」——那是抬高。
            "summaryProvenance": (
                "摘要取自信息流条目的标题与摘要（英文原文），尚未据官方决定书整理。"
                if (src or {}).get("documentType") == "news_feed"
                else "摘要为中文转述：采集时据登记文书整理，非逐字引用；"
                     "罚款金额、受影响人数等数值未在本次逐项复核。"
            ),
            "stillMissing": ["decisionDate"],
            "recheck": {
                "possible": False,
                "checkedAt": TODAY,
                "reason": reason,
                # 优先用该记录 dateGap 里已写明的具体情形（如「KVKK 页面仅返回导航模板」），
                # 通用映射只在缺 detail 时兜底——否则会把 JS 渲染页说成「报道文章」，不准确。
                "note": gap.get("detail") or RECHECK_BLOCK.get(reason, "未分类"),
            },
            "plainStatus": (
                "案件事实有登记文书支撑，缺决定日" if src else "仅有线索，无登记文书"
            ),
        }
        rl["evidenceStatus"] = evidence
        n += 1

    if not dry and n:
        from jsonio import save_json
        save_json(CASES, data)
    print(f"{'试跑' if dry else '已写入'}：{n} 条补 evidenceStatus")

    # 汇总，便于核对结论
    from collections import Counter
    tally = Counter()
    for r in recs:
        if (r.get("dates") or {}).get("decisionDate"):
            continue
        e = (r.get("recordLevel") or {}).get("evidenceStatus") or {}
        fs = e.get("factSource")
        tally[fs["evidenceLevel"] if fs else "无文书"] += 1
    print("事实依据的等级分布：", dict(tally))


if __name__ == "__main__":
    main()
