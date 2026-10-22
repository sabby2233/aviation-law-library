#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取中国民航大学图书馆各资源栏目，导出数据库/资源清单。

用途：核对我列的 ICAO 文档清单在校内图书馆能否获取。
"""
import re, sys, time, urllib.request

BASE = "https://www.cauc.edu.cn"
PAGES = {
    "数据库导航-更多": "/tsg/node/311.jspx",
    "民航特色资源": "/tsg/node/327.jspx",
    "学位论文": "/tsg/node/361.jspx",
    "会议论文": "/tsg/node/440.jspx",
    "图书": "/tsg/node/325.jspx",
    "期刊报纸": "/tsg/node/326.jspx",
    "多媒体资源": "/tsg/node/362.jspx",
    "专利资源": "/tsg/node/442.jspx",
    "开放课程": "/tsg/node/364.jspx",
    "随书光盘": "/tsg/node/377.jspx",
    "校外访问": "/tsg/node/441.jspx",
    "资源总览": "/tsg/node/300.jspx",
}
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}


def get(path):
    url = BASE + path
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def strip_tags(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def main():
    for name, path in PAGES.items():
        print("=" * 72)
        print(f"## {name}  {BASE}{path}")
        try:
            h = get(path)
        except Exception as e:
            print("  !! 抓取失败:", e)
            continue
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h, re.S | re.I)
        seen = set()
        out = []
        for u, t in links:
            t = strip_tags(t).strip()
            t = re.sub(r"\s+", " ", t)
            if not t or len(t) < 2:
                continue
            if (t, u) in seen:
                continue
            seen.add((t, u))
            # 过滤纯导航
            if t in ("首页", "资源", "数据库导航", "更多>>", "上一页", "下一页", "返回"):
                continue
            out.append((t, u))
        for t, u in out:
            print(f"  - {t[:60]:60} | {u[:110]}")
        if not out:
            body = strip_tags(h)
            body = re.sub(r"\s+", " ", body)
            print("  (无链接) 正文摘要:", body[:400])
        time.sleep(0.6)


if __name__ == "__main__":
    main()
