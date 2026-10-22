const { chromium } = require('playwright');

const URL = 'https://flowus.cn/flyngin/share/925292e4-e5d6-4ab3-9aad-e6028a006fb3';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'zh-CN',
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();

  const apiCalls = [];
  page.on('response', async (res) => {
    const u = res.url();
    if (/api|share|page|block|content/i.test(u) && res.status() === 200) {
      const ct = res.headers()['content-type'] || '';
      if (ct.includes('json')) {
        try {
          const body = await res.text();
          if (body.length > 80) apiCalls.push({ url: u, size: body.length, body });
        } catch (e) { /* ignore */ }
      }
    }
  });

  console.log('打开页面…');
  try {
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
  } catch (e) {
    console.log('goto 超时，继续尝试取内容:', e.message.slice(0, 80));
  }
  await page.waitForTimeout(5000);

  const title = await page.title();
  console.log('页面标题:', title);

  const text = await page.evaluate(() => document.body.innerText);
  console.log('正文长度:', text.length);
  console.log('\n===== 页面正文（前 3000 字）=====');
  console.log(text.slice(0, 3000));

  // 找所有链接（文件/子页面）
  const links = await page.evaluate(() =>
    Array.from(document.querySelectorAll('a')).map(a => ({
      text: (a.innerText || '').trim().slice(0, 80),
      href: a.href,
    })).filter(x => x.href && !x.href.startsWith('javascript'))
  );
  console.log('\n===== 链接数:', links.length, '=====');
  links.slice(0, 40).forEach(l => console.log(`  ${l.text || '(无文字)'}  →  ${l.href.slice(0, 110)}`));

  console.log('\n===== 捕获的 JSON 接口 ====', apiCalls.length, '个');
  apiCalls.slice(0, 8).forEach(c => {
    console.log(`  ${c.url.slice(0, 110)}  (${c.size}B)`);
    console.log(`     ${c.body.slice(0, 300).replace(/\s+/g, ' ')}`);
  });

  await page.screenshot({ path: 'C:/Users/qwesz/AppData/Local/Temp/flowus.png', fullPage: false });
  console.log('\n截图已存 flowus.png');

  // 保存原始数据供后续解析
  require('fs').writeFileSync(
    'C:/Users/qwesz/AppData/Local/Temp/flowus_capture.json',
    JSON.stringify({ title, text, links, apiCalls: apiCalls.map(c => ({ url: c.url, body: c.body })) }, null, 1),
    'utf-8'
  );

  await browser.close();
})();
