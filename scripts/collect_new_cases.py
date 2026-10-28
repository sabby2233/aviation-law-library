#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_new_cases.py — 从监管机构信息流增量发现「航空数据保护」新案

为什么要单独一个脚本：
    仓库原有的 collect_aviation_data_cases.py 是**整表重建**（从上游 cases.json 全量导入），
    跑一次就会覆盖本地已核验的 decisionDate / correction / dateGap。
    data-quality.yml 当初也正是因此删掉了自动采集任务。
    本脚本的定位相反：**只追加新记录，绝不改动任何已存在的 recordId**。

入库口径（用户 2026-10-29 明确授权）：
    · 先用二手线索入库，标 sourceTier = L3、verificationStatus = pending；
    · **新闻发布日期不写入 decisionDate**——新闻日不是决定日，这个区别正是当年
      上游数据被判为不可靠的原因。新闻日单独存 dates.newsDate；
    · 每条都写明「待回官方决定书核对」，让读者一眼看出这条还没核。

监测源：RSS（本机实测可达的才列在这里；FTC、ICO、Datatilsynet、UODO、EDÖB 的
        RSS 均已改版或下线，实测 404/超时，故不列）

用法：
    python scripts/collect_new_cases.py            # 试跑，只报告不写盘
    python scripts/collect_new_cases.py --apply    # 追加写入
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id          # noqa: E402
from jsonio import save_json           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "records" / "cases_aviation_data.json"

# 监测源：只放实测能取到 <item> 的
FEEDS = [
    {"name": "EDPB", "jurisdiction": "EU",
     "url": "https://www.edpb.europa.eu/rss.xml",
     "note": "欧洲数据保护委员会新闻流（含成员国执法消息）"},
    {"name": "CNIL", "jurisdiction": "FR",
     "url": "https://www.cnil.fr/fr/rss.xml",
     "note": "法国数据保护局新闻流（含制裁与处罚公告）"},
]

# 航空相关关键词。含航司名与多语种通用词——只靠 "air" 会把 "affair" 也捞进来。
AIRLINES = [
    "ryanair", "lufthansa", "scandinavian airlines", "sas ", "klm", "air france",
    "tap air", "lot polish", "cathay", "emirates", "qatar airways", "easyjet",
    "wizz", "iberia", "british airways", "air canada", "united airlines",
    "american airlines", "delta air", "southwest airlines", "norwegian air",
    "austrian airlines", "swiss international", "brussels airlines", "vueling",
    "volotea", "air india", "korean air", "asiana", "singapore airlines",
    "flightaware", "sabre", "amadeus", "travelport", "boeing", "airbus",
    "schiphol", "frankfurt airport", "heathrow", "copenhagen airports",
]
GENERIC = [
    r"airline", r"airlines", r"aviation", r"aircraft", r"aeroplane", r"airplane",
    r"airport", r"flight", r"flights", r"compagnie a[ée]rienne", r"fluggesellschaft",
    r"aerol[íi]nea", r"companhia a[ée]rea", r"havayolu", r"hava yolu", r"lotnicz",
    r"航空", r"航空公司",
]
KW = re.compile("|".join([re.escape(a) for a in AIRLINES] + GENERIC), re.I)

# 机构名 → 法域。只在标题**明确点名**某国监管机构时才改判，
# 否则沿用信息流自身的法域（EDPB 是全欧流，不知道具体成员国就记 EU，不猜）。
AUTHORITY_JUR = [
    ("garante", "IT"), ("italian dpa", "IT"), ("italian data protection", "IT"),
    ("cnil", "FR"), ("aepd", "ES"), ("spanish", "ES"),
    ("datatilsynet", "NO"), ("norwegian", "NO"),
    ("autoriteit persoonsgegevens", "NL"), ("dutch dpa", "NL"),
    ("ico", "GB"), ("information commissioner", "GB"), ("uk ", "GB"),
    ("bfdi", "DE"), ("german", "DE"),
    ("dsb", "AT"), ("austrian", "AT"),
    ("cnpd", "PT"), ("portuguese", "PT"),
    ("dpc", "IE"), ("irish", "IE"),
    ("uodo", "PL"), ("polish", "PL"),
    ("nAIH", "HU"), ("hungarian", "HU"),
    ("edöb", "CH"), ("fdpic", "CH"), ("swiss", "CH"),
    ("pipc", "KR"), ("korean", "KR"),
    ("kvkk", "TR"), ("turkish", "TR"),
    ("imy", "SE"), ("swedish", "SE"),
    ("datatilsynet.dk", "DK"), ("danish", "DK"),
    ("ap ", "NL"), ("dpbi", "IN"), ("india", "IN"),
]


def jur_of(title, fallback):
    t = (title or "").lower()
    for k, v in AUTHORITY_JUR:
        if k in t:
            return v
    return fallback


