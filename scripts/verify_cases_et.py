"""用 Enforcement Tracker 全库（3340 条结构化数据 + 官方文书 URL）
核对我库里的 49 条航空数据保护案例。

核验逻辑：
  1. 同一国家（C 字段）
  2. 主体名严格相似（去符号后前 8 字符互相包含）
  3. 行业优先取 Transportation and Energy
  4. 金额一致者给高置信度

输出：data/case_verification_et.json —— 每条案例的候选 ET 记录与差异
"""

import json
import re
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
ET = json.loads((Path(tempfile.gettempdir()) / "et_cases.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "data/records/cases_aviation_data.json").read_text(encoding="utf-8"))

C2ET = {"ES": "Spain", "GB": "United Kingdom", "IT": "Italy", "FR": "France",
        "BE": "Belgium", "TR": "Turkey", "DE": "Germany", "RO": "Romania",
        "CY": "Cyprus", "SE": "Sweden", "CA": "Canada", "AU": "Australia",
        "NO": "Norway", "NL": "Netherlands", "HU": "Hungary", "CH": "Switzerland",
        "KR": "South Korea", "IN": "India", "SG": "Singapore", "AT": "Austria",
        "PT": "Portugal", "IE": "Ireland", "PL": "Poland", "DK": "Denmark",
        "US": "United States", "CN": "China", "HK": "Hong Kong"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# 库里标题 → 被处罚主体名
ORG_PATTERNS = [
    r"(?:against|v\.)\s+(.{3,56}?)(?:\s+for\s|\s*\(|$)",
    r"(?:Sanction|Fine|Order|Investigation|Notice|Decision|Reprimand|Study)\s*[-–:]\s*(.{3,56}?)(?:\s*\(|$)",
    r"(?:into)\s+(.{3,56}?)(?:\s+for\s|\s*\(|$)",
]


def org_of(rec):
    t = (rec.get("titleEn") or "") + " | " + (rec.get("title") or "")
    for p in ORG_PATTERNS:
        m = re.search(p, t, re.I)
        if m:
            v = m.group(1).strip()
            v = re.sub(r"\s+(for|of|on|in)\s+.*$", "", v, flags=re.I).strip()
            if len(v) >= 3 and v.lower() not in ("airline", "a"):
                return v
    return ""


def amount_of(rec):
    p = rec.get("penalty") or {}
    return p.get("amountFinal") if p.get("amountFinal") is not None else p.get("amountOriginal")


results = []
for rec in CASES:
    jur = rec["jurisdiction"]
    country = C2ET.get(jur, "")
    org = org_of(rec)
    on = norm(org)
    mine = amount_of(rec)

    cands = []
    for r in ET:
        if country and r.get("C") != country:
            continue
        pn = norm(r.get("p"))
        if not pn or len(on) < 4:
            continue
        # 主体名相似：任一方前 8 字符被对方包含
        ok = False
        for k in (8, 7, 6, 5):
            if len(on) >= k and (on[:k] in pn or pn[:k] in on):
                ok = True
                break
        if not ok:
            continue
        et_amt = r.get("f")
        same_amt = (mine is not None and et_amt is not None
                    and abs(float(mine) - float(et_amt)) < max(1.0, float(mine) * 0.01))
        cands.append({
            "etid": r["e"],
            "date": r["d"],
            "amount": et_amt,
            "party": r["p"],
            "sector": r["s"],
            "article": r["r"],
            "violation": r["t"],
            "sourceUrl": r.get("u"),
            "amountMatch": same_amt,
        })

    # 排序：金额相符 > 行业含 transport > 名称更近
    cands.sort(key=lambda c: (not c["amountMatch"],
                              "transport" not in str(c["sector"]).lower(),
                              c["etid"]))
    results.append({
        "recordId": rec["recordId"],
        "jurisdiction": jur,
        "orgInTitle": org,
        "myAmount": mine,
        "myCurrency": (rec.get("penalty") or {}).get("currency"),
        "candidateCount": len(cands),
        "candidates": cands[:5],
    })

matched = [r for r in results if r["candidates"]]
exact = [r for r in results if any(c["amountMatch"] for c in r["candidates"])]

print(f"49 条中：ET 有候选 {len(matched)} 条；金额精确吻合 {len(exact)} 条\n")
print("=== 金额精确吻合（高置信，可直接核验）===")
for r in exact:
    best = next(c for c in r["candidates"] if c["amountMatch"])
    print(f"  {r['recordId']:<18} {r['orgInTitle'][:26]:<28} "
          f"ETid-{best['etid']:<6} {best['date']}  {best['amount']}  vs 我的 {r['myAmount']}")
    print(f"      ET 主体：{str(best['party'])[:60]}")
    print(f"      官链：{str(best['sourceUrl'])[:96]}")

print(f"\n=== 有候选但金额不符（需人工判读）===")
for r in matched:
    if r in exact:
        continue
    print(f"  {r['recordId']:<18} {r['orgInTitle'][:26]:<28} 我的 {r['myAmount']}")
    for c in r["candidates"][:2]:
        print(f"      ETid-{c['etid']:<6} {c['date']}  {str(c['amount']):>10}  {str(c['party'])[:44]}")

print(f"\n=== ET 查不到（{len(results) - len(matched)} 条）===")
for r in results:
    if not r["candidates"]:
        print(f"  {r['recordId']:<18} {r['jurisdiction']:<3} {r['orgInTitle'][:40]}")

(ROOT / "data/case_verification_et.json").write_text(
    json.dumps({"meta": {"source": "enforcementtracker.com 全库",
                         "etTotal": len(ET),
                         "retrievedAt": "2026-10-22",
                         "note": "候选仅表示同名同国记录存在，需下载官方文书确认"},
                "results": results}, ensure_ascii=False, indent=1),
    encoding="utf-8")
print(f"\n→ data/case_verification_et.json")
