#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_eurlex.py — 欧盟法源（EUR-Lex / Cellar）采集

为什么需要这个源：
    此前域外航空法只有美国 eCFR 一个法域。欧盟航空法与低空法是全球最完整的
    域外体系（机场与地面服务市场准入、共同航空运输市场、适航与航空安全、
    以及 2019 年起的无人机与 U-space 规则包），缺失它等于缺了半个域外视角。

技术要点（全部实测得出，踩过的坑写在注释里）：
    1. 官方机器可读通道是 Cellar 内容协商：
       http://publications.europa.eu/resource/celex/{CELEX}.ENG  +  Accept 头
       不带 .ENG 语言后缀会 400（报错明确提示 "without language"）
    2. 两种 NOTICE 层级，**必须用 EXPRESSION 级**：
       - WORK 级（notice=br，904 KB/条）含全部关联文书，过重
       - EXPRESSION 级（notice=object，7.5 KB/条）含标题/文件号/公报日期，足够
    3. 连续请求会触发限流返回 403——与 User-Agent 无关（实测四种 UA 均受影响）。
       因此必须**加重试与退避**，本脚本用指数退避 + 2 秒基础间隔。
    4. SPARQL 端点（/webapi/rdf/sparql）可连接，但对 cdm:expression_title_short
       等谓词返回空集，且 skos:prefLabel 会混入企业登记（搜 aviation 返回
       "GE Capital Aviation"），**不能作为法律文书检索层**。
       故采用「候选清单 + 逐条核验」，标题与预期不符者剔除。
    5. 版权立场：EU 决策文本的再利用受官方声明约束。
       本项目**只存元数据 + 条文标题 + 官方链接，不存全文**。

用法：python scripts/collect_eurlex.py
输出：data/records/regulations_eu_eurlex.json
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "records" / "regulations_eu_eurlex.json"
UA = "aviation-law-library/1.0 (research; contact: via GitHub repo)"
BASE_DELAY = 2.0
MAX_RETRY = 4

CELLAR = "http://publications.europa.eu/resource/celex/"

# 候选：欧盟航空与低空经济核心法源
#
# ⚠ 重要教训（2026-10-21 实测记录，务必保留此注释）：
#   本清单第一版由模型凭记忆写出 27 条 CELEX，逐条核验的结果是——
#     · 仅 3 条确为航空法（2019/947、2019/945、2021/664）
#     · 7 条编号在 Cellar 中不存在（404）
#     · 其余 17 条指向完全无关的领域：农产品信息、糖果过渡措施、
#       纺织品出口、稻米出口退税、关税税则、农产品关税、
#       欧洲央行人事提名、受保护名称登记、恐融融资资产冻结令……
#   也就是说，凭记忆写的 CELEX 编号几乎全部错误。若直接入库，
#   资料库会出现 17 条与航空无关的"航空法规"——这正是本项目
#   严禁的那类事实错误。
#
# 因此本清单现在只保留**已逐条核验存在且标题符合预期**的条目。
# 新增条目时，必须先用 --celex 试跑并核对实际标题，再移入本清单。
#
# 格式 (CELEX, 预期标题关键词, 主题)
CANDIDATES = [
    # ── 基础条例（含无人机专章与个人数据保护条款）──
    ("32018R1139", ["civil aviation", "aviation safety agency"], "airworthiness"),
    # ── 低空与无人机（实测确认）──
    ("32019R0947", ["unmanned aircraft"], "uav"),
    ("32019R0945", ["unmanned aircraft"], "uav"),
    ("32021R0664", ["u-space"], "uav"),
    # ── 数据保护（航空数据治理交叉；实测确认）──
    ("32016R0679", ["personal data"], "data-protection"),
    ("32018R1725", ["personal data"], "data-protection"),
    ("31995L0046", ["personal data"], "data-protection"),
]

