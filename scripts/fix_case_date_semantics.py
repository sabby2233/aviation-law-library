"""修正案例日期字段的语义污染。

背景：从旧仓库导入时，原 `date` 字段被直接当成 publicationDate（公布日）。
但该字段的真实含义是"原数据所记的日期"，口径不明——实测它与从聚合库取得的
决定日冲突（决定日 2019-10-01 晚于所谓「公布日」2019-01-10，不可能）。

按本库规矩「六个时间字段互不混用」，口径不明者不得占用任何一个正式字段，
故迁移到 dateAsReportedInSource，并显式标注 originalDateUnreliable。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\qwesz\WorkBuddy\2026-10-20-22-03-33\aviation-law-library")
P = ROOT / "data/records/cases_aviation_data.json"
cases = json.loads(P.read_text(encoding="utf-8"))
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

moved = 0
for r in cases:
    d = r.setdefault("dates", {})
    pub = d.get("publicationDate")
    if not pub:
        continue
    d["dateAsReportedInSource"] = pub
    del d["publicationDate"]
    rl = r.setdefault("recordLevel", {})
    rl["originalDateUnreliable"] = True
    rl["originalDateNote"] = (
        "旧仓库 date 字段口径不明（疑似媒体报道日），已改存 dateAsReportedInSource；"
        "决定日以官方文书或聚合库取得，见 dates.decisionDateBasis")
    moved += 1

P.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"已迁移 {moved} 条案例的 publicationDate → dateAsReportedInSource")

# 复核：还有多少案例缺决定日
no_dec = [r["recordId"] for r in cases if not r["dates"].get("decisionDate")]
print(f"仍缺决定日：{len(no_dec)} 条")
print(f"有决定日：{len(cases) - len(no_dec)} 条（其中来自聚合库 "
      f"{sum(1 for r in cases if r['dates'].get('decisionDateBasis') == 'aggregator')} 条）")
