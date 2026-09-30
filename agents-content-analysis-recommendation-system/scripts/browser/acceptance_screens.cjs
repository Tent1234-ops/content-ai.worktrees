const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const out = path.resolve(__dirname, '../../artifacts/acceptance/20260930');
const report = { checks: [], errors: [], http_errors: [], screenshots: [] };
let browser, page;
function write() { fs.writeFileSync(path.join(out, 'screens.json'), JSON.stringify(report, null, 2)); }
async function shot(name) {
  await page.screenshot({ path: path.join(out, name + '.png') });
  fs.writeFileSync(path.join(out, name + '.txt'), await page.locator('body').ariaSnapshot());
  report.screenshots.push(name); write();
}
async function open(route) {
  await page.goto('http://127.0.0.1:8080/#' + route, { waitUntil: 'networkidle' });
  await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
  await page.waitForTimeout(1000);
}
async function seek(name, role = 'button') {
  for (let n = 0; n < 50; n++) {
    let pos;
    for (const locator of await page.getByRole(role, { name, exact: false }).all()) {
      const box = await locator.boundingBox().catch(() => null);
      if (box && box.y > 65 && box.y + box.height / 2 < 955) return locator;
      pos ||= box;
    }
    await page.mouse.move(850, 600);
    await page.mouse.wheel(0, pos && pos.y < 65 ? -350 : 350);
    await page.waitForTimeout(170);
  }
  throw new Error(`Cannot reach ${name}`);
}
async function check(name, fn) {
  try { await fn(); report.checks.push({ name, status: 'passed' }); console.log('PASS ' + name); }
  catch (e) { report.checks.push({ name, status: 'failed', error: e.message }); console.log('FAIL ' + name + ': ' + e.message); await shot('screen-failure-' + report.checks.length); }
  write();
}
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
    page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    page.on('console', m => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text()); });
    page.on('response', r => { if (r.url().startsWith('http://127.0.0.1:8000') && r.status() >= 400) report.http_errors.push({ url: r.url(), status: r.status() }); });
    await check('YouTube cards, details, source button', async () => {
      await open('/dashboard');
      await (await seek('ดูรายละเอียด')).click(); await page.waitForTimeout(600);
      await shot('10-youtube-detail');
      assert.ok((await page.locator('body').ariaSnapshot()).includes('ยอดวิว'));
      assert.ok(await page.getByRole('button', { name: 'ดูบน YouTube', exact: true }).last().isEnabled());
    });
    await check('Google separate trends and details', async () => {
      await open('/dashboard'); await page.getByRole('tab', { name: 'Google', exact: true }).click();
      await page.waitForTimeout(1200); await shot('11-google-history');
      await (await seek('ดูรายละเอียด')).click(); await page.waitForTimeout(600);
      await shot('12-google-detail');
      assert.ok((await page.locator('body').ariaSnapshot()).includes('คำค้น'));
    });
    await check('TikTok empty state (not implemented provider)', async () => {
      await open('/dashboard'); await page.getByRole('tab', { name: 'TikTok', exact: true }).click();
      await page.waitForTimeout(800); await shot('13-tiktok');
      assert.ok((await page.locator('body').ariaSnapshot()).includes('ยังไม่มี'));
    });
    const admin = JSON.parse(fs.readFileSync(path.join(out, 'private-admin.json')));
    await check('Admin login through UI', async () => {
      await open('/login');
      for (const [name, value] of [['Email', admin.email], ['Password', admin.password]]) {
        await page.getByRole('textbox', { name, exact: true }).click();
        await page.keyboard.insertText(value);
      }
      const login = page.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Login', exact: true }).click();
      const response = await login; assert.equal(response.status(), 200);
      admin.session = await response.json(); fs.writeFileSync(path.join(out, 'private-admin.json'), JSON.stringify(admin));
      await page.waitForTimeout(1000);
    });
    for (const route of ['admin-users', 'admin-training', 'admin-analysis-settings', 'admin-dataset-review', 'admin-datasets', 'admin-logs', 'admin-transcript-import']) {
      await check('Admin page ' + route, async () => {
        await open('/' + route); await shot('14-' + route);
        assert.ok(page.url().includes(route));
        assert.ok(!(await page.locator('body').ariaSnapshot()).includes('Welcome back'));
      });
    }
    await check('Dataset trash UI', async () => {
      await open('/admin-datasets'); await page.getByRole('tab', { name: 'ถังขยะ', exact: false }).click();
      await page.waitForTimeout(900); await shot('15-dataset-trash');
      assert.ok((await page.locator('body').ariaSnapshot()).includes('ACCEPTANCE ONLY'));
    });
    await check('Trend settings and source health UI', async () => {
      await open('/admin-analysis-settings'); await page.getByRole('tab', { name: 'อัปเดตเทรนด์', exact: true }).click();
      await page.waitForTimeout(900); await shot('16-trend-settings');
      for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, 630); await page.waitForTimeout(250); await shot('16-trend-settings-' + i); }
    });
    await page.setViewportSize({ width: 1000, height: 1000 });
    for (const route of ['dashboard', 'admin-analysis-settings', 'admin-datasets']) {
      await check('Compact desktop ' + route, async () => { await open('/' + route); await shot('17-compact-' + route); });
    }
  } finally {
    write(); if (browser) await browser.close();
    console.log(JSON.stringify({ checks: report.checks, errors: report.errors, http_errors: report.http_errors }, null, 2));
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
