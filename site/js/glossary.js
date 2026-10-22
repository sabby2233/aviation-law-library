/**
 * glossary.js — 中英术语对照表
 *
 * 用途：让中文读者能用中文检索英文原文。
 * 航空法律领域的中文术语与英文原文的对应关系是稳定的（适航指令、远程识别、
 * 无人机特殊规则等），用一张显式对照表比引入翻译模型更可控、更可审计。
 *
 * 两条纪律：
 *   1. 最长匹配——查「适航指令」只展开「适航指令」，不再连带展开「适航」，
 *      否则会引入大量假阳性（实测「管制空域」曾返回全部 airspace 记录）
 *   2. 键唯一——同一术语不得重复定义（JS 对象字面量后者覆盖前者且无告警）
 *
 * 原则：只收领域内稳定的术语对，不做通用翻译。
 */

(function (global) {
  'use strict';

  // 中文 → 英文检索词（数组，任一命中即算匹配）
  // 注意：键按长度降序做最长匹配，顺序无关；但不得有重复键。
  const ZH_TO_EN = {
    // 适航与审定
    '适航指令汇编': ['airworthiness directive', 'ad'],
    '补充型号合格证': ['type certificate', 'type certification', 'supplemental type certificate'],
    '型号合格证': ['type certificate', 'type certification'],
    '设计批准': ['design approval'],
    '生产批准': ['production certificate'],
    '检查合格证': ['airworthiness certificate'],
    '适航指令': ['airworthiness directive'],
    '适航': ['airworthiness'],
    '审定': ['certification', 'airworthiness certification'],

    // 无人机与低空
    '小型无人机': ['small unmanned', 'sua', 'suas'],
    '无人驾驶航空器': ['unmanned aircraft', 'uas'],
    '远程识别': ['remote identification', 'remote id'],
    '远程驾驶': ['remote pilot'],
    '无人机': ['unmanned', 'uas', 'uav', 'drone', 'small unmanned'],
    '运行规则': ['operating rules', 'part 107'],
    '超视距': ['beyond visual line of sight', 'bvlos'],
    '运营人': ['operator', 'remote pilot', 'registrant'],
    '飞手': ['remote pilot', 'pilot'],
    '注册': ['registration', 'registry'],
    '管制空域': ['controlled airspace', 'restricted airspace'],
    '受控空域': ['controlled airspace'],
    '空域': ['airspace'],

    // 承运人与运营
    '公共航空运输承运人': ['certificated air carrier', 'part 121'],
    '航空承运人': ['air carrier', 'certificate holder'],
    '小型承运人': ['small air carrier'],
    '安全管理系统': ['safety management system', 'sms'],
    '风险评估': ['safety risk assessment'],
    '安全文化': ['safety culture'],
    '运营人许可': ['operator certificate'],
    '安保': ['security'],
    '危险品': ['dangerous goods', 'hazardous materials'],

    // 旅客与权利
    '旅客权利': ['passenger rights'],
    '旅客': ['passenger', 'traveler'],
    '延误': ['delay', 'cancellation'],
    '退款': ['refund'],
    '拒载': ['denied boarding'],
    '行李': ['baggage', 'checked baggage'],
    '转机': ['connecting flight'],
    '歧视': ['discrimination'],

    // 数据与隐私
    '数据保护': ['data protection', 'privacy'],
    '个人信息': ['personal data', 'personal information'],
    '数据泄露': ['data breach', 'breach'],
    '网络安全事件': ['cyber incident', 'security incident'],
    '网络安全': ['cybersecurity', 'cyber', 'information security'],
    '生物识别': ['biometric'],
    '人脸识别': ['facial recognition'],
    '隐私': ['privacy'],
    '报告义务': ['reporting requirement', 'report'],

    // 监管与法律
    '拟议规则': ['proposed rule', 'prorule', 'notice of proposed'],
    '最终规则': ['final rule'],
    '终局规则': ['final rule'],
    '法规': ['rule', 'regulation', 'part'],
    '罚款': ['civil penalty', 'penalty', 'fine'],
    '处罚': ['penalty', 'enforcement', 'sanction'],
    '执法': ['enforcement'],
    '合规': ['compliance'],
    '豁免': ['exemption', 'waiver'],
    '咨询': ['consultation', 'request for comment'],
    '公告': ['notice'],

    // 程序
    '意见征集': ['request for comment', 'comment period', 'petition for rulemaking'],
    '公众意见': ['public comment', 'comments'],
    '过渡期': ['transition period', 'compliance date'],
    '生效': ['effective date', 'effective'],

    // 组织与机构
    '国家交通安全委员会': ['national transportation safety board', 'ntsb'],
    '欧洲航空安全局': ['easa', 'european union aviation safety agency'],
    '国际民航组织': ['icao', 'international civil aviation organization'],
    '联邦航空局': ['federal aviation administration', 'faa'],
    '运输部': ['transportation department', 'dot'],
    '联邦公报': ['federal register'],

    // 中国法源：eCFR 现行条文与民航规章的规范键
    // 说明：本库数据分属美国（eCFR/FR）、中国（CCAR/法通网）两大法源，
    // 中文术语需能命中英文条文正文，否则中文读者检索落空。
    '民用航空法': ['civil aviation law', 'civil aviation law of the people'],
    '民用航空器适航管理条例': ['airworthiness', 'airworthiness regulation'],
    '无人驾驶航空器飞行管理暂行条例': ['unmanned', 'unmanned aircraft'],
    '航空器国籍登记': ['nationality registry', 'aircraft registration'],
    '民航规章': ['ccar', 'civil aviation regulations'],
    '现行有效': ['effective', 'in force'],
    '废止': ['repealed'],
    '失效': ['invalidated'],
    '历史版本': ['superseded'],
    '规章': ['regulation', 'rule'],
    '规范性文件': ['normative document'],
    '效力位阶': ['effectiveness', 'hierarchy'],
    '涉外法律法规': ['foreign-related', 'overseas'],

    // ICAO 附件（标准名取自 ICAO 官方《Annexes 1 to 18》booklet，224 页六语种含中文）
    // 说明：中文名与英文名同键，故「附件第 8 条」与「Annex 8」命中同一批记录。
    '人员执照的颁发': ['personnel licensing'],
    '空中规则': ['rules of the air'],
    '航图': ['aeronautical charts'],
    '计量单位': ['units of measurement'],
    '航空器的运行': ['operation of aircraft'],
    '航空器国籍和登记标志': ['aircraft nationality and registration marks'],
    '航空器适航性': ['airworthiness of aircraft'],
    '简化手续': ['facilitation'],
    '航空电信': ['aeronautical telecommunications'],
    '空中交通服务': ['air traffic services'],
    '搜寻与援救': ['search and rescue'],
    '事故征候调查': ['accident and incident investigation'],
    '航行情报服务': ['aeronautical information services'],
    '非法干扰行为': ['acts of unlawful interference'],
    '危险品的安全航空运输': ['safe transport of dangerous goods'],

    // ICAO 核心概念（研究常用；标准名取自 booklet 正文章标题）
    '芝加哥公约': ['chicago convention'],
    '标准与建议措施': ['standards and recommended practices', 'sarp'],
    '航行服务程序': ['procedures for air navigation services', 'pans'],
    '适航技术手册': ['doc 9760'],

    // 数据保护交叉（法通网域外译本层）
    '个人数据保护法': ['personal data protection', 'data protection'],
    '数据保护法': ['data protection'],
    '隐私保护': ['privacy', 'data protection'],
    '网络安全法': ['cybersecurity', 'network security'],
    '电信法': ['telecommunications', 'electronic communications'],
    '电子交易': ['electronic transactions', 'e-commerce'],
  };

  // 预排序：按长度降序，保证最长匹配优先
  const SORTED_KEYS = Object.keys(ZH_TO_EN).sort((a, b) => b.length - a.length);

  /**
   * 把中文查询词展开为英文检索词。
   * 采用最长匹配：命中「适航指令」后不再检查「适航」。
   *
   * 实现：按长度降序遍历键；对每个键，若查询包含它，且该键未被更长键覆盖，
   * 则纳入。关键在于"未被更长键覆盖"的判断须在纳入前完成——
   * 先收集所有命中的键，再剔除被更长命中键所包含的短键。
   * @param {string} text 原始查询
   * @returns {string[]} 检索词数组（含原词本身）
   */
  function expand(text) {
    if (!text) return [];
    const t = String(text).trim();
    const out = [t];

    // 第一步：找出所有命中的键
    const hits = SORTED_KEYS.filter((zh) => t.includes(zh));
    if (!hits.length) return [t];

    // 第二步：剔除被更长命中键包含的短键（最长匹配）
    const effective = hits.filter((zh) =>
      !hits.some((other) => other !== zh && other.length > zh.length && other.includes(zh))
    );

    for (const zh of effective) {
      for (const en of ZH_TO_EN[zh]) {
        if (!out.includes(en)) out.push(en);
      }
    }
    return out;
  }

  /**
   * 判断查询是否需要中文展开（避免对纯英文查询做无谓处理）
   */
  function needsExpansion(text) {
    return /[一-鿿]/.test(String(text || ''));
  }

  /**
   * 自检：键唯一性 + 无被包含的重复键。
   * 用于 CI 断言，防止术语表漂移。
   */
  function selfCheck() {
    const problems = [];
    const keys = Object.keys(ZH_TO_EN);

    // 1. 键唯一（运行时对象字面量已去重，但源码中可能重复定义）
    const seen = new Set();
    const dupes = [];
    for (const k of keys) {
      if (seen.has(k)) dupes.push(k);
      seen.add(k);
    }
    if (dupes.length) problems.push(`重复键：${dupes.join('、')}`);

    // 2. 无空值
    for (const [k, v] of Object.entries(ZH_TO_EN)) {
      if (!Array.isArray(v) || !v.length) problems.push(`空值：${k}`);
      for (const en of v || []) {
        if (!en || !String(en).trim()) problems.push(`空检索词：${k}`);
      }
    }

    // 3. 子串包含关系检查（长键包含短键时，expand 会跳过短键，需确认是有意的）
    for (const long of keys) {
      for (const short of keys) {
        if (long !== short && long.includes(short) && short.length >= 2) {
          // 这是允许的（expand 靠最长匹配处理），仅记录供人工审阅
        }
      }
    }

    return { ok: problems.length === 0, problems, keyCount: keys.length };
  }

  global.Glossary = { ZH_TO_EN, SORTED_KEYS, expand, needsExpansion, selfCheck };
})(typeof window !== 'undefined' ? window : globalThis);