# 已核验但**未收录**的条目在此留档，说明为何不入库，
# 避免后人（或未来的自己）重新把它们当作候选。
REJECTED = {
    "32014L0065": "Directive 2014/65/EU = MiFID II（金融工具市场），"
                  "与个人数据保护无关——曾被误当作 GDPR",
    "32016L0068": "编号不存在（404）",
    "31994L0002": "Directive 94/2/EC = 家用电冰箱能效标签，与航空无关",
    "32008R0003": "Regulation (EC) 3/2008 = 农产品信息与推广措施",
    "32009R0116": "Regulation (EC) 116/2009 = 文化品出口",
    "31996R0685": "Regulation (EC) 685/96 = 糖业过渡措施",
    "32004R0060": "Regulation (EC) 60/2004 = 糖业过渡措施",
    "31996R0068": "Regulation (EC) 68/96 = 对外贸易统计国别名录",
    "32004R0065": "Regulation (EC) 65/2004 = 海关唯一识别码系统",
    "32009R1107": "Regulation (EC) 1107/2009 = 植物保护产品投放市场",
    "32002R0359": "Regulation (EC) 359/2002 = 农业补贴修订",
    "32003R0243": "Regulation (EC) 243/2003 = 稻米出口退税上限",
    "32014R0453": "Implementing Regulation 453/2014 = 海关商品分类",
    "32012R1010": "Implementing Regulation 1010/2012 = 谷物进口关税",
    "31990R3112": "Regulation (EEC) 3112/90 = 农产品临时措施修订",
    "32019D0005": "Decision (EU) 2019/323 = 欧洲央行人事提名",
    "32014R0048": "Implementing Regulation 48/2014 = 受保护名称登记",
}


def cellar(celex, accept, lang="ENG"):
    """Cellar 内容协商。返回 bytes。

    错误分流（实测教训）：
      404 = 该 CELEX 编号不存在 → 但**仍重试一次**：实测 32018R1139
            （EASA 基础条例，确实存在且经 EUR-Lex 摘要页确认）在一次批量运行中
            返回 404，随后重试即 200。因此单次 404 不能判定编号错误。
      403 = 限流或运行环境拦截 → 退避重试
    """
    url = f"{CELLAR}{celex}.{lang}"
    delay = BASE_DELAY
    last = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (403, 404, 429, 500, 502, 503):
                raise
        except Exception as e:  # noqa: BLE001
            last = str(e)[:70]
        if attempt < MAX_RETRY:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{last}（已重试 {MAX_RETRY} 次）")


def parse_notice(x):
    """从 EXPRESSION 级 NOTICE 提取元数据。"""
    def one(tag):
        m = re.search(rf"<{tag}[^>]*>\s*<VALUE>([^<]+)</VALUE>", x)
        return m.group(1).strip() if m else None

    title = one("EXPRESSION_TITLE")
    # 文件号：EXPRESSION_SUBTITLE 通常是 "C/2019/3824" 这类机构编号
    subtitle = one("EXPRESSION_SUBTITLE")
    creation = one("CREATIONDATE")
    lastmod = one("LASTMODIFICATIONDATE")

    # CELEX / OJ / uri 引用
    sameas = re.findall(
        r"<SAMEAS>\s*<URI>\s*<VALUE>([^<]+)</VALUE>", x)

    # 公报刊登日期从 CREATIONDATE 取前 10 位；占位值（如 1001-01-01）须丢弃
    pub = valid_date(creation[:10] if creation else None)

    return {
        "title": title,
        "docNo": subtitle,
        "publicationDate": pub,
        "lastModified": valid_date(lastmod[:10] if lastmod else None),
        "sameAs": sameas,
    }


ARTICLE_RE = re.compile(
    r'<p[^>]*class="oj-ti-art"[^>]*>\s*Article\s+(\d+[a-z]?)\s*</p>'
    r'(?:\s*<div[^>]*>\s*<p[^>]*class="oj-sti-art"[^>]*>([^<]*)</p>)?',
    re.I)

