"""第二轮 ET 匹配：修正主体名提取，最大化可核验条数。

第一轮的 bug：标题形如 "AEPD €10M Fine against Aena for Biometric Boarding System"，
    提取到的主体名是 "Aena for Biometric Boarding System"，与 ET 的
    "Aena, S.M.E., S.A." 对不上 —— 因为 "for ..." 后缀没剥掉。
修法：先按 " for " / " over " / " regarding " 切掉描述部分，再匹配；
    并允许"取前 N 个单词"作为辅助候选（如 "Air France"、"British Airways"）。
"""

import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\qwesz\WorkBuddy\2026-10-20-22-03-33\aviation-law-library")
ET = json.loads(Path(r"C:\Users\qwesz\AppData\Local\Temp\et_cases.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "data/records/cases_aviation_data.json").read_text(encoding="utf-8"))

C2ET = {"ES": "Spain", "GB": "United Kingdom", "IT": "Italy", "FR": "France",
        "BE": "Belgium", "TR": "Turkey", "DE": "Germany", "RO": "Romania",
        "CY": "Cyprus", "SE": "Sweden", "CA": "Canada", "AU": "Australia",
        "NO": "Norway", "NL": "Netherlands", "HU": "Hungary", "CH": "Switzerland",
        "KR": "South Korea", "IN": "India", "SG": "Singapore", "AT": "Austria",
        "PT": "Portugal", "IE": "Ireland", "PL": "Poland", "DK": "Denmark",
        "US": "United States", "CN": "China", "HK": "Hong Kong",
        "NO2": "Norway"}
# ET 里荷兰写作 The Netherlands
C2ET["NL"] = "The Netherlands"

STOP_TAIL = re.compile(
    r"\s+(?:for|over|regarding|on|in respect of|concerning|after|following|"
    r"due to|because)\s+.*$", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def org_candidates(rec):
    t = (rec.get("titleEn") or "") + " || " + (rec.get("title") or "")
    outs = []
    for pat in (r"(?:against|v\.)\s+(.{3,80})",
                r"[-–—:]\s*(?:against\s+)?(.{3,80})",
                r"(?:into|for)\s+(.{3,80})"):
        for m in re.finditer(pat, t, re.I):
            raw = m.group(1).strip()
            raw = raw.split("(")[0].strip()
            raw = STOP_TAIL.sub("", raw).strip(" ,.;:-")
            if len(raw) >= 3:
                outs.append(raw)
                # 取前 2–3 个词作辅助候选（"Air France"、"British Airways"）
                words = raw.split()
                for k in (2, 3):
                    if len(words) >= k:
                        outs.append(" ".join(words[:k]))
    return [o for o in dict.fromkeys(outs) if len(o) >= 3]


results = []
for rec in CASES:
    jur = rec["jurisdiction"]
    country = C2ET.get(jur, "")
    mine = (rec.get("penalty") or {}).get("amountFinal")
    if mine is None:
        mine = (rec.get("penalty") or {}).get("amountOriginal")

    cands = []
    for r in ET:
        et_country = r.get("C")
        pn = norm(r.get("p"))
        if not pn:
            continue
        for o in org_candidates(rec):
            on = norm(o)
            if len(on) < 5:
                continue
            hit = False
            for k in (9, 8, 7, 6, 5):
                if len(on) >= k and (on[:k] in pn or pn[:k] in on):
                    hit = True
                    break
            if not hit:
                continue
            same_country = (et_country == country)
            et_amt = r.get("f")
            same_amt = (mine is not None and et_amt is not None
                        and abs(float(mine) - float(et_amt)) < max(1.0, float(mine) * 0.01))
            cands.append({
                "etid": r["e"], "country": et_country, "date": r["d"],
                "amount": et_amt, "party": r["p"], "sector": r["s"],
                "article": r["r"], "violation": r["t"], "url": r.get("u"),
                "sameCountry": same_country, "amountMatch": same_amt,
                "matchedName": o,
            })
            break

    # 去重（同一 ETid 可能被多个候选名命中）
    seen = set()
    uniq = []
    for c in cands:
        if c["etid"] in seen:
            continue
        seen.add(c["etid"])
        uniq.append(c)

    uniq.sort(key=lambda c: (not c["amountMatch"], not c["sameCountry"],
                             "transport" not in str(c["sector"]).lower(), c["etid"]))
    results.append({
        "recordId": rec["recordId"], "jurisdiction": jur,
        "myAmount": mine,
        "myCurrency": (rec.get("penalty") or {}).get("currency"),
        "candidates": uniq[:6],
    })

hit = [r for r in results if r["candidates"]]
exact = [r for r in results if any(c["amountMatch"] for c in r["candidates"])]
print(f"第二轮：有候选 {len(hit)} / {len(results)}；金额吻合 {len(exact)}\n")
print("=== 金额精确吻合 ===")
for r in exact:
    b = next(c for c in r["candidates"] if c["amountMatch"])
    print(f"  {r['recordId']:<18} ETid-{b['etid']:<6} {b['date']}  {b['amount']:>12}  {str(b['party'])[:40]}")
print("\n=== 有候选但金额不符 ===")
for r in hit:
    if r in exact:
        continue
    print(f"  {r['recordId']:<18} 我的 {str(r['myAmount']):>12}")
    for c in r["candidates"][:2]:
        print(f"      ETid-{c['etid']:<6} {str(c['country'])[:12]:<14} {c['date']}  "
              f"{str(c['amount']):>12}  {str(c['party'])[:36]}")
print(f"\n=== 仍无候选 {len(results)-len(hit)} 条 ===")
for r in results:
    if not r["candidates"]:
        print(f"  {r['recordId']:<18} {r['jurisdiction']}")

(ROOT / "data" / "case_verification_et_r2.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
