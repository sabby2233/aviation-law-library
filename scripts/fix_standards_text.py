#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_standards_text.py — 修标准类记录的「点进去没内容」

两个真实缺陷：
1. 19 条 ICAO 记录的 edition 断言值是 booklet 的印制年份
   （`2005-06 (ICAO Annexes 1 to 18 booklet)`），而 recordLevel.edition 才是
   逐条核验过的现行版次。详情页展示的是断言表，所以读者看到的是错版次。
2. 19 条 ICAO + 18 条外文译本标准的 summary 为空，卡片无摘要、详情只有字段表。

做法（全部基于既有字段确定性拼接，不使用模型生成）：
- 更正 edition 断言，旧值写入 previousValue 留痕，locator 注明更正依据与日期
- 补 summary：只陈述「这是什么、哪一版、本站收什么、正文去哪读」四件事
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICAO = ROOT / "data" / "records" / "icao_documents.json"
TRANS = ROOT / "data" / "records" / "foreign_translation_lexcom.json"

COVERAGE = "本站只存元数据与官方链接，不收录正文"


def fix_icao():
    recs = json.loads(ICAO.read_text(encoding="utf-8"))
    fixed_ed = summed = 0
    for r in recs:
        rl = r.get("recordLevel") or {}
        ed = (rl.get("edition") or "").strip()
        title_zh = rl.get("titleZh") or r.get("title") or ""

        # 1) edition 断言改为现行版次
        for a in r.get("assertions") or []:
            if a.get("field") != "edition":
                continue
            if ed and a.get("value") != ed:
                a["previousValue"] = a.get("value")
                a["value"] = ed
                a["locator"] = "ICAO Store 产品页逐条核验（原值为 booklet 印制年份，2026-10-23 更正）"
                a["verifiedAt"] = "2026-10-23"
                fixed_ed += 1
            break

        # 2) 摘要
        amd = (rl.get("latestAmendment") or "").strip()
        parts = [f"国际民航组织《国际民用航空公约》{rl.get('icaoNumber')} {title_zh}"]
        if ed:
            parts.append(f"现行版次 {ed}")
        if amd:
            parts.append(f"最新修订 {amd}")
        parts.append(COVERAGE)
        r["summary"] = "；".join(parts) + "。"
        summed += 1
    ICAO.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ICAO：更正 edition 断言 {fixed_ed} 条，补摘要 {summed} 条")


def fix_translations():
    recs = json.loads(TRANS.read_text(encoding="utf-8"))
    n = 0
    for r in recs:
        rl = r.get("recordLevel") or {}
        country = rl.get("countryName") or ""
        title = r.get("title") or ""
        year = rl.get("issueYear")
        status = rl.get("versionStatusName") or ""
        # 标题里已经带国名的（如「南非网络犯罪和网络安全法」）不再重复加前缀
        lead = f"《{title}》中文译本" if (not country or title.startswith(country)) \
            else f"{country}《{title}》中文译本"
        parts = [lead]
        if year:
            parts.append(f"{year} 年发布")
        if status:
            parts.append(f"状态：{status}")
        parts.append("法通网（司法部）收录，本站只存元数据与译文链接，不收录译文正文")
        r["summary"] = "；".join(parts) + "。"
        n += 1
    TRANS.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"外文译本：补摘要 {n} 条")


if __name__ == "__main__":
    fix_icao()
    fix_translations()
