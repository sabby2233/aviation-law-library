// 真实浏览器验收：验证首屏两阶段加载、检索、详情、URL 分享
// 用法：node site/verify_live.js <baseUrl> [截图目录]
// 只跑必要断言，输出精简——验收脚本要便宜，交互浏览器才贵。
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE = process.argv[2] || 'http://127.0.0.1:8811';
const SHOT = process.argv[3] || null;
const log = (...a) => console.log(...a);
let pass = 0, fail = 0;
const check = (name, cond, detail) => {
  if (cond) { pass++; log(`  ✓ ${name}`); }
  else { fail++; log(`  ✗ ${name}${detail ? '  → ' + detail : ''}`); }
};

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge' });
  } catch (e) {
    log('  ! msedge 不可用，改用默认 chromium：' + e.message.split('\n')[0]);
    browser = await chromium.launch();
  }
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });

  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  const t0 = Date.now();
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });

  // 首屏：列表先出，不等检索词包
  await page.waitForSelector('.record', { timeout: 45000 });
  const listMs = Date.now() - t0;
  const firstCount = await page.textContent('#result-count');
  log(`  首屏列表 ${listMs} ms｜${firstCount.replace(/\s+/g, ' ').trim()}`);
  check('首屏先出列表（不等检索词包）', listMs < 15000, `${listMs} ms`);
  check('首屏即列出全部记录', /4229/.test(firstCount), firstCount);

  // 检索索引就绪：搜索框解禁
  await page.waitForFunction(() => {
    const q = document.getElementById('q');
    return q && !q.disabled;
  }, { timeout: 60000 });
  log('  检索索引已就绪');
  check('索引就绪后搜索框解禁', await page.isEnabled('#q'));

  // 全文检索
  await page.fill('#q', 'remote identification');
  await page.waitForTimeout(1200);
  const hitText = (await page.textContent('#result-count')).replace(/\s+/g, ' ').trim();
  const nHits = parseInt((hitText.match(/匹配\s*(\d+)/) || [0, 0])[1], 10);
  log(`  「remote identification」→ ${hitText}`);
  check('全文检索有命中', nHits > 0, hitText);

  // 零命中须给告警而不是回落全文
  await page.fill('#q', 'zzzqqqxxx不可能存在的词');
  await page.waitForTimeout(900);
  const zeroText = (await page.textContent('#result-count')).replace(/\s+/g, ' ').trim();
  const warn = ((await page.textContent('#warnings')) || '') +
    ((await page.textContent('#empty')) || '');
  const nZero = parseInt((zeroText.match(/匹配\s*(\d+)/) || [0, 1])[1], 10);
  check('零命中不回落全文', nZero === 0, zeroText);
  check('零命中给告警', /没有|未|不存在|无匹配/.test(warn.replace(/\s+/g, ' ')), warn.slice(0, 80));

  // 规范键精确查
  await page.fill('#q', '14 CFR 39');
  await page.waitForTimeout(900);
  const keyText = (await page.textContent('#result-count')).replace(/\s+/g, ' ').trim();
  log(`  「14 CFR 39」→ ${keyText}`);
  check('规范键精确查有命中', /匹配\s*[1-9]/.test(keyText), keyText);

  // 裸记录 ID
  await page.fill('#q', 'AVA-US-ADP-A-001');
  await page.waitForTimeout(900);
  const idText = (await page.textContent('#result-count')).replace(/\s+/g, ' ').trim();
  log(`  「AVA-US-ADP-A-001」→ ${idText}`);
  check('裸记录 ID 精确命中 1 条', /匹配\s*1\s*条/.test(idText), idText);

  // 详情展开
  await page.fill('#q', '');
  await page.waitForTimeout(800);
  const btn = await page.$('.record .btn-detail');
  if (btn) { await btn.click(); await page.waitForTimeout(1500); }
  const detailOpen = await page.$('.record-detail:not([hidden])');
  check('详情可展开', !!detailOpen);
  const detailText = detailOpen ? (await detailOpen.textContent()).replace(/\s+/g, ' ').trim() : '';
  check('详情含正文或断言', detailText.length > 80, `长度 ${detailText.length}`);

  // URL 分享：hash 记录筛选与展开
  const url = page.url();
  log('  当前 URL：' + url.replace(/^https?:\/\/[^/]+/, ''));
  check('URL 带查询状态', url.includes('#') || url.includes('?'), url);

  // 复制链接按钮
  const copyBtn = await page.$('.btn-copy[data-copy]');
  check('存在「复制链接」按钮', !!copyBtn);

  if (SHOT) {
    fs.mkdirSync(SHOT, { recursive: true });
    await page.screenshot({ path: path.join(SHOT, 'home.png'), fullPage: false });
    await page.fill('#q', 'remote identification');
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(SHOT, 'search.png'), fullPage: false });
    log('  截图已存 ' + SHOT);
  }

  const realErrors = errors.filter((e) => !/favicon|404 \(Not Found\)/i.test(e));
  check('无 JS 报错', realErrors.length === 0, realErrors.slice(0, 3).join(' | '));

  log(`\n结果：通过 ${pass} · 失败 ${fail}`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('验收脚本异常：', e.message); process.exit(2); });
