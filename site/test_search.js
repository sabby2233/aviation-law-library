/**
 * test_search.js — 检索层回归测试
 *
 * 这不是"打印数字"，是真正的断言测试：任一条不满足即退出码非零，CI 立刻红。
 * 每条断言都对应一个已实测确认过的缺陷（曾返回 568 条假阳性等）。
 *
 * 运行：node test_search.js
 */

const fs = require('fs');
const path = require('path');

// 该运行时的 __dirname 返回 "."，故用 cwd 定位工程根
const CWD = process.cwd();
const BASE = fs.existsSync(path.join(CWD, 'data', 'manifest.json'))
  ? CWD
  : path.join(CWD, '..');
const SITE = path.join(BASE, 'site');

function loadScripts() {
  // 用 vm 在独立沙箱里执行 IIFE，拿到其挂出的 Search / Glossary
  const vm = require('vm');
  const sandbox = { console, RegExp, Math, JSON, Set, Map, Array, Object, String, Number, Date };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);

  for (const f of ['js/glossary.js', 'js/search.js']) {
    const src = fs.readFileSync(path.join(SITE, f), 'utf-8');
    vm.runInContext(src, ctx, { filename: f });
  }
  return { Search: sandbox.Search, Glossary: sandbox.Glossary };
}

const g = loadScripts();
const Search = g.Search;
const Glossary = g.Glossary;

const manifest = JSON.parse(fs.readFileSync(path.join(BASE, 'data', 'manifest.json'), 'utf-8'));
const rules = JSON.parse(fs.readFileSync(path.join(BASE, 'data', 'identifiers.json'), 'utf-8'));

const idx = Search.buildIndex(manifest.records, rules.rules || []);

let pass = 0, fail = 0;
const failures = [];

function check(name, cond, detail) {
  if (cond) {
    pass++;
    console.log(`  ✓ ${name}`);
  } else {
    fail++;
    failures.push(`${name}${detail ? '  → ' + detail : ''}`);
    console.log(`  ✗ ${name}${detail ? '  → ' + detail : ''}`);
  }
}

function R(q) {
  return Search.search(idx, { text: q }).results.length;
}
function warn(q) {
  return Search.search(idx, { text: q }).warnings;
}

console.log('='.repeat(66));
console.log('检索层回归测试');
console.log('='.repeat(66));
console.log(`语料：${manifest.records.length} 条记录\n`);

// ─────────────────────────────────────────────────────────
console.log('【1】标识符精确查：未命中必须零命中，不得回落全文');
// 这些查询曾返回 568 / 275 / 356 条（全部或错误集合）
check('14 CFR 108 不返回全库', R('14 CFR 108') < 50, `实际 ${R('14 CFR 108')}`);
check('14 CFR 1 不返回全库', R('14 CFR 1') < 50, `实际 ${R('14 CFR 1')}`);
check('14 CFR 25.1581 不返回全库', R('14 CFR 25.1581') < 50, `实际 ${R('14 CFR 25.1581')}`);
check('39 CFR 39 不返回 14 CFR 39 的集合', R('39 CFR 39') === 0, `实际 ${R('39 CFR 39')}`);

const a39 = Search.search(idx, { text: '39 CFR 39' }).results.map((h) => h.record.recordId).sort();
const a14 = Search.search(idx, { text: '14 CFR 39' }).results.map((h) => h.record.recordId).sort();
const identical = a39.length === a14.length && a39.every((x, i) => x === a14[i]);
check('39 CFR 39 与 14 CFR 39 结果集不相同', !identical);

// ─────────────────────────────────────────────────────────
console.log('\n【2】标识符精确率：命中即为证据');
{
  // CFR 引用可能来自不同字段：
  //   FR 记录  → cfr_references（逗号分隔的多个引用）
  //   eCFR 记录 → cfr_part（所属部）与 cfr_section（所属条）
  // 因此精确率检查必须覆盖全部三个字段，否则会把正确的 eCFR 命中误判为假阳性。
  const CFR_REF_FIELDS = ['cfr_references', 'cfr_part', 'cfr_section'];
  const hasCfrRef = (rec, needle) =>
    (rec.assertions || []).some((a) =>
      CFR_REF_FIELDS.includes(a.field) && String(a.value).includes(needle));

  const res = Search.search(idx, { text: '14 CFR 39' }).results;
  const allHave = res.every((h) => hasCfrRef(h.record, '14 CFR 39'));
  check('14 CFR 39 命中项均真实含该条引用', allHave, `命中 ${res.length} 条`);
}
{
  const CFR_REF_FIELDS = ['cfr_references', 'cfr_part', 'cfr_section'];
  const hasCfrRef = (rec, needle) =>
    (rec.assertions || []).some((a) =>
      CFR_REF_FIELDS.includes(a.field) && String(a.value).includes(needle));
  const res = Search.search(idx, { text: '14 CFR 91' }).results;
  const allHave = res.every((h) => hasCfrRef(h.record, '14 CFR 91'));
  check('14 CFR 91 命中项均真实含该条引用', allHave, `命中 ${res.length} 条`);
}

