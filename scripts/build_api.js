/**
 * build_api.js — 生成对外 API 出口
 *
 * 核心原则（针对此前暴露的语义分叉问题）：
 *   **build_api 绝不能自己分词、自己匹配。**
 *   它只允许"从 site/js/search.js 构建的索引里查表"。
 *   这样客户端与 API 的检索结果在构造上就不可能不一致。
 *
 * 出口形态：
 *   /api/v1/manifest.json      完整语料（含完整证据链 assertions）
 *   /api/v1/latest.json        最近 N 条
 *   /api/v1/keys/{ns}.json     规范键 → recordId 表（标识符精确查，供 AI 自由组合）
 *   /api/v1/facets/index.json  分面统计
 *   /api/v1/agent.md           给 Agent 的接入说明
 *
 * 匿名只读，无需 API Key。
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const CWD = process.cwd();
const BASE = fs.existsSync(path.join(CWD, 'data', 'manifest.json'))
  ? CWD : path.join(CWD, '..');
const SITE = path.join(BASE, 'site');

// ── 加载站点检索引擎（唯一真值来源）────────────────────────
function loadSearchEngine() {
  const sandbox = {
    console, RegExp, Math, JSON, Set, Map, Array, Object, String, Number, Date, Boolean,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  for (const f of ['js/glossary.js', 'js/search.js']) {
    vm.runInContext(fs.readFileSync(path.join(SITE, f), 'utf-8'), ctx, { filename: f });
  }
  return { Search: sandbox.Search, Glossary: sandbox.Glossary };
}

const { Search } = loadSearchEngine();

const manifest = JSON.parse(
  fs.readFileSync(path.join(BASE, 'data', 'manifest.json'), 'utf-8'));
const rules = JSON.parse(
  fs.readFileSync(path.join(BASE, 'data', 'identifiers.json'), 'utf-8'));

const idx = Search.buildIndex(manifest.records, rules.rules || []);

const OUT = path.join(SITE, 'api', 'v1');
fs.mkdirSync(path.join(OUT, 'keys'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'facets'), { recursive: true });

// ── 记录精简（保留完整证据链）──────────────────────────────
/**
 * API 侧的记录形态。
 * 注意：不再丢弃 assertions——AI 拿到记录却不知道哪个事实来自哪个源、
 * 哪个位置，是与"命中即证据"相反的。previous 的 slim() 丢弃了整条证据链。
 */
function slim(r) {
  return {
    recordId: r.recordId,
    title: r.title,
    titleEn: r.titleEn || null,
    summary: r.summary || null,
    jurisdiction: r.jurisdiction || null,
    recordType: r.recordType,
    status: r.status,
    dates: r.dates || {},
    penalty: r.penalty || null,
    citationString: r.citationString || null,
    topics: r.topics || [],
    subjects: r.subjects || [],
    sourceUrl: r.sourceUrl || null,
    pdfUrl: r.pdfUrl || null,
    // 证据链：每条断言带 sourceId / locator / evidenceLevel
    assertions: r.assertions || [],
    // 规范键：让 AI 拿到一条记录后能反查它属于哪些可查键
    canonicalKeys: canonicalKeysOf(r.recordId),
  };
}

function canonicalKeysOf(recordId) {
  const entry = idx.entries.find((e) => e.record.recordId === recordId);
  if (!entry) return {};
  const out = {};
  for (const k of entry.keys) {
    const ns = k.split(':')[0];
    (out[ns] = out[ns] || []).push(k.slice(ns.length + 1));
  }
  return out;
}

// ── 1) manifest.json（完整语料）────────────────────────────
fs.writeFileSync(
  path.join(OUT, 'manifest.json'),
  JSON.stringify(manifest, null, 2),
  'utf-8');

