// Synthetic UI-only acceptance. All API requests are intercepted; no live DB writes.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const out = path.resolve(process.argv[2]);
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8091';
const api = 'http://127.0.0.1:8000';
fs.mkdirSync(out, { recursive: true });
const report = { fixtureOnly: true, realDatabaseWrites: false, passed: false, screenshots: [], errors: [] };
const user = { user_id: 900001, username: 'UI FIXTURE', email: 'fixture@example.test', role: 'admin' };
const context = { accepted_category: 'phone', confirmed_format: 'long_form',
  frozen_age_context: 'age_30_90d', view_metric_version: 'youtube_play_start_view_v2', qualified: true };
const metrics = Object.fromEntries(['constant_prior', 'metadata_logistic_regression',
  'metadata_topics_logistic_regression'].map(name => [name, { overall: { channel_balanced: {
    brier_score: name === 'metadata_topics_logistic_regression' ? 0.19 : 0.24,
  } }, coverage: { eligible: 30, assessed: 25, abstained: 5 } }]));
const model = { model_id: 9001, model_version: 'SYNTHETIC-UI-ONLY', target_version: 'reference_relative_views_v1',
  status: 'experimental', source_kind: 'synthetic_fixture', is_active: false, can_activate: false,
  independent_test_passed: false, production_eligible: false, artifact_available: true,
  activation_reason_codes: ['synthetic_fixture_not_activatable'],
  evaluated_scopes: { schema_version: 'outcome-qualified-scopes-v1', contexts: [context] },
  metrics: { independent_test: { status: 'experimental', evaluation: { metrics } } },
};

async function seek(page, label) {
  for (let attempt = 0; attempt < 30; attempt++) {
    for (const candidate of [page.getByText(label, { exact: false }), page.getByRole('button', { name: label, exact: false })]) {
      for (const item of await candidate.all()) {
        const box = await item.boundingBox().catch(() => null);
        if (box && box.y >= 50 && box.y + box.height < page.viewportSize().height - 15) return item;
      }
    }
    await page.mouse.move(page.viewportSize().width / 2, page.viewportSize().height / 2);
    await page.mouse.wheel(0, 220);
    await page.waitForTimeout(100);
  }
  throw new Error(`Visible control not found: ${label}`);
}

async function capture(page, name) {
  await page.waitForTimeout(400);
  const sizes = await page.evaluate(() => ({ width: innerWidth, body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth }));
  assert.ok(sizes.body <= sizes.width + 16 && sizes.document <= sizes.width + 1, name);
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
  report.screenshots.push(name);
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  let lastPage;
  try {
    for (const width of [1440, 390]) {
      const browserContext = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: 'block' });
      await browserContext.addInitScript(user => {
        if (!['http:', 'https:'].includes(location.protocol)) return;
        localStorage.setItem('flutter.access_token', JSON.stringify('synthetic-only'));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify('synthetic-only'));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(user)));
      }, user);
      let available = true;
      await browserContext.route(`${api}/**`, route => {
        const url = new URL(route.request().url());
        let payload = {};
        if (url.pathname === '/auth/me') payload = user;
        else if (url.pathname === '/analyze/settings') payload = { upload_max_duration_seconds: 300,
          asr_model: 'small', hook_duration_seconds: 60, asr_ready: true,
          outcome_upload: { contexts: available ? [context] : [] } };
        else if (url.pathname === '/admin/training') payload = { dataset: { ready: false },
          policy: {}, runs: [], models: { total: 0, items: [] }, active_model: null };
        else if (url.pathname === '/admin/outcome-training') payload = { preflight: { ready: false,
          reason_codes: ['synthetic_fixture_not_activatable'] }, models: { total: 1, items: [model] },
          runs: [], active_model: null, independent_test_opened: true };
        else if (url.pathname === '/admin/outcome-training/models/9001') payload = model;
        else if (url.pathname.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
        return route.fulfill({ status: route.request().method() === 'OPTIONS' ? 204 : 200,
          contentType: 'application/json', body: route.request().method() === 'OPTIONS' ? '' : JSON.stringify(payload),
          headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*',
            'access-control-allow-methods': 'GET,POST,OPTIONS' } });
      });
      const page = await browserContext.newPage();
      lastPage = page;
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', event => {
        if (/RenderFlex overflow|overflowed by|EXCEPTION CAUGHT/i.test(event.text())) report.errors.push(event.text());
      });
      const open = async route => {
        await page.goto('about:blank');
        await page.goto(`${web}/#${route}`, { waitUntil: 'networkidle' });
        await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
        await page.waitForTimeout(700);
      };
      await open('/upload');
      await (await seek(page, 'ไม่ประเมินผลตอบรับ')).click();
      await page.getByRole('menuitem', { name: 'วิดีโอปกติ', exact: true }).click();
      await (await seek(page, 'เลือกช่วงอายุคลิปอ้างอิง')).click();
      await page.getByRole('menuitem', { name: '30 ถึงน้อยกว่า 90 วัน', exact: true }).click();
      await capture(page, `upload-context-${width}`);
      available = false;
      await open('/upload');
      await seek(page, 'ยังไม่มีโมเดลประเมินผลตอบรับที่ผ่านการตรวจรับ');
      await capture(page, `upload-unavailable-${width}`);
      await open('/admin-training');
      await (await seek(page, 'ประเมินผลตอบรับ')).click();
      await (await seek(page, 'ดูผลประเมิน Outcome #9001')).click();
      await seek(page, 'Test · Metadata + topics');
      await capture(page, `admin-evaluation-${width}`);
      await browserContext.close();
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.errors.push(error.message);
    if (lastPage && !lastPage.isClosed()) await capture(lastPage, `failure-${lastPage.viewportSize().width}`);
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
