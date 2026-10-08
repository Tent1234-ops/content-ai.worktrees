// Real UI/API smoke check. Only --save-daily persists the requested schedule change.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const out = path.resolve(process.argv[2]);
if (fs.existsSync(path.join(out, 'verification.json'))) throw Error('Use a new evidence directory');
fs.mkdirSync(out, { recursive: true });
const report = { checks: [], errors: [], passed: false };
let browser, context, page, auth;
const save = (name, data) => fs.writeFileSync(path.join(out, name), JSON.stringify(data, null, 2));
const pass = text => { report.checks.push(text); save('verification.json', report); console.log(text); };
async function shot(name) {
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
}
async function open(route) {
  await page.goto('about:blank');
  await page.goto(`http://127.0.0.1:8080/#${route}`, { waitUntil: 'networkidle' });
  await page.locator('flt-semantics-placeholder').evaluateAll(ns => ns.forEach(n => n.click()));
  await page.waitForTimeout(1300);
}
async function seek(text, role) {
  for (let i = 0; i < 45; i++) {
    const target = role ? page.getByRole(role, {name: text, exact: false}) : page.getByText(text, {exact: false});
    for (const locator of await target.all()) {
      const box = await locator.boundingBox();
      if (box && box.y >= 60 && box.y + box.height <= page.viewportSize().height - 40) return locator;
    }
    await page.mouse.move(page.viewportSize().width * .7, 650);
    await page.mouse.wheel(0, 270);
    await page.waitForTimeout(160);
  }
  throw Error(`Not visible: ${text}`);
}
async function get(route) {
  const res = await context.request.get(`http://127.0.0.1:8000${route}`, {
    headers: auth ? {Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session} : {},
    timeout: 90000,
  });
  assert.equal(res.status(), 200, route);
  return res.json();
}
(async () => {
  try {
    browser = await chromium.launch({channel: 'msedge', headless: true});
    context = await browser.newContext({viewport: {width: 1440, height: 1000}, serviceWorkers: 'block'});
    page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    page.on('console', m => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text()); });
    const trends = await get('/dashboard/public/trends');
    save('public-trends.json', trends);
    for (const width of [1440, 1000, 390]) {
      await page.setViewportSize({width, height: 1000});
      await open('/dashboard');
      const selector = await seek(/^คลิป /, 'button');
      const selectorBox = await selector.boundingBox();
      await page.mouse.move(width * .7, 650);
      await page.mouse.wheel(0, selectorBox.y - (width < 620 ? 740 : 500));
      await page.waitForTimeout(400);
      await shot(`donut-${width}`);
      let text = await page.locator('body').ariaSnapshot();
      assert.ok(!text.includes('อันดับวิดีโอขยับขึ้นล่าสุด'));
      assert.ok(text.includes('คลิปในอันดับรวม YouTube (สูงสุด 50)'));
      await seek(/^คลิป /, 'button');
      await shot(`history-graph-${width}`);
      text = await page.locator('body').ariaSnapshot();
      assert.ok(text.includes('แนวโน้มย้อนหลัง'));
      for (const diagnostic of ['ช่วงชั่วโมง', 'เก็บไม่สำเร็จ', 'ตารางเก็บปัจจุบัน', 'ดูความครอบคลุมรายชั่วโมง', 'จุดข้อมูล']) {
        assert.ok(!text.includes(diagnostic), diagnostic);
      }
      pass(`Public donut and simplified history at ${width}px`);
    }
    auth = JSON.parse(execFileSync('python', ['-X', 'utf8', '-c', `
import json
from datetime import timedelta
from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import User
from app.services.trend_watch_sessions import start_trend_watch_session
with SessionLocal() as db:
    user = db.get(User, 2)
    assert user is not None and user.is_active and user.role == 'admin'
    watch = start_trend_watch_session(db, user=user, region='TH')
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=30), session_key=watch.session_key)
    print(json.dumps({'token': token, 'session': watch.session_key, 'user': {'user_id': user.user_id, 'username': user.username, 'email': user.email, 'role': user.role}}))
`], {encoding: 'utf8', windowsHide: true}));
    await context.addInitScript(auth => {
      if (location.origin !== 'http://127.0.0.1:8080') return;
      localStorage.setItem('flutter.access_token', JSON.stringify(auth.token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(auth.session));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(auth.user)));
    }, auth);
    const before = await get('/admin/trend-settings');
    save('schedule-before.json', before);
    const training = await get('/admin/training');
    save('training-overview.json', training);
    for (const width of [1440, 1000, 390]) {
      await page.setViewportSize({width, height: 1000});
      await open('/history');
      const text = await page.locator('body').ariaSnapshot();
      assert.ok(!text.includes('เรียงตาม'));
      assert.ok(text.includes('หมวดหมู่'));
      await shot(`ideas-${width}`);
      await open('/admin-datasets');
      const datasetText = await page.locator('body').ariaSnapshot();
      assert.ok(!datasetText.includes('คุณภาพและแผนเก็บข้อมูล'));
      await page.getByRole('button', {name: 'เครื่องมือ Dataset เพิ่มเติม'}).click();
      await page.waitForTimeout(350);
      assert.ok((await page.locator('body').ariaSnapshot()).includes('ถังขยะ'));
      await shot(`datasets-menu-${width}`);
      await page.getByRole('menuitem', {name: 'ถังขยะ', exact: true}).click();
      await page.waitForTimeout(600);
      await page.getByRole('button', {name: 'กลับรายการข้อมูล'}).click();
      await page.waitForTimeout(400);
      await shot(`datasets-${width}`);
      await open('/admin-analysis-settings');
      await page.getByRole('tab', {name: 'อัปเดตเทรนด์'}).click();
      await page.waitForTimeout(700);
      await seek('รอบแรก', 'button');
      await shot(`schedule-${width}`);
      assert.ok(!(await page.locator('body').ariaSnapshot()).includes('ตามช่วงเวลา'));
      if (width === 1440 && process.argv.includes('--save-daily')) {
        const button = await seek('บันทึกรอบอัปเดต', 'button');
        const saving = page.waitForResponse(r => r.url().endsWith('/admin/trend-settings') && r.request().method() === 'PUT');
        await button.click();
        assert.equal((await saving).status(), 200);
        await page.waitForTimeout(400);
        const after = await get('/admin/trend-settings');
        assert.equal(after.schedule_mode, 'hourly_window');
        assert.equal(after.enabled, before.enabled);
        assert.equal(after.window.start_hour, before.window.start_hour);
        assert.equal(after.window.end_hour, before.window.end_hour);
        save('schedule-after.json', after);
        report.daily_schedule_saved = true;
      }
      pass(`History, dataset secondary tools and daily schedule at ${width}px`);
    }
    const after = await get('/admin/trend-settings');
    if (process.argv.includes('--save-daily')) assert.equal(after.schedule_mode, 'hourly_window');
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.failure = String(error.message).replaceAll(auth?.token || '\0', '[redacted]');
    if (page) await shot('failure').catch(() => {});
    console.error(report.failure);
    process.exitCode = 1;
  } finally {
    if (auth) {
      try {
        const res = await context.request.post('http://127.0.0.1:8000/auth/logout', {
          headers: {Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session}, data: {},
        });
        assert.equal(res.status(), 200);
        report.temporary_session_ended = true;
      } catch (_) {
        execFileSync('python', ['-X', 'utf8', '-c', `
import sys
from app.database.db import SessionLocal
from app.database.models import UserTrendWatchSession
from app.services.trend_watch_sessions import end_trend_watch_session
with SessionLocal() as db:
    row = db.query(UserTrendWatchSession).filter_by(user_id=2, session_key=sys.stdin.read()).one()
    end_trend_watch_session(db, watch_session=row)
`], {input: auth.session, windowsHide: true, stdio: ['pipe', 'ignore', 'ignore']});
        report.temporary_session_ended = true;
      }
    }
    save('verification.json', report);
    if (browser) await browser.close();
  }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
