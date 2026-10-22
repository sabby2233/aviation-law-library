#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_ecfr.py — 美国联邦法规汇编（eCFR）现行条文采集

为什么需要这个源：
    现有 568 条 Federal Register 记录全是"变更事件"（刚发布了什么），
    但没有一条是"现行条文"（现在 Part 39 要求什么）。
    实务者要的是后者，FR API 答不了；eCFR 才是规范状态的权威。
    这是同一法域内的纵向补齐，比扩张法域更该先做。

API（免费、无需 key）：
    GET /api/versioner/v1/titles.json                     标题清单（含 up_to_date_as_of）
    GET /api/versioner/v1/structure/{date}/title-{t}.json 结构（part 层级与大小）
    GET /api/versioner/v1/full/{date}/title-{t}.xml?part=N 单 part 全文 XML
    GET /api/versioner/v1/versions/title-{t}.json         各 section 的修订历史

要点（实测得出）：
    1. {date} 必须是**已生效的版本日期**，用当天日期会 404；
       正确值取自 titles.json 的 up_to_date_as_of
    2. full 端点**必须带 Accept-Encoding**（否则 406）
    3. 响应带 hierarchy_metadata，内含 citation（如 "14 CFR Part 89"）

输出：data/records/regulations_us_ecfr.json
"""

import argparse
import gzip
import io
import json
import sys
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "records" / "regulations_us_ecfr.json"

BASE = "https://www.ecfr.gov/api"
UA = "AviationLawLibraryBot/1.1 (+https://github.com/sabby2233/aviation-law-library; contact via repository issues)"

# 航空核心 parts：适航、运营、机场、无人机、人员执照、空域
# 依据学术方法论审阅：这些是航空法的"制度性规则"，
# 而不像 Part 39 那样 275 条全是针对具体机型的技术指令。
CORE_PARTS = {
    "1": "Definitions and Abbreviations",
    "21": "Certification Procedures for Products and Articles",
    "23": "Airworthiness Standards: Normal Category Airplanes",
    "25": "Airworthiness Standards: Transport Category Airplanes",
    "27": "Airworthiness Standards: Normal Category Rotorcraft",
    "29": "Airworthiness Standards: Transport Category Rotorcraft",
    "33": "Airworthiness Standards: Aircraft Engines",
    "35": "Airworthiness Standards: Propellers",
    "36": "Noise Standards",
    "39": "Airworthiness Directives",
    "43": "Maintenance, Preventive Maintenance, Rebuilding, and Alteration",
    "47": "Aircraft Registration",
    "61": "Certification: Pilots, Flight Instructors, and Ground School",
    "63": "Certification: Flight Crewmembers Other Than Pilots",
    "65": "Certification: Airmen Other Than Flight Crewmembers",
    "67": "Medical Standards and Certification",
    "71": "Designation of Class A, B, C, D, and E Airspace Areas",
    "73": "Special Use Airspace",
    "77": "Safe, Efficient Use, and Preservation of the Navigable Airspace",
    "89": "Remote Identification of Unmanned Aircraft",
    "91": "General Operating and Flight Rules",
    "93": "Special Air Traffic Rules",
    "99": "Security Control of Air Traffic",
    "105": "Parachute Operations",
    "107": "Small Unmanned Aircraft Systems",
    "110": "General Requirements",
    "117": "Flight and Duty Limitations and Rest Requirements",
    "119": "Certification: Air Carriers and Commercial Operators",
    "121": "Operating Requirements: Domestic, Flag, and Supplemental Air Carriers",
    "125": "Aircraft Having a Seating Capacity of 20 or More",
    "129": "Operations: Foreign Air Carriers and Foreign Operators",
    "135": "Operating Requirements: Commuter and On Demand Operations",
    "139": "Certification of Airports",
    "145": "Repair Stations",
    "150": "Airport Noise Compatibility Planning",
    "158": "Passenger Facility Charges",
    "170": "Establishment and Discontinuance Criteria for Regional Airports",
    "171": "Non-Federal Navigation Facilities",
    "194": "Special Federal Aviation Regulation No. 120",
}

REQUEST_DELAY = 1.2   # 礼貌间隔（政府站点）
REQUEST_TIMEOUT = 90


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Encoding": "gzip, deflate",   # full 端点必需
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw if binary else raw.decode("utf-8")


def fetch_json(url):
    return json.loads(fetch(url))


def current_version_date(title=14):
    """取该 title 的当前生效版本日期。{date} 用错会 404。"""
    d = fetch_json(f"{BASE}/versioner/v1/titles.json")
    for t in d.get("titles", []):
        if t.get("number") == title:
            return t.get("up_to_date_as_of")
    return None


def get_versions(title=14):
    """section 级修订历史：identifier → 修订列表"""
    d = fetch_json(f"{BASE}/versioner/v1/versions/title-{title}.json")
    return d.get("content_versions", [])


def strip_text(elem):
    """把 XML 元素转为纯文本，保留段落换行。"""
    parts = []
    for node in elem.iter():
        if node.tag == "P":
            t = "".join(node.itertext())
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def get_part_amendments(version_date, part_id, part_label=""):
    """取一个 part 下所有 section 的修订信息（starts_on / change_types）。

    端点选择（实测）：
      - versions 端点只覆盖部分 title（实测 Part 89 不在其中）→ 不可依赖
      - ancestry 端点只到 part 级，不含 section → 逐条查需上千次请求，不可行
      - **search 端点 + hierarchy[part] 过滤** 可一次拿到整 part 的 section 修订信息
        （每页 per_page=100，翻页即可），这是唯一可批量的路径

    关键词策略：search 是全文匹配，单个关键词未必命中 part 内所有条文。
    故用 part 标题的各词分别查并合并；查询词取自 XML 解析出的 part 标题
    （形如 "PART 89—REMOTE IDENTIFICATION OF UNMANNED AIRCRAFT"）。

    返回：{section_no: {"startsOn":..., "changeTypes":[...], "removed":bool}}
    """
    out = {}

    # 提取候选关键词：part 标题里的实词（去掉编号与 PART 标记）
    words = []
    raw = (part_label or "").upper().replace("PART", " ")
    raw = re.sub(r"^\s*\d+[\s—-]*", " ", raw)
    for w in re.split(r"[^A-Z]+", raw):
        if len(w) >= 4 and w not in ("AIRCRAFT", "REQUIREMENTS", "FOR", "THE", "AND",
                                    "OF", "OTHER", "CERTAIN", "WITH", "THIS"):
            words.append(w.lower())
    # 去重且保留顺序
    kws = list(dict.fromkeys(words))[:4]
    if not kws:
        kws = ["aviation"]

    for kw in kws:
        page = 1
        while page <= 6:
            url = (f"{BASE}/search/v1/results?query={urllib.parse.quote(kw)}"
                   f"&per_page=100&page={page}"
                   f"&hierarchy%5Btitle%5D=14&hierarchy%5Bpart%5D={part_id}")
            try:
                d = fetch_json(url)
            except Exception:
                break
            res = d.get("results", [])
            if not res:
                break
            for r in res:
                h = r.get("hierarchy_headings") or {}
                sec = str(h.get("section") or "").replace("§", "").strip()
                if not sec:
                    continue
                so = r.get("starts_on")
                prev = out.get(sec)
                # 保留最晚的 starts_on（现行版本）
                if prev is None or (so or "") > (prev.get("startsOn") or ""):
                    out[sec] = {
                        "startsOn": so,
                        "changeTypes": r.get("change_types") or [],
                        "removed": bool(r.get("removed")),
                    }
            if len(res) < 100:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
        time.sleep(REQUEST_DELAY)
    return out


def get_ancestry(version_date, title=14, part=None, section=None):
    """取条文在 CFR 中的层级路径（title → chapter → subchapter → part → section）。

    比硬编码 subchapter 映射可靠：ancestry 端点直接给出官方层级。
    """
    url = f"{BASE}/versioner/v1/ancestry/{version_date}/title-{title}.json"
    params = {}
    if part:
        params["part"] = part
    if section:
        params["section"] = section
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        d = fetch_json(url)
    except Exception:
        return []
    return d.get("ancestors", [])


def parse_part(xml_bytes, part_id, version_date, ancestry=None):
    """解析单 part 的 XML → 记录列表（每条 record 是一个 section）。"""
    root = ET.parse(io.BytesIO(xml_bytes)).getroot()
    part_citation = ""
    part_label = ""
    for d in root.iter():
        if d.tag == "DIV5" and d.get("N") == part_id:
            hm = d.get("hierarchy_metadata")
            if hm:
                try:
                    part_citation = json.loads(hm).get("citation", "")
                except Exception:
                    pass
            part_label = d.findtext("HEAD") or ""
            break

    # ancestry 提供的官方 subchapter 归属（优先于硬编码映射）
    subchapter = ""
    if ancestry:
        for a in ancestry:
            if a.get("type") == "subchapter":
                subchapter = a.get("identifier", "")
            if a.get("type") == "part" and a.get("identifier") == part_id:
                part_citation = part_citation or a.get("label", "")
                part_label = part_label or a.get("label_description", "")

    records = []
    for div in root.iter():
        if div.tag not in ("DIV8", "DIV6"):
            continue
        # DIV8 = section；DIV6 = subpart（作为容器，其下 DIV8 才是条文）
        if div.tag == "DIV6":
            continue
        n = div.get("N")
        if not n:
            continue
        head = (div.findtext("HEAD") or "").strip()
        if not head:
            continue
        body = strip_text(div)
        if not body:
            continue

        citation = f"14 CFR {n}"
        title = re.sub(r"^§\s*", "", head).strip()
        title = re.sub(r"\s+", " ", title)

        rec = {
            "recordId": make_id("US", "CFR", f"{part_id}-{n}"),
            "recordType": "legislation",
            "title": title,
            "titleEn": title,
            "summary": body[:1200],
            "jurisdiction": "US",
            "topics": [],
            "status": "effective",
            "dates": {
                "effectiveDate": version_date,
                "publicationDate": version_date,
                "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            "citationString": citation,
            "sourceUrl": (
                f"https://www.ecfr.gov/current/title-14/chapter-I/"
                f"subchapter-{subchapter or _subchapter_of(n)}/part-{part_id}/section-{n}"
            ),
            "recordLevel": {
                "cfrPart": part_id,
                "cfrSection": n,
                "cfrCitation": citation,
                "partCitation": part_citation or f"14 CFR Part {part_id}",
                "partLabel": part_label.strip(),
                "subchapter": subchapter or _subchapter_of(n),
                "versionDate": version_date,
                "sourceTier": "L0",
                "bodyChars": len(body),
                "note": "现行条文本体，采自 eCFR 官方 API；正文为官方文本",
            },
            "assertions": [],
            "revisionLog": [],
        }
        records.append(rec)
    return records, part_citation, part_label


def _amend_from_ancestry(version_date, part_id, section_no):
    """用 ancestry 端点取某条文的修订信息。

    ancestry 返回的 ancestors 里含该 section 的 amendment_date 与 issue_date
    （若该版本与前一版有差异）。versions 端点只覆盖部分 title（实测 Part 89
    不在其中），故这里作为补充路径。
    """
    url = (f"{BASE}/versioner/v1/ancestry/{version_date}/title-14.json"
           f"?part={part_id}&section={section_no}")
    try:
        d = fetch_json(url)
    except Exception:
        return None
    for a in d.get("ancestors", []):
        if a.get("type") == "section" and a.get("identifier") == section_no:
            return a.get("amendment_date") or a.get("issue_date")
    return None


def _subchapter_of(section_no):
    """按 section 号粗略判断所属 subchapter（I-A 至 I-F）。"""
    try:
        p = int(section_no.split(".")[0])
    except Exception:
        return "A"
    if p in (1, 3, 5, 11, 13, 14, 15, 16, 17):
        return "A"      # General / Administrative
    if p in (21, 22, 23, 25, 26, 27, 29, 31, 33, 34, 35, 36, 38, 39, 43, 45, 47, 48, 49):
        return "B"      # Airworthiness & Certification
    if p in (60, 61, 63, 65, 67, 68):
        return "C"      # Personnel
    if p in (71, 73, 75, 77, 89, 91, 93, 95, 97, 99, 101, 103, 105, 107, 108, 109, 110, 111, 117, 119, 120, 121, 125, 129, 133, 135, 136, 137):
        return "D"      # Air Traffic & Operating Rules
    if p in (139, 141, 142, 145, 147, 150, 151, 152, 153, 155, 156, 157, 158, 161, 169, 170, 171):
        return "E"      # Airports
    return "F"


def main():
    ap = argparse.ArgumentParser(description="eCFR 现行条文采集")
    ap.add_argument("--parts", default="", help="逗号分隔的 part 号；空则采全部核心 part")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    parts = ([p.strip() for p in args.parts.split(",") if p.strip()]
             if args.parts else sorted(CORE_PARTS.keys(), key=lambda x: int(x)))

    print("取当前生效版本日期…")
    vdate = current_version_date(14)
    if not vdate:
        print("无法获取版本日期，退出", flush=True)
        return
    print(f"  版本日期 {vdate}")

    print("取 section 修订历史…")
    versions = get_versions(14)
    # identifier → 最新一次修订的 amendment_date（取 max）
    amend = {}
    for c in versions:
        ident = c.get("identifier")
        ad = c.get("amendment_date")
        if not ident or not ad:
            continue
        if ident not in amend or ad > amend[ident]:
            amend[ident] = ad
    print(f"  versions 端点覆盖 {len(amend)} 个 section（仅部分 title）")

    all_records = []
    part_meta = {}
    for i, pid in enumerate(parts, 1):
        url = (f"{BASE}/versioner/v1/full/{vdate}/title-14.xml?part={pid}")
        try:
            raw = fetch(url, binary=True)
        except Exception as e:
            print(f"  [warn] part {pid}: {e}")
            time.sleep(REQUEST_DELAY)
            continue
        ancestry = get_ancestry(vdate, 14, part=pid)
        recs, pcitation, plabel = parse_part(raw, pid, vdate, ancestry)
        time.sleep(REQUEST_DELAY)

        # 该 part 的 section 修订信息（批量查一次）
        part_amend = get_part_amendments(vdate, pid, plabel or CORE_PARTS.get(pid, ""))

        for r in recs:
            sec = r["recordLevel"]["cfrSection"]
            # 断言：条文本身即 L0 一手证据
            r["assertions"] = [
                {
                    "field": "cfr_section",
                    "value": r["recordLevel"]["cfrCitation"],
                    "sourceId": f"ECFR-{pid}-{sec}",
                    "locator": f"14 CFR {sec}（现行条文）",
                    "evidenceLevel": "L0",
                    "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
                {
                    "field": "cfr_part",
                    "value": f"14 CFR {pid}",
                    "sourceId": f"ECFR-{pid}-{sec}",
                    "locator": f"14 CFR Part {pid}",
                    "evidenceLevel": "L0",
                    "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
                {
                    "field": "section_title",
                    "value": r["title"],
                    "sourceId": f"ECFR-{pid}-{sec}",
                    "locator": f"14 CFR {sec} 标题",
                    "evidenceLevel": "L0",
                    "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
            ]
            # 修订日期：批量查询结果优先，versions 端点兜底
            am = part_amend.get(sec)
            ad = (am or {}).get("startsOn") or amend.get(sec)
            if ad:
                r["recordLevel"]["lastAmendedDate"] = ad
                r["dates"]["lastAmendedDate"] = ad
            if am and am.get("changeTypes"):
                r["recordLevel"]["changeTypes"] = am["changeTypes"]
            r["topics"] = _topics_for(pid, r["title"])
        all_records.extend(recs)
        part_meta[pid] = {"citation": pcitation, "label": plabel.strip(),
                          "sections": len(recs), "partLabel": CORE_PARTS.get(pid, "")}
        print(f"  [{i}/{len(parts)}] 14 CFR {pid:<4} {len(recs):>4} section  "
              f"{str(plabel)[:44]}")
        time.sleep(REQUEST_DELAY)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    # 附带 part 元数据，供后续引用
    meta_out = ROOT / "data" / "ecfr_parts.json"
    with meta_out.open("w", encoding="utf-8") as f:
        json.dump({"versionDate": vdate, "parts": part_meta}, f, ensure_ascii=False, indent=2)

    try:
        rel = out.relative_to(ROOT)
    except ValueError:
        rel = out
    print(f"\n完成：{len(all_records)} 条现行条文 → {rel}")
    print(f"part 元数据 → {meta_out.relative_to(ROOT)}")
    print(f"版本日期 {vdate}")


def _topics_for(part_id, title):
    """由 part 语义推导主题标签（不引模型）。"""
    t = []
    p = part_id
    if p in ("21", "23", "25", "27", "29", "33", "35"):
        t += ["airworthiness", "type-certification"]
    if p == "36":
        t += ["noise", "environmental"]
    if p == "39":
        t += ["airworthiness", "airworthiness-directive"]
    if p in ("43", "145", "147"):
        t += ["maintenance", "repair-station"]
    if p in ("47", "48", "49"):
        t += ["registration", "aircraft-title"]
    if p in ("61", "63", "65", "67"):
        t += ["personnel-licensing", "pilot"]
    if p in ("71", "73", "77", "99"):
        t += ["airspace", "air-traffic"]
    if p in ("89", "107", "108", "109", "101", "103", "105"):
        t += ["uav", "unmanned"]
    if p in ("91", "93", "117"):
        t += ["operating-rules", "flight-rules"]
    if p in ("119", "121", "125", "129", "135"):
        t += ["air-carrier", "operating-requirements"]
    if p in ("139", "150", "151", "152", "158", "161", "169", "170", "171"):
        t += ["airport", "airport-programs"]
    if p == "1":
        t += ["definitions"]
    if p == "5":
        t += ["safety-management"]
    tl = title.lower()
    if "privacy" in tl or "data" in tl:
        t.append("data-protection")
    if "security" in tl and "airport" not in tl:
        t.append("security")
    return sorted(set(t))


if __name__ == "__main__":
    main()
