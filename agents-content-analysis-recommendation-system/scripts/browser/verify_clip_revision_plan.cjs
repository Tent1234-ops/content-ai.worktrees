const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/clip-revision-plans');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8006';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8086';
const fixtureApi = process.env.VERIFY_FIXTURE_URL || 'http://127.0.0.1:8007';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const fixture = await (await fetch(fixtureApi + '/verification/info')).json();
  assert.equal(fixture.fixture, true);
  const session = JSON.parse(execFileSync('C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const report = { isolated_sqlite: true, errors: [], cases: [], screenshots: [] };
  let browser, page;
  const planUrl = `${fixtureApi}/contents/${fixture.content_id}/revision-plan`;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: 'block',
        permissions: ['clipboard-read', 'clipboard-write'] });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', msg => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(msg.text())) report.errors.push(msg.text()); });
      let failNextSave = true;
      await page.route('**/contents/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        if (request.method() === 'PUT' && failNextSave) {
          failNextSave = false;
          return route.fulfill({ status: 503, json: { detail: 'TEST FIXTURE: จำลองฐานข้อมูลไม่พร้อม' } });
        }
        const response = await route.fetch({ url: fixtureApi + url.pathname + url.search });
        return route.fulfill({ response });
      });
      async function seek(text, role = null) {
        for (let step = 0; step < 90; step++) {
          let position;
          const finders = role ? [page.getByRole(role, { name: text, exact: false })] :
            [page.getByRole('button', { name: text, exact: false }), page.getByText(text, { exact: false })];
          for (const finder of finders) {
            for (const locator of await finder.all()) {
              const box = await locator.boundingBox({ timeout: 200 }).catch(() => null);
              if (box && box.y > 65 && box.y + box.height / 2 < 976) return locator;
              position ||= box;
            }
          }
          await page.mouse.move(width / 2, 600);
          await page.mouse.wheel(0, position && position.y < 65 ? -350 : 350);
          await page.waitForTimeout(120);
        }
        throw new Error(`Cannot find ${text}`);
      }
      async function shot(name) {
        const prefix = `${width}-${name}`;
        await page.screenshot({ path: path.join(out, prefix + '.png') });
        fs.writeFileSync(path.join(out, prefix + '.txt'), await page.locator('body').ariaSnapshot());
        report.screenshots.push(prefix);
      }
      async function openResult() {
        await page.goto(web + '/#/history', { waitUntil: 'networkidle' });
        await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
        await page.waitForTimeout(400);
        await (await seek(`${fixture.title} Keywords:`, 'button')).click();
        await page.waitForTimeout(600);
      }
      const original = await (await fetch(`${fixtureApi}/contents/${fixture.content_id}`)).json();
      const before = await (await fetch(planUrl)).json();
      await openResult();
      await shot('summary');
      const checkbox = await seek('เลือกนำไปปรับ', 'checkbox');
      if (!await checkbox.isChecked()) await checkbox.click();
      await (await seek('คัดลอกประโยคตัวอย่าง', 'button')).click();
      await page.waitForTimeout(300);
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), fixture.recommendation.actionable_recommendations.items[0].example);
      const notes = `TEST FIXTURE ${width} revision ${before.revision + 1}: ถ่ายฉากชาร์จและบันทึกเวลาจริง`;
      const input = await seek('รายละเอียดแผนปรับคลิป', 'textbox');
      await input.click();
      await page.waitForTimeout(200);
      await page.keyboard.press('ControlOrMeta+A');
      await page.keyboard.insertText(notes);
      await page.waitForTimeout(200);
      await (await seek('บันทึกแผนปรับคลิป', 'button')).click();
      await page.waitForTimeout(500);
      await seek('ยังยืนยันการบันทึกไม่ได้');
      await input.click();
      await page.waitForTimeout(200);
      assert.ok((await page.locator('input, textarea').evaluateAll(nodes => nodes.map(node => node.value))).includes(notes));
      assert.deepEqual(await (await fetch(planUrl)).json(), before);
      await shot('save-failed-draft-retained');
      await (await seek('บันทึกแผนปรับคลิป', 'button')).click();
      await page.waitForTimeout(500);
      const after = await (await fetch(planUrl)).json();
      assert.equal(after.notes, notes);
      assert.equal(after.status, 'planning');
      assert.equal(after.revision, before.revision + 1);
      assert.equal(after.selected_advice_ids.length, 1);
      await shot('saved');
      await openResult();
      const restoredCheckbox = await seek('เลือกนำไปปรับ', 'checkbox');
      assert.equal(await restoredCheckbox.isChecked(), true);
      const restoredInput = await seek('รายละเอียดแผนปรับคลิป', 'textbox');
      await restoredInput.click();
      await page.waitForTimeout(200);
      // Flutter only attaches the native editing value when its canvas field receives focus.
      const editingValues = await page.locator('input, textarea').evaluateAll(nodes => nodes.map(node => node.value));
      assert.ok(editingValues.includes(notes), 'Saved note must be restored into the real text editor');
      assert.deepEqual(await (await fetch(`${fixtureApi}/contents/${fixture.content_id}`)).json(), original);
      await shot('reopened');
      report.cases.push({ width, revision: after.revision, restored: true, clipboard: true, failed_save_preserved_draft: true });
      await context.close();
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    if (page && !page.isClosed()) {
      await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {});
      fs.writeFileSync(path.join(out, 'failure.txt'), await page.locator('body').ariaSnapshot().catch(() => ''));
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    await fetch(api + '/auth/logout', { method: 'POST', headers }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
