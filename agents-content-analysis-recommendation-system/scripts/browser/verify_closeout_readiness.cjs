// Read-only browser checks: real audited service payloads, fixture authentication.
// No real credentials, account mutations, training, or activation requests.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const out = path.resolve(process.argv[2] || 'artifacts/project-closeout/phase1-20261001');
const inventory = JSON.parse(fs.readFileSync(path.join(out, 'readiness-inventory-v2.json')));
const active = inventory.models.find(m => m.is_active);
const report = { authentication: 'browser-only fixture', data: 'readiness-inventory-v2.json', checks: [], errors: [] };
const user = { user_id: 999999, username: 'Readiness UI check', email: 'fixture@example.test', role: 'admin' };
const overview = { dataset: inventory.dataset, models: { total: inventory.models.length, items: [...inventory.models].reverse().slice(0, 20) }, active_model: active, runs: [], policy: inventory.training_policy };
let browser, page;
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ serviceWorkers: 'block' });
    assert.equal((await context.request.get('http://127.0.0.1:8000/health')).status(), 200);
    assert.equal((await context.request.get('http://127.0.0.1:8000/admin/analysis-settings')).status(), 401);
    report.live_service = 'health 200; unauthenticated admin settings 401';
    await context.addInitScript(user => {
      localStorage.setItem('flutter.access_token', JSON.stringify('browser-only-fixture'));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify('browser-only-fixture'));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(user)));
    }, user);
    await context.route('http://127.0.0.1:8000/**', async route => {
      const req = route.request();
      const url = new URL(req.url());
      const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET, OPTIONS' };
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      assert.equal(req.method(), 'GET', 'Browser check must not mutate the system');
      let data;
      if (url.pathname === '/auth/me') data = user;
      else if (url.pathname === '/admin/training') data = overview;
      else if (url.pathname === '/admin/analysis-settings') data = inventory.analysis_settings;
      else if (url.pathname === '/notifications/') data = { items: [], total: 0, unread_count: 0 };
      else if (/^\/admin\/training\/models\/\d+$/.test(url.pathname)) data = inventory.models.find(m => m.model_id === Number(url.pathname.split('/').pop()));
      else {
        report.errors.push(`Unplanned request: ${url.pathname}`);
        return route.fulfill({ status: 404, headers, json: { detail: 'Not a fixture route' } });
      }
      await route.fulfill({ status: 200, headers, json: data });
    });
    page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    page.on('console', m => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text()); });
    for (const width of [1440, 1000]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const screen of ['admin-training', 'admin-analysis-settings']) {
        await page.goto(`http://127.0.0.1:8080/#/${screen}`, { waitUntil: 'networkidle' });
        await page.waitForTimeout(1500);
        await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
        await page.getByText('ยังไม่พร้อมให้คำแนะนำเฉพาะหมวด', { exact: false }).last().waitFor();
        if (screen === 'admin-analysis-settings') {
          for (let i = 0; i < 8; i++) {
            const box = await page.getByText('ยังไม่พร้อมให้คำแนะนำเฉพาะหมวด', { exact: false }).last().boundingBox();
            if (box && box.y > 80 && box.y < 690) break;
            await page.mouse.move(width - 100, 650);
            await page.mouse.wheel(0, 350);
            await page.waitForTimeout(250);
          }
        }
        await page.waitForTimeout(300);
        const aria = await page.locator('body').ariaSnapshot();
        assert.ok(aria.includes('ยังไม่มีเกณฑ์ปฏิเสธคลิปนอกขอบเขต'));
        // Flutter exposes SelectableText as a disabled textbox without its value
        // in ariaSnapshot; verify the ID here and retain screenshots of the version.
        assert.ok(screen === 'admin-analysis-settings'
          ? aria.includes(`รหัสโมเดล: ${active.model_id}`)
          : aria.includes(active.model_version));
        const name = `${screen}-${width}`;
        await page.screenshot({ path: path.join(out, `${name}.png`) });
        fs.writeFileSync(path.join(out, `${name}.txt`), aria);
        report.checks.push({ screen, width, status: 'passed' });
        console.log(`PASS ${name}`);
      }
    }
    assert.deepEqual(report.errors, []);
  } catch (e) {
    if (page) {
      await page.screenshot({ path: path.join(out, 'browser-failure.png') });
      fs.writeFileSync(path.join(out, 'browser-failure.txt'), await page.locator('body').ariaSnapshot());
    }
    throw e;
  } finally {
    fs.writeFileSync(path.join(out, 'browser-readiness.json'), JSON.stringify(report, null, 2));
    if (browser) await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