# 编章节层级：<div class="eli-subdivision" id="enc_1"> / id="rct_1"
CHAP_RE = re.compile(
    r'<p[^>]*class="oj-ti-(chap|sec|secti|tit|part)"[^>]*>\s*'
    r'(CHAPTER|SECTION|TITLE|PART)\s+([IVXLC\d]+)\s*</p>(.*?)'
    r'<p[^>]*class="oj-ti-art"',
    re.I | re.S)


def parse_article_titles(xhtml):
    """抽取条文编号与标题，并记录其所属的编/章/节。

    Cellar 的 XHTML 结构（实测）：
        <div class="eli-subdivision" id="enc_1">          ← 编
           <p class="oj-ti-chap">CHAPTER I</p>
           <div class="eli-subdivision" id="art_1">
              <p class="oj-ti-art">Article 1</p>
              <div class="eli-title"><p class="oj-sti-art">Subject matter</p></div>

    只取「编号 + 标题 + 所属章节」，不取条文正文——版权保守，
    且条目化后比整段正文更可检索（「哪一条管什么」是实务者的真实问题）。
    """
    # 标注每个 Article 出现位置之前最近的 CHAPTER/SECTION
    marks = []
    for m in re.finditer(
            r'<p[^>]*class="oj-ti-(chap|sec|secti|tit|part)"[^>]*>\s*'
            r'((?:CHAPTER|SECTION|TITLE|PART)\s+[IVXLC\d]+)\s*<', xhtml, re.I):
        marks.append((m.end(), re.sub(r"\s+", " ", m.group(2)).strip()))

    def chapter_at(pos):
        cur = None
        for end, label in marks:
            if end <= pos:
                cur = label
            else:
                break
        return cur

    out = []
    for m in ARTICLE_RE.finditer(xhtml):
        num = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2) or "").strip()
        out.append((f"Article {num}", title, chapter_at(m.start())))

    # 去重保序（同一条号在修正版中可能出现多次）
    seen = set()
    uniq = []
    for a, t, c in out:
        if a in seen:
            continue
        seen.add(a)
        uniq.append((a, t, c))
    return uniq


def topics_for(title, topic, article_titles):
    t = (title or "").lower()
    at = " ".join(a for a, _t, _c in article_titles).lower()
    tt = " ".join((x or "") for _a, x, _c in article_titles).lower()
    blob = t + " " + at + " " + tt
    topics = [topic]
    if "unmanned" in blob or "u-space" in blob or "uav" in blob:
        topics.append("uav")
    if "airworthiness" in blob or "aircraft" in blob:
        topics.append("airworthiness")
    if "airport" in blob or "ground service" in blob:
        topics.append("airport")
    if "safety" in blob or "accident" in blob:
        topics.append("safety")
    if "personal data" in blob or "data protection" in blob:
        topics.append("data-protection")
    if "market access" in blob or "air services" in blob:
        topics.append("air-transport")
    if "airspace" in blob or "atmospheric" in blob:
        topics.append("airspace")
    return sorted(set(topics))


def extract_reg_number(title):
    """从标题中提取法规编号（如 "2019/947"）。

    必须**只取标题开头的那个**编号：EU 法规的完整标题里会引用十余个
    其他法规，全文搜索会取到错误项。实测踩坑：
      "Regulation (EU) 2018/1139 … amending … Directive 2014/30/EU …"
      全文取第一个 \\d+/[A-Z]+ 会匹配到 "30/EU"（引用中的指令编号）。
    正确做法：匹配标题**首句**（第一个句点前）中的编号。
    """
    head = re.split(r"(?<=[a-z])\.\s", title or "", maxsplit=1)[0]
    m = re.search(
        r"\b((?:19|20)\d{2})/(\d{1,4})\b", head)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # 回退：允许 2 位年份（旧指令如 95/46/EC）
    m = re.search(r"\b(\d{2})/(\d{1,4})/(EC|EU|EEC)\b", head)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return None