// ── 2) latest.json（分层取样）──────────────────────────────────
// 教训：原先单纯按 publicationDate 排序取前 200 条，结果 3191 条 eCFR
// 条文（版本日期同为一天）把整个窗口占满，AI 问「最近有什么」只看到美国。
// 改为按来源体系分层取样，每层各取若干条，保证法域与源的多样性。
const SOURCE_GROUPS = [
  { name: 'us-federal-register', label: '美国联邦公报·变更事件', match: (r) => r.recordId.includes('-FR-') },
  { name: 'us-ecfr', label: '美国联邦法规·现行条文', match: (r) => r.recordId.includes('-CFR-') },
  { name: 'cn-caac', label: '中国民航局·规章与规范性文件', match: (r) => r.recordId.startsWith('AVA-CN-CCAR') },
  { name: 'cn-lexcom', label: '中国涉外法律法规（司法部法通网）', match: (r) => r.recordId.startsWith('AVA-CN-LAW') },
  { name: 'foreign-translation', label: '域外法律中文译本', match: (r) => r.recordType === 'standard' },
  { name: 'cases', label: '航空数据保护执法案例', match: (r) => r.recordType === 'case' },
];

// 「最新」的判据因源而异：eCFR 条文的版本日期都一样，真正的时间信号是末次修订日
function recencyDate(r) {
  const d = r.dates || {};
  if (r.recordId.includes('-CFR-')) return d.lastAmendedDate || d.publicationDate || '';
  return d.decisionDate || d.publicationDate || d.effectiveDate || '';
}

const PER_GROUP = 60;
const latestRecords = [];
const groupStats = [];
for (const g of SOURCE_GROUPS) {
  const pool = manifest.records.filter(g.match);
  if (!pool.length) continue;
  const picked = pool
    .slice()
    .sort((a, b) => recencyDate(b).localeCompare(recencyDate(a)))
    .slice(0, PER_GROUP)
    .map((r) => ({ ...slim(r), sourceGroup: g.name, recencyDate: recencyDate(r) }));
  latestRecords.push(...picked);
  groupStats.push({ group: g.name, label: g.label, poolSize: pool.length, picked: picked.length });
}
latestRecords.sort((a, b) => (b.recencyDate || '').localeCompare(a.recencyDate || ''));

fs.writeFileSync(
  path.join(OUT, 'latest.json'),
  JSON.stringify({
    meta: manifest.meta,
    note: '按来源体系分层取样，非全库按日期排序——'
      + '单一源（如 eCFR 版本日期同日）会占满时间窗口而饿死其他法域',
    groups: groupStats,
    count: latestRecords.length,
    records: latestRecords,
  }, null, 2),
  'utf-8');

// ── 3) keys/{ns}.json（规范键 → recordId 表）────────────────
// AI 用它做自由组合查询：拉一次表，本地 jq 组合，无需受限于预设查询词。
const byNs = {};
for (const [k, set] of idx.keyIndex) {
  const colon = k.indexOf(':');
  const ns = k.slice(0, colon);
  const val = k.slice(colon + 1);
  (byNs[ns] = byNs[ns] || {})[val] = Array.from(set)
    .map((i) => idx.entries[i].record.recordId)
    .sort();
}

let keyFileCount = 0;
for (const [ns, keys] of Object.entries(byNs)) {
  const body = {
    meta: {
      datasetVersion: manifest.meta.datasetVersion,
      dataCutoff: manifest.meta.dataCutoff,
      namespace: ns,
      totalKeys: Object.keys(keys).length,
      note: '值为 recordId 列表。未收录的键在此表中不存在，表示本站未收录该对象，' +
            '不等于该对象在世上不存在。',
    },
    keys,
  };
  fs.writeFileSync(path.join(OUT, 'keys', ns + '.json'), JSON.stringify(body, null, 2), 'utf-8');
  keyFileCount++;
}

// ── 4) facets/index.json（分面统计）────────────────────────
const facets = {
  meta: {
    datasetVersion: manifest.meta.datasetVersion,
    dataCutoff: manifest.meta.dataCutoff,
  },
  jurisdiction: Search.facetCounts(idx, 'jurisdiction'),
  recordType: Search.facetCounts(idx, 'recordType'),
  status: Search.facetCounts(idx, 'status'),
  topics: Search.topicCounts(idx),
  evidenceLevel: (() => {
    const c = {};
    for (const e of idx.entries) {
      for (const a of e.record.assertions || []) {
        const l = a.evidenceLevel || 'unknown';
        c[l] = (c[l] || 0) + 1;
      }
    }
    return c;
  })(),
};
fs.writeFileSync(
  path.join(OUT, 'facets', 'index.json'),
  JSON.stringify(facets, null, 2),
  'utf-8');

