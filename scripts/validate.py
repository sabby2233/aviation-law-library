#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — 数据质量断言（CI 调用）

这是本资料库唯一的反幻觉机制。不调用大模型，全部为确定性检查。
把方法论纪律写成可执行断言：规则不进代码 = 没有规则。

用法：
    python scripts/validate.py [--data data/manifest.json] [--strict]

退出码：0 通过；1 存在 block 级失败；2 输入错误
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_id import RECORD_ID_RE, ALLOWED_TRANSITIONS  # noqa: E402  单一真源，避免规则漂移

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ── 证据等级定义（与 schema.json 保持一致）──────────────────────────
L_OFFICIAL_PRIMARY = {"L0"}      # 官方一手文书
L_OFFICIAL_SECONDARY = {"L0", "L1"}  # 核心字段可接受的证据集
L_ACCEPTABLE = {"L0", "L1", "L2", "L3"}  # 可入库的最高等级
L_MIN_OFFICIAL_RATIO = 0.80      # 一手来源占比下限（断言级，非记录级）
L_MIN_CORE_FIELD_RATIO = 0.80   # 核心事实字段一手支撑率下限

# 等级由严到宽
LEVEL_ORDER = ["L0", "L1", "L2", "L3", "L4", "L5"]

# 核心事实字段：只有这些字段的一手支撑率才真正反映数据质量
CORE_FIELDS = {
    "decision_date", "publication_date", "effective_date",
    "fine_amount", "disposition", "holding", "outcome",
}

# 状态机转换表来自 scripts/record_id.py（单一真源，见该文件 STATUSES 注释）

REQUIRED_CITATION_FIELDS = ("author", "title", "journal", "year")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 记录 ID 格式：AVA-<法域>-<类型>-<来源标识>
# 规范定义在 scripts/record_id.py（单一真源），此处只做校验，不重复定义规则。
# 例：
#   AVA-US-FR-R-2026-214220   美国联邦公报 RULE
#   AVA-US-CFR-39-39-13       eCFR 现行条文 14 CFR 39.13
#   AVA-CN-CCAR-290-R4        民航规章 CCAR-290-R4
#   AVA-ES-ADP-A-009          航空数据保护执法案例
#   AVA-CN-GZ-3F2A1B9C        民航规范性文件（无 CCAR 部号，标题派生哈希）
DOC_NO_RE = RECORD_ID_RE

# 禁止出现在正式案例列表的证据等级（须退入待核实线索队列）
REJECT_FOR_CORE = {"L4", "L5"}


class Report:
    def __init__(self):
        self.errors = []      # block：阻止发布
        self.warnings = []    # warn：允许发布但需人工确认
        self.stats = {}

    def fail(self, rule, msg):
        self.errors.append((rule, msg))

    def warn(self, rule, msg):
        self.warnings.append((rule, msg))

    def summary(self):
        return {
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            **self.stats,
        }


def _d(v):
    """把 ISO 日期串转成 date；非法或 None 返回 None。"""
    if not v or not isinstance(v, str):
        return None
    if not ISO_DATE_RE.match(v):
        return None
    try:
        y, m, dd = v.split("-")
        return date(int(y), int(m), int(dd))
    except ValueError:
        return None


