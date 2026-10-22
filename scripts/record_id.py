"""永久标识（recordId）生成规则 —— 单一真源。

规范：AVA-<法域>-<类型>-<来源标识>

设计取舍：
  早期版本要求固定 5 段（AVA-US-R-2026-21422），但真实数据源的标识符
  天然是多段的（CCAR-66TM-I-R5、14 CFR 63.12a、ES-A-009）。压成固定段数
  必须做有损转换，且丢掉了可人工核对的信息。
  因此改为「可解析路径式」：前 3 段固定语义，其后各段保留来源标识符原貌。

法域段：ISO 3166-1 alpha-2（US / CN / ES / GB / …）
类型段：来源体系缩写
    FR   Federal Register（美国联邦公报·变更事件）
    CFR  eCFR（美国联邦法规·现行条文）
    CCAR 中国民航规章（CCAR 部号）
    GZ   中国民航规范性文件（无 CCAR 部号）
    ADP  航空数据保护执法案例
    DP   数据保护执法案例（其他主题）
来源标识段：原样保留，仅做两件事
    1) 点号转连字符（14 CFR 63.12a → 63-12A）
    2) 统一大写（[A-Z0-9]）

不变量（由 validate.py 的 ID-01 断言强制）：
    - 唯一性：分配后永不复用、永不重编
    - 可解析：前 3 段语义固定，第 4 段起为来源标识
    - 无空格、无下划线、无中文
"""

import re
import hashlib

# 法域段：2–4 位大写字母
JUR_RE = re.compile(r"^[A-Z]{2,4}$")
# 类型段：2–5 位大写字母
TYPE_RE = re.compile(r"^[A-Z]{2,5}$")
# 来源标识段：1–12 位大写字母或数字
SEG_RE = re.compile(r"^[A-Z0-9]{1,12}$")

# 完整 recordId
RECORD_ID_RE = re.compile(r"^AVA-[A-Z]{2,4}-[A-Z]{2,5}(?:-[A-Z0-9]{1,12}){0,4}$")

# 已知类型码
TYPE_CODES = {
    "FR",     # Federal Register 变更事件
    "CFR",    # eCFR 现行条文
    "CCAR",   # 中国民航规章
    "GZ",     # 中国民航规范性文件
    "ADP",    # 航空数据保护执法案例
    "DP",     # 其他数据保护执法案例
    "LAW",    # 一般立法
    "STD",    # 标准
    "GUID",   # 指南
}


def _norm_segments(raw):
    """把来源标识切成合法段：大写、点号转连字符、丢弃非法字符。

    保留段的原始边界（不合并），因为段数本身携带语义
    （CCAR-66TM-I-R5 的 66TM / I / R5 三段各有含义）。
    """
    s = str(raw or "").strip()
    if not s:
        return []
    # 先按连字符与点号切
    parts = re.split(r"[.\-\s]+", s)
    out = []
    for p in parts:
        q = re.sub(r"[^A-Za-z0-9]", "", p).upper()
        if not q:
            continue
        # 单段过长时按 12 位切分（保序）
        while len(q) > 12:
            out.append(q[:12])
            q = q[12:]
        if q:
            out.append(q)
    return out


def make_id(jurisdiction, type_code, source_id, fallback=""):
    """生成合规 recordId。

    参数：
      jurisdiction  法域码（US/CN/ES/…），非法时抛 ValueError
      type_code     类型码（FR/CFR/CCAR/…），非法时抛 ValueError
      source_id     来源标识符（原样即可，内部会规范化）
      fallback      source_id 为空时的替代文本（通常是标题派生）

    返回：符合 RECORD_ID_RE 的 recordId 字符串
    """
    jur = str(jurisdiction or "").strip().upper()
    if not JUR_RE.match(jur):
        raise ValueError(f"非法法域码：{jurisdiction!r}")

    typ = str(type_code or "").strip().upper()
    if not TYPE_RE.match(typ):
        raise ValueError(f"非法类型码：{type_code!r}")

    segs = _norm_segments(source_id)
    if not segs:
        # 无来源标识时用标题派生的稳定短哈希（不依赖行号，避免重排即变）
        basis = re.sub(r"[^A-Za-z0-9]", "", str(fallback or ""))[:40]
        h = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8].upper()
        segs = [h] if basis else ["X" + h[1:]]

    # 段数上限：AVA-JUR-TYPE + 最多 4 段来源标识
    segs = segs[:4]

    rid = "-".join(["AVA", jur, typ] + segs)
    if not RECORD_ID_RE.match(rid):
        # 兜底：极端输入下退化为哈希形式，保证永不合规
        h = hashlib.sha1(rid.encode("utf-8")).hexdigest()[:10].upper()
        rid = f"AVA-{jur}-{typ}-{h}"
    return rid


def is_valid(rid):
    """校验 recordId 是否合规。"""
    return bool(RECORD_ID_RE.match(str(rid or "")))


# ── 状态词表（单一真源） ────────────────────────────────────────────
# 教训：本模块之前分散在 validate.py 与各采集器里，导致
#   采集器写 "in_force"、断言表写 "effective"，状态机全线报非法转换。
# 状态名与转换规则必须只有一个出处。
STATUSES = {
    "draft",            # 起草中
    "adopted",          # 已通过（案件：已作出决定）
    "withdrawn",        # 已撤回
    "promulgated",      # 已公布
    "effective",        # 现行有效  ← 注意：不是 in_force
    "not_yet_effective",  # 尚未施行
    "amended",          # 已被修改
    "superseded",       # 已被取代（历史版本）
    "repealed",         # 已废止（明文废止）
    "invalidated",      # 已失效（不再适用但未必明文废止）
    "settled",          # 已和解
    "under_appeal",     # 上诉中
    "final",            # 终局
}

# 允许的状态转换
ALLOWED_TRANSITIONS = {
    ("draft", "adopted"),
    ("draft", "withdrawn"),
    ("adopted", "promulgated"),
    ("adopted", "invalidated"),
    ("promulgated", "effective"),
    ("promulgated", "not_yet_effective"),
    ("effective", "amended"),
    ("effective", "superseded"),
    ("effective", "repealed"),
    ("effective", "invalidated"),
    ("effective", "settled"),
    ("amended", "effective"),
    ("amended", "superseded"),
    ("repealed", None),
    ("invalidated", None),
    ("superseded", None),
    ("under_appeal", "final"),
    ("under_appeal", "settled"),
    ("under_appeal", "invalidated"),
    ("final", "settled"),
}


def is_valid_status(status):
    return status in STATUSES
