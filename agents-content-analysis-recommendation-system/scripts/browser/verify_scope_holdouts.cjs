// Real local API and DB, temporary admin session. Never train or force activation.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const out = path.resolve(process.argv[2] || 'artifacts/scope-holdout-20261004/browser');
const report = { evidence: 'real API and persisted DB; minted temporary admin session, not a login-form test', checks: [], errors: [] };
if (fs.existsSync(path.join(out, 'verification.json'))) throw new Error('Use a new output directory');
fs.mkdirSync(out, { recursive: true });
let browser, context, page, auth;

(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ serviceWorkers: 'block' });
    auth = JSON.parse(execFileSync('python', ['-X', 'utf8', '-c', `
import json
from datetime import timedelta
from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import User
from app.services.trend_watch_sessions import start_trend_watch_session
with SessionLocal() as db:
    user = db.query(User).filter_by(role='admin', is_active=True).order_by(User.user_id).first()
    assert user is not None
    watch = start_trend_watch_session(db, user=user, region='TH')
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=20), session_key=watch.session_key)
    print(json.dumps({'token':token,'session':watch.session_key,'user':{'user_id':user.user_id,'username':user.username,'email':user.email,'role':user.role}}))
`], { encoding: 'utf8', windowsHide: true }));
    const headers = { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session };
    async function get(route) {
      const response = await context.request.get(`http://127.0.0.1:8000${route}`, { headers });
      assert.equal(response.status(), 200, route);
      return response.json();
    }
    const overview = await get('/admin/training');
    const queue = await get('/admin/dataset-review/queue');
    const unknown = queue.taxonomy.find(r => r.leaf_key === 'unknown');
    assert.deepEqual(unknown.split_counts, { train: 2, validation: 10, test: 30 });
    assert.equal(unknown.ready, true);
    assert.equal(overview.dataset.partition_integrity_passed, true);
    assert.equal(overview.dataset.dataset_fingerprint, 'f247c04ce87138d297e7a6e46bfe7e363b8b33e87bc71c8d3cf3db6597d80975');
    report.coverage = unknown;
    report.dataset = overview.dataset;
    report.active_before = overview.active_model.model_id;
    const run = await get('/admin/training/runs/5a2fcb84-5155-4203-b871-e344ebf74633');
    assert.equal(run.status, 'completed');
    assert.equal(run.result.best_model.qualified, false);
    report.run = run;
    const blocked = await context.request.post(`http://127.0.0.1:8000/admin/training/models/${run.result.best_model.model_id}/activate`, {
      headers, data: { expected_active_model_id: report.active_before },
    });
    assert.equal(blocked.status(), 422, 'Unqualified model must not activate');
    report.activation_block = { status: blocked.status(), response: await blocked.json() };
    report.active_after = (await get('/admin/training')).active_model.model_id;
    assert.equal(report.active_after, report.active_before);
    report.checks.push({ check: 'real API, persisted split after startup, rejected activation', passed: true });

    await context.addInitScript(auth => {
      localStorage.setItem('flutter.access_token', JSON.stringify(auth.token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(auth.session));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(auth.user)));
    }, auth);
    page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    page.on('console', m => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text()); });
    page.on('response', r => { if (r.status() >= 400 && r.url().includes('127.0.0.1:8000')) report.errors.push(`${r.status()} ${new URL(r.url()).pathname}`); });
    for (const width of [1440, 1000]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto('http://127.0.0.1:8080/#/admin-dataset-review', { waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
      await page.waitForTimeout(500);
      const reviewAria = await page.locator('body').ariaSnapshot();
      fs.writeFileSync(path.join(out, `review-${width}.txt`), reviewAria);
      for (const label of ['นอกขอบเขต 42 คลิป', 'ปรับเกณฑ์ 10/10', 'ทดสอบ 30/30', 'สำรอง 2 คลิป']) {
        assert.ok(reviewAria.includes(label), `Missing chip label: ${label}`);
      }
      await page.screenshot({ path: path.join(out, `review-${width}.png`) });
      fs.writeFileSync(path.join(out, `review-${width}.txt`), await page.locator('body').ariaSnapshot());
      report.checks.push({ screen: 'admin-dataset-review', width, passed: true });
      await page.goto('http://127.0.0.1:8080/#/admin-training', { waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
      await page.getByText('ยังไม่พร้อมให้คำแนะนำเฉพาะหมวด', { exact: false }).first().waitFor();
      await page.screenshot({ path: path.join(out, `training-${width}.png`) });
      fs.writeFileSync(path.join(out, `training-${width}.txt`), await page.locator('body').ariaSnapshot());
      report.checks.push({ screen: 'admin-training', width, passed: true });
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.failure = error.message;
    if (page) {
      await page.screenshot({ path: path.join(out, 'failure.png') });
      fs.writeFileSync(path.join(out, 'failure.txt'), await page.locator('body').ariaSnapshot());
    }
    throw error;
  } finally {
    if (auth && context) {
      const response = await context.request.post('http://127.0.0.1:8000/auth/logout', {
        headers: { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session }, data: {},
      });
      report.temporary_session_ended = response.status() === 200;
    }
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    if (browser) await browser.close();
  }
  console.log(JSON.stringify({ passed: report.passed, checks: report.checks.length, output: out }));
})().catch(error => { console.error(error.message); process.exitCode = 1; });
