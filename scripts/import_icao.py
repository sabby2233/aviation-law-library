#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_icao.py — 导入用户从 ICAO 官网下载的文档

为什么是这个设计：
    ICAO 官网（www.icao.int）全站 Cloudflare 拦截，程序无法访问；
    且 SARPs 明示保留版权、不得印刷分发——因此本站对 ICAO
    **只存元数据与引注，不存正文**。

    用户自行从官网下载文件后放入 `data/inbox/icao/`，本脚本负责：
      ① 读取元数据（优先取同名 .json，其次从文件名解析）
      ② 逐条核验编号格式是否合法（ICAO 编号有严格语法）
      ③ 生成断言与来源登记
      ④ **明确标记 verificationStatus = user-provided**
         （不是自动核验，引用前仍需用户确认）

支持的两种投放方式：
    方式 A（元数据优先，推荐）：
        data/inbox/icao/ANA-17.json     ← 我提供的模板，见 TEMPLATE
        data/inbox/icao/Annex-17.pdf   ← 正文原件（可选，仅作留档不入库）

    方式 B（仅正文，按文件名解析）：
        data/inbox/icao/Annex-17-Air-Traffic-Services.pdf

用法：
    python scripts/import_icao.py            # 导入
    python scripts/import_icao.py --template # 生成元数据模板
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import make_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "inbox" / "icao"
OUT = ROOT / "data" / "records" / "icao_documents.json"

TEMPLATE = {
    "icaoNumber": "Annex 17",
    "title": "Air Traffic Services",
    "titleZh": "空中交通服务",
    "documentType": "annex",
    "edition": "17th ed., 2010",
    "adoptedDate": "2010-02-24",
    "amendmentDate": "",
    "language": "en",
    "sourceUrl": "https://store.icao.int/en/annex-17-air-traffic-services",
    "publisher": "International Civil Aviation Organization",
    "isFreeAccess": True,
    "acquiredFrom": "store.icao.int",
    "acquiredDate": "",
    "notes": "正文是否转载须看 ICAO 的版权声明；本站默认只存元数据与引注",
}

# ICAO 编号的严格语法——用来拦住编号写错的元数据
NUM_PATTERNS = {
    "annex": re.compile(r"^Annex\s*(\d{1,2})$", re.I),
    "doc": re.compile(r"^Doc(?:ument)?\.?\s*(\d{3,5}(?:-\d{1,4})?)$", re.I),
    "pans": re.compile(r"^PANS[- ]([A-Z]{2,4})\s*(\d{3,5})$", re.I),
    "manual": re.compile(r"^(?:Doc(?:ument)?\.?\s*)?([A-Z]{2,5}-\d{3,4})$", re.I),
}

FILENAME_NUM = [
    re.compile(r"Annex[-_ ]?(\d{1,2})\b", re.I),
    re.compile(r"\bDoc(?:ument)?[-_ ]?(\d{3,5}(?:-\d{1,4})?)\b", re.I),
    re.compile(r"PANS[-_ ]?([A-Z]{2,4})[-_ ]?(\d{3,5})\b", re.I),
]


def parse_number(raw):
    """解析 ICAO 编号 → (kind, key, 规范形式)。不合法返回 (None, None, None)。"""
    s = str(raw or "").strip()
    for kind, pat in NUM_PATTERNS.items():
        m = pat.match(s)
        if not m:
            continue
        if kind == "annex":
            return "附件", f"annex:{m.group(1)}", f"Annex {m.group(1)}"
        if kind == "doc":
            return "文件", f"doc:{m.group(1)}", f"Doc {m.group(1)}"
        if kind == "pans":
            return "PANS", f"pans:{m.group(1)}:{m.group(2)}", f"PANS-{m.group(1)} Doc {m.group(2)}"
        if kind == "manual":
            return "手册", f"manual:{m.group(1)}", m.group(1)
    return None, None, None


