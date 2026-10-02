// Read-only browser proof for Phase 3. Mutating workflows use isolated DB/widget tests.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/project-closeout-phase3');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8000';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8082';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const session = JSON.parse(execFileSync(
    'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'],
    { cwd: root, encoding: 'utf8' },
  ).trim());
  const report = {
    at: new Date().toISOString(),
    evidence_type: 'live database reads; no provider fetch and no data mutation',
    viewports: [],
    errors: [],
    requests: [],
  };
  let browser;
  try {
    const headers = {
      Authorization: `Bearer ${session.access_token}`,
      'X-Trend-Session-Key': session.session_key,
    };
    for (const endpoint of [
      '/follows/preferences',
      '/follows/topics',
      '/notifications/?limit=20',
      '/admin/trend-settings',
      '/admin/datasets?limit=12',
      '/admin/users?limit=12',
      '/admin/logs?limit=16',
    ]) {
      const response = await fetch(api + endpoint, { headers });
      assert.equal(response.status, 200, endpoint);
    }

    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({
        viewport: { width, height: 950 },
        serviceWorkers: 'block',
      });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      const page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) {
          report.errors.push(message.text());
        }
      });
      page.on('response', response => {
        if (response.url().startsWith(api)) {
          report.requests.push({ url: response.url(), status: response.status() });
        }
      });

      async function open(route) {
        await page.goto(`${web}/#${route}`, { waitUntil: 'networkidle' });
        await page.locator('flt-semantics-placeholder').evaluateAll(
          nodes => nodes.forEach(node => node.click()),
        );
        await page.waitForTimeout(800);
      }

      await open('/dashboard');
      await page.screenshot({ path: path.join(out, `dashboard-${width}.png`) });
      await open('/admin-datasets');
      await page.getByRole('button', { name: 'เพิ่ม Dataset สำหรับตรวจสอบ' }).waitFor();
      await page.screenshot({ path: path.join(out, `datasets-${width}.png`) });
      await open('/admin-users');
      await page.getByText('จัดการผู้ใช้', { exact: true }).first().waitFor();
      await page.screenshot({ path: path.join(out, `users-${width}.png`) });
      await open('/admin-analysis-settings');
      await page.screenshot({ path: path.join(out, `settings-${width}.png`) });
      await open('/admin-logs');
      await page.getByText('บันทึกการทำงานระบบ', { exact: true }).first().waitFor();
      await page.screenshot({ path: path.join(out, `logs-${width}.png`) });
      fs.writeFileSync(
        path.join(out, `logs-${width}.txt`),
        await page.locator('body').ariaSnapshot(),
      );
      report.viewports.push(width);
      await context.close();
    }
    assert.deepEqual(report.errors, []);
    assert.ok(report.requests.every(item => item.status < 400));
    report.passed = true;
  } finally {
    await fetch(api + '/auth/logout', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        'X-Trend-Session-Key': session.session_key,
        'Content-Type': 'application/json',
      },
      body: '{}',
    }).catch(() => {});
    if (browser) await browser.close();
    fs.writeFileSync(
      path.join(out, 'verification.json'),
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
