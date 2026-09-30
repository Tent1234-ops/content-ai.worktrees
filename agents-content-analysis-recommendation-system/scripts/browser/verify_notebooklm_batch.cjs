const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const source = process.argv[2];
assert.ok(source, 'Provide the import-result.json path');
const imported = JSON.parse(fs.readFileSync(path.resolve(root, source), 'utf8'));
const out = path.join(path.dirname(path.resolve(root, source)), 'browser');
fs.mkdirSync(out, { recursive: true });
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8003';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8083';

(async () => {
  const session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const report = { checked_candidates: 0, errors: [], review_posts: [], images: [] };
  let browser;
  try {
    for (const run of Object.values(imported.import_runs)) {
      const expected = imported.items.filter(row => row.status === 'pending_review' && row.collection_run_id === run);
      const response = await fetch(`${api}/admin/dataset-review/queue?status=all&collection_run_id=${run}&limit=100`, { headers });
      assert.equal(response.status, 200);
      const queue = await response.json();
      assert.equal(queue.total, expected.length);
      assert.equal(queue.items.length, expected.length);
      assert.equal(new Set(queue.items.map(row => row.source_youtube_id)).size, expected.length);
      for (const item of queue.items) {
        const row = expected.find(row => row.video_id === item.source_youtube_id);
        assert.ok(row);
        assert.equal(item.review_status, 'pending');
        assert.equal(item.dataset_id, null);
        assert.equal(item.proposed_leaf_key, row.leaf_key);
        assert.equal(createHash('sha256').update(item.transcript).digest('hex'), row.transcript_sha256);
        assert.ok(item.channel_title && item.duration_seconds > 0);
        assert.ok(!/### Segment \d+/.test(item.transcript));
        report.checked_candidates++;
      }
    }
    const training = await (await fetch(api + '/admin/training', { headers })).json();
    assert.equal(training.dataset.dataset_fingerprint, imported.fingerprint_before);
    assert.equal(training.active_model.model_id, imported.active_models_before[0]);
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({ viewport: { width, height: 1050 }, serviceWorkers: 'block' });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      const page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
      });
      page.on('request', request => {
        if (request.method() === 'POST' && request.url().includes('/admin/dataset-review/')) report.review_posts.push(request.url());
      });
      await page.goto(web + '/#/admin-dataset-review', { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
      await page.waitForTimeout(700);
      const tree = await page.locator('body').ariaSnapshot();
      assert.ok(tree.includes('Dataset Review') && tree.includes('Pending'));
      fs.writeFileSync(path.join(out, `${width}-review.txt`), tree);
      await page.screenshot({ path: path.join(out, `${width}-review.png`) });
      report.images.push(`${width}-review.png`);
      await page.mouse.move(width - 90, 750);
      await page.mouse.wheel(0, 600);
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(out, `${width}-candidates.png`) });
      report.images.push(`${width}-candidates.png`);
      await context.close();
    }
    assert.deepEqual(report.review_posts, []);
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } finally {
    if (browser) await browser.close();
    await fetch(api + '/auth/logout', { method: 'POST', headers }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
