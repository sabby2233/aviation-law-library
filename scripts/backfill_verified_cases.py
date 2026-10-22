"""把 Enforcement Tracker 的核验结果回填到案例记录。

原则（不可违反）：
  1. ET 是**聚合索引**，不是一手文书 —— 回填的日期标 dateBasis="aggregator"、
     evidenceLevel="L1"，绝不冒充 L0。
  2. 每条同时写入官方文书 URL（officialSourceUrl），供后续一手核验。
  3. 金额只有在与库内值**精确吻合**时才置为已核验；不符者保留原值并标待判读。
  4. 不改动已有的一手链接；只在缺失时补充。
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\qwesz\WorkBuddy\2026-10-20-22-03-33\aviation-law-library")
CASES_PATH = ROOT / "data/records/cases_aviation_data.json"
VERIFY_PATH = ROOT / "data/case_verification_et.json"

cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
verify = json.loads(VERIFY_PATH.read_text(encoding="utf-8"))
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

by_id = {c["recordId"]: c for c in cases}
filled = confirmed = 0
log = []

for r in verify["results"]:
    rid = r["recordId"]
    rec = by_id.get(rid)
    if not rec or not r["candidates"]:
        continue

    # 选最可信候选：金额吻合者优先
    best = next((c for c in r["candidates"] if c["amountMatch"]), None)
    amount_ok = best is not None
    if best is None:
        best = r["candidates"][0]

    rl = rec.setdefault("recordLevel", {})
    rl["etCrossCheck"] = {
        "etid": best["etid"],
        "partyInEt": best["party"],
        "dateInEt": best["date"],
        "amountInEt": best["amount"],
        "articleInEt": best["article"],
        "violationInEt": best["violation"],
        "officialSourceUrl": best["sourceUrl"],
        "amountMatch": amount_ok,
        "checkedAt": TODAY,
        "checkedVia": "enforcementtracker.com（聚合索引，非一手）",
    }

    # 决定日：以聚合库日期先填，标 L1 并注明依据
    dates = rec.setdefault("dates", {})
    if not dates.get("decisionDate"):
        dates["decisionDate"] = best["date"]
        dates["decisionDateBasis"] = "aggregator"
        filled += 1

    # 官方文书链接：补在 sourceUrl 之外的独立字段，不覆盖原链接
    if best["sourceUrl"]:
        rec["officialSourceUrl"] = best["sourceUrl"]

    # 断言：新增一条 L1 级交叉核对断言
    sid = f"ET-{best['etid']}"
    assert_field = {
        "field": "decision_date_crosscheck",
        "value": best["date"],
        "sourceId": sid,
        "locator": f"Enforcement Tracker ETid-{best['etid']}",
        "evidenceLevel": "L1",
        "verifiedAt": TODAY,
    }
    rec.setdefault("assertions", []).append(assert_field)

    if amount_ok:
        confirmed += 1
        pen = rec.get("penalty") or {}
        pen["amountVerified"] = True
        pen["verifiedAgainst"] = f"ETid-{best['etid']}"
        rec["penalty"] = pen
        log.append((rid, best["etid"], best["date"], best["amount"], "金额吻合"))
    else:
        log.append((rid, best["etid"], best["date"], best["amount"],
                    f"金额待判读（库内 {r['myAmount']}）"))

# 独立产出「官方文书源」清单，供后续一手核验
official = []
for r in verify["results"]:
    for c in r["candidates"]:
        if c["sourceUrl"]:
            official.append({
                "recordId": r["recordId"],
                "etid": c["etid"],
                "dateInEt": c["date"],
                "amountInEt": c["amount"],
                "officialSourceUrl": c["sourceUrl"],
                "amountMatch": c["amountMatch"],
            })

CASES_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=1),
                      encoding="utf-8")
(ROOT / "data" / "official_sources_from_et.json").write_text(
    json.dumps(official, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"回填完成：{confirmed} 条金额吻合并确认，另有 {len(log) - confirmed} 条补了日期待判读")
print(f"官方文书链接：{len(official)} 条 → data/official_sources_from_et.json\n")
print(f"{'recordId':<20}{'ETid':<11}{'ET 日期':<13}{'ET 金额':>12}   状态")
print("-" * 78)
for rid, etid, d, a, s in log:
    print(f"{rid:<20}ETid-{etid:<6}{d:<13}{str(a):>12}   {s}")
