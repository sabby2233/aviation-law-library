"""第三轮核查：按渠道分组，逐条找权威依据。

渠道分工（不同法域走不同官方库，不用一个库硬套）：
  CJEU 判决   → curia.europa.eu（ECLI 为标识）
  美国 FTC    → ftc.gov 案卷号
  美国法院    → CourtListener（RECAP）
  中国        → 裁判文书网 / 最高法典型案例
  GDPR 罚款   → Enforcement Tracker 已做，本轮补"查不到"的记录
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url, accept="application/json", timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def courtlistener(q, court=None):
    params = {"q": q, "type": "o", "order_by": "score desc"}
    if court:
        params["court"] = court
    url = ("https://www.courtlistener.com/api/rest/v4/search/?" +
           urllib.parse.urlencode(params))
    d = json.loads(get(url))
    out = []
    for r in (d.get("results") or [])[:5]:
        out.append({
            "caseName": r.get("caseName") or r.get("case_name"),
            "court": r.get("court"),
            "dateFiled": r.get("dateFiled") or r.get("date_filed"),
            "docketNumber": r.get("docketNumber") or r.get("docket_number"),
            "citation": r.get("citation"),
            "url": "https://www.courtlistener.com" + (r.get("absolute_url") or ""),
        })
    return d.get("count", 0), out


QUERIES = [
    ("AVA-US-ADP-C-001", "United Airlines biometric privacy BIPA class action", "bipa"),
    ("AVA-US-ADP-C-002", "FlightAware data breach class action", None),
    ("AVA-US-ADP-C-003", "JetBlue surveillance pricing class action", None),
]

print("=== 美国法院案件（CourtListener）===")
res = {}
for rid, q, kw in QUERIES:
    try:
        total, hits = courtlistener(q)
        print(f"\n{rid}  查询「{q}」→ 总数 {total}")
        for h in hits[:3]:
            print(f"    {str(h['caseName'])[:62]}")
            print(f"      {h['court']} | {h['dateFiled']} | {h['docketNumber']} | {h['citation']}")
            print(f"      {h['url'][:96]}")
        res[rid] = {"query": q, "total": total, "hits": hits}
    except Exception as e:  # noqa: BLE001
        print(f"{rid} 失败: {type(e).__name__}: {str(e)[:80]}")
        res[rid] = {"query": q, "error": str(e)[:100]}
    time.sleep(0.8)

(Path(tempfile.gettempdir()) / "cl_results.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("\n→ cl_results.json")
