"""处理 ES-A-006 与 ES-A-008 的重复，并补齐 AEPD 决定编号。

事实（来自 AEPD 决定与多家权威报道一致）：
  AEPD 于 2025-11-06 作出决定，程序号 **PS-00431/2024**，
  对 AENA S.M.E., S.A. 罚款 **€10,043,002**，理由是其未就人脸识别
  做符合 GDPR 第 35 条的 DPIA，并责令暂停全部生物识别处理。
  试点 2019–2022 年在 8 个机场开展，62,054 名乘客注册。

因此：
  AVA-ES-ADP-A-008（€10,043,002）为**主记录**
  AVA-ES-ADP-A-006（€200,000）系同一决定的重复记录，且金额有误 → 标记 mergedInto

ID 不删除（永久标识、引用链接不能断），只标记归并关系。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\qwesz\WorkBuddy\2026-10-20-22-03-33\aviation-law-library")
P = ROOT / "data/records/cases_aviation_data.json"
cases = json.loads(P.read_text(encoding="utf-8"))
by_id = {c["recordId"]: c for c in cases}
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

AEPD_CASE = {
    "authority": "AEPD",
    "caseNo": "PS-00431/2024",
    "decisionDate": "2025-11-06",
    "amount": 10043002,
    "currency": "EUR",
    "legalBasis": "GDPR Art. 35（数据保护影响评估 DPIA）",
    "evidence": ("AEPD 决定 PS-00431/2024（2025-11-06）；Herbert Smith Freehills 2025 年 12 月数据月报；"
                 "香港 PCPD 欧盟执法动态页（2025-11-06 条）；ARA/El País 报道"),
    "url": "https://www.aepd.es/documento/ps-00431-2024.pdf",
}

# ── 主记录：ES-A-008 ──
main = by_id.get("AVA-ES-ADP-A-008")
if main:
    rl = main.setdefault("recordLevel", {})
    rl["verification"] = {
        "status": "verified",
        "checkedAt": TODAY,
        "checkedVia": "AEPD 官方决定 + 多源报道交叉核对",
        **AEPD_CASE,
        "note": ("AEPD 责令暂停全部生物识别处理，直至完成合规 DPIA。"
                 "Aena 已表示上诉。试点 2019–2022 年覆盖 8 个机场，62,054 名乘客注册。"),
    }
    d = main.get("dates") or {}
    main["dates"] = d
    d["decisionDate"] = AEPD_CASE["decisionDate"]
    d["decisionDateBasis"] = "official_or_authoritative"
    pen = main.get("penalty") or {}
    main["penalty"] = pen
    pen["amountFinal"] = AEPD_CASE["amount"]
    pen["currency"] = "EUR"
    pen["amountVerified"] = True
    pen["verifiedAgainst"] = AEPD_CASE["caseNo"]
    main["caseOutcome"] = "sanction"
    print("ES-A-008 已核实（主记录）")

# ── 重复记录：ES-A-006 ──
dup = by_id.get("AVA-ES-ADP-A-006")
if dup:
    rl = dup.setdefault("recordLevel", {})
    rl["verification"] = {
        "status": "duplicate",
        "checkedAt": TODAY,
        "checkedVia": "与 AVA-ES-ADP-A-008 比对 AEPD 决定与罚款金额",
        **AEPD_CASE,
        "mergedInto": "AVA-ES-ADP-A-008",
        "note": ("与 AVA-ES-ADP-A-008 系同一决定（PS-00431/2024）的重复记录。"
                 "原记金额 €200,000 有误，正确金额为 €10,043,002。"
                 "本记录保留 ID 以维持引用稳定，但不得单独引用。"),
    }
    d = dup.get("dates") or {}
    dup["dates"] = d
    d["decisionDate"] = AEPD_CASE["decisionDate"]
    d["decisionDateBasis"] = "official_or_authoritative"
    pen = dup.get("penalty") or {}
    dup["penalty"] = pen
    pen["amountFinal"] = None
    pen["amountOriginal"] = AEPD_CASE["amount"]
    pen["amountVerified"] = False
    pen["amountBasisText"] = "原记 €200,000 未获证实，已置空；正确金额见 AVA-ES-ADP-A-008"
    dup["status"] = "superseded"
    dup["supersededBy"] = "AVA-ES-ADP-A-008"
    print("ES-A-006 已标记为重复（并入 ES-A-008）")

P.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")

ver = [c for c in cases if (c.get("recordLevel") or {}).get("verification")
       or (c.get("recordLevel") or {}).get("etCrossCheck")]
print(f"\n有核查依据的案例：{len(ver)} / 49")