// 按法域与类型的切片（"某国最近处罚了什么"这类问题直接查表）
const byJurType = {};
for (const e of idx.entries) {
  const r = e.record;
  const k = `${r.recordType}/${r.jurisdiction}`;
  (byJurType[k] = byJurType[k] || []).push(r);
}
for (const [k, list] of Object.entries(byJurType)) {
  const [rt, jur] = k.split('/');
  const sorted = list
    .slice()
    .sort((a, b) =>
      ((b.dates || {}).publicationDate || '').localeCompare((a.dates || {}).publicationDate || ''));
  const useDate = rt === 'case' ? 'publicationDate' : 'publicationDate';
  fs.writeFileSync(
    path.join(OUT, 'facets', `${rt}_${jur}.json`),
    JSON.stringify({
      meta: {
        datasetVersion: manifest.meta.datasetVersion,
        recordType: rt,
        jurisdiction: jur,
        count: sorted.length,
        sortedBy: useDate,
        dateFieldNote: rt === 'case'
          ? '本站案例决定日缺失，排序与"最近"均以公布日为准'
          : '按公布日排序',
      },
      records: sorted.map(slim),
    }, null, 2),
    'utf-8');
}

// ── 5) agent.md（给 Agent 的接入说明）─────────────────────
// ── 6) 统计量（供 agent.md 引用）────────────────────────────────
const byId = (pred) => manifest.records.filter(pred).length;
const euCount = byId((r) => r.jurisdiction === 'EU');
const icaoCount = byId((r) => r.jurisdiction === 'ICAO');
const euArticles = manifest.records
  .filter((r) => r.jurisdiction === 'EU')
  .reduce((n, r) => n + ((r.recordLevel || {}).articleCount || 0), 0);
const ecfrCount = byId((r) => r.recordId.includes('-CFR-'));
const frCount = byId((r) => r.recordId.includes('-FR-'));
const caacCount = byId((r) => r.recordId.startsWith('AVA-CN-CCAR'));
const lexcomCount = byId((r) => r.recordId.startsWith('AVA-CN-LAW'));
const caseCount = byId((r) => r.recordType === 'case');
const foreignTotal = 974;   // 法通网域外译本源库总量（实测）
const foreignKept = byId((r) => r.recordType === 'standard');
const l3Count = manifest.records.filter((r) =>
  (r.assertions || []).some((a) => a.evidenceLevel === 'L3')).length;
const osr = manifest.meta.officialSourceRatio || {};
const ratioText = Object.entries(osr)
  .map(([k, v]) => `${k} ${v.withPrimarySource}/${v.records}`)
  .join(' · ');

