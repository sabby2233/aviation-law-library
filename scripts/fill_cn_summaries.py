#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_cn_summaries.py — 给缺摘要的中国规章补一句确定性摘要

背景：民航局规章栏目采集的 118 条记录（CCAR 部号命名 + AVA-CN-GZ-* 形式的废止决定）
既没有摘要也没有正文，卡片上只剩标题与几行事实字段，读者看不出这条规章是什么状态。

补法：**只用记录里已有的字段拼接**，不生成新事实、不调用模型——
标题 + 部号/文号 + 官方栏目标注的有效性 + 一句使用边界。
这与此前给 18 条域外译本补摘要的做法一致（确定性拼接，不做内容生成）。

幂等：只补 summary 为空的记录，已有摘要的不动。

用法：python scripts/fill_cn_summaries.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "data" / "records"
BOUNDARY = {
    "caac": "本站只存元数据与链接，正文请回民航局规章原文查阅。",
    "lexcom": "本站只存元数据与链接，正文请回官方公布文本（法通网收录）查阅。",
}
DEFAULT_BOUNDARY = "本站只存元数据与链接，正文请回官方原文查阅。"


def boundary_of(rec):
    """使用边界按来源分：法通网（司法部）与民航局规章栏目不是一回事，
    早先一版统一写「回民航局规章原文查阅」，套到法通网收录的法律上就是错的。"""
    url = (rec.get("sourceUrl") or "").lower()
    if "caac.gov.cn" in url:
        return BOUNDARY["caac"]
    if "lexcom" in url:
        return BOUNDARY["lexcom"]
    return DEFAULT_BOUNDARY


def compose(rec):
    """用已有字段拼一句摘要；字段缺失的部分不写，绝不臆造。"""
    rl = rec.get("recordLevel") or {}
    d = rec.get("dates") or {}
    title = (rec.get("title") or "").strip()
    no = rl.get("ccarNumber") or rec.get("ccarNumber") or rec.get("citationString") or ""
    validity = rl.get("validity") or rec.get("validity") or ""
    dept = rl.get("issuingDepartment") or rec.get("issuingDepartment") or ""
    date = d.get("publicationDate") or ""

    parts = [title]
    if no and no not in title:
        parts.append(f"（{no}）")
    if date:
        parts.append(f"，{date}")
    head = "".join(parts)

    facts = []
    if validity:
        facts.append(f"官方规章栏目标注的状态：{validity}")
    if dept:
        facts.append(f"发文部门：{dept}")
    facts.append(boundary_of(rec))
    return head + "。" + "；".join(facts)


def main():
    total = filled = 0
    for p in sorted(RECORDS.glob("*.json")):
        if ".bak" in p.name:
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        changed = False
        for rec in data:
            if not isinstance(rec, dict):
                continue
            total += 1
            if (rec.get("summary") or "").strip():
                continue
            # 只补中国法域的规章类记录：案例与标准类缺摘要是另一种问题，不在此处理
            if rec.get("jurisdiction") != "CN" or rec.get("recordType") != "legislation":
                continue
            s = compose(rec)
            if s.strip():
                rec["summary"] = s
                changed = True
                filled += 1
        if changed:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
            print(f"  {p.name}: 已补摘要")
    print(f"扫描 {total} 条，补 {filled} 条摘要")


if __name__ == "__main__":
    main()
