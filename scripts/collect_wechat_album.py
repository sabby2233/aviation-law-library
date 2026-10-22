#!/usr/bin/env python
"""抓取微信公众号相册「ICAO 国际民航公约附件」的全部文章清单。

用途：用户在微信相册里已有一整套 ICAO 附件的中文图文版，但那是**图片形式**。
本脚本只提取「标题 + 原文链接 + 发布时间」这类元数据，不抓取、不解析图片内容
——图片里是 SARPs 条文，属 ICAO 保留版权材料，不入库。

输出：data/icao_wechat_album.json（标题、链接、时间、识别出的附件号）

分页机制（实测）：同一 URL 加 begin_msgid / begin_itemidx / count 取下一批。
"""

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "icao_wechat_album.json"

BIZ = "Mzg3MzUyMDU2NA=="
ALBUM_ID = "2923696623472345089"
BASE = "https://mp.weixin.qq.com/mp/appmsgalbum"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DELAY = 1.2


def fetch_page(begin_msgid="", begin_itemidx="", count=10):
    params = {
        "__biz": BIZ,
        "action": "getalbum",
        "album_id": ALBUM_ID,
        "count": count,
    }
    if begin_msgid:
        params["begin_msgid"] = begin_msgid
        params["begin_itemidx"] = begin_itemidx
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_articles(page_html):
    """从 articleList 数组里抽 title / url / create_time / msgid / itemidx。

    页面用的是 JS 对象字面量（单引号、无引号键名），不是合法 JSON，
    因此按字段逐个用正则抽取——比先修补成 JSON 更稳。
    """
    i = page_html.find("articleList")
    if i < 0:
        return []
    seg = page_html[i:]

    # 按对象切块：每个对象以 { 开头、以 } 结尾，中间含 title:
    blocks = re.findall(
        r"\{\s*title:\s*'((?:[^'\\]|\\.)*)'.*?"
        r"url:\s*'((?:[^'\\]|\\.)*)'.*?"
        r"msgid:\s*'([^']*)'.*?"
        r"itemidx:\s*'([^']*)'",
        seg, re.S)

    out = []
    for title, url, msgid, itemidx in blocks:
        t = html.unescape(title).replace("\\x26", "&").strip()
        u = html.unescape(url).replace("\\x26", "&").replace("&amp;", "&").strip()
        out.append({"title": t, "url": u, "msgid": msgid, "itemidx": itemidx})
    return out


def parse_time(page_html, msgid):
    """取该 msgid 对应的 create_time（Unix 秒）。"""
    m = re.search(r"msgid:\s*'" + re.escape(msgid) +
                  r"'.*?create_time:\s*'(\d+)'", page_html, re.S)
    if not m:
        m = re.search(r"create_time:\s*'(\d+)'", page_html)
    return m.group(1) if m else ""


def annex_no(title):
    """从标题里识别附件号；识别不到返回 None。"""
    m = re.search(r"附件\s*(\d{1,2})", title)
    return int(m.group(1)) if m else None


def main():
    all_items = []
    seen = set()
    begin_msgid, begin_itemidx = "", ""
    for page_no in range(1, 16):
        try:
            h = fetch_page(begin_msgid, begin_itemidx)
        except Exception as e:  # noqa: BLE001
            print(f"  第 {page_no} 页失败：{str(e)[:70]}")
            break

        items = parse_articles(h)
        if not items:
            print(f"  第 {page_no} 页无文章，停止")
            break

        new = 0
        for it in items:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            ts = parse_time(h, it["msgid"])
            it["createTime"] = ts
            it["date"] = (datetime.fromtimestamp(int(ts), timezone.utc)
                          .strftime("%Y-%m-%d") if ts.isdigit() else "")
            it["annexNo"] = annex_no(it["title"])
            all_items.append(it)
            new += 1

        print(f"  第 {page_no} 页：{len(items)} 条，新增 {new}，累计 {len(all_items)}")
        if new == 0:
            break

        last = items[-1]
        begin_msgid, begin_itemidx = last["msgid"], last["itemidx"]
        time.sleep(DELAY)

    # 附件号 → 标题映射，并标出缺口
    by_annex = {}
    for it in all_items:
        n = it["annexNo"]
        if n:
            by_annex.setdefault(n, []).append(it)

    missing = [n for n in range(1, 20) if n not in by_annex]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "albumId": ALBUM_ID,
            "biz": BIZ,
            "albumTitle": "ICAO 国际民航公约附件",
            "platform": "微信公众号相册",
            "form": "图片形式（正文为图片，非文本）",
            "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "articleCount": len(all_items),
            "annexCovered": sorted(by_annex),
            "annexMissing": missing,
            "note": ("仅收录标题与链接等元数据。正文图片所载 SARPs 条文属 ICAO "
                     "保留版权材料，不入库、不转录。"),
        },
        "articles": all_items,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print(f"\n共 {len(all_items)} 篇文章 → {OUT.relative_to(ROOT)}")
    print(f"覆盖附件号：{sorted(by_annex)}")
    print(f"未覆盖附件号：{missing}")
    print("\n=== 按附件号归并 ===")
    for n in sorted(by_annex):
        for it in by_annex[n]:
            print(f"  Annex {n:>2}  {it['date']}  {it['title'][:72]}")
    other = [it for it in all_items if not it["annexNo"]]
    if other:
        print("\n=== 未识别附件号 ===")
        for it in other:
            print(f"  {it['date']}  {it['title'][:78]}")


if __name__ == "__main__":
    main()
