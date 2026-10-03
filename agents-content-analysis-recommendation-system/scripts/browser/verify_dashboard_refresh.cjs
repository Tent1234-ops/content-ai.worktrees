// Read-only checks against the local API and release web build.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/dashboard-refresh', new Date().toISOString().replace(/[:.]/g, '-'));
fs.mkdirSync(out, { recursive: true });
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8080';
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8000';
const report = { checks: [], errors: [], screenshots: [] };
let browser, session;

async function open(page, route) {
  await page.goto(`${web}/#${route}`, { waitUntil: 'networkidle' });
  await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
  await page.waitForTimeout(800);
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
  report.screenshots.push(name);
}
async function seek(page, text) {
  for (let i = 0; i < 35; i++) {
    const candidates = [page.getByText(text, { exact: false }),
      page.getByRole('group', { name: text, exact: false }),
      page.getByRole('heading', { name: text, exact: false })];
    for (const candidate of candidates) {
      for (const target of await candidate.all()) {
      const box = await target.boundingBox();
      if (box && box.y > 60 && box.y < page.viewportSize().height - 100) return target;
      }
    }
    await page.mouse.move(page.viewportSize().width - 50, page.viewportSize().height - 100);
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(100);
  }
  throw new Error(`Cannot reach ${text}`);
}
function observe(page) {
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('console', m => {
    if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text());
  });
}

(async () => {
  try {
    session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
      ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
    const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
    const response = await fetch(`${api}/admin/analysis-settings`, { headers });
    assert.equal(response.status, 200);
    const settings = await response.json();
    report.readyModels = settings.whisper_models.filter(m => m.ready).map(m => m.name);
    for (const name of ['small', 'medium', 'large-v3']) assert.ok(report.readyModels.includes(name));
    report.activeAsr = settings.asr_model;
    const history = await (await fetch(`${api}/dashboard/public/history?platform=youtube&days=7`)).json();
    assert.equal(history.daily_coverage.length, 7);
    assert.ok(history.points.length > 0);
    report.history = { coverage: history.coverage, days: history.daily_coverage, schedule: history.collection_schedule,
      selectedObservations: history.items.find(i => i.key === history.selected_key)?.observation_count };
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 1000, height: 850 }]) {
      const suffix = viewport.width;
      const guestContext = await browser.newContext({ viewport, serviceWorkers: 'block' });
      const guest = await guestContext.newPage();
      observe(guest);
      await open(guest, '/dashboard');
      assert.equal(await guest.getByRole('tab', { name: 'TikTok' }).count(), 0);
      await guest.getByRole('tab', { name: 'YouTube' }).waitFor();
      await shot(guest, `youtube-${suffix}`);
      await seek(guest, '7 วันล่าสุด');
      await guest.mouse.wheel(0, 400);
      await guest.waitForTimeout(350);
      await shot(guest, `history-coverage-${suffix}`);
      await guest.mouse.wheel(0, 500);
      await guest.waitForTimeout(350);
      await shot(guest, `history-chart-${suffix}`);
      await open(guest, '/dashboard');
      await guest.getByRole('tab', { name: 'Google' }).click();
      await seek(guest, 'อันดับคำค้นบน Google ตอนนี้');
      await shot(guest, `google-${suffix}`);
      await guestContext.close();

      const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      const page = await context.newPage();
      observe(page);
      await open(page, '/dashboard');
      await page.getByRole('button', { name: /การแจ้งเตือนเทรนด์/ }).click();
      await page.waitForTimeout(700);
      await shot(page, `notifications-${suffix}`);
      assert.ok(!(await page.locator('body').ariaSnapshot()).includes('ดำเนินการไม่สำเร็จ'));
      await page.getByRole('button', { name: 'ปิด', exact: true }).click();
      await page.getByRole('button', { name: 'หัวข้อที่ติดตาม', exact: true }).click();
      await page.waitForTimeout(500);
      await shot(page, `following-${suffix}`);
      await page.getByRole('button', { name: 'ปิด', exact: true }).click();
      await open(page, '/admin-analysis-settings');
      await page.getByRole('button', { name: /โมเดลถอดเสียง Whisper/ }).click();
      await page.getByRole('menuitem', { name: 'large-v3', exact: true }).waitFor();
      await shot(page, `whisper-options-${suffix}`);
      report.checks.push({ viewport, status: 'passed' });
      await context.close();
    }
    assert.deepEqual(report.errors, []);
    report.status = 'passed';
  } catch (e) {
    report.status = 'failed'; report.failure = e.stack; process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    if (session) await fetch(`${api}/auth/logout`, { method: 'POST', headers: {
      Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key,
    } }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ status: report.status, out, checks: report.checks, failure: report.failure }));
  }
})();
