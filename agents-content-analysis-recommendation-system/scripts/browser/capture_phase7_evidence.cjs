// Render real evaluation artifacts in the existing UI; never replace saved DB results.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const run = path.resolve(root, process.argv[2] || 'artifacts/evaluation/phase7-20260926');
const out = path.join(run, 'screenshots');
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8081';
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8001';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const response = await fetch(api + '/contents/my?limit=50', { headers });
  assert.equal(response.status, 200);
  const history = await response.json();
  const item = history.items.find(row => row.domain === 'phone') || history.items[0];
  assert.ok(item, 'Existing owned history row is required for read-only UI navigation');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const report = { preview_only: true, real_pipeline_artifacts: true, database_results_replaced: false, images: [], errors: [] };
  try {
    const liveResponse = await fetch(api + `/recommendations/from-content/${item.content_id}`, { headers });
    assert.equal(liveResponse.status, 200);
    const live = await liveResponse.json();
    assert.ok(live.hook_keywords.every(row => row.support_count > 0 && row.supporting_dataset_row_ids.length > 0));
    assert.ok(live.hook_keywords.every(row => !live.user_keywords.includes(row.keyword)));
    assert.ok(!live.hook_keywords.some(row => row.keyword === 'dimensity'));
    report.live_api_check = { content_id: item.content_id, domain: live.domain,
      hook_keywords: live.hook_keywords.map(row => row.keyword), saved_results_changed: false };
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, serviceWorkers: 'block' });
    await context.addInitScript(data => {
      localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
    }, session);
    for (const [stage, caseId] of [['before', 'existing-01'], ['after', 'existing-01'], ['after', 'existing-02']]) {
      const source = path.join(run, stage, `${caseId}.json`);
      const entry = JSON.parse(fs.readFileSync(source, 'utf8'));
      const payload = { ...entry.result, title: `Phase 7 ${stage.toUpperCase()} | ${path.basename(entry.spec.video_path)} | artifact preview`, saved: false, content_id: null };
      const page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', msg => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(msg.text())) report.errors.push(msg.text()); });
      await page.route(`**/contents/${item.content_id}`, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) }));
      await page.goto(`${web}/#/history`, { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
      await page.waitForTimeout(700);
      const seek = async name => {
        for (let i = 0; i < 40; i++) {
          let position;
          for (const candidates of [page.getByRole('heading', { name, exact: false }), page.getByRole('button', { name, exact: false }), page.getByText(name, { exact: false })]) {
            for (const target of await candidates.all()) {
              const box = await target.boundingBox().catch(() => null);
              if (box && box.y > 64 && box.y < 940) return target;
              position ||= box;
            }
          }
          await page.mouse.move(1350, 650);
          await page.mouse.wheel(0, position && position.y < 64 ? -350 : 350);
          await page.waitForTimeout(150);
        }
        throw new Error(`Cannot reach ${name}`);
      };
      await (await seek(item.title.slice(0, 50))).click();
      await page.waitForTimeout(700);
      const shot = async section => {
        const file = `${stage}-${caseId}-${section}.png`;
        await page.screenshot({ path: path.join(out, file) });
        fs.writeFileSync(path.join(out, file + '.txt'), await page.locator('body').ariaSnapshot());
        report.images.push({ file, source: path.relative(root, source), source_sha256: crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex') });
      };
      await shot('findings');
      await seek('2. ควรเพิ่มอะไร');
      await page.mouse.move(1350, 650);
      await page.mouse.wheel(0, 400);
      await page.waitForTimeout(250);
      await shot('suggestions');
      if (stage === 'after' && caseId === 'existing-01') {
        await (await seek('หลักฐาน: charging speed')).click();
        await page.waitForTimeout(300);
        await shot('evidence');
      }
      await page.close();
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } finally {
    await browser.close();
    await fetch(api + '/auth/logout', { method: 'POST', headers }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