def guess_from_filename(p):
    for pat in FILENAME_NUM:
        m = pat.search(p.stem)
        if m:
            g = m.groups()
            raw = (f"Annex {g[0]}" if len(g) == 1
                   else f"Doc {g[0]}" if len(g) == 1 or g[0].isdigit() or "-" in g[0]
                   else f"PANS-{g[0]} {g[1]}")
            return parse_number(raw)
    return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", action="store_true", help="生成元数据模板")
    args = ap.parse_args()

    INBOX.mkdir(parents=True, exist_ok=True)

    if args.template:
        p = INBOX / "Annex-17.json"
        p.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        print(f"元数据模板 → {p}")
        print("复制此文件并按实际文档填写，然后与 PDF 同名放在同一目录。")
        return

    if not INBOX.exists() or not any(INBOX.iterdir()):
        print(f"收件箱为空：{INBOX}")
        print("请把 ICAO 文档（或同名 .json 元数据）放入该目录后重跑。")
        print("模板：python scripts/import_icao.py --template")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records, skipped = [], []

    for p in sorted(INBOX.iterdir()):
        if p.name.startswith("~") or p.suffix.lower() not in (".json", ".pdf"):
            continue

        if p.suffix.lower() == ".pdf":
            meta_path = p.with_suffix(".json")
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    src = "json"
                except Exception as e:  # noqa: BLE001
                    skipped.append((p.name, f"元数据解析失败：{e}"))
                    continue
            else:
                kind, key, norm = guess_from_filename(p)
                if not norm:
                    skipped.append((p.name, "文件名无法解析出 ICAO 编号，且无同名 .json"))
                    continue
                meta = {"icaoNumber": norm, "title": p.stem}
                src = "filename"
            has_pdf = True
        else:
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                skipped.append((p.name, f"JSON 解析失败：{e}"))
                continue
            has_pdf = p.with_suffix(".pdf").exists()
            src = "json"

        kind, key, norm = parse_number(meta.get("icaoNumber"))
        if not norm:
            skipped.append((p.name,
                            f"编号不合规：{meta.get('icaoNumber')!r}"
                            "（应形如 Annex 17 / Doc 9944 / PANS-ATM 8610）"))
            continue

        title = meta.get("title") or p.stem
        title_zh = meta.get("titleZh")
        sid = f"ICAO-{key.replace(':', '-').upper()}"

        assertion_fields = [("icao_number", norm), ("title", title)]
        for k in ("edition", "adoptedDate", "amendmentDate", "publisher", "language"):
            if meta.get(k):
                assertion_fields.append((k, str(meta[k])))

        records.append({
            "recordId": make_id("ICAO", "STD", key.replace(":", "-").upper()),
            "recordType": "standard",
            "title": title,
            "titleEn": title,
            "summary": None,
            "jurisdiction": "ICAO",
            "topics": sorted(set(
                ["icao", "international-aviation"]
                + (["annex"] if kind == "附件" else [])
                + (["uav"] if "unmanned" in (title + (title_zh or "")).lower() else [])
                + (["data-protection"] if any(
                    k in (title + (title_zh or "")).lower()
                    for k in ("security", "data", "privacy")) else [])
            )),
            "status": "in_force",
            "dates": {
                "publicationDate": meta.get("adoptedDate") or None,
                "effectiveDate": meta.get("adoptedDate") or None,
                "retrievedAt": today,
            },
            "citationString": norm,
            "sourceUrl": meta.get("sourceUrl")
                          or "https://store.icao.int/en",
            "recordLevel": {
                "icaoNumber": norm,
                "icaoKind": kind,
                "canonicalKey": key,
                "titleZh": title_zh,
                "subVolumes": meta.get("subVolumes"),
                "edition": meta.get("edition"),
                "adoptedDate": meta.get("adoptedDate"),
                "amendmentDate": meta.get("amendmentDate"),
                "language": meta.get("language") or "en",
                "publisher": meta.get("publisher")
                             or "International Civil Aviation Organization",
                "isFreeAccess": meta.get("isFreeAccess"),
                "acquiredFrom": meta.get("acquiredFrom"),
                "acquiredDate": meta.get("acquiredDate"),
                "hasLocalPdf": has_pdf,
                "sourceTier": "L1",
                # 关键：标明这是用户提供的，未经程序核验
                "verificationStatus": "user-provided",
                "retrievalChannel": src,
                "note": "ICAO 官方站点无法程序访问（Cloudflare 拦截），"
                        "本条元数据由用户从官网下载后导入；"
                        "SARPs 受版权保护，本站**只存元数据与引注，不转载正文**；"
                        "引注前请核对 edition 与最新修订版本",
            },
            "assertions": [
                {
                    "field": f,
                    "value": str(v)[:400],
                    "sourceId": sid,
                    "locator": f"ICAO {norm}",
                    "evidenceLevel": "L1",
                    "verifiedAt": today,
                }
                for f, v in assertion_fields
            ],
            "revisionLog": [],
        })

    if not records:
        print("没有可导入的条目。")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if OUT.exists():
            for r in json.loads(OUT.read_text(encoding="utf-8")):
                existing[r["recordId"]] = r
        for r in records:
            existing[r["recordId"]] = r
        merged = sorted(existing.values(),
                        key=lambda r: r["recordId"])
        OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"导入 {len(records)} 条 → 累计 {len(merged)} 条")
        print(f"  → {OUT.relative_to(ROOT)}")

    if skipped:
        print(f"\n跳过 {len(skipped)} 个文件：")
        for name, why in skipped:
            print(f"  {name}: {why}")

    if records:
        print("\n下一步：python scripts/build_sources.py && "
              "python scripts/build_manifest.py && python scripts/build_browse.py "
              "&& node scripts/build_api.js")


if __name__ == "__main__":
    main()