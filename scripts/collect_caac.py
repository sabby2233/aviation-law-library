#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_caac.py — 中国民用航空局规章与规范性文件采集

为什么需要这个源：
    学术方法论审阅指出，中文读者的母法域当前召回为零。
    而 CAAC 的规章栏目是**结构化表格**，字段含 CCAR 部号、有效性、发文日期、
    办文单位——这正是法学引证最需要的元数据（"哪一部、现行有效吗、什么时候发的"）。

技术要点（实测得出）：
    1. 页面是 JS 渲染的静态页，列表数据来自 TRS 搜索服务：
       /was5/web/search?channelid=<id>&searchword=&perpage=<n>&page=<n>
    2. 规章栏目 channelid = 269689（返回表格：序号 | 名称 | CCAR部号 | 有效性）
    3. 每条记录含：办文单位、发文日期、名称、CCAR部号、有效性
    4. 结果链接形如 /XXGK/XXGK/MHGZ/202607/t20260717_231321.html

抓取礼仪：单线程、请求间隔 2 秒、明确 UA 标注研究用途。

输出：data/records/regulations_cn_caac.json
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "records" / "regulations_cn_caac.json"

BASE = "https://www.caac.gov.cn"
SEARCH = f"{BASE}/was5/web/search"
UA = ("AviationLawLibraryBot/1.1 "
      "(+https://github.com/sabby2233/aviation-law-library; contact via repository issues)")

# 栏目：TRS channelid
#   269689 = 规章（表格含 CCAR 部号与有效性）
#   283012 = 规范性文件相关
CHANNELS = {
    "269689": "规章",
}

REQUEST_DELAY = 2.0
PERPAGE = 20


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("&nbsp;", " ")
    return " ".join(s.split())


def parse_rows(page_html):
    """解析结果表格的行。

    表格结构：序号 | 名称 | CCAR部号 | 有效性
    每行内有：<a name="标题" href="链接">、办文单位、发文日期、名称、CCAR部号、有效性
    """
    rows = re.findall(
        r"<tr>\s*<td>\s*<!--\d+ -->\s*\d+\s*</td>(.*?)</tr>",
        page_html, re.S)
    out = []
    for r in rows:
        m_name = re.search(r'<a[^>]+href="([^"]+)"[^>]*name="([^"]+)"', r)
        if not m_name:
            continue
        href, name = m_name.group(1), clean(m_name.group(2))

        # 字段：<li ...><b>字段名：</b>值</li>
        fields = {}
        for fm in re.finditer(r"<b>([^<]{2,20}?)：</b>(.*?)(?=<li|</ul>)", r, re.S):
            k = clean(fm.group(1))
            v = clean(fm.group(2))
            if k:
                fields[k] = v

        # 表格列：td[0]=名称与元信息、td[1]=CCAR部号、td[2]=有效性
        # 有效性不在 <li> 里，须从表格列取（实测确认）
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(tds) >= 3:
            ccar_cell = clean(tds[1])
            validity_cell = clean(tds[2])
            if ccar_cell:
                fields["CCAR部号"] = ccar_cell
            if validity_cell:
                fields["有效性"] = validity_cell

        out.append({
            "title": name,
            "url": href if href.startswith("http") else BASE + href.replace("//", "/"),
            "fields": fields,
        })
    return out


