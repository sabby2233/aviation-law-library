"""区分「已决处罚」与「监管调查」——这是本批案例最重要的数据治理修正。

问题：49 条里有 13 条标题是「XX DPA Investigation into ...」，
它们没有处罚决定、没有金额、没有决定日，本质是监管动态而非执法案例。
若与已决处罚混在一起，读者会误以为"这些公司都被罚过"，
而实际情况可能只是"监管机构在查、尚无结论"。

处置：
  1. 新增 caseOutcome 字段：sanction（已决处罚）/ investigation（调查中）/ other
  2. 新增 sanctionsVerified 字段：是否已由官方文书或聚合库核实金额
  3. 调查类不参与「一手来源占比」的核心字段统计，也不得作为判例引用
  4. 不改 status 字段——避免破坏已有状态机断言
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\qwesz\WorkBuddy\2026-10-20-22-03-33\aviation-law-library")
P = ROOT / "data/records/cases_aviation_data.json"
cases = json.loads(P.read_text(encoding="utf-8"))
ver = {x["recordId"]: x for x in
       json.loads((ROOT / "data/case_verification_et.json").read_text(encoding="utf-8"))["results"]}
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

DECIDED = ("fine", "sanction", "decision", "order", "reprimand", "judgment",
           "ruling", "settlement", "penalty")
PENDING = ("investigation", "notice", "complaint", "study", "inquiry", "probe")

stat = {"sanction": 0, "investigation": 0, "other": 0}
verified = 0

for c in cases:
    rid = c["recordId"]
    t = (c.get("titleEn") or c.get("title") or "").lower()
    if any(k in t for k in DECIDED):
        outcome = "sanction"
    elif any(k in t for k in PENDING):
        outcome = "investigation"
    else:
        outcome = "other"

    c["caseOutcome"] = outcome
    c["caseOutcomeNote"] = {
        "sanction": "已有处罚/判决/命令作出，可作为执法案例引用",
        "investigation": "监管机构调查或程序进行中，**尚无处罚决定**，"
                         "不得作为已决执法案例或判例引用",
        "other": "性质待判读（可能为研究报告、合规提示等），不得作为执法案例引用",
    }[outcome]

    et = ver.get(rid, {})
    ok = any(x.get("amountMatch") for x in et.get("candidates", []))
    c["sanctionsVerified"] = bool(ok)
    if ok:
        verified += 1

    rl = c.setdefault("recordLevel", {})
    rl["caseOutcome"] = outcome

    stat[outcome] += 1

    # 调查类：把 evidenceLevel 从 L1 降到 L3（线索级），因为连"存在处罚"都未证实
    if outcome != "sanction":
        for a in c.get("assertions") or []:
            if a.get("evidenceLevel") in ("L0", "L1"):
                a["evidenceLevel"] = "L3"
        rl["sourceTier"] = "L3"

P.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"分类完成（{len(cases)} 条）：")
for k, n in stat.items():
    print(f"  {k:<14} {n} 条")
print(f"\n金额已核实（与聚合库精确吻合）：{verified} 条")
print(f"不可作为执法案例引用：{stat['investigation'] + stat['other']} 条")