// ─────────────────────────────────────────────────────────
console.log('\n【3】规范键语法：key:value 精确查');
check('cfr:14:39 有命中', R('cfr:14:39') > 200, `实际 ${R('cfr:14:39')}`);
check('cfr:14:39 与 "14 CFR 39" 结果一致',
  R('cfr:14:39') === R('14 CFR 39'),
  `${R('cfr:14:39')} vs ${R('14 CFR 39')}`);
check('cfr:39:39 零命中', R('cfr:39:39') === 0, `实际 ${R('cfr:39:39')}`);
check('cfr:14:108 零命中（库中无此部）', R('cfr:14:108') === 0, `实际 ${R('cfr:14:108')}`);
check('未收录标识符给出告警', warn('cfr:14:108').length > 0);

// ─────────────────────────────────────────────────────────
// ICAO 附件：五种写法必须同键，且未收录的附件号须明确告警。
// 这里的断言刻意用「精确等于 1」而非「大于 0」——
// 附件是封闭集合，Annex 8 命中 18 条就意味着退化为全文匹配。
console.log('\n【3b】ICAO 附件：五种写法归一 + 未收录告警');
{
  const icaoHits = (t) => Search.search(idx, { text: t })
    .results.filter((h) => h.record.jurisdiction === 'ICAO').length;

  let allForms = true;
  const bad = [];
  for (let n = 1; n <= 18; n++) {
    const forms = [`Annex ${n}`, `Annex${n}`, `附件 ${n}`, `附件${n}`, `附件第 ${n} 条`];
    const counts = forms.map(icaoHits);
    if (!counts.every((c) => c === 1)) { allForms = false; bad.push(`Annex ${n}: ${counts.join('/')}`); }
  }
  check('18 个附件 × 5 种写法全部精确命中 1 条', allForms, bad.slice(0, 4).join('; '));

  check('icao:annex:8 命名空间查询命中', icaoHits('icao:annex:8') === 1);
  check('括号主题名写法可解析（Annex 8 (Airworthiness of Aircraft)）',
    icaoHits('Annex 8 (Airworthiness of Aircraft)') === 1);

  // Annex 19 是 2006 年才制定的，官方 booklet（2005-06）不含，最初只能从微信相册补入（L3）。
  // 2026-10-23 拿到用户提供的第 2 版 PDF 后，改为从版权页与修订记录页取断言，升到 L1 已核验。
  // 这里断言的是「当前的真实状态」，而不是把早期的临时状态钉死。
  const a19 = icaoHits('Annex 19');
  check('Annex 19 已收录（booklet 不含，另行补入）', a19 === 1, `实际 ${a19}`);
  check('Annex 19 中文写法同键', icaoHits('附件第 19 条') === 1);
  check('Annex 19 已核验且证据等级不高于 L1', (() => {
    const hit = Search.search(idx, { text: 'Annex 19' }).results
      .find((h) => h.record.jurisdiction === 'ICAO');
    if (!hit) return false;
    const rl = hit.record.recordLevel || {};
    const lv = (hit.record.assertions || []).map((x) => x.evidenceLevel);
    const hasCore = (hit.record.assertions || []).some((x) => x.field === 'edition');
    return rl.verificationStatus === 'verified' && rl.sourceTier !== 'L3'
      && lv.every((x) => x !== 'L3') && hasCore;
  })());

  // 确实不存在的附件号：必须零命中 + 明确告警
  check('未收录附件（Annex 20）零命中', icaoHits('Annex 20') === 0);
  check('未收录附件给出告警', warn('Annex 20').length > 0);
  check('未收录附件中文写法也告警', warn('附件第 20 条').length > 0);
}

// ─────────────────────────────────────────────────────────
console.log('\n【4】机型召回：数字段分词必须生效');
for (const [model, minRecall] of [['737', 0.5], ['787', 0.5], ['A350', 0.5], ['320', 0.4]]) {
  const hit = R(model);
  const truth = manifest.records.filter((r) =>
    new RegExp(model.replace(/[A-Z]/g, (c) => c), 'i').test(JSON.stringify(r))).length;
  const recall = truth ? hit / truth : 1;
  check(`机型 ${model} 召回率 ≥ ${(minRecall * 100).toFixed(0)}%`,
    recall >= minRecall, `命中 ${hit} / 真含 ${truth} = ${(recall * 100).toFixed(0)}%`);
}

