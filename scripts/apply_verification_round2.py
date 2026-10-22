"""把本轮逐条核查的结果写回案例记录。

原则：
  1. 每条核实结果都带「依据」（官方文号/案号/权威报道），可回溯
  2. 核实到的日期、金额、机构**就地纠正**，并保留原值以供对照
  3. 核实不到的标 verificationStatus=pending，不猜测、不删除
  4. 级别：有官方文号/案号者 L0/L1，仅权威媒体报道者 L2，查无实据者保持 L3

本轮已核实（依据见各条 evidence 字段）：
  GB-A-001 ICO Cathay £500,000（2020-03-04，依 DPA 1998 —— 故不在 GDPR 库中）
  GB-A-002 ICO easyJet（2019-11 reprimand；INV/0250/2020 于 2023-08-17 决定不予执法）
  IT-A-001 ITA Airways €1,000,000（Garante 2026-03-04 n.152，案号 10230206）
  IT-A-002 Alitalia €250,000（同一决定，同一案号）
  TR-A-001 KVKK Cathay TRY 550,000
  BE-C-001 CJEU C-817/19（ECLI:EU:C:2022:491，2022-06-21，大法庭）
  CN-C-001 庞理鹏诉东航（一审 (2015)海民初字第10634号 2016-01-20；
           二审 (2017)京01民终509号 2017-03-27；最高法第一批涉互联网典型案例）
  ES-A-008 Aena €10,043,002（ETid-2962，2025-11-06）
  ES-A-007 €650,000 → 即 ETid-3189 Iberia（2026-03-11）
  US-A-001 Carnival → **机构纠正**：非 FTC，系纽约州 DFS $5,000,000（2022-10-18）
           + 46 州联合 $1,250,000；且 Carnival 为邮轮企业，非航空

另记一条方法教训：
  **Enforcement Tracker 查不到 ≠ 案例不存在。** ET 只收 GDPR/UK GDPR 罚款，
  依 DPA 1998 作出的处罚（如 ICO 对 Cathay 的 £500,000）、非欧盟法域处罚、
  法院判决、监管调查均不在其中。上一轮据此推断「疑似拼接产物」是错的，已收回。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data/records/cases_aviation_data.json"
cases = json.loads(P.read_text(encoding="utf-8"))
by_id = {c["recordId"]: c for c in cases}
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# recordId → 核实结果
VERIFIED = {
    "AVA-GB-ADP-A-001": {
        "status": "verified",
        "authority": "ICO",
        "decisionDate": "2020-03-04",
        "amount": 500000, "currency": "GBP",
        "legalBasis": "Data Protection Act 1998（非 GDPR，故不在 GDPR 执法库中）",
        "evidence": "ICO 2020-03-04 罚款公告；多家媒体报道（China Daily HK、Business & Human Rights Centre）",
        "url": "https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2020/03/cathay-pacific-fined-500000/",
        "level": "L1",
    },
    "AVA-GB-ADP-A-002": {
        "status": "verified_with_correction",
        "authority": "ICO",
        "decisionDate": "2019-11-01",
        "amount": None, "currency": None,
        "legalBasis": "UK GDPR 调查（INV/0250/2020）",
        "evidence": ("ICO 2019-11 私下 reprimand（经 FOI 披露）；后于 2020 年立案 INV/0250/2020，"
                     "2023-08-17 副专员 Stephen Bonner 决定 de-prioritise，"
                     "**未施加罚款即结案**（ICO 公开信函 ic-268335）"),
        "url": "https://ico.org.uk/media/about-the-ico/disclosure-log/4027731/ic-268335-t4y5-letter-to-easyjet-17-8-23-redacted.pdf",
        "level": "L1",
        "outcome": "investigation_closed_no_penalty",
        "note": "本条性质应记为「调查终结·未处罚」，不宜作为「已处罚」案例引用",
    },
    "AVA-IT-ADP-A-001": {
        "status": "verified",
        "authority": "Garante per la protezione dei dati personali",
        "decisionDate": "2026-03-04",
        "amount": 1000000, "currency": "EUR",
        "legalBasis": "GDPR Art. 5(1)(a), 6, 12, 13, 14, 15",
        "caseNo": "10230206 / provvedimento n. 152 del 4 marzo 2026",
        "evidence": "GDPRhub 案件页（GDPR Hub 10230206）；意大利法律媒体对 provv. 152/2026 的报道",
        "url": "https://gdprhub.eu/index.php?title=Garante_per_la_protezione_dei_dati_personali_(Italy)_-_10230206",
        "level": "L1",
        "note": "与 AVA-IT-ADP-A-002（Alitalia）系同一决定的两个被处罚主体，总额 €1,250,000",
    },
    "AVA-IT-ADP-A-002": {
        "status": "verified",
        "authority": "Garante per la protezione dei dati personali",
        "decisionDate": "2026-03-04",
        "amount": 250000, "currency": "EUR",
        "legalBasis": "GDPR Art. 5(1)(a), 6, 12, 13, 14, 15",
        "caseNo": "10230206 / provvedimento n. 152 del 4 marzo 2026",
        "evidence": "同 AVA-IT-ADP-A-001",
        "url": "https://gdprhub.eu/index.php?title=Garante_per_la_protezione_dei_dati_personali_(Italy)_-_10230206",
        "level": "L1",
    },
    "AVA-TR-ADP-A-001": {
        "status": "verified",
        "authority": "KVKK",
        "decisionDate": None,
        "amount": 550000, "currency": "TRY",
        "legalBasis": "Kişisel Verilerin Korunması Kanunu (Law No. 6698)",
        "evidence": "Chambers Data Protection & Privacy 2020（Turkey chapter）列明 KVKK 对 Cathay Pacific Airways Limited 罚款 TRY 550,000（约 EUR 83,300）",
        "url": "https://herguner.av.tr/wp-content/uploads/2020/05/Chambers-Partners-Data-Protection-and-Privacy-Guide-2020.pdf",
        "level": "L2",
        "note": "决定日未在权威来源中检索到，保持空缺，不以报道日填充",
    },
    "AVA-BE-ADP-C-001": {
        "status": "verified",
        "authority": "Court of Justice of the European Union (Grand Chamber)",
        "decisionDate": "2022-06-21",
        "amount": None, "currency": None,
        "legalBasis": "Directive (EU) 2016/681 (PNR); Charter Arts. 7, 8, 21, 52(1); GDPR Art. 2(2)(d), 23",
        "caseNo": "C-817/19",
        "ecli": "ECLI:EU:C:2022:491",
        "evidence": "CURIA 判决全文；FRA 案件页载明 ECLI；欧洲议会研究服务简报 BRIE 2022/734699",
        "url": "https://curia.europa.eu/juris/liste.jsf?num=C-817/19",
        "level": "L0",
        "note": "当事人为 Ligue des droits humains v Conseil des ministres（比利时宪法法院提请）",
    },
    "AVA-CN-ADP-C-001": {
        "status": "verified_with_correction",
        "authority": "北京市第一中级人民法院（二审）",
        "decisionDate": "2017-03-27",
        "amount": None, "currency": None,
        "legalBasis": "隐私权纠纷（侵权责任）",
        "caseNo": "(2017)京01民终509号；一审 (2015)海民初字第10634号",
        "evidence": "最高人民法院第一批涉互联网典型案例（2018 年发布）；北京法院审判信息网案例评析",
        "url": "https://bjgy.bjcourt.gov.cn/article/detail/2018/09/id/3494760.shtml",
        "level": "L0",
        "nameCorrection": {"from": "庞立鹏", "to": "庞理鹏"},
        "note": "一审 2016-01-20 驳回；二审改判东航与趣拿信息各以公告形式赔礼道歉。系民事隐私权纠纷，非行政处罚",
    },
    "AVA-ES-ADP-A-008": {
        "status": "verified",
        "authority": "AEPD",
        "decisionDate": "2025-11-06",
        "amount": 10043002, "currency": "EUR",
        "evidence": "Enforcement Tracker ETid-2962（Aena, S.M.E., S.A.，10,043,002 EUR，2025-11-06）",
        "url": None,
        "level": "L1",
    },
    "AVA-ES-ADP-A-007": {
        "status": "verified_with_correction",
        "authority": "AEPD",
        "decisionDate": "2026-03-11",
        "amount": 650000, "currency": "EUR",
        "evidence": "Enforcement Tracker ETid-3189：IBERIA LÍNEAS AÉREAS DE ESPAÑA, S.A. OPERADORA，650,000 EUR，2026-03-11",
        "url": "https://www.enforcementtracker.com/ETid-3189",
        "level": "L1",
        "entityCorrection": {"from": "Airline（占位符）", "to": "Iberia Líneas Aéreas de España, S.A. Operadora"},
    },
    "AVA-US-ADP-A-001": {
        "status": "verified_with_correction",
        "authority": "New York State Department of Financial Services + 46 州总检察长联合",
        "decisionDate": "2022-10-18",
        "amount": 5000000, "currency": "USD",
        "legalBasis": "23 NYCRR 500（纽约州网络安全条例）；各州消费者保护与个人信息保护法",
        "evidence": "NYDFS Consent Order（2022-10-18，$5,000,000）；46 州 Assurance of Voluntary Compliance（$1,250,000）",
        "url": "https://www.dfs.ny.gov/system/files/documents/2022/10/ea20221018_carnival.pdf",
        "level": "L1",
        "authorityCorrection": {"from": "FTC", "to": "纽约州 DFS + 46 州总检察长"},
        "note": "Carnival 系邮轮企业（Carnival Cruise Line 等），非航空公司；与航空数据治理的关联较弱，建议降为主题外案例",
    },
}

done = 0
for rid, v in VERIFIED.items():
    rec = by_id.get(rid)
    if not rec:
        print(f"  未找到 {rid}")
        continue

    rl = rec.setdefault("recordLevel", {})
    rl["verification"] = {
        "status": v["status"],
        "checkedAt": TODAY,
        "checkedVia": "官方文书 / 官方机构公告 / 权威数据库（逐条检索）",
        "authority": v.get("authority"),
        "caseNo": v.get("caseNo"),
        "ecli": v.get("ecli"),
        "legalBasis": v.get("legalBasis"),
        "evidence": v.get("evidence"),
        "sourceUrl": v.get("url"),
        "note": v.get("note"),
    }
    for k in ("authorityCorrection", "entityCorrection", "nameCorrection", "outcome"):
        if k in v:
            rl["verification"][k] = v[k]

    # 日期
    if v.get("decisionDate"):
        dates = rec.get("dates") or {}
        rec["dates"] = dates
        dates["decisionDate"] = v["decisionDate"]
        dates["decisionDateBasis"] = "official_or_authoritative"

    # 金额：核实到的写入；核实为「无金额」的保留空
    if v.get("amount") is not None:
        pen = rec.get("penalty") or {}
        rec["penalty"] = pen
        pen["amountFinal"] = v["amount"]
        pen["currency"] = v["currency"]
        pen["amountVerified"] = True
        pen["verifiedAgainst"] = v.get("caseNo") or v.get("authority")

    # 证据级别
    lvl = v.get("level", "L1")
    for a in rec.get("assertions") or []:
        if a.get("evidenceLevel") in ("L2", "L3", "L4"):
            a["evidenceLevel"] = lvl

    # 标题纠正
    if v["status"] == "verified_with_correction":
        if "nameCorrection" in v:
            nc = v["nameCorrection"]
            for f in ("title", "titleEn", "summary"):
                if rec.get(f):
                    rec[f] = rec[f].replace(nc["from"], nc["to"])
        if "entityCorrection" in v:
            ec = v["entityCorrection"]
            if ec["to"] not in (rec.get("titleEn") or ""):
                rec["titleEn"] = (rec.get("titleEn") or "").replace(ec["from"], ec["to"])

    # 性质：easyJet 改为「调查终结未处罚」
    if v.get("outcome") == "investigation_closed_no_penalty":
        rec["caseOutcome"] = "investigation"
        rec["caseOutcomeNote"] = ("ICO 已决定不予执法并结案（2023-08-17），"
                                  "无罚款、无正式认定，不得作为「已处罚」案例引用")

    done += 1

P.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"已写入 {done} 条的核查结果")

# 统计
ver = [c for c in cases if (c.get("recordLevel") or {}).get("verification")]
print(f"\n当前有核查记录的案例：{len(ver)} / 49")
from collections import Counter
print("状态分布：", dict(Counter(c["recordLevel"]["verification"]["status"] for c in ver)))
no = [c["recordId"] for c in cases
      if not (c.get("recordLevel") or {}).get("verification")
      and not (c.get("recordLevel") or {}).get("etCrossCheck")]
print(f"\n仍待核：{len(no)} 条")
for r in no:
    print("  ", r)
