#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_browse.py — 生成首屏精简索引与按需详情文件

为什么需要这一步：
    manifest.json 承载全部 4199 条记录、约 16 MB。公开站首屏若加载全量，
    在 GitHub Pages（且读者主要在境内）会慢到不可用。
    但检索需要全文——eCFR 的条文正文里才有 "remote identification" 这类词。

解法（不牺牲检索能力）：
    ① browse.json —— 首屏加载。每条记录只保留列表渲染与检索所需字段，
       并把「全文去重后的检索词集合」预先抽出来存为 terms。
       前端用 terms 建倒排，检索召回与全量一致。
    ② details/<桶>/<recordId>.json —— 点击「展开」时按需拉取完整正文与断言。

体积对比（实测后写入 README）：
    全量 manifest ≈ 16 MB → browse.json ≈ 2~3 MB（gzip 后约 1/4）
    详情按需加载，单次仅数十 KB。

约束：terms 的抽取规则必须与前端 tokenizer 一致，
      否则会出现「索引里有词、正文里搜不到」的错觉。
      规则见 TERMS_TOKEN_RE，与 site/js/search.js 的 tokenize 对齐。

用法：python scripts/build_browse.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DETAILS = DATA / "details"

# 与 site/js/search.js 的 tokenize 对齐（必须严格一致，否则精简索引与全量索引
# 召回会不一致——表现为「明明库里���，搜不到」）：
#   英文/数字：原样 + 去分隔符版本 + 数字段单独抽出
#   中文：长度 1 的段保留单字；长度 ≥2 做二元切分；长度 ≥3 另留整词
LATIN_RE = re.compile(r"[a-z0-9][a-z0-9\-._/]*")
CJK_RE = re.compile(r"[一-鿿]+")

# 检索时忽略的高频虚词（英文停用词子集）——仅用于 terms 体积裁剪，
# 不影响召回（真正的召回由倒排索引的 AND 交集决定）
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "has", "have", "had", "not", "but", "its", "his", "her",
    "which", "shall", "will", "would", "may", "can", "such", "other",
    "than", "into", "upon", "been", "being", "there", "their", "they",
    "must", "does", "any", "all", "each", "who", "whom", "under", "over",
    "a", "an", "as", "at", "be", "by", "in", "of", "on", "or", "to", "is",
    "it", "no", "so", "up", "we", "if",
}

SUMMARY_PREVIEW = 220

# 参与规范键解析的断言字段——与 site/js/search.js 的 KEY_REF_FIELDS 一致
KEY_REF_FIELDS = {
    "cfr_references", "docket_ids", "document_number", "citation",
    "cfr_part", "cfr_section", "ccar_number",
    # 欧盟法源
    "celex_id", "regulation_number", "article",
}


def tokenize(text):
    """与前端 tokenize 对齐的切词。

    严格一致是硬要求：terms 一旦与前端切词规则有出入，就会出现
    「库里明明有，搜不到」的错觉——这比少几条命中严重得多。
    实测教训：曾按词长裁剪 terms，导致 "787"、"part 108" 这类
    稀有但关键的标识符被裁掉，召回从 25 条掉到 0 条。
    因此此处不做任何裁剪。
    """
    t = str(text or "").lower()
    out = set()

    for w in LATIN_RE.findall(t):
        if len(w) >= 2:
            out.add(w)
        bare = re.sub(r"[-._/]", "", w)
        if len(bare) >= 2 and bare != w:
            out.add(bare)
        for n in re.findall(r"\d+", w):
            if len(n) >= 2 and n != w:
                out.add(n)

    for m in CJK_RE.finditer(t):
        seg = m.group(0)
        if len(seg) == 1:
            out.add(seg)
        else:
            for i in range(len(seg) - 1):
                out.add(seg[i:i + 2])
            if len(seg) >= 3:
                out.add(seg)
    return out


def terms_of(rec):
    """抽取一条记录参与检索的词集合。

    与前端 buildIndex 的取材范围一致：
      标题、英文名、摘要、文号、法域、类型、主题、断言值
    """
    parts = [
        rec.get("title"), rec.get("titleEn"), rec.get("summary"),
        rec.get("citationString"), rec.get("jurisdiction"), rec.get("recordType"),
        " ".join(rec.get("topics") or []),
    ]
    for a in rec.get("assertions") or []:
        parts.append(a.get("value"))
    # 断言值理论上都是字符串，但一条数字值（如 pages: 46）就足以让整次构建崩掉，
    # 而崩的是 4225 条全部记录。这里统一转字符串，别让单条脏数据毁掉构建。
    return tokenize(" ".join(str(p) for p in parts if p not in (None, "")))