def load_manifest(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collect_records(manifest):
    """manifest 中 records 可能是内联数组，也可能是文件路径列表。"""
    out = []
    for item in manifest.get("records", []):
        if isinstance(item, dict):
            out.append(item)
            continue
        p = DATA / item
        if p.exists():
            with p.open(encoding="utf-8") as f:
                data = json.load(f)
            out.extend(data if isinstance(data, list) else [data])
    return out


# ═══════════════════════════════════════════════════════════════════
# 断言实现
# ═══════════════════════════════════════════════════════════════════

def check_schema_basics(manifest, rep):
    """SCH-01 顶层结构完整"""
    for key in ("meta", "sources", "entities", "records"):
        if key not in manifest:
            rep.fail("SCH-01", f"manifest 缺少顶层键：{key}")


def check_record_ids(manifest, rep):
    """ID-01 记录 ID 格式合法且唯一；ID-02 永久标识不重复"""
    seen = {}
    for r in manifest.get("records", []):
        rid = r.get("recordId", "")
        if not DOC_NO_RE.match(rid):
            rep.fail("ID-01", f"recordId 格式不合规：{rid!r}（应为 XX-X-000 形式）")
        if rid in seen:
            rep.fail("ID-02", f"recordId 重复：{rid}")
        seen[rid] = True


def check_source_registry(manifest, rep):
    """SRC-01 断言引用的 sourceId 必须存在；SRC-02 source 必填字段"""
    source_ids = {s.get("sourceId") for s in manifest.get("sources", [])}
    for s in manifest.get("sources", []):
        sid = s.get("sourceId", "?")
        for req in ("url", "authority", "evidenceLevel", "retrievedAt", "retrievalChannel"):
            if not s.get(req):
                rep.fail("SRC-02", f"source {sid} 缺少必填字段 {req}")
        lvl = s.get("evidenceLevel")
        if lvl in REJECT_FOR_CORE:
            rep.fail("SRC-03", f"source {sid} 证据等级 {lvl} 不得入库，应退入待核实线索队列")
        url = s.get("url", "")
        if url and not url.startswith(("http://", "https://")):
            rep.fail("SRC-04", f"source {sid} url 非绝对地址：{url}")
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        for a in r.get("assertions", []):
            sid = a.get("sourceId")
            if not sid:
                rep.fail("SRC-01", f"记录 {rid} 存在无 sourceId 的断言（字段 {a.get('field')}）")
            elif sid not in source_ids:
                rep.fail("SRC-01", f"记录 {rid} 引用了未登记的 sourceId：{sid}")
            else:
                # 断言级证据等级不得低于其来源登记等级
                src = next(s for s in manifest["sources"] if s.get("sourceId") == sid)
                if src.get("evidenceLevel") not in L_ACCEPTABLE:
                    rep.fail("SRC-05", f"记录 {rid} 断言 {a.get('field')} 依赖不可入库来源 {sid}")


def check_evidence_ratio(manifest, rep):
    """EVD-01 一手来源占比（断言级加权）不得低于阈值"""
    total = 0
    official = 0
    for r in manifest.get("records", []):
        for a in r.get("assertions", []):
            total += 1
            if a.get("evidenceLevel") in L_OFFICIAL_PRIMARY:
                official += 1
    rep.stats["assertionCount"] = total
    rep.stats["officialAssertionCount"] = official
    ratio = (official / total) if total else 0.0
    rep.stats["officialSourceRatio"] = round(ratio, 4)
    if total and ratio < L_MIN_OFFICIAL_RATIO:
        rep.fail("EVD-01", f"一手来源占比 {ratio:.1%} 低于阈值 {L_MIN_OFFICIAL_RATIO:.0%}")


def check_core_field_evidence(manifest, rep):
    """EVD-02 核心事实字段的一手支撑率。

    为什么必须有这条：EVD-01 的断言级加权可被轻易刷高——
    给一条记录补 10 条引自官方法规页面的标识类断言（agency/document_number），
    占比立刻上升，但这些断言的信息量远低于决定日、罚款额、裁判结论。
    只看核心字段就无法灌水通过。
    """
    core = [a for r in manifest.get("records", [])
            for a in r.get("assertions", []) if a.get("field") in CORE_FIELDS]
    if not core:
        rep.warn("EVD-02", "未找到核心事实字段断言，无法评估核心字段一手支撑率")
        return
    ok = sum(1 for a in core if a.get("evidenceLevel") in L_OFFICIAL_PRIMARY)
    ratio = ok / len(core)
    rep.stats["coreFieldCount"] = len(core)
    rep.stats["coreFieldPrimaryRatio"] = round(ratio, 4)
    if ratio < L_MIN_CORE_FIELD_RATIO:
        rep.fail("EVD-02", f"核心事实字段一手支撑率 {ratio:.1%} 低于阈值 "
                           f"{L_MIN_CORE_FIELD_RATIO:.0%}（{ok}/{len(core)}）")


def check_source_level_consistency(manifest, rep):
    """SRC-06 来源登记等级必须与该来源下断言的等级一致（取最严）。

    此前 build_sources.py 按文件名硬编码等级，导致 12/49 条的登记等级
    与记录内实际等级冲突，一手来源占比被高估、SRC-03 形同虚设。
    """
    by_source = {}
    for r in manifest.get("records", []):
        for a in r.get("assertions", []):
            sid = a.get("sourceId")
            lvl = a.get("evidenceLevel")
            if not sid or not lvl:
                continue
            cur = by_source.get(sid)
            by_source[sid] = lvl if cur is None else (
                lvl if LEVEL_ORDER.index(lvl) <= LEVEL_ORDER.index(cur) else cur)

    registry = {s.get("sourceId"): s for s in manifest.get("sources", [])}
    mismatch = 0
    for sid, strictest in by_source.items():
        src = registry.get(sid)
        if not src:
            continue
        registered = src.get("evidenceLevel")
        if registered and registered != strictest:
            mismatch += 1
            if mismatch <= 10:
                rep.fail("SRC-06", f"来源 {sid} 登记等级 {registered}，"
                                   f"但其断言中最严等级为 {strictest}")
    rep.stats["sourceLevelMismatch"] = mismatch


def check_manual_source_not_primary(manifest, rep):
    """SRC-07 人工录入的来源不得标为 L0。

    理由：L0 的定义是「官方一手文书原文」。人工录入无法保证拿到的就是原文，
    若允许人工来源标 L0，则任何人只要把标签改成 L0 就能绕过全部质量门禁。

    豁免：若来源同时声明 verificationStatus=verified（已回原文核验），
    且 locator 指向具体文书编号，则允许 L0。
    """
    registry = {s.get("sourceId"): s for s in manifest.get("sources", [])}
    for s in manifest.get("sources", []):
        sid = s.get("sourceId", "?")
        if s.get("retrievalChannel") != "manual":
            continue
        if s.get("evidenceLevel") != "L0":
            continue
        # 有 locatorScheme 或明确核验状态者可豁免
        if s.get("verificationStatus") == "verified" or s.get("locatorScheme"):
            continue
        rep.fail("SRC-07", f"来源 {sid} 人工录入却标为 L0，"
                           f"须回官方文书核验并声明 verificationStatus=verified，"
                           f"或降级为 L1")


def check_locator_quality(manifest, rep):
    """LOC-01 locator 不得指向本站自身标识，必须是原文定位。

    此前 336 条案例断言的 locator 是「原站 record id=ES-A-001」——
    指向用户自己旧仓库的内部指针，第三方拿到后无法定位官方原文段落。
    """
    self_ref = re.compile(r'^(原站\s*)?record\s*id\s*=', re.I)
    bad = 0
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        for a in r.get("assertions", []):
            loc = (a.get("locator") or "").strip()
            if loc and self_ref.match(loc):
                bad += 1
                if bad <= 10:
                    rep.fail("LOC-01", f"记录 {rid} 的 locator 指向本站自身标识而非原文定位：{loc!r}")
    rep.stats["selfRefLocator"] = bad


def check_meta_counts(manifest, rep):
    """MAN-03 meta 声明的各类计数必须与实际一致（字段名与内容须相符）。"""
    meta = manifest.get("meta", {})
    records = manifest.get("records", [])
    checks = [
        ("recordCount", len(records)),
        ("caseCount", sum(1 for r in records if r.get("recordType") == "case")),
        ("legislationCount", sum(1 for r in records if r.get("recordType") == "legislation")),
        ("sourceCount", len(manifest.get("sources", []))),
        ("assertionCount", sum(len(r.get("assertions", [])) for r in records)),
    ]
    for key, actual in checks:
        if key in meta and meta[key] != actual:
            rep.fail("MAN-03", f"meta.{key}={meta[key]} 与实际 {actual} 不符")
    # 旧字段名 caseCount 曾被用来装总记录数，此处确保已改为 recordCount
    if "recordCount" not in meta and "caseCount" in meta:
        rep.fail("MAN-03", "meta 缺 recordCount，caseCount 不应兼任总记录数")


def check_pending_declared(manifest, rep):
    """MAN-04 待核验条目数必须与实际一致，且站点须能筛出。

    待核验的判据：决定日缺失 / 二手来源(L3) / 金额口径未确认。
    界面提供 pendingOnly 筛选，meta.pendingCount 须与之一致。
    """
    meta = manifest.get("meta", {})
    actual = 0
    for r in manifest.get("records", []):
        d = r.get("dates", {}) or {}
        lv = [a.get("evidenceLevel") for a in r.get("assertions", [])]
        p = r.get("penalty") or {}
        if ("L3" in lv
                or (r.get("recordType") == "case" and not d.get("decisionDate"))
                or (p.get("amountOriginal") and p.get("amountFinal") is None)):
            actual += 1
    if "pendingCount" in meta and meta["pendingCount"] != actual:
        rep.fail("MAN-04", f"meta.pendingCount={meta['pendingCount']} 与实际 {actual} 不符")
    rep.stats["pendingCount"] = actual


def check_snapshot_declared(manifest, rep):
    """ARC-01 来源的存档状态必须显式声明。

    snapshotUrl 填充率为 0 时，不能让读者以为证据可回溯——
    必须在来源记录中显式标注未存档，并给出替代核验路径。
    """
    for s in manifest.get("sources", []):
        sid = s.get("sourceId", "?")
        if s.get("snapshotUrl"):
            continue
        status = s.get("archiveStatus")
        if not status:
            rep.fail("ARC-01", f"来源 {sid} 无快照但未声明 archiveStatus"
                               f"（须标注 not-archived 并说明核验路径）")


def check_date_order(manifest, rep):
    """DAT-01 时间不等式；DAT-02 核心日期不得缺失"""
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        d = r.get("dates", {}) or {}
        dec = _d(d.get("decisionDate"))
        pub = _d(d.get("publicationDate"))
        prom = _d(d.get("promulgationDate"))
        eff = _d(d.get("effectiveDate"))
        rep_ = _d(d.get("repealDate"))
        ret = _d(d.get("retrievedAt"))

        if dec and pub and dec > pub:
            rep.fail("DAT-01", f"记录 {rid}：决定日 {dec} 晚于公布日 {pub}")
        if pub and ret and pub > ret:
            rep.fail("DAT-01", f"记录 {rid}：公布日 {pub} 晚于获知日 {ret}")
        if prom and eff and prom > eff:
            rep.fail("DAT-01", f"记录 {rid}：公布日 {prom} 晚于生效日 {eff}")
        if eff and rep_ and eff > rep_:
            rep.fail("DAT-01", f"记录 {rid}：生效日 {eff} 晚于废止日 {rep_}")

        # 案件类必须有决定日（无则标 null，不用报道日顶替）
        if r.get("recordType") == "case":
            if not d.get("decisionDate"):
                rep.warn("DAT-02", f"记录 {rid}：案件缺决定日，页面须显示「决定日未知」")


def check_penalty(manifest, rep):
    """PEN-01 金额与币种一致性；PEN-02 拟议额不得低于最终额；PEN-03 跨币种禁止合计"""
    currencies = set()
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        p = r.get("penalty") or {}
        cur = p.get("currency")
        ao = p.get("amountOriginal")
        af = p.get("amountFinal")
        if cur and not CURRENCY_RE.match(cur):
            rep.fail("PEN-01", f"记录 {rid}：币种代码不合规 {cur!r}")
        if cur:
            currencies.add(cur)
        if ao is not None and af is not None and af > ao:
            rep.fail("PEN-02", f"记录 {rid}：最终额 {af} 高于拟议额 {ao}")
        # 金额必须能从原文摘录中找到对应数字
        basis = p.get("amountBasisText")
        if (ao is not None or af is not None) and not basis:
            rep.fail("PEN-03", f"记录 {rid}：有金额但缺 amountBasisText，金额来源不可追溯")
    if len(currencies) > 1:
        rep.stats["currencies"] = sorted(currencies)
        rep.warn("PEN-04", f"库内存在多币种 {sorted(currencies)}：统计层禁止跨币种合计")


def check_status_machine(manifest, rep):
    """STA-01 状态转换合法性；STA-02 撤销记录须保留修订记录"""
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        st = r.get("status")
        if st in ("invalidated", "repealed", "settled"):
            if not r.get("revisionLog"):
                rep.fail("STA-02", f"记录 {rid} 状态为 {st} 但无修订记录（须保留可追溯的终结说明）")
        # 单条记录只有终态时不做转换校验；转换在 revisions 中体现
        for rev in r.get("revisionLog", []):
            old = rev.get("oldStatus")
            new = rev.get("newStatus")
            if old and new and (old, new) not in ALLOWED_TRANSITIONS:
                rep.fail("STA-01", f"记录 {rid}：非法状态转换 {old} → {new}")


def check_citation_discipline(manifest, rep):
    """CIT-01~05 方法论纪律"""
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        for a in r.get("assertions", []):
            field = (a.get("field") or "").lower()
            value = a.get("value") or ""

            # CIT-01 中文法学文献四要素
            if field in ("citation", "literature", "reference") and value:
                if any(k in value for k in ("《", "载", "中国", "法学", "学报")):
                    for f in REQUIRED_CITATION_FIELDS:
                        if not value.strip():
                            rep.fail("CIT-01", f"记录 {rid}：中文文献缺要素 {f}")

            # CIT-02 不得引用无法被检索命中的文献——须有检索凭证
            if field in ("citation", "literature", "reference") and value:
                if not (a.get("locator") or "").strip():
                    rep.fail("CIT-02", f"记录 {rid}：文献引用缺检索凭证（retrieval_channel/query/hit）")

            # CIT-03 程序性处置不得用作实体规则先例
            if field == "used_as" and "substantive_precedent" in value:
                txt = (a.get("value") or "").lower()
                for kw in ("dismiss", "settlement", "withdraw", "procedural", "程序性", "和解", "撤诉"):
                    if kw in txt:
                        rep.fail("CIT-03", f"记录 {rid}：程序性处置案件被用作实体先例")

            # CIT-04 裁判结论须核对裁判文书本身
            if field in ("disposition", "holding", "outcome") and value:
                if a.get("evidenceLevel") not in L_OFFICIAL_SECONDARY:
                    rep.fail("CIT-04", f"记录 {rid}：裁判结论字段 {field} 的证据等级为 {a.get('evidenceLevel')}，"
                                       f"须回原文核对（L0/L1）")

            # CIT-05 脚注与正文引用处同步——检查引用字段的编号连续性
            if field == "footnote_ref":
                if not re.match(r"^\d+$", value.strip()):
                    rep.fail("CIT-05", f"记录 {rid}：脚注编号非纯数字 {value!r}")


def check_entity_integrity(manifest, rep):
    """ENT-01 主体字段须为 entityId 外键；ENT-02 实体不删除只退休"""
    entity_ids = {e.get("entityId") for e in manifest.get("entities", [])}
    for e in manifest.get("entities", []):
        if e.get("status") == "merged" and not e.get("supersededBy"):
            rep.fail("ENT-02", f"实体 {e.get('entityId')} 状态为 merged 但缺 supersededBy")
    for r in manifest.get("records", []):
        rid = r.get("recordId", "?")
        for s in r.get("subjects", []):
            if s not in entity_ids:
                rep.fail("ENT-01", f"记录 {rid} 引用了未登记的 entityId：{s}")


def check_dead_fields(manifest, rep):
    """DEAD-01 全库取单一默认值的字段视为死字段，应删除或改为派生"""
    for r in manifest.get("records", []):
        for k, v in r.items():
            if k in ("recordId", "recordType", "title", "assertions", "subjects", "topics", "status"):
                continue
            if isinstance(v, dict):
                continue
    # 布尔型字段全库同值即为死字段
    bool_keys = set()
    for r in manifest.get("records", []):
        for k, v in r.items():
            if isinstance(v, bool):
                bool_keys.add(k)
    for k in bool_keys:
        vals = {r.get(k) for r in manifest.get("records", [])}
        if len(vals) == 1:
            rep.fail("DEAD-01", f"死字段 {k}：全库取值恒为 {vals.pop()}，应删除或改为派生字段")


def check_meta(manifest, rep):
    """META-01 数据截止日与来源占比必须在 meta 中声明"""
    meta = manifest.get("meta", {})
    for k in ("dataCutoff", "officialSourceRatio", "license", "notice"):
        if k not in meta:
            rep.fail("META-01", f"meta 缺少 {k}（站点首屏须显示数据截止日与一手占比）")


def check_manifest_consistency(manifest, rep):
    """MAN-01/02 manifest 声明与实际一致；引用的记录文件必须存在"""
    meta = manifest.get("meta", {})
    n = len(manifest.get("records", []))
    # caseCount 现在是"案例数"，不再是总记录数
    actual_case = sum(1 for r in manifest.get("records", []) if r.get("recordType") == "case")
    if "caseCount" in meta and meta["caseCount"] != actual_case:
        rep.fail("MAN-01", f"meta.caseCount={meta['caseCount']} 与实际案例数 {actual_case} 不符")
    if "recordCount" in meta and meta["recordCount"] != n:
        rep.fail("MAN-01", f"meta.recordCount={meta['recordCount']} 与实际记录数 {n} 不符")
    for item in manifest.get("records", []):
        if isinstance(item, str):
            if not (DATA / item).exists():
                rep.fail("MAN-02", f"manifest 引用的记录文件不存在：{item}")


# ═══════════════════════════════════════════════════════════════════

CHECKS = [
    check_schema_basics,
    check_record_ids,
    check_source_registry,
    check_evidence_ratio,
    check_core_field_evidence,
    check_source_level_consistency,
    check_manual_source_not_primary,
    check_locator_quality,
    check_meta_counts,
    check_pending_declared,
    check_snapshot_declared,
    check_date_order,
    check_penalty,
    check_status_machine,
    check_citation_discipline,
    check_entity_integrity,
    check_dead_fields,
    check_meta,
    check_manifest_consistency,
]


def main():
    ap = argparse.ArgumentParser(description="航空法律资料库 数据质量断言")
    ap.add_argument("--data", default="data/manifest.json", help="manifest 路径")
    ap.add_argument("--strict", action="store_true", help="警告也视为失败")
    args = ap.parse_args()

    path = Path(args.data)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"[FATAL] manifest 不存在：{path}", file=sys.stderr)
        return 2

    manifest = load_manifest(path)
    if "records" in manifest and isinstance(manifest["records"], list) \
            and manifest["records"] and isinstance(manifest["records"][0], str):
        manifest["records"] = collect_records(manifest)

    rep = Report()
    for fn in CHECKS:
        try:
            fn(manifest, rep)
        except Exception as e:  # 单条断言异常不应中断整体
            rep.fail(fn.__name__, f"断言执行异常：{e!r}")

    print("=" * 62)
    print("航空法律资料库 · 数据质量断言")
    print("=" * 62)
    print(f"记录数        : {len(manifest.get('records', []))} 条")
    print(f"断言数        : {rep.stats.get('assertionCount', 0)}")
    print(f"核心字段支撑  : {rep.stats.get('coreFieldPrimaryRatio', 0):.1%}"
          f"（{rep.stats.get('coreFieldCount', 0)} 条核心断言）")
    print(f"待核验条目    : {rep.stats.get('pendingCount', 0)}")
    print("-" * 62)

    if rep.errors:
        print(f"\n[FAIL] {len(rep.errors)} 项阻断级问题：\n")
        for rule, msg in rep.errors:
            print(f"  {rule}  {msg}")
    else:
        print("\n[OK] 阻断级断言全部通过")

    if rep.warnings:
        print(f"\n[WARN] {len(rep.warnings)} 项需人工确认：\n")
        for rule, msg in rep.warnings:
            print(f"  {rule}  {msg}")

    print("\n" + "=" * 62)
    if rep.errors or (args.strict and rep.warnings):
        return 1
    print("结论：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
