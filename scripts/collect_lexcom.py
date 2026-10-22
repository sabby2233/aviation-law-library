#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_lexcom.py — 司法部「法通」网涉外法律资源采集

为什么需要这个源：
    ① 中国法域此前只有 CCAR 部门规章（民航局 TRS），缺上位法。
       法通网收录我国涉外法律/行政法规 1919 部，其中《民用航空法》
       《无人驾驶航空器飞行管理暂行条例》《民用航空器适航管理条例》
       均在其中——这是中文读者最常引的母法。
    ② 域外法律中文译本 974 部，覆盖 187 个国家（译本源为商务部全球法规网
       policy.mofcom.gov.cn）。这是本资料库目前唯一的中文域外法律层，
       eVTOLHOT 之类站点完全没有。

与已有源的分工（不重复）：
    民航局 TRS   → 部门规章/规范性文件（CCAR 部级）
    法通网       → 法律/行政法规/涉外规章（上位法）+ 域外法律中文译本
    两者是上下位关系，不是重复收录。

技术要点（实测得出）：
    1. 前端为 Vue SPA，接口基址在 bundle 里：axios create({baseURL:"/api"})
    2. 可用端点：
       GET /api/law/chinese/page?current=N&size=100[&keyword=&searchType=&lawCategory=&timeliness=&日期区间]
       GET /api/law/chinese/query?id=<id>          详情：含 replacedBy / files / content
       GET /api/law/foreign/translation/page?current=N&size=100[&continent=&countryCode=]
       GET /api/law/foreign/resource/tree          国家-洲树
       GET /api/law/foreign/translation/query?id=<id>
    3. size 上限 100；超限返回空
    4. 域外译本页**没有 keyword 参数**，只能按国家/洲浏览 → 全量拉取后本地筛选
    5. 字典接口 /api/dict/list?dictCode= 的编码未公开 → 效力位阶与时效性
       由「发布机关 + 数值」反推，并标注为推断值，不冒充官方字典

抓取礼仪：单线程、请求间隔 1.5 秒、明确 UA 标注研究用途；只存元数据与官方
链接，不下载 PDF 全文（版权保守，符合本站"不转载原文"的原则）。

输出：data/records/regulations_cn_lexcom.json
      data/records/foreign_translation_lexcom.json
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://lexcom.12348.gov.cn/api"
UA = "aviation-law-library/1.0 (research; contact: via GitHub repo)"
REQUEST_DELAY = 1.5
PAGE_SIZE = 100

# ── 航空主题关键词（用于筛选） ──────────────────────────────
CN_KEYWORDS = [
    "航空", "航空器", "航空运输", "民航", "飞机", "航线", "航空港",
    "机场", "适航", "飞行", "无人机", "无人驾驶", "空域", "签派",
    "飞行员", "机长", "空中交通", "航权", "双边航空", "开放天空",
    "芝加哥公约", "国际民航组织",
]

# 域外译本：实测 974 条中**航空法相关为 0**（主题分布为投资贸易 271 /
# 环境资源 106 / 劳动社保 47 / 行政宪法 25 / 数据网络 22 / 刑事 9 / 教育 4），
# 该库是"走出去"导向的对外投资与贸易法库，不是航空法库。
# 因此本项目只收录与航空数据治理交叉的「数据与网络安全」类，
# 其余不入库——如实反映源库覆盖状况，不以"收录数"充数。
FOREIGN_KEYWORDS = [
    "个人数据", "数据保护", "隐私", "网络安全", "网络犯罪",
    "电信法", "电子信息", "信息保护",
]

# 域外译本源库的主题普查结果（用于报告与留痕，不参与筛选）
FOREIGN_SOURCE_PROFILE = {
    "total": 974,
    "aviation_related": 0,
    "note": "实测全量扫描：974 条译本中无一条以航空法为规范对象；"
            "本库收录的是与航空数据治理交叉的数据与网络安全类",
}

# lawCategory 数值 → 效力位阶（由「发布机关 × 数值」归纳，非官方字典）
CATEGORY_MAP = {
    1: ("法律", "全国人大常委会"),
    2: ("行政法规", "国务院"),
    3: ("法律", "全国人民代表大会及其常委会"),
    4: ("行政法规", "国务院"),
}

# timeliness 数值 → 时效性
TIMELINESS_MAP = {
    1: "尚未施行",
    2: "现行有效",
    3: "已被修改",
    4: "废止或失效",
}