// ─────────────────────────────────────────────────────────
console.log('\n【5】术语表：最长匹配与键唯一');
{
  const sc = Glossary.selfCheck();
  check('术语表自检通过', sc.ok, sc.problems.join('；'));
}
{
  // 「适航指令」不应连带展开「适航」（曾展开 4 组，引入 57 条假阳性）
  const exp = Glossary.expand('适航指令');
  check('适航指令 只展开 1 组', exp.length === 2, `实际展开 ${exp.length} 组：${exp.join(' | ')}`);
  check('适航指令 不含泛化的 airworthiness', !exp.includes('airworthiness'), exp.join(' | '));
}
{
  // 「管制空域」曾连带展开「空域」，返回全部 airspace 记录
  const exp = Glossary.expand('管制空域');
  check('管制空域 不含泛化的 airspace', !exp.includes('airspace'), exp.join(' | '));
}
{
  // 短词仍应能独立工作
  const exp = Glossary.expand('适航');
  check('适航 可独立展开', exp.includes('airworthiness'), exp.join(' | '));
}

// ─────────────────────────────────────────────────────────
console.log('\n【6】记录 ID 自身可回查（曾 0/617 可查回）');
{
  const sample = manifest.records.slice(0, 20);
  let ok = 0;
  for (const r of sample) {
    if (Search.search(idx, { text: 'id:' + r.recordId }).results.length === 1) ok++;
  }
  check('抽 20 条记录，ID 均可回查', ok === sample.length, `${ok}/${sample.length}`);
}

// ─────────────────────────────────────────────────────────
console.log('\n【7】自由词检索行为');
check('不存在的英文词零命中', R('zzzznonexistent') === 0, `实际 ${R('zzzznonexistent')}`);
check('不存在的词给出告警', warn('zzzznonexistent').length > 0);
check('空查询返回全库', Search.search(idx, { text: '' }).results.length === manifest.records.length);
check('中文查询有命中', R('无人机') > 0, `实际 ${R('无人机')}`);
check('英文查询有命中', R('unmanned') > 0, `实际 ${R('unmanned')}`);

// ─────────────────────────────────────────────────────────
console.log('\n【8】日期筛选不回退（不得用报道日/公布日顶替决定日）');
{
  // 案例只能凭 decisionDate 参与日期筛选。核查后部分案例已取得决定日，
  // 因此断言改为「凡进入结果的案例，必有 decisionDate」——这才是规则本身；
  // 早期版本断言「结果中不得有案例」是把当时的空数据当成了规则，已过时。
  const res = Search.search(idx, { text: '', from: '2026-01-01', to: '2026-12-31' });
  const casesInRange = res.results.filter((h) => h.record.recordType === 'case');
  const allHaveDecision = casesInRange.every((h) =>
    (h.record.dates || {}).decisionDate);
  check('进入日期筛选结果的案例均有决定日', allHaveDecision,
    `${casesInRange.length} 条案例进入，其中 ${
      casesInRange.filter((h) => !(h.record.dates || {}).decisionDate).length
    } 条无决定日`);
}
{
  // 法规参与日期筛选时，至少要有公布日或生效日之一（eCFR 部分条文只有生效日）。
  // 但要允许「数据源本身未提供日期」的记录存在——实测：法通网 78 条中仅 11 条有发文日期，
  // ICAO 附件按设计只存版次不存日期。这类记录不得伪造日期，只能如实披露。
  // 因此断言改为：无日期记录的比例可控（< 5%），且在报告中披露具体来源。
  const res = Search.search(idx, { text: '', from: '2026-01-01' });
  const noDate = res.results.filter((h) => {
    const d = h.record.dates || {};
    return !d.publicationDate && !d.effectiveDate;
  });
  const ratio = noDate.length / Math.max(1, res.results.length);
  check('无日期记录占比可控（< 5%），且不做伪日期填充',
    ratio < 0.05,
    `${noDate.length}/${res.results.length} = ${(ratio * 100).toFixed(1)}%`);
  if (noDate.length) {
    const byJur = {};
    for (const h of noDate) {
      const j = h.record.jurisdiction || '?';
      byJur[j] = (byJur[j] || 0) + 1;
    }
    console.log(`  · 无日期记录分布：${JSON.stringify(byJur)}`);
    console.log('  · 说明：法通网部分记录未提供发文日期、ICAO 附件只存版次，均如实留空');
  }
}

