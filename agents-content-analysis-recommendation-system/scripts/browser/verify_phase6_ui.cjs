// Read-only real admin/result screens. Destructive workflows are tested in isolated unit databases.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/phase6');
fs.mkdirSync(out, { recursive: true });
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8001';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8081';

(async () => {
  const session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const report = { at: new Date().toISOString(), read_only: true, errors: [], screenshots: [], requests: [] };
  let browser, page;
  try {
    async function read(url) {
      const response = await fetch(api + url, { headers: { Authorization: `Bearer ${session.access_token}`,
        'X-Trend-Session-Key': session.session_key } });
      assert.equal(response.status, 200, url);
      return response.json();
    }
    const health = await read('/admin/sources/health');
    const datasets = await read('/admin/datasets?limit=12');
    const trash = await read('/admin/datasets?trashed=true&limit=12');
    const history = await read('/contents/my?limit=50');
    assert.ok(datasets.items.every(row => row.quality && row.deleted_at === null));
    assert.ok(trash.items.every(row => row.deleted_at !== null));
    assert.ok(health.items.some(row => row.platform === 'youtube'));
    const selected = history.items.find(row => row.domain === 'phone') || history.items[0];
    assert.ok(selected, 'A saved analysis is required for read-only result verification');
    report.api = { health_scopes: health.items.length, datasets: datasets.total, trash: trash.total, content_id: selected.content_id };
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, serviceWorkers: 'block' });
    await context.addInitScript(data => {
      localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
    }, session);
    page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', msg => {
      if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(msg.text())) report.errors.push(msg.text());
    });
    page.on('response', response => {
      if (response.url().startsWith(api)) report.requests.push({ url: response.url(), status: response.status() });
    });
    async function open(route) {
      await page.goto(`${web}/#${route}`, { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
      await page.waitForTimeout(900);
    }
    async function shot(name) {
      await page.screenshot({ path: path.join(out, `${name}.png`) });
      fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
      report.screenshots.push(name);
    }
    async function seek(name) {
      for (let n = 0; n < 35; n++) {
        let position;
        for (const candidate of [page.getByRole('heading', { name, exact: false }), page.getByRole('button', { name, exact: false }), page.getByText(name, { exact: false })]) {
          for (const locator of await candidate.all()) {
            const box = await locator.boundingBox({ timeout: 300 }).catch(() => null);
            if (box && box.y > 64 && box.y < page.viewportSize().height - 90) return locator;
            position ||= box;
          }
        }
        await page.mouse.move(page.viewportSize().width - 70, 600);
        await page.mouse.wheel(0, position && position.y < 64 ? -380 : 380);
        await page.waitForTimeout(200);
      }
      throw new Error(`Section not found: ${name}`);
    }
    await open('/admin-datasets');
    await shot('datasets-desktop');
    await page.getByRole('tab', { name: 'ถังขยะ', exact: false }).click();
    await page.waitForTimeout(700);
    await shot('trash');
    await open('/admin-analysis-settings');
    await page.getByRole('tab', { name: 'อัปเดตเทรนด์', exact: true }).click();
    await page.waitForTimeout(900);
    await shot('source-health');
    for (const width of [1440, 900]) {
      await page.setViewportSize({ width, height: 1050 });
      await open('/history');
      await (await seek(selected.title.slice(0, 55))).click();
      await page.waitForTimeout(800);
      await shot(`result-found-${width}`);
      await seek('2. ควรเพิ่มอะไร');
      await shot(`result-advice-${width}`);
      await seek('3. เพราะอะไรจึงแนะนำ');
      await shot(`result-reasons-${width}`);
      const evidence = await seek('หลักฐาน:');
      await evidence.click();
      await page.waitForTimeout(400);
      await shot(`result-evidence-${width}`);
    }
    await open('/admin-datasets');
    await shot('datasets-compact');
    assert.deepEqual(report.errors, []);
    assert.ok(report.requests.every(r => r.status < 400), 'Some API reads failed');
    report.passed = true;
  } catch (error) {
    if (page) {
      await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {});
      fs.writeFileSync(path.join(out, 'failure.txt'), await page.locator('body').ariaSnapshot().catch(() => ''));
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
