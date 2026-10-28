#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rewrite_cn_summaries.py — 重写中国民航局规章的摘要

为什么重写：
    256 条有全文的 CAAC 规章，其 summary 是**正文前 2000 字的原样摘录**
    （recordLevel.summaryKind = "verbatim-excerpt"）。卡片上显示的就是
    「中华人民共和国交通运输部令 / 2025 年第 9 号 / 《X》已于…」这类公文头，
    带换行残留、全角数字与目录点线——读者看不出这条规章是什么、管什么。

改成什么：
    从**正文自身**抽取结构化事实，拼成一句可读的摘要：
        制定机关与令号 · 通过日期与会议届次 · 施行日期 · 章数 · 有效性 · 全文规模
    全部字段都来自该记录自己的 fullText 或 recordLevel，
    不引入外部信息、不生成新事实、不做概括性推断。

纪律：
    · 解析失败的记录**绝不保留原文摘录**，退回「元数据拼接式」摘要
      （与 scripts/fill_cn_summaries.py 同一写法），并在 summaryKind 标注，
      使「哪些是读正文拼的、哪些只是元数据」在数据层可分辨；
    · 幂等：只处理 summaryKind 为 verbatim-excerpt 或空的记录，
      已是 structured-from-text 的不动（避免反复重写造成 diff 噪声）。

用法：
    python scripts/rewrite_cn_summaries.py            # 写入
    python scripts/rewrite_cn_summaries.py --dry-run  # 只看统计与样例
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "data" / "records"
TARGETS = ["regulations_cn_caac.json", "regulations_cn_lexcom.json"]

# 制定机关 + 令号。三种写法都出现过：
#   中华人民共和国交通运输部令 2025 年第 9 号
#   中国民用航空总局令 第 163 号
#   交通运输部令 2026 年第 14 号（「交通运\n输部令」被 PDF 断行切开）
RE_ORDER = re.compile(
    r"(中华人民共和国)?(交通运输部|中国民用航空总局|中国民用航空局|民航总局)令"
    r"[\s\S]{0,12}?(?:(?P<year>\d{4})\s*年\s*)?第?\s*(?P<no>\d+)\s*号")

# 通过日期与会议：已于 2025 年 11 月 21 日经第 28 次部务会议通过
RE_PASSED = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[，,]?\s*经\s*第?\s*(\d+|十[一二三四五六七八九]?|[一二三四五六七八九十]+)"
    r"\s*次\s*(部务会议|局务会议|部务会|局务会)\s*通过")

# 施行日期
RE_EFFECT_FIXED = re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起施行")
RE_EFFECT_ISSUE = re.compile(r"自\s*(?:公布|发布|印发)\s*之日起施行")

# 章节：目录里的「A 章总则」「第一章 总则」「第 121.1 条」
RE_CHAPTER = re.compile(r"(?:^|\n)\s*(?:(?P<latin>[A-Z])\s*章|第(?P<cn>[一二三四五六七八九十]+)\s*章)\s*(?P<name>[^\n]{0,24})")

# 条文条数：第 121.1 条 / 第一条
RE_ARTICLE_DOT = re.compile(r"第\s*\d+\.\d+\s*条")
RE_ARTICLE_CN = re.compile(r"第[一二三四五六七八九十百零]+条")

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10}


def cn2int(s):
    if s is None:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        h, _, t = s.partition("十")
        return (CN_NUM.get(h, 1) if h else 1) * 10 + (CN_NUM.get(t, 0) if t else 0)
    return CN_NUM.get(s)