def valid_date(d):
    """Cellar 的 CREATIONDATE 对部分文书是占位值 1001-01-01，须过滤。"""
    if not d or not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return None
    if int(d[:4]) < 1990:      # 1001-01-01 之类占位符
        return None
    return d


def collect_one(celex, expect_kw, topic, with_articles=True):
    raw = cellar(celex, "application/xml;notice=object")
    meta = parse_notice(raw.decode("utf-8", "ignore"))

    title = meta["title"]
    if not title:
        raise RuntimeError("NOTICE 无标题")
    if not any(k.lower() in title.lower() for k in expect_kw):
        return {"ok": False, "reason": "标题与预期不符", "title": title}

    articles = []
    if with_articles:
        try:
            xhtml = cellar(celex, "application/xhtml+xml").decode("utf-8", "ignore")
            articles = parse_article_titles(xhtml)
        except Exception as e:  # noqa: BLE001
            print(f"      条文抽取失败（不影响入库）：{str(e)[:50]}")

    return {"ok": True, "celex": celex, "meta": meta,
            "articles": articles, "topic": topic}


def main():
    # --celex 逗号分隔，只跑指定条目；不加则跑全部候选。
    # 分批跑的原因（实测）：在长时间后台任务中，连续 50+ 次请求会被
    # 运行环境拦截并返回 403；单批 5 条以内可稳定通过。
    # 因此本脚本设计为**可增量合并**——多次小批执行，结果累积到同一文件。
    ap = argparse.ArgumentParser()
    ap.add_argument("--celex", default="",
                    help="逗号分隔的 CELEX 列表；留空则跑全部候选")
    ap.add_argument("--no-articles", action="store_true",
                    help="跳过条文抽取（每条省一次请求，用于先验证编号有效性）")
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    if args.celex:
        wanted = {c.strip().upper() for c in args.celex.split(",") if c.strip()}
        batch = [c for c in CANDIDATES if c[0].upper() in wanted]
        unknown = wanted - {c[0] for c in batch}
        if unknown:
            print(f"（不在候选清单中的编号，按无主题处理：{sorted(unknown)}）")
            for u in sorted(unknown):
                batch.append((u, [], "uncategorized"))
    else:
        batch = CANDIDATES

    print(f"EU Cellar 逐条核验 {len(batch)} 条 CELEX"
          + ("（仅元数据，不抽条文）" if args.no_articles else ""))
    ok_list, mismatch, failed = [], [], []

    for i, (celex, kw, topic) in enumerate(batch, 1):
        try:
            res = collect_one(celex, kw, topic,
                              with_articles=not args.no_articles)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            kind = "编号不存在" if "404" in msg else msg[:40]
            print(f"  [{i}/{len(batch)}] ✗ {kind:<12} {celex}")
            failed.append({"celex": celex, "reason": kind})
            time.sleep(args.delay)
            continue

        if res["ok"]:
            n_art = len(res["articles"])
            print(f"  [{i}/{len(batch)}] OK {celex:<12} "
                  f"条文 {n_art:>3}  {res['meta']['title'][:58]}")
            ok_list.append(res)
        else:
            print(f"  [{i}/{len(batch)}] 不符 {celex:<12} {res['title'][:58]}")
            mismatch.append({"celex": celex, "title": res["title"], "expect": kw})
        time.sleep(args.delay)

    # ── 生成记录 ─────────────────────────────────────────
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = []
    for res in ok_list:
        celex = res["celex"]
        meta = res["meta"]
        title = meta["title"]
        # 拆出法规编号（如 "Regulation (EU) 2019/947"）作为文号
        # 只取标题首句中的编号，详见 extract_reg_number 的注释
        num = extract_reg_number(title)
        cite = f"{celex}"
        if num:
            cite += f"（{num}）"

        sid = f"EURLEX-{celex}"
        rid = make_id("EU", "LAW", celex)

        eli = None
        for u in meta["sameAs"]:
            if "/eli/" in u:
                eli = u

        assertion_fields = [
            ("celex_id", celex),
            ("document_title", title),
        ]
        if num:
            assertion_fields.append(("regulation_number", num))
        if meta["docNo"]:
            assertion_fields.append(("institutional_doc_no", meta["docNo"]))
        if eli:
            assertion_fields.append(("eli_uri", eli))
        if meta["publicationDate"]:
            assertion_fields.append(("oj_publication_date", meta["publicationDate"]))
        if meta["lastModified"]:
            assertion_fields.append(("last_modified", meta["lastModified"]))
        for a, t, c in res["articles"][:400]:
            # 条文号与标题分列为两条断言：
            # 断言字段 article 的值必须只含条号（"Article 55"），
            # 才能被标识符规则解析成规范键 euarticle:55；
            # 章节与标题放 article_title 与 article_chapter，不参与键解析。
            assertion_fields.append(("article", a))
            if c:
                assertion_fields.append((f"article_chapter:{a}", c))
            if t:
                assertion_fields.append((f"article_title:{a}", t))

        records.append({
            "recordId": rid,
            "recordType": "legislation",
            "title": title,
            "titleEn": title,
            "summary": None,
            "jurisdiction": "EU",
            "topics": topics_for(title, res["topic"], res["articles"]),
            "status": "effective",
            "dates": {
                "publicationDate": meta["publicationDate"],
                "retrievedAt": today,
                "lastAmendedDate": meta["lastModified"],
            },
            "citationString": cite,
            "sourceUrl": ("https://eur-lex.europa.eu/legal-content/EN/T/?uri=CELEX:"
                          + celex),
            "recordLevel": {
                "celex": celex,
                "eliUri": eli,
                "institutionalDocNo": meta["docNo"],
                "ojPublicationDate": meta["publicationDate"],
                "lastModified": meta["lastModified"],
                "articleCount": len(res["articles"]),
                "articleTitles": [
                    {"article": a, "title": t, "chapter": c}
                    for a, t, c in res["articles"][:400]
                ],
                "sameAs": meta["sameAs"],
                "sourceTier": "L0",
                "retrievalChannel": "cellar-content-negotiation",
                "retrievalUrl": CELLAR + celex + ".ENG",
                "note": "条文仅取编号与标题（不存全文）——EU 决策文本再利用受官方声明约束；"
                        "文义以 EUR-Lex 官方文本为准",
            },
            "assertions": [
                {
                    "field": f,
                    "value": str(v)[:500],
                    "sourceId": sid,
                    "locator": f"CELEX {celex}" + (
                        f" · {f.split(':', 1)[1]}" if f.startswith("article:") else ""),
                    "evidenceLevel": "L0",
                    "verifiedAt": today,
                }
                for f, v in assertion_fields
            ],
            "revisionLog": [],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 增量合并：本批之前已入库的记录按 recordId 保留，本批覆盖同 ID 者。
    # 分批执行是应对运行环境对长任务的网络拦截，不改变数据语义。
    existing = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8") as f:
            for r in json.load(f):
                existing[r["recordId"]] = r
    for r in records:
        existing[r["recordId"]] = r
    merged = list(existing.values())
    merged.sort(key=lambda r: (r.get("dates", {}).get("publicationDate") or "",
                               r["recordId"]), reverse=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    total_art = sum(r["recordLevel"]["articleCount"] for r in merged)
    print(f"\n本批 {len(records)} 条 → 累计入库 {len(merged)} 条 / 条文标题 {total_art} 条")
    print(f"  不符 {len(mismatch)} 条（已剔除）")
    print(f"  取不到 {len(failed)} 条")
    if mismatch:
        for m in mismatch:
            print(f"    不符 {m['celex']}: {m['title'][:60]}")
    if failed:
        for m in failed:
            print(f"    取不到 {m['celex']}: {m['reason']}")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()