def to_record(item, channel_label):
    """转为本站记录格式。"""
    f = item["fields"]
    title = item["title"]

    # 发文日期：2026年07月01日 → 2026-07-01
    d_raw = f.get("发文日期", "")
    dm = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", d_raw)
    pub = ""
    if dm:
        y, mo, dd = (int(x) for x in dm.groups())
        pub = f"{y:04d}-{mo:02d}-{dd:02d}"

    ccar = f.get("CCAR部号", "")
    validity = f.get("有效性", "")
    dept = f.get("办文单位", "")
    name_field = f.get("名称", "")

    # recordId：AVA-CN-<类型>-<来源标识>
    #   有 CCAR 部号  CCAR-290-R4   → AVA-CN-CCAR-290-R4
    #   有 CCAR 部号  CCAR-66TM-I-R5 → AVA-CN-CCAR-66TM-I-R5
    #   无 CCAR 部号（规范性文件） → AVA-CN-GZ-<标题派生稳定哈希>
    ccar_segs = [p for p in str(ccar).split("-") if p]
    if ccar_segs and ccar_segs[0].upper() == "CCAR":
        ccar_segs = ccar_segs[1:]
    if ccar_segs:
        rid = make_id("CN", "CCAR", "-".join(ccar_segs), fallback=title)
    else:
        rid = make_id("CN", "GZ", None, fallback=title)

    topics = []
    if "无人机" in title or "无人驾驶" in title or "无人" in title:
        topics.append("uav")
    if "适航" in title:
        topics.append("airworthiness")
    if "运输" in title or "经营许可" in title:
        topics.append("air-carrier")
    if "空域" in title or "管制" in title or "飞行管理" in title:
        topics.append("airspace")
    if "机场" in title:
        topics.append("airport")
    if "执照" in title or "合格证" in title or "人员" in title:
        topics.append("personnel-licensing")
    if "安全" in title:
        topics.append("safety")
    topics.append("cn-regulation")

    # 有效性 → 状态机
    # 民航局表格的「有效性」列有四种取值，需分别映射：
    #   有效     → effective
    #   失效     → invalidated（非明文废止，但不再适用）
    #   废止     → repealed（明文废止）
    #   历史版本 → superseded（已被后续版本取代，仍可作沿革参考）
    #   即将施行/尚未生效 → not_yet_effective
    status = "effective"
    if validity == "废止":
        status = "repealed"
    elif validity == "失效":
        status = "invalidated"
    elif validity == "历史版本":
        status = "superseded"
    elif validity in ("即将施行", "尚未生效"):
        status = "not_yet_effective"

    sid = f"CAAC-{rid}"

    assertions = []
    for field, value in [
        ("ccar_number", ccar),
        ("validity", validity),
        ("issuing_department", dept),
        ("regulation_name", name_field or title),
        ("publication_date", pub),
    ]:
        if value:
            assertions.append({
                "field": field,
                "value": value,
                "sourceId": sid,
                "locator": "民航局政务公开·规章栏目表格行",
                "evidenceLevel": "L0",
                "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })

    # 终结说明：非现行有效的规章必须留下可追溯的轨迹
    # 否则读者只看到「已废止」而无法知道何时、因何终止，也无法回溯依据。
    revision_log = []
    if status in ("repealed", "invalidated", "superseded"):
        revision_log.append({
            "oldStatus": "effective",
            "newStatus": status,
            "date": pub or None,
            "reason": validity,
            "reasonSource": "民航局规章栏目「有效性」列原文",
            "sourceId": sid,
            "note": "废止/失效的确切日期与替代规章未在该表中给出，"
                    "需回规章原文或公报核实；此处只记录官方栏目明示的有效性状态",
        })

    return {
        "recordId": rid,
        "recordType": "legislation",
        "title": title,
        "titleEn": None,
        "summary": "",
        "jurisdiction": "CN",
        "topics": sorted(set(topics)),
        "status": status,
        "dates": {
            "publicationDate": pub or None,
            "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
        "citationString": ccar or title,
        "sourceUrl": item["url"],
        "assertions": assertions,
        "recordLevel": {
            "ccarNumber": ccar,
            "validity": validity,
            "issuingDepartment": dept,
            "sourceTier": "L0",
            "channel": channel_label,
            "note": "采自中国民用航空局政务公开栏目的规章表；"
                    "表内含 CCAR 部号与有效性字段",
        },
        "revisionLog": revision_log,
    }


def main():
    ap = argparse.ArgumentParser(description="CAAC 规章与规范性文件采集")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--max-pages", type=int, default=40)
    args = ap.parse_args()

    all_records = []
    for cid, label in CHANNELS.items():
        page = 1
        while page <= args.max_pages:
            url = (f"{SEARCH}?channelid={cid}&searchword="
                   f"&perpage={PERPAGE}&page={page}")
            try:
                page_html = fetch(url)
            except Exception as e:
                print(f"  [warn] {label} 第 {page} 页: {e}")
                break
            items = parse_rows(page_html)
            if not items:
                print(f"  {label} 第 {page} 页无结果，结束")
                break
            for it in items:
                all_records.append(to_record(it, label))
            print(f"  {label} 第 {page} 页 → {len(items)} 条")
            page += 1
            time.sleep(REQUEST_DELAY)

    # 去重（按 recordId）
    uniq = {}
    for r in all_records:
        uniq[r["recordId"]] = r
    records = list(uniq.values())
    records.sort(key=lambda r: (r.get("dates", {}).get("publicationDate") or ""), reverse=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    with_ccar = sum(1 for r in records if r["recordLevel"].get("ccarNumber"))
    valid = sum(1 for r in records if r["status"] == "effective")
    print(f"\n完成：{len(records)} 条 → {out.name}")
    print(f"  含 CCAR 部号：{with_ccar}")
    print(f"  现行有效：{valid} | 其他状态：{len(records) - valid}")


if __name__ == "__main__":
    main()
