#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三轮案例核查回填（2026-10-22）。

只写 recordLevel.verification / caseOutcome / penalty / dates 四类字段，
不动正文与断言。原始文件为 CRLF + 2 空格缩进，写回保持一致。
"""
import json, sys

P = "data/records/cases_aviation_data.json"

V = {
    # ── 已核实 ──────────────────────────────────────────────
    "AVA-GB-ADP-A-003": dict(
        status="verified", outcome="sanction",
        authority="ICO", legalBasis="UK GDPR / DPA 2018",
        caseNo="COM0808/2019（ICO 案件编号未公开披露）",
        evidence="ICO 2020-10-16 罚款公告；Enforcement Tracker ETid-58 记 22,046,000 EUR（即 £20,000,000 的欧元折算），同一决定",
        sourceUrl="https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2020/10/ico-fines-british-airways-20m-for-data-breach/",
        note="原始拟议罚款 £183,390,000，最终降至 £20,000,000；金额口径 GBP 与 EUR 并存，勿混用",
        date="2020-10-16",
    ),
    "AVA-SG-ADP-A-001": dict(
        status="verified", outcome="sanction",
        authority="Personal Data Protection Commission (PDPC), Singapore",
        legalBasis="PDPA 2012 s.11(3)、s.12（accountability）、s.24（protection）",
        caseNo=None,
        evidence="PDPC 决定（2025-10-31 作出，2026-01-08 公布）；Baker McKenzie 2026-01 评述；影响 336,759 人，泄露含 NRIC 与护照影像",
        sourceUrl="https://www.pdpc.gov.sg/organisations/regulations-decisions/enforcement-decisions/breach-of-the-accountability-and-protection-obligations-by-air-sino-euro-associates-travel-pte-ltd",
        note="作出日 2025-10-31 与公布日 2026-01-08 不同，引用时须写明用的是哪一个",
        date="2025-10-31", amount=47000, cur="SGD", against="PDPC",
    ),
    # ── 已核实但须纠正 ──────────────────────────────────────
    "AVA-AU-ADP-A-001": dict(
        status="verified_with_correction", outcome="other",
        authority="Office of the Australian Information Commissioner (OAIC)",
        legalBasis="Privacy Act 1988 (Cth)，APP 1.2 / 8.1 / 11.1",
        caseNo=None,
        evidence="OAIC《Report into preliminary inquiries of Qantas》（2026-07-16）；隐私专员 Carly Kind 新闻稿：初步调查未发现违法可能，不启动 CII、不采取执法行动",
        sourceUrl="https://www.oaic.gov.au/news/media-centre/privacy-commissioner-completes-preliminary-inquiries-into-qantas-2025-data-incident",
        note="结论与库内原判断相反：不是「调查中」，而是 2026-07-16 已结案且未处罚。事件本身真实：2025-06-28 对境外第三方客服中心的 vishing 攻击，5,670,000 条记录 / 约 5,120,000 名澳大利亚人。原记「5.7M」是记录数不是人数",
        date="2026-07-16", title_en="OAIC Preliminary Inquiry into Qantas Data Breach (2025, Closed Without Action)",
    ),
    "AVA-CA-ADP-A-001": dict(
        status="verified_with_correction", outcome="other",
        authority="Office of the Privacy Commissioner of Canada (OPC)",
        legalBasis="PIPEDA, Principle 4.7",
        caseNo=None,
        evidence="OPC 新闻稿 2026-07-14（WestJet 签署 compliance letter）；WestJet 2026-10-14 公告：OPC 关闭调查、未认定违反 PIPEDA；影响 5,164,000 人",
        sourceUrl="https://www.priv.gc.ca/en/opc-news/news-and-announcements/2026/nr-c_260714",
        note="不是「调查中」：2025-08 立案 CII，2026-07 签 compliance letter（强化 MFA、身份与访问控制、安全意识、第三方评估），2026-10-14 结案，无行政处罚。属「合规函+承诺」替代处罚的样本",
        date="2026-10-14", title_en="OPC Investigation into WestJet Breach (Closed with Compliance Letter, No Penalty)",
    ),
    "AVA-HK-ADP-A-001": dict(
        status="verified_with_correction", outcome="other",
        authority="Office of the Privacy Commissioner for Personal Data (PCPD), Hong Kong, China",
        legalBasis="PDPO (Cap. 486) 附表 1 保障资料原则第 4(1) 条",
        caseNo="PCPD 调查报告编号 r26_11405",
        evidence="PCPD《Wrongful Disclosure of Personal Data Through Sample Forms by an Airline Company》2026-03-27；Tanner De Witt 2026-04-29 评述",
        sourceUrl="https://www.pcpd.org.hk/english/enforcement/commissioners_findings/files/r26_11405_e.pdf",
        note="主体纠正：被裁定违反 DPP 4(1) 并获发强制执行通知（Enforcement Notice）的是**航空公司**（data user），不是地面服务代理——代理是其 processor。无罚款。事实为香港飞越南航班行李延误索赔中，富国岛地代把含他人姓名/航班/银行账户的样表发给投诉人",
        date="2026-03-27", title_en="PCPD Enforcement Notice against an Airline (Ground Agent Disclosed Passenger Data)",
    ),
    "AVA-US-ADP-A-003": dict(
        status="verified_with_correction", outcome="sanction",
        authority="27 个州总检察长（Assurance of Discontinuance），**非 FTC**",
        legalBasis="州不公平/欺骗性行为法与数据泄露通知法；PCI DSS",
        caseNo=None,
        evidence="多家媒体与 Digital Guardian 报道：2021 年圣诞节前与 27 州 AG 达成 AOD，和解金约 $2.4M；涉 2016-08 至 2017-03 SynXis 中央预订系统入侵、约 130 万张支付卡",
        sourceUrl="https://www.digitalguardian.com/blog/sabre-agrees-24m-settlement-following-2017-data-breach",
        note="机构与金额纠正：FTC 未对 Sabre 发布同意令。原记「FTC Consent Order」错误，实为多州 AG 和解。与 Carnival 条目同属「把州级执法误记为 FTC」的系统性错误",
        title_en="Multistate AG Settlement with Sabre Corporation (SynXis Data Breach)",
        amount=2400000, cur="USD", against="27-state AG AOD", date=None,
    ),
    "AVA-US-ADP-C-003": dict(
        status="verified_with_correction", outcome="other",
        authority="U.S. District Court, Eastern District of New York",
        legalBasis="Electronic Communications Privacy Act；N.Y. Gen. Bus. Law §§ 349、350",
        caseNo="1:26-cv-02405",
        evidence="CBS News 2026-04-23；Top Class Actions（载明案号与法院）；中国航空新闻网 2026-04-24 转载",
        sourceUrl="https://www.cbsnews.com/news/jetblue-lawsuit-surveillance-pricing-personal-data-tickets/",
        note="诉讼真实：2026-04-22 立案，原告 Andrew Phillips，指控 JetBlue 用浏览数据动态定价并与 FullStory、PROS Holdings 共享数据。**「索赔 $2.5B」无任何来源支持，已置空**。案件未决，不得作为已决赔偿引用",
        date="2026-04-22", amount=None, cur=None, against=None,
    ),
    "AVA-FR-ADP-A-002": dict(
        status="verified_with_correction", outcome="other",
        authority="CNIL（仅受通报，未见立案调查的公开信息）",
        legalBasis="GDPR 第 33 条（泄露通报）",
        caseNo=None,
        evidence="Air France-KLM 2025-08-06 披露；已向 CNIL 与荷兰 AP 通报；涉第三方客服平台（疑 Salesforce 相关 ShinyHunters 活动）",
        sourceUrl="https://www.bleepingcomputer.com/news/security/air-france-and-klm-disclose-data-breaches-impacting-customers/",
        note="性质纠正：这是**泄露事件+依法通报**，不是「CNIL 展开调查」。截至目前无 CNIL 立案或处罚的公开记录。泄露内容为姓名、联系方式、Flying Blue 号码与客服请求主题，不含护照/支付/行程",
        date="2025-08-06", title_en="Air France Data Breach (Notified to CNIL, 2025)",
    ),
    # ── 无法证实 ────────────────────────────────────────────
    "AVA-DE-ADP-A-001": dict(
        status="unverified", outcome="investigation",
        authority="BfDI（未见任何官方确认）",
        legalBasis=None, caseNo=None,
        evidence="仅 botcrawl.com、brinztech.com 等安全营销博客转述「暗网论坛叫卖」，无 Lufthansa 官方声明、无 BfDI 立案公告、无主流媒体报道",
        sourceUrl=None,
        note="**无法证实**。同期真实的航空泄露为 Qantas、Iberia、Collins Aerospace、Air France-KLM、Vietnam Airlines，均无 Lufthansa。细节表述（如「航空业最严重」）系内容农场话术。已降为 L4 线索，不得作为案例引用",
        date=None,
    ),
}

# 本轮未能取得可核依据的，写明确认状态与下一步渠道（不是「已核」，也不是空白）
PENDING_ROUTE = {
    "AVA-ES-ADP-A-003": "AEPD 决定库按 PS- 编号检索；疑与 ETid-196 拼接，需先验是否存在独立决定",
    "AVA-ES-ADP-A-004": "AEPD 决定库按 Ryanair + 2023 检索",
    "AVA-ES-ADP-A-005": "疑与 ETid-86（2019 Vueling cookie, €30,000）拼接，€60,000/2023 无对应记录",
    "AVA-FR-ADP-A-001": "CNIL sanctions 库（Derichebourg Multiservices, €400,000）",
    "AVA-IT-ADP-A-003": "Garante 决定库 / NOYB 案件页（Ryanair 人脸识别投诉）",
    "AVA-SE-ADP-A-001": "IMY 决定库（SAS 数据主体访问请求）",
    "AVA-TR-ADP-A-002": "KVKK 决定库（航空公司复印身份证）",
    "AVA-US-ADP-A-002": "DOT 执法记录 / aviation consumer reports",
    "AVA-US-ADP-A-004": "FTC 6(b) order 公告（surveillance pricing）",
    "AVA-US-ADP-C-001": "CourtListener / PACER（United Airlines BIPA）",
    "AVA-US-ADP-C-002": "CourtListener / PACER（FlightAware 泄露集体诉讼）",
    "AVA-NO-ADP-A-001": "Datatilsynet 决定库（Norwegian Air Shuttle）",
    "AVA-NL-ADP-A-001": "AP 决定库（Schiphol 生物识别）",
    "AVA-HU-ADP-A-001": "NAIH 决定库（Lufthansa）",
    "AVA-CH-ADP-A-001": "FDPIC 决定库（SWISS）",
    "AVA-KR-ADP-A-001": "PIPC 决定库（Korean Air）",
    "AVA-IN-ADP-A-001": "DPBI / MeitY 通知（Air India SITA 泄露）",
    "AVA-AT-ADP-A-001": "DSB 决定库（Austrian Airlines）",
    "AVA-PT-ADP-A-001": "CNPD 决定库（TAP）",
    "AVA-IE-ADP-A-001": "DPC 决定库（Ryanair cookie）",
    "AVA-PL-ADP-A-001": "UODO 决定库（LOT）",
    "AVA-DK-ADP-A-001": "Datatilsynet 决定库（Copenhagen Airports 生物识别）",
}


def main():
    data = json.load(open(P, encoding="utf-8"))
    idx = {r["recordId"]: r for r in data}
    done = 0
    for rid, u in V.items():
        r = idx.get(rid)
        if not r:
            print("!! missing", rid, file=sys.stderr)
            continue
        rl = r.setdefault("recordLevel", {})
        rl["verificationStatus"] = u["status"]
        rl["caseOutcome"] = u["outcome"]
        rl["verification"] = {
            "status": u["status"],
            "checkedAt": "2026-10-22",
            "checkedVia": "官方机构公告 / 官方文书 / 权威数据库（逐条检索）",
            "authority": u["authority"],
            "caseNo": u.get("caseNo"),
            "ecli": None,
            "legalBasis": u.get("legalBasis"),
            "evidence": u["evidence"],
            "sourceUrl": u.get("sourceUrl"),
            "note": u.get("note"),
        }
        if u.get("title_en"):
            r["titleEn"] = u["title_en"]
        d = r.setdefault("dates", {})
        if u.get("date"):
            d["decisionDate"] = u["date"]
            d["decisionDateBasis"] = "official"
        elif rid.startswith("AVA-DE-"):
            d["decisionDate"] = None
            d["decisionDateBasis"] = "unknown"
        # penalty
        if "amount" in u:
            if u["amount"] is None:
                r["penalty"] = None
            else:
                p = r.get("penalty") or {}
                p.update({
                    "amountOriginal": u["amount"],
                    "amountFinal": u["amount"],
                    "currency": u["cur"],
                    "amountVerified": True,
                    "verifiedAgainst": u["against"],
                })
                r["penalty"] = p
        done += 1

    for rid, route in PENDING_ROUTE.items():
        r = idx.get(rid)
        if not r:
            continue
        rl = r.setdefault("recordLevel", {})
        if (rl.get("verification") or {}).get("status") in ("verified", "verified_with_correction"):
            continue
        rl["verificationStatus"] = "pending"
        rl["verification"] = {
            "status": "pending",
            "checkedAt": "2026-10-22",
            "checkedVia": "本轮未取得可核依据",
            "authority": None, "caseNo": None, "ecli": None, "legalBasis": None,
            "evidence": None, "sourceUrl": None,
            "note": "待查渠道：" + route,
        }

    out = json.dumps(data, ensure_ascii=False, indent=2)
    with open(P, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(out)
    print(f"回填 {done} 条；标注 pending 渠道 {len(PENDING_ROUTE)} 条")


if __name__ == "__main__":
    main()
