#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 FlowUs 候选附件并核验其真实版次（不信文件名，只信 PDF 内页）。

用法：
  1) 先跑 scripts/fetch_flowus.py 生成 data/snapshots/flowus_pages.json
  2) 本脚本按 --pick 里的关键字筛出文件，下载到 data/inbox/flowus/，
     解析第 1-6 页提取 "Xth Edition, YYYY" / "Doc NNNN" / 修订号，输出核验表。
"""
import json, os, re, sys, time, urllib.request, urllib.parse

HDR = {
    "Referer": "https://flowus.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
}
OUTDIR = "data/inbox/flowus"
PAGES = "data/snapshots/flowus_pages.json"

# 只下"版次可能现行"的 + 中文正式本（中文译本稀缺，即使旧版也留作对照）
PICK = [
    "Annex.3-", "Annex.4-", "Annex.5-", "Annex.7-", "Annex.10-", "Annex.11-",
    "Annex.15-", "Annex.16-", "Annex.18-", "Doc.4444-", "8168 Volume II",
]


def signed_url(oss):
    u = "https://flowus.cn/api/download_url/" + oss
    req = urllib.request.Request(u, headers=HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode())
    if j.get("code") != 200:
        raise RuntimeError(j)
    return j["data"]["url"]


def safe(name):
    n = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return n[:150]


def verify(path):
    """从 PDF 前 6 页抽版次/文档号/修订号"""
    try:
        import pypdf
        r = pypdf.PdfReader(path)
        txt = ""
        for i in range(min(6, len(r.pages))):
            try:
                txt += (r.pages[i].extract_text() or "") + "\n"
            except Exception:
                pass
        ed = re.search(r"([A-Za-z]+)\s*Edition[,]?\s*((?:19|20)\d{2})", txt)
        ed2 = re.search(r"第\s*(\d+)\s*版", txt)
        doc = re.search(r"Doc\s*\.?\s*(\d{4})", txt)
        amd = re.search(r"Amendment[s]?\s*(?:No\.?)?\s*(\d+)\s*(?:dated\s*)?([\d/]{6,10})?", txt)
        return {
            "pages": len(r.pages),
            "edition": (ed.group(0) if ed else (ed2.group(0) if ed2 else "")),
            "docNo": doc.group(1) if doc else "",
            "amendHint": amd.group(0)[:40] if amd else "",
            "head": re.sub(r"\s+", " ", txt[:160]),
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    pages = json.load(open(PAGES, encoding="utf-8"))
    todo = []
    for p in pages:
        for f in p["files"]:
            if any(k.lower() in f["name"].lower() for k in PICK):
                todo.append(f)
    print(f"候选 {len(todo)} 份，开始下载…\n")
    report = []
    for i, f in enumerate(todo, 1):
        fn = safe(f["name"])
        if not fn.lower().endswith(".pdf"):
            fn += ".pdf"
        dst = os.path.join(OUTDIR, fn)
        rec = {"name": f["name"], "file": fn, "sizeBytes": f.get("sizeBytes")}
        if os.path.exists(dst) and os.path.getsize(dst) > 10240:
            rec["download"] = "cached"
        else:
            try:
                url = signed_url(f["ossName"])
                # CDN 直链必须带 UA/Referer，否则 404；urlretrieve 不带 header，故手写
                req = urllib.request.Request(url, headers=HDR)
                with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as fh:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                rec["download"] = f"{os.path.getsize(dst)/1048576:.1f}MB"
            except Exception as e:
                rec["download"] = f"FAIL {e}"
                report.append(rec)
                print(f"{i:2}. FAIL {f['name'][:50]} {e}")
                continue
        rec.update(verify(dst))
        report.append(rec)
        print(f"{i:2}. {rec.get('download'):>10} | {rec.get('pages')}p | {rec.get('edition'):28} | {f['name'][:56]}")
        time.sleep(0.4)
    json.dump(report, open("data/snapshots/flowus_verify.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n完成，明细 -> data/snapshots/flowus_verify.json")


if __name__ == "__main__":
    main()