def brief(rec, terms):
    """首屏用精简记录。

    refValues：保留全部断言值（去重）。这些值是规范键的原料——
    丢了它们，`cfr:14:89`、`ccar:290` 这类精确查会全部失效。
    代价约 78 字符/记录，远小于携带完整 assertions 的代价。
    """
    lvl = None
    ref_values = []
    seen = set()
    levels = []
    for a in rec.get("assertions") or []:
        v = str(a.get("value") or "").strip()
        if v and v not in seen:
            seen.add(v)
            ref_values.append(v)
        if a.get("evidenceLevel") and not lvl:
            lvl = a.get("evidenceLevel")
        if a.get("evidenceLevel") and a["evidenceLevel"] not in levels:
            levels.append(a["evidenceLevel"])

    rl = rec.get("recordLevel") or {}
    d = rec.get("dates") or {}

    # keyRefs：能产生规范键的断言值（供界面显示「可精确检索：14 CFR 39」）
    # 字段白名单与 site/js/search.js 的 KEY_REF_FIELDS 保持一致
    key_refs = []
    seen_k = set()
    for a in rec.get("assertions") or []:
        if a.get("field") not in KEY_REF_FIELDS:
            continue
        v = str(a.get("value") or "").strip()
        if v and v not in seen_k:
            seen_k.add(v)
            key_refs.append(v)

    out = {
        "recordId": rec["recordId"],
        "recordType": rec.get("recordType"),
        "title": rec.get("title"),
        "citationString": rec.get("citationString"),
        "jurisdiction": rec.get("jurisdiction"),
        "status": rec.get("status"),
        "topics": rec.get("topics") or [],
        "dates": {k: d.get(k) for k in
                  ("publicationDate", "effectiveDate", "decisionDate",
                   "lastAmendedDate") if d.get(k)},
        "evidenceLevel": lvl,
        # 该记录涉及的全部证据等级（不止最低的那个）：证据等级筛选要按
        # 「记录含此等级」判定，只给最低级会让 L3 记录在 L3 筛选下消失。
        "evidenceLevels": levels,
        "sourceUrl": rec.get("sourceUrl"),
        "summary": (rec.get("summary") or "")[:SUMMARY_PREVIEW],
        # 全文标记：卡片上标出「有全文 N 字」，让读者知道详情里有完整条文可读
        "hasFullText": bool(rec.get("fullText")),
        # 注意：**terms 不在这里**。检索词占记录字节的 63%，把它单独放进
        # data/terms.json，首屏只加载列表包、索引随后台补齐（见 main()）。
        "refValues": ref_values,
        "keyRefs": key_refs,
    }
    # 列表卡要显示的少量专有字段
    keep = ("ccarNumber", "validity", "lawCategoryName", "issuingDepartment",
            "countryName", "versionStatusName", "cfrPart", "cfrSection",
            "partCitation",
            # 欧盟法源
            "celex", "eliUri", "institutionalDocNo", "articleCount",
            # 案例性质（已决处罚 / 监管调查）必须进首屏，否则读者会把「调查」当成「已处罚」
            "caseOutcome", "sanctionsVerified",
            # ICAO 附件：中文标准名与分卷结构须进首屏，否则中文读者看不到附件叫什么
            "titleZh", "icaoNumber", "edition", "subVolumes",
            # 全文长度：卡片显示「全文 N 字」
            "charCount", "textStatus")
    for k in keep:
        if rl.get(k) is not None:
            out[k] = rl[k]
        elif rec.get(k) is not None:   # 部分字段写在记录顶层（如 sanctionsVerified）
            out[k] = rec[k]
    # 罚款与待核验标记
    if rec.get("penalty"):
        out["penalty"] = rec["penalty"]
    # 决定日缺失的成因，必须进首屏：卡片写「未知（待核验）」时，
    # 「链接指错」「页面失效」「机构未公布」的可靠性含义完全不同。
    gap = rl.get("dateGap") or {}
    if gap.get("reason"):
        out["dateGapReason"] = gap["reason"]
    # 事实有几分依据：卡片上「决定日未确认」必须同时交代有没有文书来源，
    # 否则会被读成「整条案件没有依据」。
    # 记录级核验状态：前端筛选「仅待核验」要用，而精简索引不带整个 recordLevel
    if rl.get("verificationStatus") == "pending":
        out["verificationPending"] = True
    ev = rl.get("evidenceStatus") or {}
    fs = ev.get("factSource") or {}
    if fs.get("evidenceLevel"):
        out["factSourceLevel"] = fs["evidenceLevel"]
        out["factSourceType"] = fs.get("documentType")
    if rec.get("recordType") == "case" and not d.get("decisionDate"):
        out["pendingDecisionDate"] = True
    # FR 文件号：同一份 Federal Register 引注可能对应两个文件（两份规则可同页起排），
    # 卡片上只显示「91 FR 37787」读者分不出是哪一份，附上文件号才可区分。
    for a in rec.get("assertions") or []:
        if a.get("field") == "document_number":
            v = str(a.get("value") or "").strip()
            if v:
                out["documentNumber"] = v
            break
    return out


