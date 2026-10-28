#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_case_decisions.py — 把已从官方文书正文核到的决定日写入案例记录

与 annotate_case_date_gaps.py 的分工：
    annotate  → 核不到的，写清楚**为什么**核不到（不改 decisionDate）
    本脚本    → 核到的，才写 decisionDate，并留下可复查的定位

入参：data/case_decisions_verified.json（人工判读后写下的核验结论）
纪律：
    · 只写文书正文能直接读到的日期，且必须区分「决定日」与「公布/报道日」；
    · 上游数据集日期与官方文书不一致时，以**官方文书**为准，并在 note 里写明分歧；
    · 罚款金额只在文书载明确定数额时写入，不把「最高可达」的估算当已决金额。

用法：python scripts/apply_case_decisions.py [--dry-run]
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "records" / "cases_aviation_data.json"
VERIFIED = ROOT / "data" / "case_decisions_verified.json"

# ── 核验结论（逐条从文书正文读出）────────────────────────────
# 每条的 locator 都能回去复查：给的是页码/页眉字段，不是「我记得」。
ITEMS = [
    {
        "recordId": "AVA-SE-ADP-A-001",
        "decisionDate": "2022-07-18",
        "authorityCaseNo": "DI-2021-5301",
        "sourceId": "ADP-SE-A-001",
        "sourceUrl": "https://www.edpb.europa.eu/system/files/2023-02/se_2022-07decisionpublic_redacted.pdf",
        "locator": "IMY 最终决定（英文非官方译本）第 1 页页头：「Date of final decision: 2022-07-18」；"
                   "第 2 页页眉「Date:2022-07-18」；文号 DI-2021-5301，IMI case no. 115747",
        "evidenceLevel": "L0",
        "courtOrAuthority": "瑞典隐私保护局（IMY）",
        "note": "上游数据集记为 2023-02-20，与文书载明的 2022-07-18 不符（该日更可能是 EDPB 存档公布日）。"
                "以决定书正文为准。此件为官方决定之英文非官方译本，瑞典文原本为唯一正本——"
                "正本未取得，故按译本页头记载采信，证据等级按官方文书（译本）记 L0 并注明译本属性。",
        "upstreamDate": "2023-02-20",
        "discrepancy": "upstream_2023-02-20_vs_document_2022-07-18",
    },
    {
        "recordId": "AVA-US-ADP-C-001",
        "decisionDate": "2022-03-22",
        "authorityCaseNo": "No. 17 C 9080 (N.D. Ill.)",
        "sourceId": "ADP-US-C-001",
        "sourceUrl": "https://www.courthousenews.com/wp-content/uploads/2022/03/privacy-airline-ruling.pdf",
        "locator": "判决书第 1 页页眉：「Case: 1:17-cv-09080 Document #: 111 Filed: 03/22/22 Page 1 of 15」；"
                   "文首「UNITED STATES DISTRICT COURT NORTHERN DISTRICT OF ILLINOIS EASTERN DIVISION」、"
                   "「Kislov et al. v. American Airlines, Inc.」「Judge Rebecca R. Pallmeyer」",
        # 按站点「证据等级随来源渠道」的既有口径：文书是法院原件，但经二手站托管，
        # 注册表把 courthousenews.com 记为 L3，断言不得高于来源，故记 L3。
        # 内容的一手性另用 documentIsPrimary 表达，避免把「渠道二手」误读成「内容二手」。
        "evidenceLevel": "L3",
        "documentIsPrimary": True,
        "courtOrAuthority": "美国伊利诺伊北区联邦地区法院（N.D. Ill.），Pallmeyer 法官",
        "note": "上游数据集记为 2022-03-23，与法院文书页眉 Filed 03/22/22 差一日。以文书页眉为准。"
                "本件为 Memorandum Opinion and Order（即决判决意见），非终局判决。"
                "案件当事人为 Alex Kislov 与 Niko Hearn 诉 American Airlines，涉 BIPA 生物识别信息。",
        "upstreamDate": "2022-03-23",
        "discrepancy": "upstream_2022-03-23_vs_document_2022-03-22",
    },
]