const md = `# 航空法律资料库 · Agent 接入说明

公开只读，无需注册与 API Key。返回内容为中文 Markdown / JSON。

> 本站是**事实层检索库**，不含学理分析与观点，也不提供法律意见。
> 所有事实请核对 \`sourceUrl\` 指向的官方原文。

## 库里有五个源

| 源 | 内容 | 条数 | 一手性 |
|---|---|---|---|
| 美国联邦法规汇编 eCFR | 14 CFR 现行条文（含修订日期） | ${ecfrCount} | L0 官方一手 |
| 美国联邦公报 Federal Register | 航空法规变更事件（文号/生效日） | ${frCount} | L0 官方一手 |
| 中国民航局规章栏目 | CCAR 规章与规范性文件（含 CCAR 部号、有效性） | ${caacCount} | L0 官方一手 |
| 司法部「法通」网 | 我国涉外法律法规 + 域外法律中文译本 | ${lexcomCount} | L0 / L1 |
| **欧盟 EUR-Lex / Cellar** | EASA 基础条例、无人机与 U-space 规则包、GDPR（含条文标题） | ${euCount} | L0 官方一手 |
| **ICAO 附件** | 芝加哥公约附件 1–18（中英标准名 + 分卷结构，仅元数据） | ${icaoCount} | L1 用户提供 |
| 航空数据保护执法案例 | 各国 DPA 处罚与法院判决 | ${caseCount} | 多数待核验 |

**已知边界（先读这一段）**

- 本库是**本站收录范围**，不是航空法律领域的全集。当前 ${manifest.records.length} 条记录。
- **案例类的决定日全部缺失**（${caseCount} 条），只能用公布日，引用时须说明是公布日。
- 案例中 ${l3Count} 条为二手来源（律所简报、媒体），检索界面以虚线徽章标出，引用前必须回官方一手。
- 罚款金额中 \`amountFinal\` 为 null 者，表示**拟议罚款额**，不是最终罚款额。
- 中国民航规章的「失效/废止/历史版本」只表明**官方栏目标注的状态**，
  废止的确切日期与替代规章未在栏目中给出，需回规章原文核实。
- 法通网的**域外法律中文译本**是"走出去"导向的对外国法库，
  实测其 ${foreignTotal} 条中**以航空法为规范对象的为 0 条**；
  本库只收录其中与航空数据治理交叉的数据与网络安全类 ${foreignKept} 条。
- 跨币种**不可合计**（见 \`penalty.currency\`）。
- **域外航空法**目前覆盖美国（eCFR 现行条文）、欧盟（EASA 条例 + 无人机/U-space 规则包）
  与 ICAO（附件 1–18 的标准名与引注），
  欧盟部分共 ${euArticles} 条条文标题。
- **ICAO 附件已接入**（Annex 1–18，${icaoCount} 条）：中英文标准名取自 ICAO 官方
  《Annexes 1 to 18》booklet 并逐条校验，**仅存元数据与引注，不存条文正文**
  ——SARPs 保留版权、不得印刷分发。
- **ICAO 程序文件未接入**：\`Doc 9944\`、\`PANS-ATM Doc 8610\` 这类查询会明确返回
  「本站未收录」——这是正确行为，不是故障。booklet 只提及 PANS 是一类程序文件，
  未给出任何文件号，无法凭空构造。
- 欧盟法源**只存元数据、机构文件号与条文标题**（如 Article 132「Processing of personal
  data」），**不存条文正文**——EU 决策文本再利用受官方声明约束；文义以 EUR-Lex 原文为准。
- 一手来源（记录级·分类型）：${ratioText}

## 决策树：先选对接口

| 你想知道 | 用哪个接口 | 特点 |
|---|---|---|
| 已知条款号 / 文号 / 部号 | \`/api/v1/keys/{ns}.json\` | **精确命中即证据**，未收录则该键不存在 |
| 欧盟法规（CELEX / 编号 / 条文） | \`/api/v1/keys/celex.json\`、\`eureg.json\`、\`euarticle.json\` | 三套键互为补充，见下 |
| 已知记录 ID | \`/data/details/{桶}/{recordId}.json\` | 单条完整证据链，**不要**为查一条去拉 16 MB 的 manifest |
| 某法域 / 某类型的记录 | \`/api/v1/facets/{类型}_{法域}.json\` | 已排好序 |
| 最近有什么动态 | \`/api/v1/latest.json\` | 按源分层取样，保证法域多样 |
| 主题探索 | \`/api/v1/facets/index.json\` 的 topics | 主题词 + 计数 |

> \`/api/v1/manifest.json\` 是**完整语料**（约 16 MB），只在需要全量时用。
> 查单条记录请用 \`details/\`，路径规则见文末。

## 标识符精确查（推荐）

规范键是归一化后的标识符，\`cfr:14:39\` 天然吸收 \`14 CFR 39\`、\`14 CFR Part 39\` 等写法。
键在表中**不存在 = 本站未收录**，不等于该对象不存在——必须原样转述这个结论。

\`\`\`bash
# 14 CFR Part 39 下的全部条文（现行状态 + 相关变更事件）
curl -s HOST/api/v1/keys/cfr.json | jq '.keys["14:39"] | length'

# 某条具体条文：14 CFR 89.305（无人机远程识别）
curl -s HOST/api/v1/keys/cfr.json | jq '.keys["14:89.305"]'

# 组合多个条款（未收录的返回空数组，不是报错）
curl -s HOST/api/v1/keys/cfr.json | jq '[.keys | to_entries[] | select(.key|test("^(14:39|49:1544)")) | .value[]] | unique'

# 中国民航规章：按 CCAR 部号（不含版次）
curl -s HOST/api/v1/keys/ccar.json | jq '.keys["91"]'

# 欧盟：按 CELEX 序号（自动吃掉前导零，CELEX:…0679 与 celex:679 同键）
curl -s HOST/api/v1/keys/celex.json | jq '.keys["679"]'

# 欧盟：按人读编号（(EU) 2019/947 / Regulation (EU) 2019/947 同键）
curl -s HOST/api/v1/keys/eureg.json | jq '.keys["2019:947"]'

# 欧盟：按条文号（Article 132 = EASA 基础条例的「个人数据处理」条款）
curl -s HOST/api/v1/keys/euarticle.json | jq '.keys["132"]'

# 联邦公报文号
curl -s HOST/api/v1/keys/fr.json | jq '.keys["91:66283"]'

# 适航指令号
curl -s HOST/api/v1/keys/ad.json | jq '.keys["2026-20-14"]'
\`\`\`

## 结构化过滤

\`\`\`bash
# 西班牙案例（已按公布日倒序）
curl -s HOST/api/v1/facets/case_ES.json | jq '.records[] | {title, dates, penalty, sourceUrl}'

# 中国民航规章
curl -s HOST/api/v1/facets/legislation_CN.json | jq '.records[] | {title, citationString, status}'

# 主题分布
curl -s HOST/api/v1/facets/index.json | jq '.topics | to_entries | sort_by(-.value) | .[:20]'
\`\`\`

## 单条记录：必须看 assertions

\`\`\`bash
# 详情文件路径：recordId 各字符码之和 mod 32 → 两位桶号
# 例：AVA-US-CFR-89-89-305
curl -s HOST/data/details/13/AVA-US-CFR-89-89-305.json | jq '{title, dates, assertions, sourceUrl}'
\`\`\`

每条断言带 \`field\` / \`value\` / \`sourceId\` / \`locator\` / \`evidenceLevel\`。
- \`evidenceLevel\`：L0 官方一手文书 / L1 官方二手 / L2 国际组织文件 / L3 专业二手
- **核心事实只用 L0/L1**
- \`locator\` 指向原文位置；FR 与 eCFR 为条文级定位，
  案例类的官方决定编号定位尚在补齐中（LOC-01 断言跟踪此项）

## 硬约束（务必遵守）

1. 零命中 = "本站未收录"，必须原样转述。
2. \`penalty.amountFinal\` 为 null 时，说"拟议罚款额"，不能说"罚款 X 元"。
3. \`dates.decisionDate\` 为 null 时，说"公布日"。
4. 跨币种不合计。
5. 中国规章状态为"失效/废止/历史版本"时，须说明该状态取自民航局规章栏目，
   废止日期与替代规章需回原文核实。
6. 引用前逐条核对 \`sourceUrl\`。本库不做权威性背书。
7. 本库内容为 CC BY 4.0（仅及于本库自行编制的编排与事实性转述），
   所引官方文本的权利归各权利人。二次分发时请遵守各源适用条款。

## 数据结构

\`\`\`
manifest.json  { meta, sources, entities, records }
records[]      { recordId, title, summary, jurisdiction, recordType, status,
                 dates{decisionDate,publicationDate,effectiveDate,lastAmendedDate},
                 penalty{amountOriginal,amountFinal,currency},
                 topics[], sourceUrl,
                 assertions[{field,value,sourceId,locator,evidenceLevel,verifiedAt}],
                 recordLevel{...} }
keys/{ns}.json { meta, keys{ "值": [recordId, ...] } }
facets/*.json  { meta, records[] }
details/*/*.json  { 单条完整记录（含 assertions 与全文） }
latest.json    { meta, groups[], records[] }   ← 按源分层，非全库按日期
\`\`\`

## 许可

数据内容 CC BY 4.0（署名）；原始文本权利归各权利人，本站不转载，只提供元数据与链接。
`;
fs.writeFileSync(path.join(OUT, 'agent.md'), md, 'utf-8');
fs.writeFileSync(path.join(OUT, 'agent.md'), md, 'utf-8');

console.log('API 出口生成：' + path.relative(BASE, OUT));
console.log(`  manifest.json   ${manifest.records.length} 条完整记录`);
console.log(`  latest.json     ${latestRecords.length} 条（分层：${groupStats.map((g) => g.picked).join('/')}）`);
console.log(`  keys/           ${keyFileCount} 个命名空间文件`);
console.log(`  facets/         索引 + ${Object.keys(byJurType).length} 个切片`);
console.log(`  agent.md        Agent 接入说明`);
console.log(`  规范键总数      ${idx.keyIndex.size}`);
