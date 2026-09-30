// Read-only verification of real public data and the web dashboard. No provider API calls.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8001';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8081';
const out = path.resolve(__dirname, '../../artifacts/browser/dashboard-phase5');
fs.mkdirSync(out, { recursive: true });

async function seekButton(page, name) {
  const target = page.getByRole('button', { name, exact: true });
  for (let i = 0; i < 35; i++) {
    const box = await target.boundingBox({ timeout: 300 }).catch(() => null);
    if (box && box.y > 60 && box.y + box.height < page.viewportSize().height - 30) return target;
    await page.mouse.move(page.viewportSize().width - 80, 500);
    await page.mouse.wheel(0, box && box.y < 60 ? -500 : 500);
    await page.waitForTimeout(150);
  }
  throw new Error(`Control is not reachable: ${name}`);
}

(async () => {
  const report = { at: new Date().toISOString(), api: [], screenshots: [], errors: [], requests: [] };
  let browser;
  let page;
  try {
    async function audit(query) {
      const started = performance.now();
      const response = await fetch(`${api}/dashboard/public/history?${query}`);
      assert.equal(response.status, 200);
      const raw = await response.text();
      const data = JSON.parse(raw);
      assert.equal(data.method_version, 'observed-scope-history-v2');
      let verified = 0;
      for (const p of data.points) {
        if (data.platform === 'youtube' && data.ranking_scope === 'global') {
          assert.equal(Object.values(p.category_counts).reduce((a, b) => a + b, 0), p.total);
        } else assert.deepEqual(p.category_counts, {});
        if (data.platform === 'google') {
          assert.deepEqual(p.views, {});
          assert.deepEqual(p.view_intervals, {});
        }
        assert.ok(Object.keys(p.view_intervals).length <= 1);
        for (const v of Object.values(p.view_intervals)) {
          if (v.status === 'measured') {
            assert.equal(p.break_before, false);
            assert.equal(v.delta, v.to_views - v.from_views);
            assert.ok(Math.abs(v.per_hour - v.delta * 3600 / v.elapsed_seconds) < 0.011);
            assert.ok(Math.abs(v.elapsed_seconds - (Date.parse(v.to_at) - Date.parse(v.from_at)) / 1000) < 0.002);
            assert.ok(v.from_run_id && v.to_run_id);
            verified++;
          } else {
            assert.equal(v.delta, null);
            assert.equal(v.per_hour, null);
          }
        }
      }
      report.api.push({ query, points: data.points.length, verified_intervals: verified,
        response_bytes: Buffer.byteLength(raw), elapsed_ms: Math.round(performance.now() - started), coverage: data.coverage });
      return data;
    }
    const youtube = await audit('platform=youtube&days=7');
    await audit('platform=youtube&days=90');
    await audit('platform=youtube&days=7&video_category_id=20');
    await audit('platform=google&days=7');
    if (youtube.items.length > 1) {
      const selected = youtube.items[1].key;
      const specific = await audit(`platform=youtube&days=7&item_key=${selected}`);
      assert.equal(specific.selected_key, selected);
    }
    assert.ok(report.api.some(row => row.verified_intervals > 0), 'No real comparable view intervals to verify');
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', msg => {
      if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(msg.text())) report.errors.push(msg.text());
    });
    page.on('response', response => {
      if (response.url().includes('/dashboard/public/history')) report.requests.push({ url: response.url(), status: response.status() });
    });
    async function shot(name) {
      await page.screenshot({ path: path.join(out, `${name}.png`) });
      fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
      report.screenshots.push(name);
    }
    async function top() {
      await page.mouse.move(page.viewportSize().width - 80, 400);
      await page.mouse.wheel(0, -20000);
      await page.waitForTimeout(400);
    }
    await page.goto(web, { waitUntil: 'networkidle' });
    await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
    await page.waitForTimeout(1500);
    await (await seekButton(page, '7 วัน')).click();
    await page.waitForTimeout(1200);
    await shot('desktop-overview');
    await page.mouse.wheel(0, 470);
    await page.waitForTimeout(400);
    await shot('desktop-rank-growth');
    await (await seekButton(page, 'ดูตารางข้อมูลกราฟ')).click();
    await page.waitForTimeout(400);
    assert.ok((await page.locator('body').ariaSnapshot()).includes('ยอดเพิ่มจริง'));
    await shot('evidence-table');
    await page.getByRole('button', { name: 'ปิด', exact: true }).click();
    await top();
    await (await seekButton(page, 'ดูความครอบคลุมรายชั่วโมง')).click();
    await page.waitForTimeout(300);
    await shot('coverage');
    await page.getByRole('button', { name: 'ปิด', exact: true }).click();
    await top();
    await page.getByRole('tab', { name: 'Google', exact: true }).click();
    await page.waitForTimeout(1000);
    let semantics = await page.locator('body').ariaSnapshot();
    assert.ok(semantics.includes('ลำดับจาก Google Trends'));
    assert.ok(!semantics.includes('ยอดวิวกำลังเพิ่มเร็วแค่ไหน'));
    assert.ok(!semantics.includes('หมวดไหนติดอันดับรวมมากขึ้น'));
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(300);
    await shot('google');
    await top();
    await page.getByRole('tab', { name: 'YouTube', exact: true }).click();
    await page.waitForTimeout(800);
    const selector = page.getByRole('button', { name: 'เลือกแพลตฟอร์ม หมวดหมู่ ทั้งหมด', exact: true });
    const box = await selector.boundingBox();
    await selector.click({ position: { x: 200, y: box.height - 22 } });
    const categoryLoaded = page.waitForResponse(response =>
      response.url().includes('/dashboard/public/history?') && response.url().includes('video_category_id=20'));
    await page.getByRole('menuitem', { name: /เกม \(/ }).click();
    assert.equal((await (await categoryLoaded).json()).ranking_scope, 'category:20');
    await page.waitForTimeout(1000);
    semantics = await page.locator('body').ariaSnapshot();
    assert.ok(semantics.includes('เลือกแพลตฟอร์ม หมวดหมู่ เกม'));
    assert.ok(!semantics.includes('หมวดไหนติดอันดับรวมมากขึ้น'));
    await page.mouse.wheel(0, 350);
    await page.waitForTimeout(300);
    await shot('category-rank-growth');
    await page.setViewportSize({ width: 900, height: 1050 });
    await top();
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
    await page.waitForTimeout(1000);
    await page.mouse.wheel(0, 500);
    await page.waitForTimeout(300);
    await shot('compact-rank-growth');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(report.errors, []);
    assert.ok(report.requests.every(row => row.status === 200));
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