def main():
    dry = "--dry-run" in sys.argv
    data = json.loads(CASES.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    by_id = {r["recordId"]: r for r in recs}

    applied = []
    for it in ITEMS:
        rec = by_id.get(it["recordId"])
        if not rec:
            print(f"  ✗ 找不到 {it['recordId']}")
            continue
        d = rec.setdefault("dates", {})
        old = d.get("decisionDate")
        d["decisionDate"] = it["decisionDate"]
        d["decisionDateBasis"] = "决定书正文/法院文书页眉"
        d["decisionDateLocator"] = it["locator"]
        # 上游给的是报道日的情形，保留原值以便日后对账
        if it.get("upstreamDate") and it["upstreamDate"] != it["decisionDate"]:
            d["upstreamDateRejected"] = it["upstreamDate"]
            d["upstreamDateRejectedReason"] = "与文书载明日期不符，以文书为准"

        rl = rec.setdefault("recordLevel", {})
        rl.pop("dateGap", None)          # 已核实，删除「未知原因」标注
        # 记录级核验状态必须跟着改：只补日期、状态仍写 pending，
        # 会让「待核验」计数把已核实的条目继续算进去（实际发生过）。
        # 若上游日期与文书不一致，用 verified_with_correction 如实标注「核过且更正过」。
        rl["verificationStatus"] = (
            "verified_with_correction"
            if it.get("upstreamDate") and it["upstreamDate"] != it["decisionDate"]
            else "verified")
        rl["decisionVerified"] = {
            "verifiedAt": date.today().isoformat(),
            "decisionDate": it["decisionDate"],
            "authorityCaseNo": it["authorityCaseNo"],
            "courtOrAuthority": it["courtOrAuthority"],
            "locator": it["locator"],
            "evidenceLevel": it["evidenceLevel"],
            "documentIsPrimary": it.get("documentIsPrimary"),
            "sourceUrl": it["sourceUrl"],
            "note": it["note"],
            "discrepancy": it.get("discrepancy"),
        }
        # 同步断言：追加一条判决日期的可审计断言。
        # sourceId 指向**该案原始文书**（登记在 data/sources/registry.json），
        # 不用「本轮核验」这类批次标签——批次编号无法回查文书，等于没有来源。
        rec["assertions"] = [a for a in (rec.get("assertions") or [])
                             if not (a.get("field") == "decision_date"
                                     and a.get("sourceId") == "CASE-VERIFY-R4")]
        rec.setdefault("assertions", []).append({
            "field": "decision_date",
            "value": it["decisionDate"],
            "sourceId": it["sourceId"],
            "locator": it["locator"],
            "evidenceLevel": it["evidenceLevel"],
            "verifiedAt": date.today().isoformat(),
        })
        applied.append(it["recordId"])

    if not dry:
        from jsonio import save_json
        save_json(CASES, data)
        VERIFIED.write_text(json.dumps(
            {"verifiedAt": date.today().isoformat(),
             "method": "取官方文书 PDF，读第 1 页页眉/页头的日期字段；与上游数据集比对，分歧以文书为准",
             "items": ITEMS,
             "blockedFromThisNetwork": [
                 {"recordId": "AVA-ES-ADP-A-004", "reason": "AEPD 返回「Acceso Bloqueado」，PDF 入口同样 500"},
                 {"recordId": "AVA-FR-ADP-A-001", "reason": "Legifrance 返回 Cloudflare 403；cnil.fr 该文号 404"},
             ],
             "notResolved": "其余 19 条：链接指向机构首页/已 404/页面无决定日，逐条原因见各记录 recordLevel.dateGap"},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{'试跑' if dry else '已写入'}：{len(applied)} 条决定日已核实入记录 → {applied}")


if __name__ == "__main__":
    main()
