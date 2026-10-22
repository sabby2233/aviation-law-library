#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_manifest.py — 从 data/records/*.json 与 data/sources/*.json 汇总生成 manifest.json

manifest 是站点唯一的数据入口，站点前端与 API 出口只读这一个文件。
派生统计（分面计数、一手占比、待核验数）在构建期算好，不在前端算。

用法：python scripts/build_manifest.py
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

L_OFFICIAL_PRIMARY = {"L0"}
L_ACCEPTABLE = {"L0", "L1", "L2", "L3"}

# 核心事实字段：只有这些字段的一手支撑率才真正反映数据质量
CORE_FIELDS = {
    "decision_date", "publication_date", "effective_date",
    "fine_amount", "disposition", "holding", "outcome",
}


def load_dir(sub):
    out = []
    d = DATA / sub
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
        out.extend(data if isinstance(data, list) else [data])
    return out


def official_ratio_by_type(records):
    """分类型 + 记录级的一手来源占比。

    为什么不用断言级加权：那种算法可被轻易刷高——
    一条记录挂 8 条 L0 断言就能拉高总分，而标识类断言（agency / document_number）
    与核心事实断言（决定日 / 金额 / 裁判结论）的信息量完全不同。

    记录级 + 分类型的口径：
      法规：568 条中 568 条有 L0 支撑 → 100%（来源单一，这个数字本身信息量有限）
      案例： 49 条中  32 条有 L0 支撑 →  65%（这才是有信息量的数字）
    """
    out = {}
    for t in ("legislation", "case", "standard", "guidance", "policy"):
        rs = [r for r in records if r.get("recordType") == t]
        if not rs:
            continue
        ok = sum(1 for r in rs
                  if any(a.get("evidenceLevel") in L_OFFICIAL_PRIMARY
                         for a in r.get("assertions", [])))
        out[t] = {
            "records": len(rs),
            "withPrimarySource": ok,
            "ratio": round(ok / len(rs), 4),
        }
    return out


def core_field_ratio(records):
    """核心事实字段的一手支撑率（只看核心字段，无法靠灌水通过）。"""
    core = [a for r in records for a in r.get("assertions", [])
            if a.get("field") in CORE_FIELDS]
    if not core:
        return 0.0, 0
    ok = sum(1 for a in core if a.get("evidenceLevel") in L_OFFICIAL_PRIMARY)
    return round(ok / len(core), 4), len(core)


def count_pending(records):
    """待核验条目：决定日缺失 / 二手来源 / 金额口径未确认。"""
    n = 0
    for r in records:
        d = r.get("dates", {}) or {}
        lv = [a.get("evidenceLevel") for a in r.get("assertions", [])]
        p = r.get("penalty") or {}
        if ("L3" in lv
                or (r.get("recordType") == "case" and not d.get("decisionDate"))
                or (p.get("amountOriginal") and p.get("amountFinal") is None)):
            n += 1
    return n


def git_commit_sha():
    """当前 commit SHA。用于把"我引用了一个可核验的版本"变成事实。"""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def main():
    records = load_dir("records")
    sources = load_dir("sources")
    entities = load_dir("entities")

    # 去重：按 recordId，后写覆盖先写
    rmap = {}
    for r in records:
        rmap[r["recordId"]] = r
    records = list(rmap.values())

    dates = [r.get("dates", {}).get("publicationDate") for r in records]
    dates = [d for d in dates if d]
    cutoff = max(dates) if dates else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    by_type = official_ratio_by_type(records)
    core_ratio, core_count = core_field_ratio(records)
    pending = count_pending(records)
    sha = git_commit_sha()

    manifest = {
        "meta": {
            "datasetVersion": f"avl-{cutoff[:7]}",
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dataCutoff": cutoff,
            "retrievalCutoff": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            # 字段名与内容必须一致：caseCount 是案例数，不是总记录数
            "recordCount": len(records),
            "caseCount": sum(1 for r in records if r.get("recordType") == "case"),
            "legislationCount": sum(1 for r in records if r.get("recordType") == "legislation"),
            "sourceCount": len(sources),
            "entityCount": len(entities),
            "jurisdictionCount": len({r.get("jurisdiction") for r in records
                                      if r.get("jurisdiction")}),
            "assertionCount": sum(len(r.get("assertions", [])) for r in records),
            # 一手来源：分类型 + 记录级；另给核心字段口径
            "officialSourceRatio": by_type,
            "coreFieldPrimaryRatio": core_ratio,
            "coreFieldCount": core_count,
            "pendingCount": pending,
            "commitSha": sha,
            "license": "代码 MIT；数据内容 CC BY 4.0（署名），仅及于本库自行编制的编排与"
                       "事实性转述；所引官方文本的权利归各权利人，本站不转载",
            "notice": "本站整理自公开来源，不提供法律意见，事实以官方原文为准。",
        },
        "sources": sources,
        "entities": entities,
        "records": records,
    }

    out = DATA / "manifest.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"manifest：{len(records)} 条记录"
          f"（法规 {manifest['meta']['legislationCount']}"
          f" + 案例 {manifest['meta']['caseCount']}）"
          f" / {manifest['meta']['jurisdictionCount']} 法域")
    print(f"核心字段一手支撑率：{core_ratio:.1%}（{core_count} 条核心断言）")
    print(f"待核验条目：{pending}")
    print("一手来源（记录级·分类型）："
          + "  ".join(f"{k} {v['withPrimarySource']}/{v['records']}"
                      for k, v in by_type.items()))
    print(f"commit SHA：{sha or '（非 git 仓库，未获取）'}")
    print(f"数据截止：{cutoff}")
    print(f"→ {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
