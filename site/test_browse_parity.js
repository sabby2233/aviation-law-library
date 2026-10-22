/**
 * test_browse_parity.js — 首屏精简索引与全量索引的召回一致性断言
 *
 * 为什么要这条测试：
 *   站点首屏加载 data/browse.json（精简），完整语料在 data/manifest.json。
 *   两者的检索召回**必须完全一致**——否则会出现「库里明明有，搜不到」，
 *   这比少几条命中严重得多。
 *
 *   曾实测踩过的坑：
 *     ① Python 端切词缺「数字段单独抽出」规则 → "part 108" 少 4 条
 *     ② 为压缩体积按词长裁剪 terms → "787" 从 25 条掉到 0 条
 *   两者都说明：精简索引的切词规则一旦与前端有出入，召回会静默塌陷。
 *   本测试把这条不变量钉死。
 *
 * 运行：node site/test_browse_parity.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const CWD = process.cwd();
const BASE = fs.existsSync(path.join(CWD, 'data', 'manifest.json'))
  ? CWD : path.join(CWD, '..');
const SITE = path.join(BASE, 'site');

const sandbox = { console, RegExp, Math, JSON, Set, Map, Array, Object, String, Number, Date, Boolean };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);
for (const f of ['js/glossary.js', 'js/search.js']) {
  vm.runInContext(fs.readFileSync(path.join(SITE, f), 'utf-8'), ctx, { filename: f });
}
const Search = sandbox.Search;

const manifest = JSON.parse(fs.readFileSync(path.join(BASE, 'data', 'manifest.json'), 'utf-8'));
const browsePath = path.join(BASE, 'data', 'browse.json');
const rules = JSON.parse(fs.readFileSync(path.join(BASE, 'data', 'identifiers.json'), 'utf-8'));

let pass = 0, fail = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; failures.push(`${name}${detail ? '  → ' + detail : ''}`); console.log(`  ✗ ${name}${detail ? '  → ' + detail : ''}`); }
}

if (!fs.existsSync(browsePath)) {
  console.log('data/browse.json 不存在，请先运行 python scripts/build_browse.py');
  process.exit(2);
}
const browse = JSON.parse(fs.readFileSync(browsePath, 'utf-8'));

console.log('='.repeat(66));
console.log('首屏精简索引 · 召回一致性测试');
console.log('='.repeat(66));
console.log(`  全量 ${manifest.records.length} 条 | 精简 ${browse.records.length} 条`);

const idxFull = Search.buildIndex(manifest.records, rules.rules || []);
const idxBrow = Search.buildIndex(browse.records, rules.rules || []);

// ── 1. 记录集合必须一致 ─────────────────────────────────
console.log('\n【1】记录集合');
check('记录数一致', manifest.records.length === browse.records.length,
  `${manifest.records.length} vs ${browse.records.length}`);
{
  const a = new Set(manifest.records.map((r) => r.recordId));
  const b = new Set(browse.records.map((r) => r.recordId));
  let onlyFull = 0, onlyBrow = 0;
  a.forEach((x) => { if (!b.has(x)) onlyFull++; });
  b.forEach((x) => { if (!a.has(x)) onlyBrow++; });
  check('recordId 集合一致', onlyFull === 0 && onlyBrow === 0,
    `全量独有 ${onlyFull} / 精简独有 ${onlyBrow}`);
}

// ── 2. 规范键必须一致 ───────────────────────────────────
console.log('\n【2】规范键索引');
check('规范键总数一致',
  idxFull.keyIndex.size === idxBrow.keyIndex.size,
  `${idxFull.keyIndex.size} vs ${idxBrow.keyIndex.size}`);
{
  let mismatch = 0;
  for (const [k, set] of idxFull.keyIndex) {
    const other = idxBrow.keyIndex.get(k);
    if (!other || other.size !== set.size) { mismatch++; continue; }
    for (const i of set) if (!other.has(i)) { mismatch++; break; }
  }
  check('规范键内容逐一致', mismatch === 0, `不一致键 ${mismatch} 个`);
}

// ── 3. 召回必须逐查询一致 ───────────────────────────────
console.log('\n【3】召回一致性（30 组查询）');
const QUERIES = [
  'unmanned', 'remote identification', 'airworthiness directive',
  'aircraft', 'certificate', 'security', 'privacy', 'electronic',
  'part 108', 'part 91', '787', '737', 'A350', '320',
  'cfr:14:89', 'cfr:14:39', 'cfr:14:89.305', 'cfr:49:1544',
  'ccar:91', 'ccar:290', 'fr:91:66283',
  '适航指令', '无人机', '远程识别', '数据泄露', '适航', '飞机', '机场',
  '航空器', '飞行', '民用航空法', '现行有效',
];
{
  let same = 0;
  const diffs = [];
  for (const q of QUERIES) {
    const a = Search.search(idxFull, { text: q }).results.map((h) => h.record.recordId).sort();
    const b = Search.search(idxBrow, { text: q }).results.map((h) => h.record.recordId).sort();
    const ok = a.length === b.length && a.every((x, i) => x === b[i]);
    if (ok) same++; else diffs.push(`${q}: 全量 ${a.length} vs 精简 ${b.length}`);
  }
  check('全部查询召回一致', same === QUERIES.length,
    `${same}/${QUERIES.length}` + (diffs.length ? ' 差异：' + diffs.slice(0, 3).join('; ') : ''));
}

// ── 4. 详情文件必须齐备且桶号正确 ───────────────────────
console.log('\n【4】详情文件');
{
  let missing = 0, wrongBucket = 0;
  const sample = browse.records.slice(0, 200);
  for (const r of sample) {
    const rid = r.recordId;
    let h = 0;
    for (let i = 0; i < rid.length; i++) h += rid.charCodeAt(i);
    const bucket = String(h % 32).padStart(2, '0');
    const p = path.join(BASE, 'data', 'details', bucket, `${rid}.json`);
    if (!fs.existsSync(p)) {
      missing++;
      // 排查是不是桶号算法不一致
      const alt = path.join(BASE, 'data', 'details',
        String(sumOrd(rid) % 32).padStart(2, '0'), `${rid}.json`);
      if (fs.existsSync(alt)) wrongBucket++;
    }
  }
  check('抽查 200 条详情文件齐备', missing === 0, `缺失 ${missing}`);
  check('桶号算法前后端一致', wrongBucket === 0, `桶号不一致 ${wrongBucket}`);
}
function sumOrd(s) {
  let h = 0;
  for (const ch of s) h += ch.codePointAt(0);
  return h;
}

// ── 5. 体积收益 ─────────────────────────────────────────
console.log('\n【5】体积');
{
  const zlib = require('zlib');
  const fullRaw = fs.statSync(path.join(BASE, 'data', 'manifest.json')).size;
  const browRaw = fs.statSync(browsePath).size;
  const fullGz = zlib.gzipSync(fs.readFileSync(path.join(BASE, 'data', 'manifest.json')), { level: 9 }).length;
  const browGz = zlib.gzipSync(fs.readFileSync(browsePath), { level: 9 }).length;
  console.log(`  manifest ${(fullRaw / 1048576).toFixed(2)} MB → gzip ${(fullGz / 1048576).toFixed(2)} MB`);
  console.log(`  browse   ${(browRaw / 1048576).toFixed(2)} MB → gzip ${(browGz / 1048576).toFixed(2)} MB`);
  check('精简索引 gzip 后不超过全量的 85%', browGz <= fullGz * 0.85,
    `${(browGz / fullGz * 100).toFixed(0)}%`);
}

console.log('\n' + '='.repeat(66));
console.log(`通过 ${pass} · 失败 ${fail}`);
if (fail) {
  console.log('\n失败项：');
  failures.forEach((f) => console.log('  - ' + f));
}
console.log('='.repeat(66));
process.exit(fail ? 1 : 0);
