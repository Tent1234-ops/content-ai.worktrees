// Preview real regression artifacts without replacing saved database analyses.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const run = path.resolve(root, process.argv[2] || 'artifacts/evaluation/classification-scope-20260927');
const out = path.join(run, 'screenshots');
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8082';
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8002';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const report = { preview_only: true, real_pipeline_artifacts: true, database_results_replaced: false, images: [], errors: [] };
  let browser;
  try {
    const response = await fetch(api + '/contents/my?limit=50', { headers });
    assert.equal(response.status, 200);
    const history = await response.json();
    const item = history.items.find(row => row.domain === 'phone') || history.items[0];
    assert.ok(item, 'Read-only navigation needs an existing owned history row');
    const liveResponse = await fetch(api + `/recommendations/from-content/${item.content_id}`, { headers });
    assert.equal(liveResponse.status, 200);
    const live = await liveResponse.json();
    assert.equal(live.domain, 'unknown');
    assert.equal(live.classification.acceptance.reason, 'scope_validation_unavailable');
    assert.ok(live.classification.raw_taxonomy_leaf_key);
    assert.deepEqual(live.missing_keywords, []);
    assert.deepEqual(live.hook_keywords, []);
    assert.equal(live.dataset_profile.sample_size, 0);
    report.live_api_check = { content_id: item.content_id, domain: live.domain,
      acceptance: live.classification.acceptance, suggestions: 0, references: 0, saved_results_changed: false };
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({ viewport: { width, height: 1050 }, serviceWorkers: 'block' });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      for (const caseId of ['existing-01', 'existing-03']) {
        const source = path.join(run, `${caseId}.json`);
        const entry = JSON.parse(fs.readFileSync(source, 'utf8'));
        const payload = { ...entry.result, title: `${caseId} | ${path.basename(entry.video_path)} | regression preview`, saved: false, content_id: null };
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
                if (box && box.y > 64 && box.y < 920) return target;
                position ||= box;
              }
            }
            await page.mouse.move(width - 70, 650);
            await page.mouse.wheel(0, position && position.y < 64 ? -300 : 300);
            await page.waitForTimeout(150);
          }
          throw new Error(`Cannot reach ${name}`);
        };
        await (await seek(item.title.slice(0, 50))).click();
        await page.waitForTimeout(700);
        await (await seek('ผลทายก่อนตรวจรับ')).click();
        await page.waitForTimeout(250);
        const shot = async section => {
          const file = `${caseId}-${width}-${section}.png`;
          await page.screenshot({ path: path.join(out, file) });
          const tree = await page.locator('body').ariaSnapshot();
          fs.writeFileSync(path.join(out, file + '.txt'), tree);
          report.images.push({ file, source: path.relative(root, source), source_sha256: crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex') });
          return tree;
        };
        const findings = await shot('findings');
        assert.ok(findings.includes('ยังไม่ยืนยันหมวดหมู่'));
        assert.ok(findings.includes('ไม่ใช้เลือกคลิปอ้างอิง'));
        await seek('งดคำแนะนำเฉพาะหมวด เพราะผลจำแนกยังไม่ผ่านเกณฑ์ตรวจรับ');
        const suggestions = await shot('withheld');
        assert.ok(suggestions.includes('งดคำแนะนำเฉพาะหมวด'));
        await page.close();
      }
      await context.close();
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } finally {
    if (browser) await browser.close();
    await fetch(api + '/auth/logout', { method: 'POST', headers }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
