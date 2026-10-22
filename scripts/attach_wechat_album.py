"""把微信公众号相册里的 ICAO 附件中文图文版挂到对应记录上。

定位与边界：
  - 该相册是**第三方公众号**，不是 ICAO 官方源 → 标 L3（线索级），不标 L0/L1。
  - 只挂「标题 + 链接」，**不抓取、不转录正文图片**——图片所载 SARPs 条文
    属 ICAO 保留版权材料。
  - **补上 Annex 19**：官方 booklet（2005-06）不含该附件，相册里有，
    但相册不是官方源，故 Annex 19 记录的标题标注「编号与名称来自相册文章标题，
    待以 ICAO 官网核验」。
  - **补分卷**：相册的 Annex 16 有四卷（III 飞机 CO2、IV CORSIA），
    比 2005 booklet 的两卷更新；同样只作线索记录。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALBUM = ROOT / "data" / "icao_wechat_album.json"
ICAO = ROOT / "data/records/icao_documents.json"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

album = json.loads(ALBUM.read_text(encoding="utf-8"))
arts = album["articles"]
recs = json.loads(ICAO.read_text(encoding="utf-8"))
by_id = {r["recordId"]: r for r in recs}

# ── 1. 按附件号归并相册文章 ──
groups = {}
for a in arts:
    n = a.get("annexNo")
    if n:
        groups.setdefault(n, []).append(a)

attached = 0
for n, items in sorted(groups.items()):
    rid = f"AVA-ICAO-STD-ANNEX-{n}"
    rec = by_id.get(rid)
    if rec is None:
        continue  # Annex 19 等另行处理
    rec.setdefault("recordLevel", {})["wechatAlbum"] = {
        "albumTitle": album["meta"]["albumTitle"],
        "platform": "微信公众号相册",
        "evidenceLevel": "L3",
        "note": ("第三方公众号图文版，正文为图片，仅作检索线索；"
                 "SARPs 条文以 ICAO 官方文件为准，本库不转录图片内容"),
        "articles": [{"title": i["title"], "url": i["url"], "date": i["date"]}
                     for i in items],
    }
    attached += 1

    # 追加一条 L3 断言：证明「中文图文版存在」这件事，而非证明条文内容
    sid = f"WXA-ANNEX-{n}"
    rec.setdefault("assertions", []).append({
        "field": "chinese_illustrated_version",
        "value": f"微信公众号相册《{album['meta']['albumTitle']}》收录 {len(items)} 篇",
        "sourceId": sid,
        "locator": items[0]["title"][:60],
        "evidenceLevel": "L3",
        "verifiedAt": TODAY,
    })

print(f"已挂中文图文版入口：{attached} 条附件记录")

# ── 2. 补 Annex 19（booklet 不含）──
if 19 in groups and "AVA-ICAO-STD-ANNEX-19" not in by_id:
    items = groups[19]
    new = {
        "recordId": "AVA-ICAO-STD-ANNEX-19",
        "recordType": "standard",
        "title": "Safety Management",
        "titleZh": "安全管理",
        "jurisdiction": "ICAO",
        "topics": ["safety-management", "sms"],
        "status": "effective",
        "citationString": "Annex 19",
        "sourceUrl": "https://www.icao.int/safety/SMS/Pages/default.aspx",
        "summary": ("《国际民用航空公约》附件 19《安全管理》。"
                    "本库对其编号与名称的采集来源为第三方公众号图文版，"
                    "官方英文名 Safety Management 待以 ICAO 官网核验。"),
        "recordLevel": {
            "icaoNumber": "Annex 19",
            "icaoKind": "annex",
            "titleZh": "安全管理",
            "language": "en",
            "sourceTier": "L3",
            "verificationStatus": "pending",
            "note": ("booklet（2005-06）不含本附件（2006 年才制定）；"
                     "编号与名称取自微信公众号相册文章标题，非 ICAO 官方出处，"
                     "故标 L3 待核验。仅存元数据与引注，不存正文。"),
            "wechatAlbum": {
                "albumTitle": album["meta"]["albumTitle"],
                "platform": "微信公众号相册",
                "evidenceLevel": "L3",
                "articles": [{"title": i["title"], "url": i["url"],
                              "date": i["date"]} for i in items],
            },
        },
        "dates": {"retrievedAt": TODAY},
        "assertions": [{
            "field": "icao_annex_number",
            "value": "Annex 19",
            "sourceId": "WXA-ANNEX-19",
            "locator": items[0]["title"][:60],
            "evidenceLevel": "L3",
            "verifiedAt": TODAY,
        }],
        "revisionLog": [],
    }
    recs.append(new)
    print("已新增 Annex 19（标 L3 待核验）")

# ── 3. 分卷线索：相册的分卷比 booklet 新 ──
for n, items in groups.items():
    subs = [i["title"] for i in items if "卷" in i["title"] or "部分" in i["title"]]
    if len(subs) > 1:
        rid = f"AVA-ICAO-STD-ANNEX-{n}"
        if rid in by_id:
            by_id[rid]["recordLevel"]["volumesFromAlbum"] = subs

ICAO.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nICAO 记录数：{len(recs)} → {ICAO.name}")
for r in recs:
    w = (r.get("recordLevel") or {}).get("wechatAlbum")
    vols = (r.get("recordLevel") or {}).get("volumesFromAlbum")
    print(f"  {r['recordId']:<26} {r.get('titleZh',''):<12} "
          f"{'图文版 ✓' if w else '—':<8} {len(vols) if vols else ''}")
