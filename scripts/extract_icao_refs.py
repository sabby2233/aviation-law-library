import collections
import json
import re

# 从已核验的官方文本中抽取 ICAO 引用——
# 编号本身是被 eCFR / EUR-Lex 官方文本确认过的，不是凭记忆写的。
# 这一点很重要：今天在 EUR-Lex 上，正是"凭记忆写编号"导致 27 条候选里
# 17 条指向无关领域。凡是无法从官方文本核验的编号，一律不列。
SOURCES = [
    ("data/records/regulations_us_ecfr.json", "14 CFR (eCFR 现行条文)"),
    ("data/records/regulations_eu_eurlex.json", "EUR-Lex (欧盟官方文本)"),
    ("data/records/regulations_us.json", "US Federal Register"),
]

ANNEX = re.compile(
    r"Annex\s+(\d{1,2})\s*(?:to\s+the\s+Convention)?"
    r"(?:\s*[,\(（]\s*([^)\n]{3,60})\s*[)\)）]?)?", re.I)
DOC = re.compile(
    r"(?:ICAO\s+)?Doc(?:ument)?\.?\s+(\d{3,5}(?:-\d{1,4})?)"
    r"(?:\s*[,\(（]\s*([^)\n]{3,60})\s*[)\)）]?)?", re.I)
PANS = re.compile(
    r"PANS[-\s]?(ATM|AOC|AG|MET|SAD|CAO)\s*(?:Doc(?:ument)?\.?\s*)?(\d{3,5})"
    r"(?:\s*[,\(（]\s*([^)\n]{3,60})\s*[)\)）]?)?", re.I)

hits = {}


def add(kind, key, subject, ctx, src):
    k = f"{kind}|{key}"
    h = hits.setdefault(k, {
        "kind": kind, "number": key, "subjects": [], "sources": set(),
        "contexts": [], "count": 0,
    })
    h["count"] += 1
    h["sources"].add(src)
    if subject and subject not in h["subjects"] and len(h["subjects"]) < 4:
        h["subjects"].append(subject.strip(" ,;()（）"))
    if ctx not in h["contexts"] and len(h["contexts"]) < 3:
        h["contexts"].append(ctx)


for path, label in SOURCES:
    try:
        data = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        continue
    for rec in data:
        blob = " ".join([
            rec.get("title") or "", rec.get("summary") or "",
            " ".join((a.get("value") or "") for a in (rec.get("assertions") or [])),
        ])
        for m in ANNEX.finditer(blob):
            if len(m.group(1)) <= 2:
                add("附件", m.group(1), m.group(2), m.group(0)[:120], label)
        for m in DOC.finditer(blob):
            add("文件", m.group(1), m.group(2), m.group(0)[:120], label)
        for m in PANS.finditer(blob):
            add("PANS", f"{m.group(1)} {m.group(2)}", m.group(3),
                m.group(0)[:120], label)

# PANS-ATM Doc 8610 等若只以 "8610" 形式出现会被 Doc 规则误捕，
# 这里剔除明显不是 ICAO 文件号的（ICAO Doc 号为 3~5 位且不与常见法规号混淆）
# 明显不是 ICAO 文件号的误捕：FR 里的日期片段（2024-05）
SUSPECT = {"886", "676", "3", "6", "2024-05", "2025-05"}
out = []
for h in hits.values():
    if h["kind"] == "文件" and h["number"] in SUSPECT:
        continue
    out.append(h)
out.sort(key=lambda h: (h["kind"], h["number"]))

print("=== 从已核验官方文本抽出的 ICAO 编号 ===")
print("编号本身出现在 eCFR / EUR-Lex / FR 的官方文本里，因此已被官方确认。")
print()
cur = None
for h in out:
    if h["kind"] != cur:
        cur = h["kind"]
        print(f"  ── {cur} ──")
    subj = " / ".join(h["subjects"]) or "（原文未带主题名）"
    print(f"    {h['number']:<14} {subj[:52]}")
    print(f"        出处: {', '.join(sorted(h['sources']))}  次数 {h['count']}")
    print(f"        原文: …{h['contexts'][0]}…")
print()
print("合计:", len(out), "个编号")
clean = [{**h, "sources": sorted(h["sources"])} for h in out]
json.dump(clean, open("data/icao_refs_extracted.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("→ data/icao_refs_extracted.json")