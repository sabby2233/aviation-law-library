#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_caac_fulltext.py — 给民航局规章补全文

为什么单独写一个：
    collect_caac.py 只采了「栏目表格行」（部号、名称、有效性、发文日期），
    295 条规章的正文一个字都没存。而民航局规章依《著作权法》第五条
    不适用著作权法（法律法规、国家机关的行政文件），可以全文收录、公开。

正文在哪：
    规章详情页（如 /XXGK/XXGK/MHGZ/202607/t20260717_231321.html）本身
    只是「部长令 + 附件」，正文在随附的 PDF 里。所以要：
      详情页 → 找 .pdf 附件 → 下载 → 抽文本

用法：
    python scripts/collect_caac_fulltext.py            # 增量：跳过已有 fullText 的
    python scripts/collect_caac_fulltext.py --limit 5  # 先试 5 条
    python scripts/collect_caac_fulltext.py --force    # 全部重采
"""

import argparse
import io
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = DATA / "records" / "regulations_cn_caac.json"
TMP = DATA / "inbox" / "caac_pdf"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

DELAY = 1.2          # 对政府站点保持克制：约 1 条/秒
BODY_PREVIEW = 600   # 摘要取正文前 600 字，卡片与检索都用它


def fetch(url, binary=False, referer=None, timeout=60, retries=3):
    hdrs = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        hdrs["Referer"] = referer
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return raw if binary else raw.decode("utf-8", "ignore")
        except Exception as e:          # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def decode_html(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def clean_pdf_text(txt):
    """去掉页码、页眉残留与多余空行，并修复 PDF 抽取常见的「字间空格」。

    民航局规章 PDF 的页脚形如「— 3 —」，也见过「- 3 -」。
    只清这两种明确是页码的形态，不动正文里的破折号。

    另一类问题：部分 PDF 每两个汉字之间都被塞进一个空格
    （「中 华 人 民 共 和 国 交 通 运 输 部」）。这会让条文号匹配全部失效，
    因此把「汉字 + 空格 + 汉字」的空格去掉。
    """
    txt = txt.replace("\u3000", " ")
    txt = re.sub(r"[\r\n]+", "\n", txt)
    txt = re.sub(r"^\s*[—\-–]{1,2}\s*\d{1,3}\s*[—\-–]{1,2}\s*$", "", txt, flags=re.M)
    # 去掉汉字之间的空格（最多连着处理）
    prev = None
    while prev != txt:
        prev = txt
        txt = re.sub(r"(?<=[一-鿿]) +(?=[一-鿿])", "", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    lines = [ln.strip() for ln in txt.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def extract_pdf(raw):
    if not raw:
        return "", 0
    r = pypdf.PdfReader(io.BytesIO(raw))
    if r.is_encrypted:
        try:
            r.decrypt("")
        except Exception:                # noqa: BLE001
            return "", 0
    parts = []
    for pg in r.pages:
        try:
            parts.append(pg.extract_text() or "")
        except Exception:                # noqa: BLE001
            continue
    return clean_pdf_text("\n".join(parts)), len(r.pages)


def content_div_text(h):
    """没有 PDF 时的回退：取 data-role="n_content" 的正文块。"""
    m = re.search(r'<div class="content"[^>]*data-role="n_content"[^>]*>(.*?)</div>\s*</div>',
                  h, re.S)
    seg = m.group(1) if m else ""
    seg = re.sub(r"<script.*?</script>", " ", seg, flags=re.S | re.I)
    seg = re.sub(r"<style.*?</style>", " ", seg, flags=re.S | re.I)
    seg = re.sub(r"<[^>]+>", "\n", seg)
    seg = seg.replace("&nbsp;", " ").replace("&amp;", "&")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in seg.split("\n")]
    return clean_pdf_text("\n".join(ln for ln in lines if ln))


def find_attachment(h, page_url):
    """找正文附件。

    民航局的附件有四种写法，都实测出现过：
      1. href="./P020xxxx.pdf"
      2. href="...download.pdf?..."（带查询串）
      3. 只出现在 JS 里：var appendixfile="xxx.pdf"
      4. 附件是 .doc / .docx / .wps（早期规章大量使用）
    只认第 1 种会漏掉相当一部分，然后把「附件： xxx.pdf」这行链接文字当成正文。
    """
    cands = re.findall(r'href="([^"]+\.(?:pdf|docx?|wps)[^"]*)"', h, re.I)
    if not cands:
        cands = re.findall(
            r'(?:appendixfile|appendixlink|url)\s*=\s*"([^"]+\.(?:pdf|docx?|wps))"', h, re.I)
    for c in cands:
        u = urllib.parse.urljoin(page_url, c)
        if re.search(r"\.(pdf|docx?|wps)(\?|$)", u, re.I):
            return u
    return None


def extract_doc(raw):
    """从 .doc/.docx 里抽文本。

    民航局早期规章的附件多是「Word 97 存成 HTML」或 RTF：
      - 以 <html 开头 → 直接按 HTML 解析
      - 以 {\\rtf 开头 → 去控制字后取正文
    真正的二进制 .doc（OLE 复合文档）本机无解析器，放弃并如实记为未取到。
    """
    head = raw[:400].lstrip()
    low = head.lower()
    if b"<html" in low or b"<body" in low:
        t = re.sub(r"<script.*?</script>", " ", raw.decode("utf-8", "ignore"), flags=re.S | re.I)
        t = re.sub(r"<[^>]+>", "\n", t)
        t = t.replace("&nbsp;", " ")
        return clean_pdf_text(t)
    if head.startswith(b"{\\rtf"):
        t = raw.decode("utf-8", "ignore")
        t = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), t)
        t = re.sub(r"\\[a-zA-Z]+-?\d*\s?", " ", t)
        t = t.replace("{", "").replace("}", "")
        return clean_pdf_text(t)
    if raw[:4] == b"PK\x03\x04":        # 其实是 docx（zip）
        try:
            import zipfile
            z = zipfile.ZipFile(io.BytesIO(raw))
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
            xml = re.sub(r"</w:p>", "\n", xml)
            t = re.sub(r"<[^>]+>", "", xml)
            return clean_pdf_text(t)
        except Exception:                # noqa: BLE001
            return ""
    return ""


def looks_like_regulation(text):
    """判断抽出来的东西是不是条文，而不是「附件： xxx.pdf」这类链接清单。

    见过的最短真条文是 340 字（一则修改决定，本身就短），
    所以只按长度卡会误杀；同时要求出现条文的标志性字眼。
    """
    if not text:
        return False
    # 条号可能是「第十二条」「第121.2条」「第 61.3 条」——不能只认纯中文数字。
    has_article = re.search(r"第[^条\n]{1,14}条", text) is not None
    has_chapter = re.search(r"第[^章\n]{1,6}章", text) is not None
    has_item = re.search(r"第[^款\n]{1,14}款", text) is not None
    has_decree = ("部令" in text) or ("总局令" in text) or ("现予公布" in text)
    if len(text) >= 800 and (has_article or has_chapter or has_item or has_decree):
        return True
    if len(text) >= 200 and (has_article or has_item):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0, help="从第 N 条待补记录开始（分片用）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=1, help="并发数；对政府站点建议不超过 4")
    ap.add_argument("--src", default="", help="读取路径；分片时指向主记录文件")
    ap.add_argument("--out", default=str(SRC))
    args = ap.parse_args()

    TMP.mkdir(parents=True, exist_ok=True)
    src = Path(args.src) if args.src else Path(args.out)
    records = json.loads(src.read_text(encoding="utf-8"))
    todo = [r for r in records if args.force or not r.get("fullText")]
    if args.offset:
        todo = todo[args.offset:]
    if args.limit:
        todo = todo[:args.limit]
    print(f"待补全文 {len(todo)} / {len(records)} 条｜并发 {args.workers}", flush=True)

    ok = pdf_ok = html_ok = fail = 0
    lock = threading.Lock()

    def work(idx_rec):
        nonlocal ok, pdf_ok, html_ok, fail
        i, rec = idx_rec
        rid = rec["recordId"]
        url = rec.get("sourceUrl") or ""
        if not url:
            with lock:
                fail += 1
            return
        try:
            h = decode_html(fetch(url, binary=True, referer="https://www.caac.gov.cn/"))
            att = find_attachment(h, url)
            text, pages, kind = "", 0, ""
            if att:
                raw = fetch(att, binary=True, referer=url)
                if re.search(r"\.pdf(\?|$)", att, re.I):
                    text, pages = extract_pdf(raw)
                    kind = "附件 PDF"
                else:
                    text = extract_doc(raw)
                    kind = "附件 Word"
            if len(text) > 200:
                with lock:
                    pdf_ok += 1
            else:
                # 附件取不到（扫描件、二进制 doc、链接失效）→ 退回页面正文块。
                # 但页面正文块常常只是「部长令 + 附件链接」，不是条文，
                # 所以下面还要过一次 looks_like_regulation 才收。
                text = content_div_text(h)
                pages = 0
                kind = "详情页正文块"
                with lock:
                    html_ok += 1
            if not looks_like_regulation(text):
                print(f"  [{i}/{len(todo)}] {rid} 不像条文（{len(text)} 字，{kind}），跳过", flush=True)
                with lock:
                    fail += 1
                return

            rec["fullText"] = text
            rec["summary"] = text[:BODY_PREVIEW]
            rl = rec.setdefault("recordLevel", {})
            rl["charCount"] = len(text)
            rl["textSource"] = kind or "官方文本"
            rl["pdfPages"] = pages
            rl["fullTextNote"] = (
                "正文附于部长令之后，全文收录。民航局规章属《著作权法》第五条"
                "不适用著作权法的国家机关行政文件，可全文转载。")
            with lock:
                ok += 1
                done = ok + fail
            # 每 10 条存一次盘：中途被中断时已完成的进度不会丢
            if done % 10 == 0:
                with lock:
                    Path(args.out).write_text(
                        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
                print(f"  进度 {done}/{len(todo)}（已存盘）", flush=True)
        except Exception as e:              # noqa: BLE001
            print(f"  [{i}/{len(todo)}] {rid} 失败：{type(e).__name__} {str(e)[:80]}", flush=True)
            with lock:
                fail += 1
        time.sleep(DELAY)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        list(ex.map(work, list(enumerate(todo, 1))))

    Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    got = [r for r in records if r.get("fullText")]
    print(f"\n完成：成功 {ok}（PDF {pdf_ok} / 正文块 {html_ok}）失败 {fail}")
    print(f"库内已有全文 {len(got)} / {len(records)} 条")
    if got:
        tot = sum(len(r.get("fullText") or "") for r in got)
        print(f"全文合计 {tot:,} 字符，均 {tot // len(got):,} 字符")


if __name__ == "__main__":
    main()
