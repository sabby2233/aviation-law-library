/**
 * search.js — 客户端检索引擎
 *
 * 设计原则：全库数据在浏览器内加载，检索完全在本地完成。
 * 优点：零后端、零数据库、零延迟、无隐私外泄、无 API Key。
 *
 * 三层索引：
 *   ① 规范键索引  key(ns:value) → Set<recordIndex>   标识符精确查，唯一真值来源
 *   ② 字段倒排    field:token  → Set<recordIndex>     分字段，精确率 100%
 *   ③ 全文倒排    token       → Set<recordIndex>     主题发现，容错
 *
 * 铁律：标识符查询只走 ①，绝不回落 ②③。
 *   理由——法律检索里"命中即证据"，未命中必须是可表达的合法答案（"库中没有"），
 *   而不是静默降级成宽松匹配。假阳性比零命中危险得多：
 *   用户不会意识到"39 CFR 39"其实返回的是 14 CFR 39 的内容。
 *
 * 全部为确定性实现，不调用任何模型。
 */

const Search = (function (global) {
  'use strict';

  // ── 切词 ────────────────────────────────────────────────
  /**
   * 英文/数字：按非字母数字边界切分，额外产出「去分隔符」与「数字段」版本。
   * 数字段单独产出是机型召回的关键——"737-600" 若只产出整体 token，
   * 单独查 "737" 会零命中（实测召回 11% → 83%）。
   */
  function tokenizeLatin(text) {
    const tokens = [];
    const words = String(text).toLowerCase().match(/[a-z0-9][a-z0-9\-._/]*/g) || [];
    for (const w of words) {
      if (w.length >= 2) tokens.push(w);
      const bare = w.replace(/[-._/]/g, '');
      if (bare.length >= 2 && bare !== w) tokens.push(bare);
      // 数字段：把连字符/点分隔的数字各段单独抽出
      const nums = w.match(/\d+/g) || [];
      for (const n of nums) {
        if (n.length >= 2 && n !== w) tokens.push(n);
      }
    }
    return tokens;
  }

  /**
   * 中文：二元切分（不引分词词典），保留长度≥3 的整词。
   * 长度为 2 的整词不单独保留——二元循环已产出它，重复保留会使其权重翻倍。
   */
  function tokenizeCjk(text) {
    const tokens = [];
    const segs = String(text)
      .replace(/[^一-鿿]+/g, ' ')
      .split(/\s+/)
      .filter(Boolean);
    for (const seg of segs) {
      if (seg.length === 1) {
        tokens.push(seg);
      } else {
        for (let i = 0; i < seg.length - 1; i++) tokens.push(seg.slice(i, i + 2));
        if (seg.length >= 3) tokens.push(seg);
      }
    }
    return tokens;
  }

  function tokenize(text) {
    if (!text) return [];
    return tokenizeLatin(text).concat(tokenizeCjk(text));
  }

  // ── 标识符规范化 ────────────────────────────────────────
  /**
   * 标识符规则表由 data/identifiers.json 提供（数据不是代码，可独立扩展）。
   * 本函数在浏览器端与 Node 端共用同一份规则，保证归一一致。
   */
  function makeIdentifierResolver(rules) {
    const compiled = (rules || []).map((r) => ({
      ns: r.ns,
      label: r.label,
      re: new RegExp(r.pattern, 'i'),
      key: r.key,
    }));

    /**
     * 尝试把一段文本解析为规范键。
     * @returns {string|null} 如 cfr:14:39
     */
    function resolve(text) {
      const t = String(text || '').trim();
      if (!t) return null;
      for (const r of compiled) {
        const m = t.match(r.re);
        if (m) {
          try {
            return r.key.replace(/\$(\d+)/g, (_, i) => (m[i] !== undefined ? m[i] : ''));
          } catch (e) {
            return null;
          }
        }
      }
      return null;
    }

    /** 某段文本是否"看起来像"标识符（含数字与标点的短串） */
    function looksLikeIdentifier(text) {
      const t = String(text || '').trim();
      if (!t) return false;
      if (/\d/.test(t) && t.length <= 40) return true;
      if (/^(annex|doc|part|ad|ccar|gb)\b/i.test(t)) return true;
      return false;
    }

    return { resolve, looksLikeIdentifier, rules: compiled };
  }

  // ── 索引构建 ────────────────────────────────────────────
  // 参与规范键解析的断言字段。值本身是标识符（"14 CFR 39"、"CCAR-290-R4"、
  // "32016R0679"、"Article 55"），字段名只用于在全量记录里筛选，
  // 精简索引则统一走 refValues。
  // 两侧（此处与 scripts/build_browse.py 的 KEY_REF_FIELDS）必须同步，
  // 否则精简索引会多出或少掉规范键，test_browse_parity 会当场报红。
  const KEY_REF_FIELDS = [
    'cfr_references', 'docket_ids', 'document_number', 'citation',
    'cfr_part', 'cfr_section', 'ccar_number',
    // 欧盟法源
    'celex_id', 'regulation_number', 'article',
  ];

  /**
   * @param {Array} records
   * @param {Object} identifierRules 来自 data/identifiers.json
   */
  function buildIndex(records, identifierRules) {
    const resolver = makeIdentifierResolver(identifierRules || []);

    const entries = records.map((r) => {
      // 全文语料：标题、摘要、主题、断言值（不含断言字段名——否则搜 docket_ids 会命中 549 条）
      const parts = [
        r.title, r.titleEn, r.summary, r.citationString,
        r.jurisdiction, r.recordType,
        (r.topics || []).join(' '),
        (r.subjects || []).join(' '),
      ];
      for (const a of r.assertions || []) parts.push(a.value);

      const allText = parts.filter(Boolean).join(' \n ');

      // 检索词：优先用构建期预抽的 terms（首屏精简索引 data/browse.json）
      // 预抽与前端 tokenizer 对齐（scripts/build_browse.py 的 tokenize），
      // 这样精简索引与全量索引的召回完全一致，且不必在前端重复切词。
      let tokens;
      if (Array.isArray(r.terms) && r.terms.length) {
        tokens = r.terms.slice();
      } else {
        tokens = tokenize(allText);
      }

      // 规范键：从文号、docket、CFR 引用、记录 ID 中解析
      const keys = new Set();
      const addKey = (k) => { if (k) keys.add(k); };

      // 记录 ID 自身
      addKey('id:' + r.recordId);
      // 引注（如 "91 FR 66283"）
      if (r.citationString) {
        addKey(resolver.resolve(r.citationString));
        // 逐段尝试（"14 CFR 39" 之类）
        for (const part of String(r.citationString).split(/[,;]\s*/)) {
          addKey(resolver.resolve(part));
        }
      }
      // 断言值中的标识符（cfr_references / document_number / docket_ids /
      // cfr_part / cfr_section / ccar_number）
      // 精简索引用 refValues 承载这些值（字段名已丢弃，值本身足以解析规范键）
      const refValues = Array.isArray(r.refValues)
        ? r.refValues
        : (r.assertions || [])
            .filter((a) => KEY_REF_FIELDS.includes(a.field))
            .map((a) => String(a.value || ''));
      for (const v of refValues) {
        for (const part of String(v).split(/[,;]\s*/)) {
          addKey(resolver.resolve(part));
        }
      }
      // 主题
      for (const t of r.topics || []) addKey('topic:' + t);
      addKey('jur:' + r.jurisdiction);
      addKey('type:' + r.recordType);

      // 字段倒排：recordId / sourceUrl / 各断言字段
      const fields = {};
      fields['id'] = [r.recordId];
      if (r.sourceUrl) fields['source'] = [r.sourceUrl];
      if (r.pdfUrl) fields['pdf'] = [r.pdfUrl];
      for (const a of r.assertions || []) {
        (fields[a.field] = fields[a.field] || []).push(a.value);
      }

      return { record: r, tokens, allText: allText.toLowerCase(), keys, fields, resolver };
    });

    // 倒排索引
    const textIndex = new Map();
    const keyIndex = new Map();
    const fieldIndex = new Map();

    entries.forEach((e, i) => {
      for (const t of new Set(e.tokens)) {
        if (!textIndex.has(t)) textIndex.set(t, new Set());
        textIndex.get(t).add(i);
      }
      for (const k of e.keys) {
        if (!keyIndex.has(k)) keyIndex.set(k, new Set());
        keyIndex.get(k).add(i);
      }
      for (const [f, vals] of Object.entries(e.fields)) {
        for (const v of vals) {
          for (const t of new Set(tokenize(String(v)))) {
            const k = f + ':' + t;
            if (!fieldIndex.has(k)) fieldIndex.set(k, new Set());
            fieldIndex.get(k).add(i);
          }
        }
      }
    });

    // 前缀桶：只对规范键建（键数少，成本可忽略）
    const prefixBuckets = new Map();
    for (const k of keyIndex.keys()) {
      for (let len = 3; len <= Math.min(k.length, 24); len++) {
        const p = k.slice(0, len);
        if (!prefixBuckets.has(p)) prefixBuckets.set(p, new Set());
        prefixBuckets.get(p).add(k);
      }
    }

    return { entries, textIndex, keyIndex, fieldIndex, prefixBuckets, resolver };
  }

  // ── 检索 ────────────────────────────────────────────────
  /**
   * @param {Object} idx buildIndex 的返回值
   * @param {Object} query { text, jurisdiction, recordType, topics, status,
   *                         evidenceLevel, pendingOnly, from, to }
   * @returns {{results: Array, warnings: Array, zeroHit: boolean}}
   */
  function search(idx, query) {
    const q = query || {};
    const warnings = [];
    const raw = (q.text || '').trim();

    let candidates = null;      // 候选记录下标集合
    let explicitKeyMode = false;

    if (raw) {
      // ── 1. 拆出显式的 key:value 查询 ──
      const keyTerms = [];
      const freeTerms = [];
      for (const rawTerm of raw.split(/\s+/)) {
        if (!rawTerm) continue;
        if (rawTerm.includes(':')) {
          const colon = rawTerm.indexOf(':');
          const ns = rawTerm.slice(0, colon).toLowerCase();
          const val = rawTerm.slice(colon + 1);
          if (val) keyTerms.push({ ns, val, term: rawTerm });
          else freeTerms.push(rawTerm);
        } else {
          freeTerms.push(rawTerm);
        }
      }

      // ── 1b. 整串标识符查询 → 规范键通道 ──
      // 法律检索里标识符常写成多词空格形式（"14 CFR 39"），也有无空格写法
      // （"Annex8"、"附件8"）。两种都必须走精确通道，否则会退化为全文匹配
      // 并产生假阳性（实测 "Annex18" 会误召回全部 18 条 ICAO 记录）。
      if (!keyTerms.length && freeTerms.length) {
        const whole = freeTerms.join(' ');
        const key = idx.resolver.resolve(whole);
        if (key) {
          keyTerms.push({
            ns: key.slice(0, key.indexOf(':')),
            val: key.slice(key.indexOf(':') + 1),
            term: whole,
          });
          freeTerms.length = 0;
        }
      }

      // ── 2. 显式 key:value → 规范键通道（未命中即零命中，不回落）──
      if (keyTerms.length) {
        explicitKeyMode = true;
        const sets = [];
        for (const kt of keyTerms) {
          const hit = lookupKey(idx, kt.ns, kt.val);
          if (hit === null) {
            warnings.push(`未收录：${kt.term}`);
            sets.push(new Set());
          } else {
            sets.push(hit);
          }
        }
        candidates = intersectSets(sets);
        if (!candidates.size) {
          return finish(idx, q, new Set(), warnings, true, explicitKeyMode);
        }
      }

      // ── 3. 自由词 → 全文通道 ──
      if (freeTerms.length) {
        const groups = buildFreeGroups(raw, freeTerms);
        const groupSets = [];
        const missed = [];
        for (const group of groups) {
          const set = resolveGroup(idx.textIndex, group.tokens);
          if (set === null) {
            missed.push(group.label);
            continue;
          }
          groupSets.push(set);
        }
        if (missed.length) {
          warnings.push(`未在库中找到：${missed.join('、')}`);
        }
        if (groupSets.length) {
          const union = new Set();
          for (const s of groupSets) for (const i of s) union.add(i);
          candidates = candidates === null ? union : intersectSets([candidates, union]);
        } else if (candidates === null) {
          // 有查询词但一个都没命中索引 → 零命中
          return finish(idx, q, new Set(), warnings, true, explicitKeyMode);
        }
      }
    }

    return finish(idx, q, candidates, warnings, false, explicitKeyMode);
  }

  /** 规范键查询：精确命中或前缀命中；未命中返回 null（不回落） */
  function lookupKey(idx, ns, val) {
    const exact = idx.keyIndex.get(ns + ':' + val);
    if (exact) return exact;

    // 前缀
    const prefix = ns + ':' + val;
    const bucket = idx.prefixBuckets.get(prefix);
    if (bucket && bucket.size) {
      const union = new Set();
      for (const k of bucket) {
        const s = idx.keyIndex.get(k);
        if (s) for (const i of s) union.add(i);
      }
      if (union.size) return union;
    }
    return null;
  }

  /**
   * 自由词的组：中文查询经术语表展开为多个英文候选组（组间 OR）。
   * 组内 AND，但若组内某 token 不在索引中，该组仍然可成立（只要其他 token 有命中）——
   * 自由词的容错是合理的；标识符的严格由 keyTerms 通道保证。
   */
  function buildFreeGroups(raw, freeTerms) {
    const groups = [];
    const glossary = global.Glossary;

    if (glossary && glossary.needsExpansion(raw)) {
      // 中文查询：原词一组 + 术语表展开组
      const zhTokens = tokenizeCjk(raw);
      if (zhTokens.length) groups.push({ label: raw, tokens: zhTokens });
      for (const term of glossary.expand(raw)) {
        if (term === raw) continue;
        const t = tokenizeLatin(term);
        if (t.length) groups.push({ label: term, tokens: t });
      }
    } else {
      // 纯西文查询：整串一组 + 各词一组
      const all = tokenize(raw);
      if (all.length) groups.push({ label: raw, tokens: all });
      for (const ft of freeTerms) {
        const t = tokenize(ft);
        if (t.length && ft !== raw) groups.push({ label: ft, tokens: t });
      }
    }
    return groups;
  }

  /** 组内 AND 求交；全部 token 都不在索引时返回 null */
  function resolveGroup(textIndex, tokens) {
    const uniq = [...new Set(tokens)];
    let seed = null;
    for (const t of uniq) {
      const s = textIndex.get(t);
      if (!s) continue;
      if (!seed || s.size < seed.size) seed = s;
    }
    if (!seed) return null;
    const set = new Set(seed);
    for (const t of uniq) {
      const s = textIndex.get(t);
      if (!s) continue;
      for (const i of Array.from(set)) {
        if (!s.has(i)) set.delete(i);
      }
    }
    return set;
  }

  function intersectSets(sets) {
    if (!sets.length) return new Set();
    let out = new Set(sets[0]);
    for (let i = 1; i < sets.length; i++) {
      const next = sets[i];
      for (const x of Array.from(out)) {
        if (!next.has(x)) out.delete(x);
      }
    }
    return out;
  }

  /** 应用过滤条件并排序 */
  function finish(idx, q, candidates, warnings, zeroHit, explicitKeyMode) {
    const results = [];
    const total = idx.entries.length;

    for (let i = 0; i < total; i++) {
      if (candidates && !candidates.has(i)) continue;
      const r = idx.entries[i].record;

      if (q.jurisdiction && r.jurisdiction !== q.jurisdiction) continue;
      if (q.recordType && r.recordType !== q.recordType) continue;
      if (q.status && r.status !== q.status) continue;

      if (q.topics && q.topics.length) {
        const rt = r.topics || [];
        if (!q.topics.some((t) => rt.includes(t))) continue;
      }

      if (q.evidenceLevel && q.evidenceLevel.length) {
        const levels = (r.assertions || []).map((a) => a.evidenceLevel);
        if (!levels.some((l) => q.evidenceLevel.includes(l))) continue;
      }

      if (q.pendingOnly) {
        const d = r.dates || {};
        const lv2 = (r.assertions || []).map((a) => a.evidenceLevel);
        const isPending =
          lv2.includes('L3') ||
          (r.recordType === 'case' && !d.decisionDate) ||
          (r.penalty && r.penalty.amountOriginal && r.penalty.amountFinal === null);
        if (!isPending) continue;
      }

      const d = r.dates || {};
      // 日期筛选：案件用决定日，法规用公布日；缺该日期则不参与日期筛选（不回退）
      const dateForFilter = r.recordType === 'case' ? d.decisionDate : d.publicationDate;
      if (q.from) {
        if (!dateForFilter) continue;
        if (dateForFilter < q.from) continue;
      }
      if (q.to) {
        if (!dateForFilter) continue;
        if (dateForFilter > q.to) continue;
      }

      let score = 0;
      if (q.text) {
        const hay = idx.entries[i].allText;
        const tRaw = String(q.text).trim().toLowerCase();
        if (hay.includes(tRaw)) score += 100;
        for (const t of new Set(tokenize(q.text))) if (hay.includes(t)) score += 1;
        const title = String(r.title || '').toLowerCase();
        if (title.includes(tRaw)) score += 50;
      }
      results.push({ record: r, score, idx: i });
    }

    results.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const da = (a.record.dates || {}).publicationDate || '';
      const db = (b.record.dates || {}).publicationDate || '';
      return db.localeCompare(da);
    });

    return { results, warnings, zeroHit: zeroHit && !results.length, explicitKeyMode };
  }

  // ── 分面统计 ────────────────────────────────────────────
  function facetCounts(idx, key) {
    const counts = {};
    for (const e of idx.entries) {
      const v = e.record[key];
      const vals = Array.isArray(v) ? v : (v ? [v] : []);
      for (const x of vals) counts[x] = (counts[x] || 0) + 1;
    }
    return counts;
  }

  function topicCounts(idx) {
    const counts = {};
    for (const e of idx.entries) {
      for (const t of e.record.topics || []) counts[t] = (counts[t] || 0) + 1;
    }
    return counts;
  }

  /** 规范键统计：key → 记录数。用于 API 出口与检索层断言 */
  function keyCounts(idx) {
    const out = {};
    for (const [k, set] of idx.keyIndex) out[k] = set.size;
    return out;
  }

  return {
    buildIndex, search, facetCounts, topicCounts, keyCounts,
    tokenize, makeIdentifierResolver, lookupKey,
  };
})(typeof window !== 'undefined' ? window : globalThis);

// 挂到全局：浏览器端供 app.js 使用；Node 端供 test_search.js 使用
if (typeof window !== 'undefined' && window) {
  window.Search = Search;
} else if (typeof globalThis !== 'undefined') {
  globalThis.Search = Search;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = (typeof globalThis !== 'undefined' && globalThis.Search)
    || (typeof window !== 'undefined' && window.Search);
}