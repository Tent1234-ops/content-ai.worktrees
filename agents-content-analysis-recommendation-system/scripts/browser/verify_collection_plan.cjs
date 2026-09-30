const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8003';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8083';
const out = path.join(root, 'artifacts/evaluation/classification-scope-20260927/collection-plan-ui');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const report = { errors: [], images: [], training_requested: false, channel_input_is_format_fixture: true };
  let browser;
  try {
    const response = await fetch(api + '/admin/training', { headers });
    assert.equal(response.status, 200);
    const before = await response.json();
    const plan = before.dataset.collection_plan;
    assert.equal(plan.rows.length, 5);
    assert.equal(plan.unknown_total_minimum, 40);
    assert.equal(plan.additional_minimum, plan.rows.reduce((sum, row) => sum + row.additional_minimum, 0));
    report.plan = plan;
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
      page.on('console', msg => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(msg.text())) report.errors.push(msg.text()); });
      page.on('request', request => {
        if (request.method() === 'POST' && /\/admin\/training\/(runs|models\/\d+\/activate)$/.test(new URL(request.url()).pathname)) {
          report.training_requested = true;
        }
      });
      await page.goto(web + '/#/admin-training', { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
      await page.waitForTimeout(500);
      const seek = async name => {
        for (let attempt = 0; attempt < 35; attempt++) {
          let position;
          for (const matches of [page.getByRole('textbox', { name, exact: false }),
              page.getByRole('button', { name, exact: false }), page.getByText(name, { exact: false })]) {
            for (const target of await matches.all()) {
              const box = await target.boundingBox().catch(() => null);
              if (box && box.y > 70 && box.y < 900) return target;
              position ||= box;
            }
          }
          await page.mouse.move(width - 70, 650);
          await page.mouse.wheel(0, position && position.y < 70 ? -300 : 300);
          await page.waitForTimeout(150);
        }
        throw new Error(`Cannot reach ${name}`);
      };
      const heading = await seek('แผนเก็บข้อมูลเพิ่ม');
      const headingBox = await heading.boundingBox();
      await page.mouse.move(width - 70, 650);
      await page.mouse.wheel(0, headingBox.y - 150);
      await page.waitForTimeout(250);
      const snapshot = async section => {
        const filename = `${width}-${section}.png`;
        await page.screenshot({ path: path.join(out, filename) });
        const tree = await page.locator('body').ariaSnapshot();
        fs.writeFileSync(path.join(out, filename + '.txt'), tree);
        report.images.push(filename);
        return tree;
      };
      const tree = await snapshot('collection');
      assert.ok(tree.includes(`ยังขาดอย่างน้อย ${plan.additional_minimum}`));
      await (await seek('ตรวจชุดข้อมูลจากรหัสช่อง')).click();
      await page.waitForTimeout(200);
      await seek('รหัสช่อง YouTube');
      await page.getByRole('textbox', { name: 'รหัสช่อง YouTube', exact: false }).fill('UC' + 'a'.repeat(22));
      await seek(/^ตรวจชุดข้อมูล$/);
      const button = page.getByRole('button', { name: 'ตรวจชุดข้อมูล', exact: true });
      await button.click();
      await page.waitForTimeout(600);
      await seek('ผลนี้ตรวจการแบ่งชุดเท่านั้น');
      const previewTree = await snapshot('channel-preview');
      assert.ok(previewTree.includes('ยังไม่ยืนยันว่าช่องมีอยู่จริง'));
      await context.close();
    }
    const after = await (await fetch(api + '/admin/training', { headers })).json();
    assert.equal(after.dataset.dataset_fingerprint, before.dataset.dataset_fingerprint);
    assert.equal(after.active_model.model_id, before.active_model.model_id);
    assert.equal(after.runs.length, before.runs.length);
    assert.equal(report.training_requested, false);
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } finally {
    if (browser) await browser.close();
    await fetch(api + '/auth/logout', { method: 'POST', headers }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