// ─────────────────────────────────────────────────────────
console.log('\n【9】字段倒排：断言字段名不应进入全文索引');
check('搜 docket_ids 不应命中大量记录', R('docket_ids') < 5, `实际 ${R('docket_ids')}`);

// ─────────────────────────────────────────────────────────
console.log('\n【10】规范键索引规模（供 API 出口与体积评估）');
{
  const counts = Search.keyCounts(idx);
  const nsCount = {};
  for (const k of Object.keys(counts)) {
    const ns = k.split(':')[0];
    nsCount[ns] = (nsCount[ns] || 0) + 1;
  }
  console.log('  规范键总数:', Object.keys(counts).length);
  console.log('  按命名空间:', JSON.stringify(nsCount));
  // 用「每条记录平均键数」而非绝对值衡量——绝对值会随语料线性增长，
  // 而真正要防的是「键爆炸」（每条记录生成海量键导致索引与 API 出口膨胀）。
  const perRecord = Object.keys(counts).length / manifest.records.length;
  console.log('  每条记录平均键数:', perRecord.toFixed(2));
  check('每条记录平均规范键数在合理区间（≤ 6）', perRecord <= 6,
    `实际 ${perRecord.toFixed(2)}`);
  check('规范键总量与语料规模相称（< 20000）',
    Object.keys(counts).length < 20000, `实际 ${Object.keys(counts).length}`);
}

// ─────────────────────────────────────────────────────────
// 【11】中国法域标识符精确查（CCAR 部号 / 中国上位法）
// 背景：新增 CCAR 与法通网两个中国源后，「按部号查规章」「按法律名查上位法」
//       成为中文读者的主检索路径。若这层不通，中国源等于白收。
console.log('\n【11】中国法域标识符精确查');
{
  const keyOf = (ns, val) => {
    const c = Search.keyCounts(idx);
    return c[ns + ':' + val] ? c[ns + ':' + val] : 0;
  };
  const hits = (ns, val) => {
    const res = Search.search(idx, { text: `${ns}:${val}` });
    return res.results.length;
  };

  const ccarKeys = Object.keys(Search.keyCounts(idx)).filter((k) => k.startsWith('ccar:'));
  console.log('  ccar 规范键数:', ccarKeys.length);
  console.log('  样例:', ccarKeys.slice(0, 5).join(', '));
  check('CCAR 规范键已生成', ccarKeys.length > 50, `实际 ${ccarKeys.length}`);

  // 精确查必须命中且规模合理（不得回落为全库）
  const firstCcar = ccarKeys[0].slice(5);
  const n = hits('ccar', firstCcar);
  check('CCAR 精确查命中且不回落全库',
    n > 0 && n < 50, `${firstCcar} → ${n} 条`);

  // 未收录的 CCAR 部号必须零命中
  check('未收录 CCAR 部号零命中', hits('ccar', '99999') === 0,
    `实际 ${hits('ccar', '99999')} 条`);

  // 中国上位法（法通网）应能按名称命中
  const cnLaw = manifest.records.filter((r) =>
    (r.title || '').includes('民用航空'));
  console.log('  标题含「民用航空」的中国记录:', cnLaw.length);
  check('中国上位法已入库', cnLaw.length > 0);
}

// ─────────────────────────────────────────────────────────
// 【12】eCFR 现行条文的层级可查性
// 背景：568 条 FR 全是「变更事件」，3191 条 eCFR 才是「现行条文」。
//       读者要能按 part 聚合（14 CFR 89 现在共几条），
//       也能按 section 精确定位（14 CFR 89.305 讲什么）。
console.log('\n【12】eCFR 现行条文层级可查');
{
  const cfrSec = (v) => Search.search(idx, { text: `cfr:${v}` }).results.length;
  const part89 = cfrSec('14:89');
  console.log('  cfr:14:89 →', part89, '条');
  check('CFR part 级可聚合（> 20 条）', part89 > 20, `实际 ${part89}`);

  const sec = cfrSec('14:89.305');
  console.log('  cfr:14:89.305 →', sec, '条');
  check('CFR section 级可精确定位（1 条）', sec === 1, `实际 ${sec}`);

  check('未收录 CFR 条款零命中', cfrSec('14:999') === 0,
    `实际 ${cfrSec('14:999')}`);
}