# 版本状态（域外译本用 versionStatus）
FOREIGN_VERSION_MAP = {
    1: "现行",
    2: "已修订",
    3: "历史版本",
}


def fetch_json(path, params=None, retries=3):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"抓取失败 {url}: {last}")


def paged(path, params=None, key="records"):
    """遍历分页接口，产出全部记录。"""
    out = []
    page = 1
    total = None
    while True:
        p = dict(params or {})
        p["current"] = page
        p["size"] = PAGE_SIZE
        d = fetch_json(path, p)
        data = d.get("data") or {}
        recs = data.get(key) or []
        if total is None:
            total = data.get("total")
            try:
                total = int(total)
            except (TypeError, ValueError):
                total = None
            print(f"  源库总量：{total}")
        if not recs:
            break
        out.extend(recs)
        if total is not None and len(out) >= total:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return out, total


def hit_keywords(text, keywords):
    t = str(text or "")
    return [k for k in keywords if k in t]


def topics_for(title, categories, extra=()):
    """由标题与效力位阶推导主题标签。"""
    t = str(title or "")
    topics = []
    if any(k in t for k in ("无人机", "无人驾驶", "低空")):
        topics.append("uav")
    if "适航" in t or "航空器" in t:
        topics.append("airworthiness")
    if "运输" in t or "机场" in t or "航空港" in t or "航线" in t:
        topics.append("air-transport")
    if "飞行" in t or "空域" in t or "签派" in t:
        topics.append("flight-ops")
    if "数据" in t or "个人信息" in t or "网络安全" in t:
        topics.append("data-protection")
    for c in categories:
        topics.append(c)
    for e in extra:
        if e not in topics:
            topics.append(e)
    return sorted(set(topics))


