// 临时探针：实测查询行为（审阅用，可删除）
const fs = require('fs'), path = require('path'), vm = require('vm');
const BASE = process.cwd();
const site = path.join(BASE, 'site');
const sandbox = { console, RegExp, Math, JSON, Set, Map, Array, Object, String, Number, Date };
sandbox.window = sandbox; sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);
for (const f of ['js/glossary.js', 'js/search.js']) {
  vm.runInContext(fs.readFileSync(path.join(site, f), 'utf-8'), ctx, { filename: f });
}
const S = sandbox.Search, G = sandbox.Glossary;
const manifest = JSON.parse(fs.readFileSync(path.join(BASE, 'data/manifest.json'), 'utf-8'));
const rules = JSON.parse(fs.readFileSync(path.join(BASE, 'data/identifiers.json'), 'utf-8'));
const t0 = Date.now();
const idx = S.buildIndex(manifest.records, rules.rules);
console.log(`buildIndex: ${Date.now() - t0} ms | records=${idx.entries.length} keys=${idx.keyIndex.size} textTokens=${idx.textIndex.size} fieldKeys=${idx.fieldIndex.size} prefixBuckets=${idx.prefixBuckets.size}`);
console.log(`heapRSS=${(process.memoryUsage().rss / 1048576).toFixed(0)}MB`);

const QS = process.argv.slice(2);
for (const q of QS) {
  const t = Date.now();
  const r = S.search(idx, { text: q });
  const ms = Date.now() - t;
  const jur = {};
  for (const h of r.results) jur[h.record.jurisdiction] = (jur[h.record.jurisdiction] || 0) + 1;
  const top = r.results.slice(0, 3).map((h) => h.record.recordId);
  console.log(`\n[${JSON.stringify(q.length > 60 ? q.slice(0, 60) + '…' : q)}] hits=${r.results.length} zero=${r.zeroHit} keyMode=${r.explicitKeyMode} ${ms}ms`);
  console.log(`   warn=${JSON.stringify(r.warnings)} jur=${JSON.stringify(jur)}`);
  console.log(`   top=${JSON.stringify(top)}`);
}

// 规范键抽样
const kc = S.keyCounts(idx);
const byNs = {};
for (const k of Object.keys(kc)) byNs[k.split(':')[0]] = (byNs[k.split(':')[0]] || 0) + 1;
console.log('\nkeys by ns:', JSON.stringify(byNs), 'total', Object.keys(kc).length);

// 中文记录实测
const cjk = /[\u4e00-\u9fff]/;
const zhTitle = manifest.records.filter((r) => cjk.test(r.title || '')).length;
const zhAny = manifest.records.filter((r) => cjk.test(JSON.stringify(r))).length;
const zhJur = manifest.records.filter((r) => r.jurisdiction === 'CN').length;
console.log(`CJK title=${zhTitle} CJK anywhere=${zhAny} CN jur=${zhJur} total=${manifest.records.length}`);
const zhType = {};
for (const r of manifest.records) if (cjk.test(r.title || '')) zhType[r.recordType] = (zhType[r.recordType] || 0) + 1;
console.log('CJK title by type:', JSON.stringify(zhType));