// ─────────────────────────────────────────────────────────
// 【13】中文检索在新增源上仍然有效
console.log('\n【13】中文检索跨源可达');
{
  const zh = (q) => Search.search(idx, { text: q }).results.length;
  const cases = [
    ['无人机', 1], ['适航指令', 1], ['远程识别', 1],
    ['民用航空法', 1], ['现行有效', 1], ['数据保护', 1],
  ];
  cases.forEach(([q, min]) => {
    const n = zh(q);
    check(`中文「${q}」有命中（≥${min}）`, n >= min, `实际 ${n}`);
  });
}

// ─────────────────────────────────────────────────────────
// 【14】欧盟法域标识符精确查（CELEX / 人读编号 / 条文号）
// 背景：新增 EUR-Lex 源后，「按 CELEX 查」「按法规编号查」「按条文查」
//       成为欧盟法源的主检索路径。注意 ceLEx 前导零必须归一——
//       实测踩坑：key 写成 celex:$4 而 pattern 只有 3 个捕获组，
//       导致 celex: 为空、全部查空。
console.log('\n【14】欧盟法域标识符精确查');
{
  const r = (q) => Search.search(idx, { text: q }).results;
  const warn = (q) => (Search.search(idx, { text: q }).warnings || []);

  const celexCases = [
    ['celex:679', 'GDPR'],
    ['celex:1139', 'EASA 基础条例'],
    ['celex:947', '无人机运行规则'],
    ['celex:664', 'U-space 框架'],
  ];
  celexCases.forEach(([k, label]) => {
    check(`CELEX 精确查 ${label}`, r(k).length === 1, `实际 ${r(k).length}`);
  });

  check('人读编号精确查 2018/1139', r('eureg:2018:1139').length === 1,
    `实际 ${r('eureg:2018:1139').length}`);
  check('裸 CELEX 自动归一（32016R0679）', r('32016R0679').length === 1,
    `实际 ${r('32016R0679').length}`);
  check('裸法规编号自动归一（(EU) 2019/947）', r('(EU) 2019/947').length === 1,
    `实际 ${r('(EU) 2019/947').length}`);

  // 条文号：Article 132 是 EASA 基础条例的「个人数据处理」条款
  const art = r('euarticle:132');
  check('条文精确查 Article 132', art.length >= 1, `实际 ${art.length}`);
  if (art.length) {
    const isEasa = art.some((h) => String(h.record.citationString || '').includes('1139'));
    check('Article 132 命中 EASA 基础条例', isEasa);
  }

  // 未收录的 CELEX 必须零命中且给出告警
  check('未收录 CELEX 零命中', r('celex:9999').length === 0,
    `实际 ${r('celex:9999').length}`);
  check('未收录 CELEX 给出告警', warn('celex:9999').length > 0);

  // ICAO 命名空间的规则已就绪（可解析 Annex / Doc / PANS 及中文写法），
  // 但数据尚未接入——查询必须报「未收录」而非静默返回全集。
  // 数据接入后（用户从官网下载后导入）本断言会失败，
  // 那时应改为核对 Annex 17 等具体附件是否真的入库。
  const icaoRules = rules.rules.filter((r) => r.ns === 'icao').length;
  check('ICAO 命名空间规则已就绪（≥3 条）', icaoRules >= 3, `实际 ${icaoRules}`);
  const icaoRecs = manifest.records.filter((r) => r.jurisdiction === 'ICAO').length;
  if (icaoRecs === 0) {
    check('ICAO 附件查询报未收录（数据未接入）',
      r('Annex 17').length === 0 && warn('Annex 17').length > 0,
      `命中 ${r('Annex 17').length} / 告警 ${warn('Annex 17').length}`);
    check('ICAO 文件号查询报未收录',
      r('Doc 9944').length === 0 && warn('Doc 9944').length > 0);
  } else {
    // 附件的五种写法与未收录告警已在【3b】统一断言，此处不重复
    console.log(`  · ICAO 数据已接入（${icaoRecs} 条附件），五种写法断言见【3b】`);
    // 19 = booklet 的 Annex 1–18（官方标准名）+ 微信相册补入的 Annex 19（L3 待核验）
    check('ICAO 附件已入库 19 条（18 官方 booklet + 1 相册补入）',
      icaoRecs === 19, `实际 ${icaoRecs}`);
  }
}

console.log('\n' + '='.repeat(66));
console.log(`通过 ${pass} · 失败 ${fail}`);
if (fail) {
  console.log('\n失败项：');
  failures.forEach((f) => console.log('  - ' + f));
}
console.log('='.repeat(66));
process.exit(fail ? 1 : 0);