def collect_cn():
    """我国涉外法律、行政法规、涉外规章。"""
    print("【一】法通网 · 我国涉外法律法规")
    raw, total = paged("/law/chinese/page")
    print(f"  拉取 {len(raw)} 条，筛选航空相关…")

    records = []
    for r in raw:
        name = r.get("lawName") or ""
        hits = hit_keywords(name, CN_KEYWORDS)
        if not hits:
            continue
        cat = r.get("lawCategory")
        cat_name, cat_dept = CATEGORY_MAP.get(cat, (None, None))
        tl = r.get("timeliness")
        tl_name = TIMELINESS_MAP.get(tl)

        # 文号：法通网 list 端点不返回文号，详情端点才有 → 留空待补
        file_url = r.get("fileUrl") or ""
        detail = None
        rid = make_id("CN", "LAW", r.get("id") or name[:20], fallback=name)

        records.append({
            "recordId": rid,
            "recordType": "legislation",
            "title": name,
            "titleEn": r.get("lawNameEn") or None,
            "summary": None,
            "jurisdiction": "CN",
            "topics": topics_for(name, ["cn-foreign-related"],
                                extra=[c for c in [cat_name] if c]),
            "status": _status_of(tl),
            "dates": {
                "publicationDate": r.get("issueDate"),
                "effectiveDate": r.get("effectiveDate"),
                "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            "citationString": None,
            "sourceUrl": ("https://lexcom.12348.gov.cn/api/law/chinese/file/"
                          + urllib.parse.quote(file_url)
                          if file_url else
                          "https://lexcom.12348.gov.cn/"),
            "recordLevel": {
                "lexcomId": r.get("id"),
                "lawCategoryCode": cat,
                "lawCategoryName": cat_name,
                "lawCategoryNote": "由发布机关与数值归纳，非官方字典",
                "issuingDepartment": r.get("issueDept"),
                "timelinessCode": tl,
                "timelinessName": tl_name,
                "fileName": file_url or None,
                "matchedKeywords": hits,
                "sourceTier": "L0",
                "note": "司法部法通网收录的我国涉外法律法规；正式文本以官方公布为准",
            },
            "assertions": [],
            "revisionLog": [],
        })

    print(f"  命中航空相关 {len(records)} 条 / 全库 {total} 条")
    return records


def _status_of(tl):
    return {1: "not_yet_effective", 2: "effective",
            3: "amended", 4: "repealed"}.get(tl, "effective")


def collect_foreign():
    """域外法律中文译本。"""
    print("【二】法通网 · 域外法律中文译本")
    raw, total = paged("/law/foreign/translation/page")
    print(f"  拉取 {len(raw)} 条，筛选航空相关…")

    records = []
    for r in raw:
        name = r.get("lawName") or ""
        hits = hit_keywords(name, FOREIGN_KEYWORDS)
        if not hits:
            continue
        cc = r.get("countryCode") or "XX"
        vs = r.get("versionStatus")
        records.append({
            "recordId": make_id(cc, "STD", r.get("id") or name[:20], fallback=name),
            "recordType": "standard",
            "title": name,
            "titleEn": r.get("lawNameCn") or None,
            "summary": None,
            "jurisdiction": cc,
            "topics": topics_for(name, ["foreign-translation"],
                                extra=["translated"]),
            "status": "effective" if vs in (1, 2) else "superseded",
            "dates": {
                "publicationDate": None,
                "effectiveDate": None,
                "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            "citationString": None,
            "sourceUrl": "https://lexcom.12348.gov.cn/overseas-law",
            "recordLevel": {
                "lexcomId": r.get("id"),
                "countryCode": cc,
                "countryName": r.get("countryName"),
                "continentId": r.get("continent"),
                "versionStatusCode": vs,
                "versionStatusName": FOREIGN_VERSION_MAP.get(vs),
                "issueYear": r.get("issueYear"),
                "matchedKeywords": hits,
                "sourceTier": "L1",
                "coverageNote": FOREIGN_SOURCE_PROFILE["note"],
                "note": "域外法律中文译本（译本源：商务部全球法规网）；"
                        "译本仅供理解参考，法律效力以原文为准。"
                        "本条属数据与网络安全类，与航空数据治理交叉，非航空法本身",
            },
            "assertions": [],
            "revisionLog": [],
        })

    print(f"  命中数据与网络安全类 {len(records)} 条 / 全库 {total} 条")
    print(f"  ⚠ 源库航空法覆盖为 {FOREIGN_SOURCE_PROFILE['aviation_related']} 条"
          f"（{FOREIGN_SOURCE_PROFILE['note']}）")
    return records


def attach_assertions(records):
    """为每条记录补断言（字段级证据 + 来源登记）。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for r in records:
        rl = r["recordLevel"]
        sid = f"LEXCOM-{r['recordId']}"
        fields = []

        if rl.get("lexcomId"):
            fields.append(("platform_record_id", str(rl["lexcomId"])))
        if r.get("title"):
            fields.append(("title", r["title"]))
        if rl.get("issuingDepartment"):
            fields.append(("issuing_department", rl["issuingDepartment"]))
        if r.get("dates", {}).get("publicationDate"):
            fields.append(("publication_date", r["dates"]["publicationDate"]))
        if r.get("dates", {}).get("effectiveDate"):
            fields.append(("effective_date", r["dates"]["effectiveDate"]))
        if rl.get("lawCategoryName"):
            fields.append(("effectiveness", rl["lawCategoryName"]))
        if rl.get("timelinessName"):
            fields.append(("timeliness", rl["timelinessName"]))
        if rl.get("countryName"):
            fields.append(("country_name", rl["countryName"]))
        if rl.get("versionStatusName"):
            fields.append(("version_status", rl["versionStatusName"]))

        r["assertions"] = [
            {
                "field": f,
                "value": v,
                "sourceId": sid,
                "locator": f"法通网记录 id={rl.get('lexcomId')}",
                "evidenceLevel": rl.get("sourceTier", "L1"),
                "verifiedAt": today,
            }
            for f, v in fields
        ]
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-cn", default=str(ROOT / "data" / "records" / "regulations_cn_lexcom.json"))
    ap.add_argument("--out-foreign", default=str(ROOT / "data" / "records" / "foreign_translation_lexcom.json"))
    ap.add_argument("--skip-foreign", action="store_true")
    args = ap.parse_args()

    cn = attach_assertions(collect_cn())
    out_cn = Path(args.out_cn)
    out_cn.parent.mkdir(parents=True, exist_ok=True)
    with out_cn.open("w", encoding="utf-8") as f:
        json.dump(cn, f, ensure_ascii=False, indent=2)
    print(f"  → {out_cn.relative_to(ROOT)}（{len(cn)} 条）")

    if not args.skip_foreign:
        fr = attach_assertions(collect_foreign())
        out_fr = Path(args.out_foreign)
        out_fr.parent.mkdir(parents=True, exist_ok=True)
        with out_fr.open("w", encoding="utf-8") as f:
            json.dump(fr, f, ensure_ascii=False, indent=2)
        print(f"  → {out_fr.relative_to(ROOT)}（{len(fr)} 条）")


if __name__ == "__main__":
    main()
