/**
 * app.js — 界面逻辑
 *
 * 只做三件事：加载数据、驱动检索、渲染结果。
 * 不调用模型，不请求外部接口（数据与接口均在本站静态托管）。
 */

(function () {
  'use strict';

  // 数据根目录有两种形态，靠路径判断 + 探测兜底，两种部署共用同一份代码：
  //   本地：仓库根起服务，页面在 /site/index.html → ../data
  //   Pages：index.html 在发布目录根部 → ./data
  // 先按路径给出首选，省掉一次必然 404 的探测；再用探测兜住路径不规则的情况。
  const DATA_BASES = (function () {
    const nested = /\/site\/?$/.test(location.pathname);   // /site/ 目录下的本地布局
    return nested ? ['../data', './data'] : ['./data', '../data'];
  })();
  let DATA_BASE = DATA_BASES[0];

  async function resolveDataBase() {
    for (const b of DATA_BASES) {
      try {
        const r = await fetch(`${b}/browse.json`, { method: 'HEAD' });
        if (r.ok) return b;
      } catch (e) { /* 换下一个候选 */ }
    }
    return DATA_BASES[0];
  }

  function dataUrl(name) { return `${DATA_BASE}/${name}`; }
  function detailBucket(recordId) {
    let h = 0;
    for (let i = 0; i < recordId.length; i++) h += recordId.charCodeAt(i);
    return String(h % 32).padStart(2, '0');
  }

  const state = {
    index: null,
    indexReady: false,
    rules: [],
    records: [],
    meta: {},
    topics: [],
    selectedTopics: new Set(),
    expanded: null,      // 当前展开详情的记录 ID（进 URL，便于分享单条记录）
  };

  const el = (id) => document.getElementById(id);

  // 决定日缺失的成因分类。与 scripts/annotate_case_date_gaps.py 的 reason 取值一一对应。
  const DATE_GAP_REASON = {
    'source-is-index-page': '来源链接指向机构首页/栏目页，未指向决定书',
    'source-gone': '原链接已失效（404/改址）',
    'source-blocked': '官方站点反爬拦截，取不到正文',
    'page-has-no-date': '页面未载决定日',
    'upstream-uncertain': '上游数据集日期口径未核实',
    'lead-from-feed': '监管机构信息流自动发现，尚未定位官方决定书',
  };

  // ── 加载 ─────────────────────────────────────────────
  // 分两段：先取列表包（browse.json，约 0.5 MB）立刻出列表，
  // 再取检索词包（terms.json，约 1.5 MB）补齐索引。
  // 原来两样混在一个 2.05 MB 的包里，首屏要等全部下完才动。
  async function load() {
    try {
      DATA_BASE = await resolveDataBase();
      const [browseRes, rulesRes] = await Promise.all([
        fetch(dataUrl('browse.json')),
        fetch(dataUrl('identifiers.json')).catch(() => null),
      ]);
      if (!browseRes.ok) throw new Error('HTTP ' + browseRes.status);
      const browse = await browseRes.json();
      const rules = rulesRes && rulesRes.ok ? await rulesRes.json() : { rules: [] };

      state.rules = rules.rules || [];
      state.records = browse.records || [];
      state.meta = browse.meta || {};
      state.topics = topTopicsOf(18);
      renderHeader();
      renderFacets();
      renderNav();
      bindEvents();
      applyHash();
      setIndexState('loading');
      run();                      // 先出列表（此时只有筛选可用）
      loadTerms();                // 索引随后台补齐
    } catch (e) {
      el('result-count').textContent = '数据加载失败：' + e.message;
      el('results').innerHTML =
        '<p class="empty">数据文件未找到。请先运行采集脚本生成 data/browse.json，' +
        '并用本地服务器打开本页（直接双击 index.html 会被浏览器同源策略拦截 fetch）。</p>';
      setIndexState('failed', e.message);
    }
  }

  /** 取检索词包并重建索引 */
  async function loadTerms() {
    try {
      const r = await fetch(dataUrl('terms.json'));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const pack = await r.json();
      const pos = new Map(pack.ids.map((id, i) => [id, i]));
      state.records.forEach((rec) => {
        const i = pos.get(rec.recordId);
        if (i != null) rec.terms = pack.terms[i];
      });
      state.index = Search.buildIndex(state.records, state.rules);
      state.indexReady = true;
      setIndexState('ready');
      // 只有含文本检索时才需要重绘：没有文本词时，本地筛选与索引检索的结果完全一致，
      // 而重绘意味着把 4229 张卡片再插一遍 DOM——那是首屏最重的一步，不能做两次。
      if (currentQuery().text) run();
      expandFromHash();
    } catch (e) {
      setIndexState('failed', e.message);
    }
  }

  /** 索引状态：加载中禁用检索框并说明，加载完放开 */
  function setIndexState(s, detail) {
    const input = el('q');
    const hint = el('index-state');
    if (s === 'ready') {
      input.disabled = false;
      hint.textContent = '';
      hint.classList.add('hidden');
      return;
    }
    input.disabled = true;
    hint.classList.remove('hidden');
    if (s === 'loading') {
      hint.textContent = '列表已就绪；全文检索索引正在加载（约 1.5 MB），加载完成后即可检索。';
    } else {
      hint.textContent = '检索索引加载失败：' + (detail || '未知错误') +
        '。列表与筛选仍可使用，检索暂不可用。';
    }
  }

  /** 分面计数直接数记录，不依赖检索索引。
   *  索引包（terms.json）现在延后加载，首屏的筛选器必须立刻可用。 */
  function facetOf(key) {
    const counts = {};
    for (const r of state.records) {
      const v = r[key];
      const vals = Array.isArray(v) ? v : (v ? [v] : []);
      for (const x of vals) counts[x] = (counts[x] || 0) + 1;
    }
    return counts;
  }

  function topicCountsOf() {
    const counts = {};
    for (const r of state.records) {
      for (const t of r.topics || []) counts[t] = (counts[t] || 0) + 1;
    }
    return counts;
  }

  function topTopicsOf(n) {
    return Object.entries(topicCountsOf())
      .sort((a, b) => b[1] - a[1])
      .slice(0, n);
  }

  // ── 渲染：页头与页脚 ─────────────────────────────────

  /** 待核验的三个构成。数字本身不解释自己，读者只会问「为什么这么多」。 */
  function pendingBreakdown() {
    let noDate = 0, noAmount = 0, unverified = 0;
    for (const r of state.records) {
      const d = r.dates || {};
      if (r.recordType === 'case' && !d.decisionDate) noDate++;
      if (r.penalty && r.penalty.amountOriginal && r.penalty.amountFinal === null) noAmount++;
      if (r.verificationPending === true) unverified++;
    }
    return { noDate, noAmount, unverified };
  }

  function pendingTitle() {
    const b = pendingBreakdown();
    return `待核验 = 案例缺决定日 ${b.noDate} 条 ＋ 罚款未记录减免后数额 ${b.noAmount} 条 ＋ 记录级核验未完成 ${b.unverified} 条（有重叠，故总数小于三项之和）。\n「来源等级 L3」不计入待核验——那是来源等级，不是核验状态。`;
  }

  function renderHeader() {
    const m = state.meta;
    // 一手来源占比：分类型 + 记录级。旧的单一数字（断言级加权）可被灌水刷高，
    // 且 98% 来自单一来源，读者体感与实际遭遇脱节。改为展示最诚实的口径。
    const byType = m.officialSourceRatio || {};
    const caseStat = byType.case;
    const legStat = byType.legislation;

    const parts = [
      `<div><b>${esc(String(m.recordCount ?? state.records.length))}</b><span class="meta-label">收录条目</span></div>`,
      `<div><b>${esc(String(m.jurisdictionCount ?? '—'))}</b><span class="meta-label">法域</span></div>`,
      `<div><b>${esc(m.dataCutoff || '—')}</b><span class="meta-label">数据截止</span></div>`,
    ];
    if (caseStat) {
      parts.push(
        `<div><b>${caseStat.withPrimarySource}/${caseStat.records}</b>` +
        `<span class="meta-label">案例一手来源</span></div>`);
    }
    if (legStat) {
      parts.push(
        `<div><b>${legStat.withPrimarySource}/${legStat.records}</b>` +
        `<span class="meta-label">法规一手来源</span></div>`);
    }
    if (m.pendingCount) {
      parts.push(
        `<div class="meta-pending" title="${pendingTitle()}"><b>${m.pendingCount}</b>` +
        `<span class="meta-label">待核验</span></div>`);
    }
    el('header-meta').innerHTML = parts.join('');

    el('notice').textContent = m.notice || '';

    const bits = [`语料版本 ${esc(m.datasetVersion || '—')}`];
    if (m.commitSha) bits.push(`commit ${esc(m.commitSha.slice(0, 8))}`);
    bits.push(`检索截止 ${esc(m.retrievalCutoff || '—')}`);
    // 这里不再放「核心字段一手支撑率」。
    // 该指标 1464 条核心断言里 1443 条是法规的公布日/生效日（从官方接口抓的，
    // 必然是官方），是把同义反复换算成百分比；真实有信息量的案例层只有 4.8%（1/21）。
    // 两个口径混在一个数字里放在首屏，只会让读者记住那个大的。
    // 它仍是 validate.py 的 EVD-02 门禁（阈值 80%），属于构建期约束，不是给读者的信息。
    // 首屏改为陈述可数的事实：断言条数。
    if (m.assertionCount) bits.push(`断言 ${m.assertionCount.toLocaleString('en-US')} 条`);
    el('footer-meta').innerHTML = bits.join(' · ');
  }

  // ── 渲染：筛选器 ─────────────────────────────────────
  // ── 标签中文化 ─────────────────────────────────────────
  // 数据层用稳定的英文标识（便于规范键与 API 消费），
  // 界面层译中文。映射表在此集中维护，改一个词只改一处。
  const STATUS_LABELS = {
    draft: '起草中',
    adopted: '已通过',
    withdrawn: '已撤回',
    promulgated: '已公布',
    effective: '现行有效',
    not_yet_effective: '尚未施行',
    amended: '已被修改',
    superseded: '已被取代',
    repealed: '已废止',
    invalidated: '已失效',
    settled: '已和解',
    under_appeal: '上诉中',
    final: '终局',
  };

  const TOPIC_LABELS = {
    uav: '无人机/低空',
    airworthiness: '适航',
    'air-transport': '航空运输',
    'flight-ops': '运行与空域',
    'data-protection': '数据保护',
    'air-carrier': '运输经营',
    airport: '机场',
    security: '安保',
    'cn-foreign-related': '涉外法规',
    'foreign-translation': '域外译本',
    translated: '中文译本',
    'air-traffic': '空中交通',
    definitions: '定义',
    registration: '登记',
    maintenance: '维修',
    certification: '人员资格',
    noise: '噪声',
    airspace: '空域',
  };

  // 法域中文名。ISO 代码是数据层的稳定标识，界面层给中文名。
  // 中国香港、中国澳门、中国台湾按规范表述。
  const JUR_LABELS = {
    CN: '中国', US: '美国', ES: '西班牙', GB: '英国', IT: '意大利',
    FR: '法国', BE: '比利时', TR: '土耳其', DE: '德国', NL: '荷兰',
    IE: '爱尔兰', CA: '加拿大', AU: '澳大利亚', SG: '新加坡',
    HK: '中国香港', MO: '中国澳门', TW: '中国台湾',
    BR: '巴西', MX: '墨西哥', RU: '俄罗斯', IN: '印度',
    JP: '日本', KR: '韩国', ZA: '南非', NO: '挪威', DK: '丹麦',
    SE: '瑞典', FI: '芬兰', AT: '奥地利', CH: '瑞士', PL: '波兰',
    CZ: '捷克', PT: '葡萄牙', RO: '罗马尼亚', HU: '匈牙利',
    IL: '以色列', AE: '阿联酋', OM: '阿曼', QA: '卡塔尔',
    MY: '马来西亚', ID: '印度尼西亚', TH: '泰国', VN: '越南',
    PH: '菲律宾', MM: '缅甸', KH: '柬埔寨', LA: '老挝',
    NZ: '新西兰', CY: '塞浦路斯', MT: '马耳他',
    // 国际组织与区域组织（不是国家，故单列）
    ICAO: '国际民航组织', EU: '欧盟',
  };

  function statusLabel(s) {
    return STATUS_LABELS[s] || s;
  }

  function topicLabel(t) {
    return TOPIC_LABELS[t] || t;
  }

  function jurLabel(j) {
    if (!j) return '';
    return JUR_LABELS[j] ? `${JUR_LABELS[j]}（${j}）` : j;
  }

  function renderFacets() {
    const juris = facetOf('jurisdiction');
    const sel = el('f-jurisdiction');
    Object.keys(juris).sort().forEach((k) => {
      const o = document.createElement('option');
      o.value = k; o.textContent = `${jurLabel(k)}（${juris[k]}）`;
      sel.appendChild(o);
    });

    const st = facetOf('status');
    const sel2 = el('f-status');
    Object.keys(st).sort().forEach((k) => {
      const o = document.createElement('option');
      o.value = k; o.textContent = `${statusLabel(k)}（${st[k]}）`;
      sel2.appendChild(o);
    });

    const row = el('topic-row');
    state.topics.forEach(([t, n]) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'topic-chip';
      b.dataset.topic = t;
      b.innerHTML = `${esc(topicLabel(t))}<span class="n">${esc(String(n))}</span>`;
      b.addEventListener('click', () => {
        if (state.selectedTopics.has(t)) state.selectedTopics.delete(t);
        else state.selectedTopics.add(t);
        b.classList.toggle('on');
        run();
      });
      row.appendChild(b);
    });
  }

  // ── 渲染：左侧导航 ───────────────────────────────────
  // 导航与顶部下拉框是同一组筛选器的两个入口，共用 select 的值，不另存状态。
  // 这样「点侧栏 → 下拉框跟着变」「清空下拉框 → 侧栏高亮自动消失」都成立，
  // 不会再出现两处状态各自为政、互相覆盖的老问题。
  function renderNav() {
    const total = state.records.length;
    const types = facetOf('recordType');
    const typeBox = el('nav-type');
    [
      ['', '全部记录', total],
      ['legislation', '法规', types.legislation || 0],
      ['case', '案例', types.case || 0],
      ['standard', '标准', types.standard || 0],
    ].forEach(([v, label, n]) => {
      if (v && !n) return;
      typeBox.appendChild(navButton('type', v, label, n));
    });

    // 法域只列前 6：41 个法域全铺开就是第二个下拉框，导航要能一眼扫完。
    // 其余法域仍可在上方下拉框里选。
    const juris = facetOf('jurisdiction');
    const top = Object.entries(juris).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const jurBox = el('nav-jur');
    jurBox.appendChild(navButton('jurisdiction', '', '全部法域', total));
    top.forEach(([k, n]) => jurBox.appendChild(navButton('jurisdiction', k, JUR_LABELS[k] || k, n)));

    el('nav-extra').appendChild(
      navButton('pending', '1', '仅待核验', state.meta.pendingCount || 0, pendingTitle()));
  }

  function navButton(kind, value, label, count, title) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'nav-item';
    if (title) b.title = title;
    b.dataset.navKind = kind;
    b.dataset.navValue = value;
    b.innerHTML = `<span class="nav-label">${esc(label)}</span>` +
                  `<span class="n">${Number(count || 0).toLocaleString('en-US')}</span>`;
    b.addEventListener('click', () => {
      if (kind === 'type') el('f-type').value = value;
      else if (kind === 'jurisdiction') el('f-jurisdiction').value = value;
      else if (kind === 'pending') {
        // 待核验是开关：再点一次取消，否则点了就取消不掉
        el('f-pending').value = el('f-pending').value === '1' ? '' : '1';
      }
      run();
    });
    return b;
  }

  /** 把当前筛选状态回写到导航高亮。必须在 run() 里调，因为筛选可能来自下拉框或重置按钮。 */
  function syncNav() {
    const t = el('f-type').value;
    const j = el('f-jurisdiction').value;
    const pending = el('f-pending').value === '1';
    document.querySelectorAll('.nav-item').forEach((b) => {
      const kind = b.dataset.navKind;
      const v = b.dataset.navValue;
      const on = (kind === 'type' && t === v) ||
                 (kind === 'jurisdiction' && j === v) ||
                 (kind === 'pending' && pending && v === '1');
      b.classList.toggle('on', on);
      if (on) b.setAttribute('aria-current', 'true');
      else b.removeAttribute('aria-current');
    });
  }

  // ── 事件 ─────────────────────────────────────────────
  function bindEvents() {
    let timer = null;
    el('q').addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(run, 120);
    });

    ['f-jurisdiction', 'f-type', 'f-status', 'f-evidence', 'f-pending', 'f-from', 'f-to']
      .forEach((id) => el(id).addEventListener('change', run));

    el('btn-reset').addEventListener('click', () => {
      el('q').value = '';
      ['f-jurisdiction', 'f-type', 'f-status', 'f-evidence', 'f-pending', 'f-from', 'f-to']
        .forEach((id) => { el(id).value = ''; });
      state.selectedTopics.clear();
      document.querySelectorAll('.topic-chip.on').forEach((c) => c.classList.remove('on'));
      run();
    });

    // 复制单条记录的固定链接
    el('results').addEventListener('click', async (ev) => {
      const cb = ev.target.closest('.btn-copy');
      if (!cb) return;
      const url = location.origin + location.pathname + '#rec=' + cb.dataset.copy;
      try {
        await navigator.clipboard.writeText(url);
        cb.textContent = '已复制';
        setTimeout(() => { cb.textContent = '复制链接'; }, 1600);
      } catch (e) {
        window.prompt('复制这条记录的链接：', url);
      }
    });

    // 浏览器前进/后退，或用户直接改 hash：回到对应状态
    window.addEventListener('hashchange', () => {
      applyHash();
      run();
      expandFromHash();
    });

    // 详情按需加载（事件委托：结果列表会重绘，不能逐个绑定）
    el('results').addEventListener('click', (ev) => {
      const btn = ev.target.closest('.btn-detail');
      if (!btn) return;
      const rec = btn.closest('.record');
      const box = rec && rec.querySelector('.record-detail');
      if (!box) return;
      if (!box.hidden) {
        box.hidden = true; btn.textContent = '展开详情 ▾';
        state.expanded = null; syncHash();
        return;
      }
      btn.textContent = '收起 ▴';
      state.expanded = btn.dataset.id; syncHash();
      loadDetail(btn.dataset.id, box);
    });
  }

  // ── URL 状态 ─────────────────────────────────────────
  // 检索词、筛选条件、展开的记录都写进 hash：
  // 读者可以把某条记录或某个筛选结果的链接直接发给别人，刷新也不会丢。
  function hashParams() {
    const q = currentQuery();
    const p = new URLSearchParams();
    if (q.text) p.set('q', q.text);
    if (q.jurisdiction) p.set('jur', q.jurisdiction);
    if (q.recordType) p.set('type', q.recordType);
    if (q.status) p.set('status', q.status);
    if (q.evidenceLevel && q.evidenceLevel.length) p.set('ev', q.evidenceLevel[0]);
    if (q.pendingOnly) p.set('pending', '1');
    if (q.from) p.set('from', q.from);
    if (q.to) p.set('to', q.to);
    if (q.topics.length) p.set('topics', q.topics.join(','));
    if (state.expanded) p.set('rec', state.expanded);
    return p;
  }

  function syncHash() {
    const s = hashParams().toString();
    const h = s ? '#' + s : '';
    if (location.hash !== h) {
      history.replaceState(null, '', h || location.pathname + location.search);
    }
  }

  function applyHash() {
    const p = new URLSearchParams(location.hash.replace(/^#/, ''));
    el('q').value = p.get('q') || '';
    el('f-jurisdiction').value = p.get('jur') || '';
    el('f-type').value = p.get('type') || '';
    el('f-status').value = p.get('status') || '';
    el('f-evidence').value = p.get('ev') || '';
    el('f-pending').value = p.get('pending') || '';
    el('f-from').value = p.get('from') || '';
    el('f-to').value = p.get('to') || '';
    state.selectedTopics = new Set((p.get('topics') || '').split(',').filter(Boolean));
    state.expanded = p.get('rec') || null;
    document.querySelectorAll('.topic-chip').forEach((c) => {
      c.classList.toggle('on', state.selectedTopics.has(c.dataset.topic));
    });
  }

  /** hash 里指定了记录就自动展开并滚到它 */
  function expandFromHash() {
    const rid = state.expanded;
    if (!rid) return;
    const btn = document.querySelector('.record .btn-detail[data-id="' + CSS.escape(rid) + '"]');
    if (!btn) return;
    const rec = btn.closest('.record');
    const box = rec && rec.querySelector('.record-detail');
    if (!box || !box.hidden) return;
    btn.click();                       // 走既有展开逻辑，状态与 URL 由那里统一维护
    rec.scrollIntoView({ block: 'center' });
  }

  // ── 检索与渲染 ───────────────────────────────────────
  function currentQuery() {
    const ev = el('f-evidence').value;
    return {
      text: el('q').value,
      jurisdiction: el('f-jurisdiction').value,
      recordType: el('f-type').value,
      status: el('f-status').value,
      evidenceLevel: ev ? [ev] : null,
      pendingOnly: el('f-pending').value === '1',
      topics: Array.from(state.selectedTopics),
      from: el('f-from').value,
      to: el('f-to').value,
    };
  }

  function run() {
    const q = currentQuery();
    let hits, warnings = [];
    if (state.index) {
      const res = Search.search(state.index, q);
      hits = res.results;
      warnings = res.warnings;
    } else {
      hits = localFilter(q);
      // URL 里带检索词（如分享链接 ?q=…）时，索引未就绪这一瞬不能装作已检索过：
      // 此时只按筛选条件过滤，必须说明文字检索尚未生效。
      if (q.text) warnings = ['全文检索索引仍在加载，当前结果仅按筛选条件显示'];
    }
    syncNav();
    render(hits, q, warnings);
    syncHash();
  }

  /** 索引未就绪时的本地筛选：只按字段过滤，文本检索暂不可用。
   *  判据与 search.js 的 finish() 逐条对齐，证据等级同样取 evidenceLevels。 */
  function localFilter(q) {
    const out = [];
    for (const r of state.records) {
      if (q.jurisdiction && r.jurisdiction !== q.jurisdiction) continue;
      if (q.recordType && r.recordType !== q.recordType) continue;
      if (q.status && r.status !== q.status) continue;
      if (q.topics && q.topics.length) {
        const rt = r.topics || [];
        if (!q.topics.some((t) => rt.includes(t))) continue;
      }
      const lv = r.evidenceLevels || (r.evidenceLevel ? [r.evidenceLevel] : []);
      if (q.evidenceLevel && q.evidenceLevel.length) {
        if (!lv.some((l) => q.evidenceLevel.includes(l))) continue;
      }
      if (q.pendingOnly) {
        const d = r.dates || {};
        const isPending =
          (r.recordType === 'case' && !d.decisionDate) ||
          (r.penalty && r.penalty.amountOriginal && r.penalty.amountFinal === null) ||
          r.verificationPending === true;
        if (!isPending) continue;
      }
      const d = r.dates || {};
      const df = r.recordType === 'case' ? d.decisionDate : d.publicationDate;
      if (q.from && (!df || df < q.from)) continue;
      if (q.to && (!df || df > q.to)) continue;
      out.push({ record: r });
    }
    return out;
  }

  function render(hits, q, warnings) {
    const total = state.records.length;
    // pendingOnly 漏在判断之外时，只勾「仅待核验」会让顶部显示「共 4230 条」
    // 而实际只渲染 35 张卡——数字与列表自相矛盾。
    const hasFilter = q.text || q.jurisdiction || q.recordType || q.status ||
      q.evidenceLevel || q.topics.length || q.from || q.to || q.pendingOnly;

    el('result-count').innerHTML = hasFilter
      ? `匹配 <b>${hits.length}</b> 条 / 共 ${total} 条`
      : `共 <b>${total}</b> 条记录`;

    // 零命中提示：区分"库里没有"与"查询写错"
    const emptyEl = el('empty');
    if (!hits.length) {
      emptyEl.innerHTML = warnings && warnings.length
        ? `没有匹配记录。${warnings.map((w) => esc(w)).join('；')}。<br>
           <span class="empty-note">标识符类查询未命中，通常表示本站未收录该对象，而非该规定不存在。</span>`
        : '没有匹配的记录。试试放宽筛选条件，或更换关键词。';
      emptyEl.classList.remove('hidden');
    } else {
      emptyEl.classList.add('hidden');
    }

    // 警告条
    const warnEl = el('warnings');
    if (warnings && warnings.length) {
      warnEl.innerHTML = warnings
        .map((w) => `<span class="warn-item">${esc(w)}</span>`)
        .join('');
      warnEl.classList.remove('hidden');
    } else {
      warnEl.classList.add('hidden');
    }

    const box = el('results');
    box.innerHTML = '';
    hits.forEach((h) => box.appendChild(renderRecord(h.record)));
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── 来源链接的标签 ───────────────────────────────────
  // 从前这里写死「官方原文 ↗」，凡是 sourceUrl 都挂这个文案。
  // 但 4225 条里有 18 条指向 store.icao.int（官方出版方的商品页，付费墙，点开没有正文），
  // 8 条指向媒体、律所博客或第三方判决镜像（courtlistener 不是 PACER）。
  // 用「有没有链接」决定文案，等于把 L3 二手来源标成官方原文——而可核验正是本站唯一的立身之本。
  // 所以标签必须由域名派生；域名单之外的默认写成中性的「来源链接」，宁可含糊不可假冒。
  const PUBLISHER_HOSTS = new Set(['store.icao.int']);
  const THIRD_PARTY_HOSTS = new Set([
    'baylos.com',            // 西班牙律所博客
    'ppc.land',              // 数据保护媒体
    'vixio.com',             // 付费法律新闻
    'ilfattoquotidiano.it',  // 意大利媒体
    'noyb.eu',               // NGO（提起申诉的一方，非裁判者）
    'courthousenews.com',    // 法律媒体
    'news.bloomberglaw.com', // 付费法律新闻
    'courtlistener.com',     // 第三方判决书镜像，非官方 PACER
  ]);
  const OFFICIAL_HOSTS = new Set([
    // 美国
    'ecfr.gov', 'federalregister.gov', 'ftc.gov', 'transportation.gov',
    // 中国
    'caac.gov.cn', 'lexcom.12348.gov.cn', 'english.court.gov.cn', 'pcpd.org.hk',
    // 欧盟与欧洲各国监管机构
    'eur-lex.europa.eu', 'edpb.europa.eu', 'legifrance.gouv.fr', 'cnil.fr',
    'ico.org.uk', 'bfdi.bund.de', 'edoeb.admin.ch', 'dsb.gv.at', 'dataprotection.ie',
    'cnpd.pt', 'uodo.gov.pl', 'dmp.hu', 'datatilsynet.no', 'datatilsynet.dk',
    'autoriteitpersoonsgegevens.nl', 'garanteprivacy.it', 'dataprotection.ro',
    'dataprotection.gov.cy', 'dataprotectionauthority.be', 'aepd.es',
    // 其他法域
    'kvkk.gov.tr', 'priv.gc.ca', 'oaic.gov.au', 'meity.gov.in', 'pdpc.gov.sg',
    'pipc.go.kr',
    // 国际组织
    'icao.int',
  ]);

  function hostOf(url) {
    try { return new URL(url).hostname.toLowerCase().replace(/^www\./, ''); }
    catch (e) { return ''; }
  }

  function sourceLabel(url) {
    const h = hostOf(url);
    if (PUBLISHER_HOSTS.has(h)) {
      return { text: '出版社页面（付费）↗', title: '官方出版方的商品页，需购买或授权才能读到正文', cls: 'src-paywall' };
    }
    if (THIRD_PARTY_HOSTS.has(h)) {
      return { text: '报道（非官方）↗', title: `媒体或第三方机构的报道，不是官方文本：${h}`, cls: 'src-third' };
    }
    if (OFFICIAL_HOSTS.has(h)) {
      return { text: '官方原文 ↗', title: `官方站点：${h}`, cls: 'src-official' };
    }
    return { text: '来源链接 ↗', title: `该域名未纳入分级名单：${h || '未知域名'}`, cls: 'src-unknown' };
  }

  function renderRecord(r) {
    const div = document.createElement('article');
    div.className = 'record';

    const d = r.dates || {};
    const rl = r.recordLevel || {};
    const lv = lowestEvidence(r);
    const typeLabel = {
      legislation: '法规', case: '案例', standard: '标准',
      guidance: '指南', policy: '政策'
    }[r.recordType] || r.recordType;

    const facts = [];
    // 决定日缺失时显式说明，不用公布日顶替
    if (d.decisionDate) facts.push(['决定', d.decisionDate]);
    else if (r.recordType === 'case') facts.push(['决定日', '未知（待核验）']);    if (d.publicationDate) facts.push(['公布', d.publicationDate]);
    if (d.effectiveDate) facts.push(['生效', d.effectiveDate]);
    if (d.lastAmendedDate) facts.push(['末次修订', d.lastAmendedDate]);
    if (r.citationString) facts.push(['文号', r.citationString, true]);
    // Federal Register：同一引注可能对应两个文件（两份规则可同页起排），
    // 只给「91 FR 37787」读者分不出是哪一份，补上文件号才可区分。
    if (r.documentNumber) facts.push(['文件号', r.documentNumber, true]);
    if (r.jurisdiction) facts.push(['法域', jurLabel(r.jurisdiction)]);

    // 各源的专有字段：CCAR 部号与有效性、法通网效力位阶、eCFR 条文层级
    // 精简索引把这些字段平铺在记录顶层（见 scripts/build_browse.py 的 keep 列表）
    if (r.ccarNumber) facts.push(['CCAR', r.ccarNumber, true]);
    if (r.validity) facts.push(['有效性', r.validity]);
    if (r.lawCategoryName) facts.push(['位阶', r.lawCategoryName]);
    if (r.issuingDepartment) facts.push(['发文', r.issuingDepartment]);
    if (r.countryName) facts.push(['国家', r.countryName]);
    if (r.versionStatusName) facts.push(['版本', r.versionStatusName]);
    if (r.cfrSection) facts.push(['条文', r.cfrSection, true]);
    if (r.celex) facts.push(['CELEX', r.celex, true]);
    if (r.institutionalDocNo) facts.push(['文件号', r.institutionalDocNo, true]);
    if (r.articleCount) facts.push(['条文数', String(r.articleCount)]);
    if (rl.titleZh) facts.push(['中文名', rl.titleZh]);
    // 有全文就把长度摊出来：读者看到「全文 8,981 字」才知道详情里值得点开
    if (r.hasFullText && r.charCount) {
      facts.push(['正文', `全文 ${Number(r.charCount).toLocaleString('en-US')} 字`]);
    } else if (r.textStatus) {
      facts.push(['正文', '未收录（见详情）']);
    }

    // 罚款三态：
    //   有减免（final ≠ original）→ 两个数都显示，「罚额 X / 减免后 Y」
    //   无减免（final = original 或 final 未填）→ 只显示一个数
    //   只有 final（如 NYDFS 只公布和解金额）→ 显示 final
    // 原实现用 amountOriginal 配「最终额」标签，一旦出现真减免就会把 18,000,000 标成最终额。
    const pen = r.penalty || {};
    if (pen.amountOriginal != null || pen.amountFinal != null) {
      const cur = pen.currency || '';
      const fmt = (v) => `${cur} ${Number(v).toLocaleString('en-US')}`;
      const o = pen.amountOriginal, f = pen.amountFinal;
      if (o != null && f != null && f !== o) {
        facts.push(['罚额', fmt(o)]);
        facts.push(['减免后', fmt(f)]);
      } else if (o != null) {
        facts.push(['金额', fmt(o)]);
      } else {
        facts.push(['金额', fmt(f)]);
      }
    }

    const links = [];
    if (r.sourceUrl) {
      const src = sourceLabel(r.sourceUrl);
      links.push(`<a class="${src.cls}" href="${esc(r.sourceUrl)}" target="_blank" rel="noopener" title="${esc(src.title)}">${esc(src.text)}</a>`);
    }
    if (r.pdfUrl) links.push(`<a href="${esc(r.pdfUrl)}" target="_blank" rel="noopener">PDF ↗</a>`);

    // 核验状态标签：二手来源或关键字段待核验时明示
    const notes = [];
    // 状态徽章：非现行状态必须在卡片上就看得见。
    // 此前「已被取代」只写在详情里，卡片上 Doc 9760 与现行文本长得一模一样，
    // 读者扫一眼列表就可能把第四版当第五版引用。
    const stNote = r.status && !['effective', 'adopted', 'final'].includes(r.status)
      ? statusLabel(r.status) : null;
    // 案例性质优先显示：读者最容易被「调查」误当成「已处罚」
    if (r.caseOutcome === 'investigation') notes.push('监管调查·未决');
    if (r.caseOutcome === 'other') notes.push('性质待判读');
    if (r.caseOutcome === 'sanction' && r.sanctionsVerified) notes.push({ text: '金额已核实', cls: 'verified' });
    if (lv === 'L3') notes.push('二手来源');
    if (r.recordType === 'case' && !d.decisionDate) {
      // 「未知」有三种成因，可靠性含义完全不同：链接指错、页面已失效、机构未公布。
      // 只写「待核验」等于把工作量藏起来，读者没法判断该不该引用。
      // 同时必须说清「事实有没有来源」——有文书来源与什么都没有，可信度差一个量级。
      const why = DATE_GAP_REASON[r.dateGapReason] || '原因未分类';
      // 信息流线索不是「文书来源」，措辞必须分开，否则等于把新闻标题抬成执法文书
      const fs = r.factSourceLevel
        ? (r.factSourceType === 'news_feed'
            ? `仅有 ${r.factSourceLevel} 信息流线索`
            : `事实有 ${r.factSourceLevel} 文书来源`)
        : '事实暂无文书来源';
      notes.push(`决定日未确认｜${fs}｜${why}`);
    }
    // 注意：amountFinal === null 不等于「拟议额」。
    // schema 没定义 null 的含义，实际数据里同样情形一半填了 final=original（A-007 等 8 条）、
    // 一半留了 null（A-001 等 7 条）——所以 null 只是「未记录减免后的数额」。
    // 已核实的记录不再提示拟议（否则与绿色「金额已核实」自相矛盾），只有未核实的才提示待核。
    if (r.penalty && r.penalty.amountOriginal && r.penalty.amountFinal === null
        && !r.sanctionsVerified) {
      notes.push('金额待核');
    }

    // 规范键：让读者与 AI 知道这条记录归属哪些可查键
    // 精简索引用 keyRefs 承载（全量记录则从 assertions 的键字段派生）
    const keyBadges = [];
    const cfr = (r.keyRefs && r.keyRefs.length)
      ? r.keyRefs.slice(0, 2)
      : (r.assertions || [])
          .filter((a) => ['cfr_references', 'cfr_part', 'cfr_section',
            'ccar_number'].includes(a.field) && a.value)
          .flatMap((a) => String(a.value).split(/,\s*/))
          .filter(Boolean)
          .slice(0, 2);
    cfr.forEach((c) => keyBadges.push(`<span class="badge key" title="可精确检索：${esc(c)}">${esc(c)}</span>`));
    if (r.citationString) {
      keyBadges.push(`<span class="badge key mono" title="文号">${esc(r.citationString)}</span>`);
    }

    div.innerHTML = `
      <div class="record-top">
        <span class="record-id">${esc(r.recordId)}</span>
        <h3 class="record-title">
          ${r.sourceUrl
            ? `<a href="${esc(r.sourceUrl)}" target="_blank" rel="noopener">${esc(r.title)}</a>`
            : esc(r.title)}
        </h3>
        <span class="badge type-${esc(r.recordType)}">${esc(typeLabel)}</span>
        ${stNote ? `<span class="badge pending" title="状态：${esc(statusLabel(r.status))}">${esc(stNote)}</span>` : ''}
        ${lv ? `<span class="badge lv${lv.slice(1)}" title="证据等级">${esc(lv)}</span>` : ''}
        ${notes.map((n) => {
          const text = typeof n === 'string' ? n : n.text;
          const cls = typeof n === 'string' ? 'pending' : (n.cls || 'pending');
          const tip = cls === 'verified' ? '已与官方文书或聚合库核对'
            : '需人工核验，勿直接引用';
          return `<span class="badge ${cls}" title="${tip}">${esc(text)}</span>`;
        }).join('')}
      </div>
      ${r.summary ? `<p class="record-summary">${esc(r.summary)}</p>` : ''}
      <div class="record-facts">
        ${facts.map(([k, v, mono]) =>
          `<span><span class="k">${k}</span><span class="v${mono ? ' mono' : ''}">${esc(v)}</span></span>`
        ).join('')}
      </div>
      ${keyBadges.length ? `<div class="record-keys">${keyBadges.join('')}</div>` : ''}
      ${(r.topics || []).length ? `<div class="record-tags">${
        r.topics.slice(0, 8).map((t) => `<span class="tag">${esc(topicLabel(t))}</span>`).join('')
      }</div>` : ''}
      <div class="record-detail" hidden>
        <div class="detail-body"><span class="muted">载入中…</span></div>
      </div>
      <div class="record-links">
        <button class="btn-detail" type="button" data-id="${esc(r.recordId)}">展开详情 ▾</button>
        <button class="btn-copy" type="button" data-copy="${esc(r.recordId)}"
                title="复制这条记录的固定链接（#rec=记录ID）">复制链接</button>
        ${links.join('')}
      </div>
    `;
    return div;
  }

  // ── 详情按需加载 ────────────────────────────────────────
  async function loadDetail(recordId, box) {
    const url = `${dataUrl('details')}/${detailBucket(recordId)}/${recordId}.json`;
    const body = box.querySelector('.detail-body');
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const d = await res.json();
      body.innerHTML = renderDetail(d);
      box.hidden = false;
    } catch (e) {
      body.innerHTML = `<span class="muted">详情载入失败：${esc(e.message)}</span>`;
      // 失败时也要展开，否则按钮已变「收起」而面板不可见，用户需再点两次
      box.hidden = false;
      const b = box.closest('.record') && box.closest('.record').querySelector('.btn-detail');
      if (b) b.textContent = '展开详情 ▾';
    }
  }

  function renderDetail(d) {
    const parts = [];
    const rl0 = d.recordLevel || {};
    // 全文优先：有 fullText 就整篇给出，不再只给 220 字的摘要
    if (d.fullText) {
      const n = d.fullText.length;
      const cut = rl0.summaryKind === 'verbatim-excerpt';
      parts.push(
        `<div class="detail-fulltext">` +
        `<div class="fulltext-head"><b>正文全文</b>` +
        `<span class="muted">${n.toLocaleString('en-US')} 字符 · ` +
        `${esc(rl0.textSource || '官方文本')}${cut ? ' · 列表页只显示前 2,000 字' : ''}</span></div>` +
        `<div class="fulltext-body">${esc(d.fullText)}</div>` +
        (rl0.fullTextNote ? `<p class="muted detail-note">${esc(rl0.fullTextNote)}</p>` : '') +
        `</div>`);
    } else if (d.summary) {
      // 卡片上的摘要固定 3 行截断（style.css 的 .record-summary，-webkit-line-clamp: 3），
      // 约 200 字以内在卡片上已完整可读，详情里再放一遍只是重复。
      // 因此只有两种情况在这里补摘要：超出卡片可视范围的，或该记录没有断言可看——
      // 原实现是">220 才显示"，结果标准类（摘要 80–120 字）点开只剩一张字段表，读起来像空的。
      const n0 = (d.assertions || []).length;
      if (d.summary.length > 200 || n0 === 0) {
        parts.push(`<p class="detail-summary">${esc(d.summary)}</p>`);
      }
    } else {
      // 既无正文也无摘要：说清楚本站收什么，而不是留白
      parts.push('<p class="detail-summary muted">本条为元数据记录：本站只存标识、版次与来源链接，' +
        '不含正文。正文请点下方来源链接到官方站点查阅。</p>');
    }
    const asserts = d.assertions || [];
    if (asserts.length) {
      // 详情开头直接是一张表时读者不知道在看什么，补一行小标题说明这是断言表
      parts.push(`<p class="muted detail-subhead">字段与证据 · ${asserts.length} 条断言 ` +
        `<span class="subhead-hint">（每条均标出定位，可回原文复核）</span></p>`);
      parts.push('<table class="detail-table"><thead><tr><th>字段</th><th>值</th>' +
        '<th>证据</th><th>定位</th></tr></thead><tbody>' +
        asserts.map((a) => `<tr><td class="mono">${esc(a.field)}</td>` +
          `<td>${esc(a.value)}</td><td>${esc(a.evidenceLevel || '')}</td>` +
          `<td class="muted">${esc(a.locator || '')}</td></tr>`).join('') +
        '</tbody></table>');
    }
    const rl = d.recordLevel || {};
    // 证据状态：把「缺决定日」与「没有来源」分开说。
    // 此前只显示「待核验」，读者会以为整条案件没有依据——实际是文书齐备、只缺一个日期字段。
    const es = rl.evidenceStatus;
    if (es && es.factSource) {
      const fs = es.factSource;
      parts.push(
        '<div class="detail-evidence">' +
        `<b>${fs.documentType === 'news_feed' ? '线索来源' : '事实依据'}</b>：` +
        `<span class="mono">${esc(fs.evidenceLevel || '')}</span> ` +
        `${esc(fs.documentType || '')}《${esc(fs.title || '')}》` +
        `<span class="muted">（登记号 ${esc(fs.sourceId || '')}）</span>` +
        `<div class="muted">${esc(es.summaryProvenance || '')}</div>` +
        `<div class="muted">仍未确认：${esc((es.stillMissing || []).join('、'))}。` +
        `能否回原文复核：${es.recheck && es.recheck.possible ? '可以' : '当前不可以'}` +
        `${es.recheck && es.recheck.note ? '——' + esc(es.recheck.note) : ''}</div>` +
        '</div>');
    }
    const rev = d.revisionLog || [];
    if (rev.length) {
      parts.push('<div class="detail-rev"><b>修订与终结说明</b>' +
        rev.map((r) => `<div class="rev-row">` +
          `<span class="rev-transition">${esc(r.oldStatus || '')} → ${esc(r.newStatus || '')}</span>` +
          (r.date ? `<span class="rev-date">${esc(r.date)}</span>` : '') +
          `<span>${esc(r.reason || '')}</span>` +
          (r.note ? `<span class="muted">${esc(r.note)}</span>` : '') +
          '</div>').join('') + '</div>');
    }
    if (rl.note) {
      parts.push(`<p class="muted detail-note">${esc(rl.note)}</p>`);
    }
    if (rl.textStatus) {
      parts.push(`<p class="muted detail-note">正文状态：${esc(rl.textStatus)}</p>`);
    }
    if (!parts.length) parts.push('<span class="muted">无更多详情。</span>');
    return parts.join('');
  }

  function lowestEvidence(r) {
    // 精简索引直接带 evidenceLevel；全量记录需从断言派生
    if (r.evidenceLevel) return r.evidenceLevel;
    const levels = (r.assertions || []).map((a) => a.evidenceLevel).filter(Boolean);
    if (!levels.length) return '';
    const order = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5'];
    return order.find((l) => levels.includes(l)) || '';
  }

  document.addEventListener('DOMContentLoaded', load);
})();