def fetch(url, timeout=35):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; aviation-law-library/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_feed(raw):
    """解析 RSS/Atom。返回 [(title, link, date, desc)]。"""
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    for item in root.iter():
        tag = item.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue
        d = {}
        for ch in item:
            ct = ch.tag.split("}")[-1].lower()
            if ct == "link":
                d["link"] = (ch.get("href") or (ch.text or "")).strip()
            elif ct in ("title", "summary", "content", "description"):
                d.setdefault(ct, (ch.text or "").strip())
            elif ct in ("pubdate", "published", "updated", "date"):
                d.setdefault("date", (ch.text or "").strip())
        if d.get("link"):
            out.append(d)
    return out


def to_date(raw):
    if not raw:
        return None
    for fn in (parsedate_to_datetime,
               lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))):
        try:
            return fn(raw).date().isoformat()
        except Exception:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    return m.group(0) if m else None


def clean(s, n=220):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


def slug_of(url):
    """从 URL 取一个稳定短标识：末段非数字部分 + 短哈希，保证幂等重跑不产生新 ID。"""
    import hashlib
    tail = [x for x in url.rstrip("/").split("/") if x][-1]
    tail = re.sub(r"[^A-Za-z0-9]", "-", tail).strip("-").upper()[:14] or "LEAD"
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:4].upper()
    return f"{tail}-{h}"


def main():
    apply = "--apply" in sys.argv
    data = json.loads(CASES.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    have_ids = {r["recordId"] for r in recs}
    have_urls = {(r.get("sourceUrl") or "").rstrip("/").lower() for r in recs}

    added, seen_feed = [], []
    for feed in FEEDS:
        try:
            raw = fetch(feed["url"])
        except Exception as e:
            print(f"  ✗ {feed['name']}: 取不到（{type(e).__name__}: {str(e)[:50]}）")
            continue
        items = parse_feed(raw)
        hits = []
        for it in items:
            blob = f'{it.get("title","")} {it.get("summary","")} {it.get("description","")}'
            if not KW.search(blob):
                continue
            url = it["link"].rstrip("/")
            if url.lower() in have_urls:
                continue
            title_raw = clean(it.get("title"), 160) or "(无标题)"
            jur = jur_of(title_raw, feed["jurisdiction"])
            rid = make_id(jur, "ADP", slug_of(url).replace("-", ""))
            if rid in have_ids:
                continue
            news_date = to_date(it.get("date"))
            title = title_raw
            desc = clean(it.get("summary") or it.get("description"), 300)
            rec = {
                "recordId": rid,
                "recordType": "case",
                "title": title,
                "summary": (
                    f"[待核线索] 该条来自 {feed['name']} 信息流（{news_date or '日期未载'}），"
                    f"标题与摘要为信息流原文，**尚未回官方决定书核对**。"
                    + (f" 原文摘要：{desc}" if desc else "")
                ),
                "jurisdiction": jur,
                "topics": ["GDPR", "airline", "feed-lead"],
                # 用词表内的 adopted：信息流若称「已罚款」，即决定已作出；
                # 「是否真作过、金额是否如此」由 verificationStatus=pending 与 L3 另行表达。
                "status": "adopted",
                "citationString": f"{feed['name']} 信息流条目（待核）",
                "sourceUrl": url,
                "dates": {
                    "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    # 新闻日绝不冒充决定日
                    "newsDate": news_date,
                },
                "caseOutcome": "unknown",
                "sanctionsVerified": False,
                "recordLevel": {
                    "sourceTier": "L3",
                    "verificationStatus": "pending",
                    "channel": f"{feed['name']} RSS 信息流",
                    "note": "自动发现线索，未经人工核验；决定日、金额、处罚性质均须回官方文书确认",
                    "dateGap": {
                        "annotatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "reason": "lead-from-feed",
                        "detail": f"由 {feed['name']} 信息流自动发现，尚未定位官方决定书",
                        "nextStep": "按机构站内检索该企业名，取决定书编号与落款日",
                    },
                },
                "assertions": [{
                    "field": "feed_title",
                    "value": title,
                    "sourceId": f"FEED-{feed['name']}",
                    "locator": f"{feed['name']} RSS，条目链接 {url}",
                    "evidenceLevel": "L3",
                    "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                }],
            }
            hits.append(rec)
            have_ids.add(rid)
            have_urls.add(url.lower())
        seen_feed.append((feed["name"], len(items), len(hits)))
        added.extend(hits)

    print(f"\n监测源状况：")
    for name, total, hit in seen_feed:
        print(f"  {name}: 抓取 {total} 条，航空相关新增 {hit} 条")
    print(f"\n合计拟新增 {len(added)} 条")

    for r in added:
        print(f"  + {r['recordId']:34s} [{r['dates'].get('newsDate')}] {r['title'][:60]}")

    if not added:
        print("\n无新增，未改动任何记录。")
        return
    if not apply:
        print("\n（试跑，未写盘；加 --apply 写入）")
        return

    recs.extend(added)
    save_json(CASES, data)
    print(f"\n已追加 {len(added)} 条 → {CASES.relative_to(ROOT)}（未改动任何已有记录）")


if __name__ == "__main__":
    main()