def fmt_date(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def org_of(m):
    """把「交通运输部」这类机关名规范成对外写法。"""
    raw = m.group(2)
    return {"民航总局": "中国民用航空总局"}.get(raw, raw)


def parse_head(text):
    """从正文前 1500 字抽取公文头事实。抽不到就返回空字典，不做推断。"""
    head = re.sub(r"[ \t\u3000]+", " ", (text or "")[:1500])
    f = {}
    m = RE_ORDER.search(head)
    if m:
        f["organ"] = org_of(m)
        f["orderNo"] = int(m.group("no"))
        if m.group("year"):
            f["orderYear"] = int(m.group("year"))
    m = RE_PASSED.search(head)
    if m:
        f["passedDate"] = fmt_date(m.group(1), m.group(2), m.group(3))
        f["sessionNo"] = cn2int(m.group(4))
        f["sessionKind"] = m.group(5)
    m = RE_EFFECT_FIXED.search(head)
    if m:
        f["effectDate"] = fmt_date(m.group(1), m.group(2), m.group(3))
    elif RE_EFFECT_ISSUE.search(head):
        f["effectNote"] = "自公布之日起施行"
    return f


def _clean_chapter_name(raw):
    """章名只接受「像目录里的一条」，否则宁可不要。

    正文里也会出现「第二章」这类词，后面紧跟的是一整句法条，
    早期版本把它当章名，产出了「第二章 国籍登记证有:人或使用人应向民航局申请…」
    这种东西。判据：短、无句读、不以「条」结尾。
    """
    s = (raw or "").strip()
    s = re.sub(r"[.．·…\s]{2,}.*$", "", s).strip()      # 目录点线与页码
    if not s or len(s) > 20:
        return ""
    if re.search(r"[。，；：、！？（）()《》“”\"']", s):
        return ""
    if re.search(r"第\s*[\d一二三四五六七八九十百.]+\s*条", s):
        return ""
    if s.endswith("条") or s.endswith("的"):
        return ""
    return s


def structure_of(text):
    """数章节与条文规模。章名按 label 去重，只保留第一处像目录的写法。"""
    body = text or ""
    seen = {}
    for m in RE_CHAPTER.finditer(body[:8000]):
        label = (m.group("latin") + " 章") if m.group("latin") else ("第" + m.group("cn") + "章")
        if label in seen:
            continue
        nm = _clean_chapter_name(m.group("name"))
        seen[label] = nm          # 章数按 label 计，名字可能为空
    chapters = [(lb, nm) for lb, nm in seen.items()]
    n_art = len(set(RE_ARTICLE_DOT.findall(body))) or len(set(RE_ARTICLE_CN.findall(body)))
    return chapters, n_art


def compose(rec, facts, chapters, n_art):
    """把事实拼成一句摘要。缺的字段不写，绝不填空。"""
    rl = rec.get("recordLevel") or {}
    title = (rec.get("title") or "").strip()
    ccar = rl.get("ccarNumber") or ""
    parts = []

    if facts.get("organ") and facts.get("orderNo"):
        y = facts.get("orderYear")
        if y:
            parts.append(f"由{facts['organ']}以 {y} 年第 {facts['orderNo']} 号令公布")
        else:
            parts.append(f"由{facts['organ']}以第 {facts['orderNo']} 号令公布")
    if facts.get("passedDate"):
        s = f"{facts['passedDate']} 经"
        if facts.get("sessionNo"):
            s += f"第 {facts['sessionNo']} 次"
        s += facts.get("sessionKind") or "会议"
        s += "通过"
        parts.append(s)
    if facts.get("effectDate"):
        parts.append(f"自 {facts['effectDate']} 起施行")
    elif facts.get("effectNote"):
        parts.append(facts["effectNote"])

    if chapters:
        named = "、".join(f"{lb} {nm}" for lb, nm in chapters[:3] if nm)
        seg = f"共 {len(chapters)} 章"
        if named:
            seg += f"（{named}{'等' if len(chapters) > 3 else ''}）"
        parts.append(seg)
    if n_art:
        parts.append(f"计 {n_art} 条")

    head = f"《{title.replace('《', '〈').replace('》', '〉')}》" + (f"（{ccar}）" if ccar and ccar not in title else "")
    tail = []
    if rl.get("validity"):
        tail.append(f"官方规章栏目标注状态：{rl['validity']}")
    if rl.get("issuingDepartment"):
        tail.append(f"发文部门：{rl['issuingDepartment']}")
    if rl.get("charCount") and rl.get("pdfPages"):
        tail.append(f"本站收录全文 {rl['charCount']:,} 字（PDF {rl['pdfPages']} 页）")
    elif rl.get("charCount"):
        tail.append(f"本站收录全文 {rl['charCount']:,} 字")

    s = head
    if parts:
        s += "：" + "，".join(parts)
    s += "。"
    if tail:
        s += "；".join(tail) + "。"
    return s


def compose_meta(rec):
    """解析失败时的兜底：只用元数据拼接（与 fill_cn_summaries.py 同款），
    绝不把正文原样摘录当成摘要。"""
    rl = rec.get("recordLevel") or {}
    d = rec.get("dates") or {}
    title = (rec.get("title") or "").strip().replace("《", "〈").replace("》", "〉")
    s = f"《{title}》"
    if rl.get("ccarNumber"):
        s += f"（{rl['ccarNumber']}）"
    if d.get("publicationDate"):
        s += f"，{d['publicationDate']} 公布"
    facts = []
    if rl.get("validity"):
        facts.append(f"官方规章栏目标注状态：{rl['validity']}")
    if rl.get("issuingDepartment"):
        facts.append(f"发文部门：{rl['issuingDepartment']}")
    if rl.get("charCount"):
        facts.append(f"本站收录全文 {rl['charCount']:,} 字")
    s += "。" + ("；".join(facts) + "。" if facts else "")
    return s


def main():
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    total = done_text = done_meta = skipped = 0
    samples = []

    for name in TARGETS:
        p = RECORDS / name
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        recs = data if isinstance(data, list) else data.get("records", [])
        changed = False
        for rec in recs:
            if not isinstance(rec, dict):
                continue
            total += 1
            rl = rec.setdefault("recordLevel", {})
            kind = rl.get("summaryKind") or ""
            # 幂等：已重写过的不再动（--force 用于修正生成规则后重刷）
            if kind in ("structured-from-text", "metadata-composed") and not force:
                skipped += 1
                continue
            text = rec.get("fullText") or ""
            old = (rec.get("summary") or "").strip()
            if not text:
                # 无全文：只在缺摘要时用元数据兜底
                if old:
                    skipped += 1
                    continue
                new = compose_meta(rec)
                rl["summaryKind"] = "metadata-composed"
                done_meta += 1
            else:
                facts = parse_head(text)
                chapters, n_art = structure_of(text)
                new = compose(rec, facts, chapters, n_art)
                if facts or chapters:
                    rl["summaryKind"] = "structured-from-text"
                    rl["summarySource"] = "本记录 fullText 的公文头与目录"
                    done_text += 1
                else:
                    new = compose_meta(rec)
                    rl["summaryKind"] = "metadata-composed"
                    done_meta += 1
                rl["summaryChars"] = len(new)
            rec["summary"] = new
            changed = True
            if len(samples) < 6:
                samples.append((rec.get("citationString") or rec.get("recordId"), old[:60], new))
        if changed and not dry:
            from jsonio import save_json
            save_json(p, data)
            print(f"  已写入 {name}")

    print(f"\n扫描 {total} 条｜读正文拼摘要 {done_text} 条｜元数据兜底 {done_meta} 条｜跳过 {skipped} 条")
    print("\n样例（旧 → 新）：")
    for cid, old, new in samples:
        print(f"\n  [{cid}]")
        print(f"    旧：{old}…")
        print(f"    新：{new}")


if __name__ == "__main__":
    main()
