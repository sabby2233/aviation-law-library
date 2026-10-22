#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 FlowUs 分享页（ICAO 附件和文件）全部子页面，导出文本与附件清单。

关键：必须带 Referer: https://flowus.cn/ ，否则 401。
输出：data/snapshots/flowus_pages.json
"""
import json, os, re, sys, time, urllib.request, urllib.error

ROOT_UUID = "925292e4-e5d6-4ab3-9aad-e6028a006fb3"
BASE = "https://flowus.cn/api/docs/"
HDR = {
    "Referer": "https://flowus.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
OUT = "data/snapshots/flowus_pages.json"


def fetch(uuid, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(BASE + uuid, headers=HDR)
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8")
            j = json.loads(raw)
            if j.get("code") == 200:
                return j["data"]
        except Exception as e:
            if i == retries - 1:
                print(f"  !! {uuid[:8]} failed: {e}", file=sys.stderr)
        time.sleep(1.2 * (i + 1))
    return None


def seg_text(b):
    """拼 block 的 segments 文本"""
    segs = (b.get("data") or {}).get("segments") or []
    return "".join(s.get("text", "") for s in segs if isinstance(s, dict))


def collect_files(b):
    """提取附件。FlowUs 附件 block type=14，路径在 data.ossName（oss/<uuid>/<urlenc 文件名>）。
    下载需先换签名直链：GET https://flowus.cn/api/download_url/{ossName}（Referer 必须带）。"""
    out = []
    data = b.get("data") or {}
    t = b.get("type")
    oss = data.get("ossName") or ""
    if t == 14 and oss:
        out.append({
            "name": seg_text(b) or oss.rsplit("/", 1)[-1],
            "ossName": oss,
            "ext": data.get("extName") or "",
            "sizeBytes": data.get("size"),
            "blockType": t,
        })
        return out
    url = data.get("url") or data.get("source") or data.get("src") or ""
    name = data.get("name") or data.get("title") or data.get("fileName") or seg_text(b)
    if isinstance(url, str) and re.search(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|txt|md)(\?|$)", url, re.I):
        out.append({"name": name, "url": url, "blockType": t})
    return out


def main():
    os.makedirs("data/snapshots", exist_ok=True)
    main_data = fetch(ROOT_UUID)
    if not main_data:
        print("root fetch failed")
        return
    root_blocks = main_data["blocks"]
    root = root_blocks[ROOT_UUID]

    pages = {}   # uuid -> {title, parent, text[], files[]}
    queue = [(ROOT_UUID, None, 0)]
    seen = set()
    result = []

    # 先手工 BFS：对每个 page 请求其文档
    order = []
    def walk(uuid, parent_title, depth):
        if uuid in seen or depth > 4:
            return
        seen.add(uuid)
        d = fetch(uuid)
        if not d:
            return
        blocks = d.get("blocks", {})
        page = blocks.get(uuid) or {}
        title = page.get("title") or ""
        texts, files = [], []
        for bid, b in blocks.items():
            if bid == uuid:
                continue
            if b.get("type") == 0:      # 子页面本身，跳过正文收集
                continue
            t = seg_text(b).strip()
            if t:
                texts.append(t)
            files.extend(collect_files(b))
        rec = {
            "uuid": uuid,
            "title": title,
            "parentTitle": parent_title,
            "depth": depth,
            "text": "\n".join(texts),
            "files": files,
        }
        result.append(rec)
        print(f"{'  '*depth}[{depth}] {title[:60]}  files={len(files)} blocks={len(blocks)}")
        # 递归子页面
        for sn in (blocks.get(uuid, {}).get("subNodes") or []):
            child = blocks.get(sn)
            if child and child.get("type") == 0:
                walk(sn, title, depth + 1)
            else:
                walk(sn, title, depth + 1)

    walk(ROOT_UUID, None, 0)

    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n抓取页面 {len(result)} 个 -> {OUT}")
    nf = sum(len(r["files"]) for r in result)
    print(f"附件链接 {nf} 条")


if __name__ == "__main__":
    main()