def bucket_of(record_id):
    """详情文件分桶：避免单目录文件过多。"""
    h = sum(ord(c) for c in record_id)
    return f"{h % 32:02d}"


def main():
    manifest_path = DATA / "manifest.json"
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    records = manifest.get("records") or []

    # 详情文件采用**增量写入**：只创建/覆盖本次涉及的 recordId 对应文件，
    # 不做整目录删除。原因有二：
    #   ① 整目录 rmtree 是破坏性操作，在受限环境会被安全策略拦截
    #   ② 删除全部重建会让每次构建都重写 4000+ 文件，git 上产生巨大 diff
    # 孤儿文件（记录已从 manifest 移除时残留）由 --prune 显式清理，
    # 且只删「不在当前 manifest 中」的那些，不触碰有效数据。
    DETAILS.mkdir(parents=True, exist_ok=True)
    live_ids = {r["recordId"] for r in records}

    if "--prune" in sys.argv:
        removed = 0
        for p in DETAILS.rglob("*.json"):
            if p.stem not in live_ids:
                p.unlink()
                removed += 1
        if removed:
            print(f"清理孤儿详情文件 {removed} 个")

    briefs = []
    terms_list = []
    detail_files = 0
    for rec in records:
        t = terms_of(rec)
        terms_list.append(sorted(t))
        briefs.append(brief(rec, t))
        # 详情：去掉已在精简索引里的 terms，其余原样保留
        detail = {k: v for k, v in rec.items() if k != "assertions"}
        detail["assertions"] = rec.get("assertions") or []
        b = DETAILS / bucket_of(rec["recordId"])
        b.mkdir(parents=True, exist_ok=True)
        with (b / f"{rec['recordId']}.json").open("w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False, separators=(",", ":"))
        detail_files += 1

    browse = {
        "meta": {
            **manifest.get("meta", {}),
            "browseGeneratedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "detailFilePattern": "data/details/{bucket}/{recordId}.json",
            "detailBuckets": 32,
            "termsFile": "data/terms.json",
        },
        "records": briefs,
    }
    out = DATA / "browse.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(browse, f, ensure_ascii=False, separators=(",", ":"))

    # 检索词单独成包：它占记录字节的 63%，与列表混在一起会让首屏多传 1 MB 上下。
    # 拆开后首屏先渲染列表，索引随后台补齐——用户看到的列表几乎立刻出现，
    # 检索框在索引就绪前显示加载态。
    terms_pack = {
        "ids": [b["recordId"] for b in briefs],
        "terms": terms_list,
    }
    terms_out = DATA / "terms.json"
    with terms_out.open("w", encoding="utf-8") as f:
        json.dump(terms_pack, f, ensure_ascii=False, separators=(",", ":"))

    full_mb = manifest_path.stat().st_size / 1024 / 1024
    browse_mb = out.stat().st_size / 1024 / 1024
    terms_mb = terms_out.stat().st_size / 1024 / 1024
    avg_terms = sum(len(t) for t in terms_list) / max(1, len(terms_list))
    detail_sizes = [p.stat().st_size for p in DETAILS.rglob("*.json")]
    avg_detail = sum(detail_sizes) / max(1, len(detail_sizes))

    print(f"browse 索引：{len(briefs)} 条 → {out.relative_to(ROOT)}")
    print(f"  体积 {browse_mb:.2f} MB（原 manifest {full_mb:.2f} MB，"
          f"降至 {browse_mb / full_mb:.0%}）")
    print(f"  平均检索词 {avg_terms:.1f} 个/条")
    print(f"检索词包：{terms_out.relative_to(ROOT)}  {terms_mb:.2f} MB"
          f"（首屏后加载）")
    print(f"详情文件：{detail_files} 个 → {DETAILS.relative_to(ROOT)}/")
    print(f"  单文件平均 {avg_detail / 1024:.1f} KB"
          f"（合计 {sum(detail_sizes) / 1024 / 1024:.1f} MB，按需加载）")


if __name__ == "__main__":
    main()
