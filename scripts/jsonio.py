#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jsonio.py — 按目标文件**既有的**行尾与缩进写 JSON

为什么需要：
    仓库里 .gitattributes 设了 `* -text`，行尾不做归一。但不同文件的既有约定并不一致：
      · data/records/cases_aviation_data.json 与 data/sources/registry.json 历来是 CRLF
      · data/records/regulations_cn_*.json 与 icao_documents.json 历来是 LF
    脚本若一律用 newline="\\n" 或一律用 CRLF 写盘，就会把整文件刷成「全行变更」
    （已实际发生过两次：一次 registry.json 76663 行全红，一次 build_browse.py 303 行全红）。
    这种假 diff 会淹没真正的改动，也让 review 失效。

做法：
    写之前先读原文件，探测它的行尾（CRLF / LF）与缩进宽度，然后照原样写回。
    文件不存在时按仓库默认（LF、缩进 2）创建。
"""

import json
import re
from pathlib import Path


def _detect_style(path: Path):
    """返回 (newline, indent)。探测失败时回落到仓库默认值。"""
    if not path.exists():
        return "\n", 2
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8", "ignore")
    # 缩进：取第二行行首空白数（第一行是 "{" 或 "["）
    m = re.search(r"\n([ ]+)\S", text)
    indent = len(m.group(1)) if m else 2
    if indent > 8:          # 目录页之类的异常缩进不作为依据
        indent = 2
    return newline, indent


def save_json(path, obj, *, ensure_ascii=False):
    """按文件既有风格写 JSON。返回写入字节数。"""
    p = Path(path)
    newline, indent = _detect_style(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent)
    # 统一先转 LF，再整体替换成目标行尾，避免出现 \r\r\n
    body = body.replace("\r\n", "\n").replace("\n", newline)
    with p.open("wb") as f:
        f.write(body.encode("utf-8"))
    return len(body)


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        nl, ind = _detect_style(Path(a))
        print(f"{a}: newline={nl!r} indent={ind}")
