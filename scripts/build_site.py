#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py — 组装可直接发布的静态站点目录

为什么要单独一个脚本：
    browse.json / details/ / site/api/ 都是构建产物，按设计不入库（.gitignore）。
    所以 Pages 不能直接发布仓库，必须「先构建、再组装、后发布」。
    组装规则写在这里而不是散在 workflow 的 shell 里，是为了能本地跑一遍验证。

产物结构（发布后 index.html 与 data/ 同级，故前端用 ./data）：
    _site/
      index.html
      css/  js/
      data/{browse.json, identifiers.json, details/<桶>/<id>.json}
      api/  ← 可选，site/api 的 REST 出口

用法：
    python scripts/build_site.py            # 含 API 出口
    python scripts/build_site.py --no-api   # 不含（体积少一半，部署更快）
"""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"


def copy_tree(src: Path, dst: Path):
    if not src.exists():
        raise SystemExit(f"缺少构建产物：{src}（先跑 build_browse.py / build_api.js）")
    shutil.copytree(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-api", action="store_true", help="不打包 site/api")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 1. 前端源文件（只取有用的：test_*.js 不进发布目录）
    shutil.copy2(ROOT / "site" / "index.html", out / "index.html")
    for d in ("css", "js"):
        copy_tree(ROOT / "site" / d, out / d)

    # 2. 数据与索引
    (out / "data").mkdir()
    for f in ("browse.json", "terms.json", "identifiers.json"):
        src = ROOT / "data" / f
        if not src.exists():
            raise SystemExit(f"缺少 {src}：先跑 build_browse.py")
        shutil.copy2(src, out / "data" / f)
    copy_tree(ROOT / "data" / "details", out / "data" / "details")

    # 3. API 出口（可选）
    if not args.no_api:
        copy_tree(ROOT / "site" / "api", out / "api")

    # 统计
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    files = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"发布目录：{out}")
    print(f"文件 {files:,} 个｜合计 {total / 1048576:.1f} MB")
    for sub in ("data", "api"):
        p = out / sub
        if p.exists():
            s = sum(x.stat().st_size for x in p.rglob("*") if x.is_file())
            print(f"  {sub}/  {s / 1048576:.1f} MB")
    if total > 1024 ** 3:
        raise SystemExit("发布体积超过 1 GB，GitHub Pages 站点上限，需拆分")


if __name__ == "__main__":
    main()
