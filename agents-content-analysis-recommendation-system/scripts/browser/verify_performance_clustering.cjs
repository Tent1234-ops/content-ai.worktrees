// Actual saved content and live API only; no fabricated classification/KPI response.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.argv[2] || 'artifacts/performance-clustering/20261019/browser');
const api = 'http://127.0.0.1:8011';
const web = 'http://127.0.0.1:8082';
fs.mkdirSync(output, { recursive: true });
const report = { checks: [], errors: [], mode: 'real saved content 41 and current references', mock_kpis: false };
let browser, context, page, auth, navigation = 0;
const save = () => fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(report, null, 2));
async function aria() { return page.locator('body').ariaSnapshot(); }
async function text(value) {
  for (let i = 0; i < 150; i++) {
    if ((await aria()).includes(value)) return;
    await page.waitForTimeout(200);
  }
  throw Error('Missing accessible text: ' + value);
}
async function seek(locator) {
  for (let i = 0; i < 45; i++) {
    // Flutter only exposes semantics for the visible viewport. Do not wait for an
    // offscreen element before scrolling it into the accessibility tree.
    const box = await locator.count() ? await locator.boundingBox({ timeout: 1000 }).catch(() => null) : null;
    const vp = page.viewportSize();
    if (box && box.y >= 65 && box.y + box.height < vp.height - 15) return locator;
    await page.mouse.move(vp.width - 30, vp.height - 120);
    await page.mouse.wheel(0, box ? box.y - 120 : 400);
    await page.waitForTimeout(100);
  }
  throw Error('Cannot reach ' + locator);
}
async function shot(name) {
  await page.screenshot({ path: path.join(output, name + '.png') });
  fs.writeFileSync(path.join(output, name + '.txt'), await aria());
}
async function tab(label) {
  const target = page.getByRole('tab', { name: label, exact: true });
  for (let i = 0; i < 8; i++) {
    const box = await target.boundingBox();
    if (box && box.x >= 0 && box.x + box.width <= page.viewportSize().width) break;
    const anchor = page.getByRole('tab', { name: 'ข้อความถอดเสียง', exact: true });
    const b = await (await seek(anchor)).boundingBox();
    await page.mouse.move(Math.min(b.x + 10, page.viewportSize().width - 30), b.y + b.height / 2);
    await page.mouse.wheel(350, 0);
    await page.waitForTimeout(200);
  }
  await (await seek(target)).click();
}
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ timezoneId: 'Asia/Bangkok', serviceWorkers: 'block' });
    auth = JSON.parse(execFileSync('py', ['-X', 'utf8', '-c', `
import json
from datetime import timedelta
from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import UserContent
from app.services.trend_watch_sessions import start_trend_watch_session
with SessionLocal() as db:
    user = db.get(UserContent, 41).owner
    assert user.is_active
    watch = start_trend_watch_session(db, user=user, region='TH')
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=60), session_key=watch.session_key)
    print(json.dumps({'token':token, 'session':watch.session_key, 'user':{'user_id':user.user_id,'username':user.username,'email':user.email,'role':user.role}}))
`], { cwd: root, encoding: 'utf8', windowsHide: true, env: { ...process.env, CONTENT_AI_SKIP_DB_BOOTSTRAP: '1' } }));
    const headers = { Authorization: 'Bearer ' + auth.token, 'X-Trend-Session-Key': auth.session };
    const contentUrl = api + '/contents/41';
    const endpoint = contentUrl + '/performance-clustering';
    const before = await (await context.request.get(contentUrl, { headers })).json();
    assert.equal((await context.request.get(endpoint)).status(), 401);
    assert.equal((await context.request.get(endpoint + '?minimum_views=-1', { headers })).status(), 422);
    const live = await context.request.get(endpoint, { headers });
    assert.equal(live.status(), 200);
    const actual = await live.json();
    assert.equal(actual.clustering.status, 'ready');
    fs.writeFileSync(path.join(output, 'actual-api.json'), JSON.stringify(actual, null, 2));
    await context.addInitScript(auth => {
      localStorage.setItem('flutter.access_token', JSON.stringify(auth.token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(auth.session));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(auth.user)));
      localStorage.removeItem('flutter.theme_mode');
    }, auth);
    for (const width of process.argv.includes('--quick') ? [390] : [390, 768, 1280, 1600]) {
      for (const mode of process.argv.includes('--quick') ? ['light'] : ['light', 'dark']) {
        page = await context.newPage();
        page.setDefaultTimeout(5000);
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
        page.on('pageerror', error => report.errors.push(error.message));
        page.on('console', message => {
          if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
        });
        await page.route(api + '/contents/my?*', async route => {
          const response = await route.fetch();
          const history = await response.json();
          const items = history.items.filter(item => Number(item.content_id) === 41);
          assert.equal(items.length, 1);
          await route.fulfill({ response, json: { ...history, total: 1, items } });
        });
        await page.goto(web + '/?check=' + (++navigation) + '#/history', { waitUntil: 'networkidle', timeout: 90000 });
        await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
        await text('review camera');
        if (mode === 'dark') {
          if (width < 1180) await page.getByRole('button', { name: 'Open navigation menu' }).click();
          const dark = page.getByText('โหมดมืด', { exact: true });
          if (await dark.count()) await dark.click();
          await page.getByText('โหมดสว่าง', { exact: true }).waitFor();
          if (width < 1180) await page.keyboard.press('Escape');
        }
        let calls = 0;
        page.on('request', request => { if (request.url().startsWith(endpoint)) calls++; });
        await (await seek(page.getByRole('button', { name: /review camera/ }).first())).click();
        await text('ผลวิเคราะห์บันทึกแล้ว · #41');
        assert.equal(calls, 0, 'Performance data should load only on the evidence tab');
        const responseReady = page.waitForResponse(r => r.url() === endpoint, { timeout: 45000 });
        await tab('หลักฐานอ้างอิง');
        const uiData = await (await responseReady).json();
        await text('วิเคราะห์กลุ่มผลงาน');
        assert.equal(calls, 1);
        await shot(`summary-${width}-${mode}`);
        const chart = page.getByRole('img', { name: /^กราฟกระจายยอดวิวและไลก์/ });
        await seek(chart);
        await shot(`scatter-${width}-${mode}`);
        await chart.screenshot({ path: path.join(output, `chart-${width}-${mode}.png`) });
        const bounds = await chart.boundingBox();
        const maxViews = Math.max(...uiData.reference_videos.map(v => v.views)) * 1.12;
        const maxLikes = Math.max(...uiData.reference_videos.map(v => v.likes)) * 1.12;
        const point = uiData.reference_videos.reduce((a, b) => a.likes > b.likes ? a : b);
        // Axis reservations match the chart; hover the isolated topmost real point.
        await page.mouse.move(bounds.x + 66 + (bounds.width - 66) * point.views / maxViews,
          bounds.y + (bounds.height - 54) * (1 - point.likes / maxLikes));
        await page.waitForTimeout(350);
        await chart.screenshot({ path: path.join(output, `chart-hover-${width}-${mode}.png`) });
        await page.mouse.move(width - 10, 30);
        const similarity = page.getByText('เนื้อหาคลิปของคุณใกล้เคียงกลุ่มไหน?', { exact: false });
        await seek(similarity);
        const snapshot = await aria();
        for (const level of ['low', 'high']) {
          const expected = (uiData.content_similarity[level + '_score'] * 100).toFixed(2) + '%';
          assert.ok(snapshot.includes(expected), 'UI similarity does not match API: ' + expected);
        }
        assert.ok(snapshot.includes('คะแนนนี้วัดความคล้ายของเนื้อหา ไม่ใช่การคาดการณ์ยอดวิวหรือยอดไลก์'));
        await shot(`similarity-${width}-${mode}`);
        for (const level of ['High', 'Low', 'All']) {
          const choice = page.getByRole('radio', { name: level, exact: true })
            .or(page.getByRole('checkbox', { name: level, exact: true }));
          await (await seek(choice)).click();
          await page.waitForTimeout(250);
          const count = level === 'All' ? uiData.eligible_count : uiData.clustering.clusters.find(c => c.performance_level === level.toLowerCase()).video_count;
          assert.ok((await aria()).includes(count + ' คลิป'));
          await shot(`filter-${level}-${width}-${mode}`);
        }
        const original = page.getByText(/คลิปต้นแบบประกอบคำแนะนำ|หลักฐานที่เปิดดูได้/).first();
        await seek(original);
        assert.ok((await aria()).includes('หลักฐานที่เปิดดูได้'), 'Original reference evidence missing');
        // Changing the threshold runs the actual endpoint again; no fixture response.
        if (width === 1280 && mode === 'light') {
          await page.mouse.move(width - 30, 700);
          await page.mouse.wheel(0, -50000);
          await page.waitForTimeout(400);
          const field = page.getByRole('textbox', { name: /ยอดวิวขั้นต่ำ/ });
          await (await seek(field)).fill('9000000000000');
          const changed = page.waitForResponse(r => r.url().includes('minimum_views=9000000000000'), { timeout: 45000 });
          await page.getByRole('button', { name: 'คำนวณตามยอดวิวขั้นต่ำ', exact: true }).click();
          assert.equal((await (await changed).json()).eligible_count, 0);
          await text('ต้องมีอย่างน้อย 6 คลิป');
          await shot('insufficient-references');
          await (await seek(field)).fill('25000');
          const restored = page.waitForResponse(r => r.url().includes('minimum_views=25000'), { timeout: 45000 });
          await page.getByRole('button', { name: 'คำนวณตามยอดวิวขั้นต่ำ', exact: true }).click();
          assert.equal((await (await restored).json()).clustering.status, 'ready');
          await seek(page.getByText('เนื้อหาคลิปของคุณใกล้เคียงกลุ่มไหน?', { exact: false }));
          await shot('restored-threshold');
          report.threshold_empty_and_restored = true;
        }
        report.checks.push({ width, mode, api_matched: true, filters: true, chart: true, original_evidence_preserved: true });
        save();
        await page.close();
      }
    }
    assert.deepEqual(await (await context.request.get(contentUrl, { headers })).json(), before);
    report.saved_data_unchanged = true;
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.errors.push(error.stack || String(error));
    if (page && !page.isClosed()) await shot('failure').catch(() => {});
    process.exitCode = 1;
  } finally {
    if (context && auth) {
      try {
        const response = await context.request.post(api + '/auth/logout', { headers: {
          Authorization: 'Bearer ' + auth.token, 'X-Trend-Session-Key': auth.session,
        } });
        report.temporary_session_ended = response.ok();
        if (!response.ok()) throw Error('Temporary session cleanup failed');
      } catch (error) {
        report.errors.push(error.message);
        report.passed = false;
        process.exitCode = 1;
      }
    }
    save();
    if (browser) await browser.close();
  }
})();
