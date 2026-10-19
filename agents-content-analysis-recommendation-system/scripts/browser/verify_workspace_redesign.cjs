// Read-only real-data UI checks. Upload job responses are explicitly isolated test fixtures.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.argv[2] || 'artifacts/workspace-redesign/browser');
const api = 'http://127.0.0.1:8011';
const web = 'http://127.0.0.1:8081';
const workflowOnly = process.argv.includes('--workflow-only');
fs.mkdirSync(output, { recursive: true });
const report = { checks: [], errors: [], networkWarnings: [], thumbnailResponses: [], real_asr: false,
  scope: workflowOnly ? 'upload workflow only' : 'full responsive matrix and upload workflow',
  mode: 'real saved data; temporary authenticated session; isolated upload fixtures' };
let browser, context, auth, page;
let navigationId = 0;
const save = () => fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(report, null, 2));
async function semantics() {
  await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
}
async function waitForAccessibleText(value) {
  for (let i = 0; i < 150; i++) {
    if ((await page.locator('body').ariaSnapshot()).includes(value)) return;
    await page.waitForTimeout(200);
  }
  throw new Error('Accessible text did not appear: ' + value);
}
async function open(route) {
  // A new document prevents prior hash-route state from bypassing test interception.
  await page.goto(web + '/?ui_check=' + (++navigationId) + '#' + route, { waitUntil: 'networkidle', timeout: 90000 });
  await semantics();
  await page.waitForTimeout(700);
  if (route === '/history') {
    const refresh = page.getByRole('button', { name: 'โหลดประวัติล่าสุด', exact: true });
    await refresh.waitFor();
    for (let i = 0; i < 120 && !await refresh.isEnabled(); i++) await page.waitForTimeout(250);
    assert.ok(await refresh.isEnabled(), 'History is still loading after 30 seconds');
    await page.waitForTimeout(250);
  }
}
async function seek(locator) {
  for (let i = 0; i < 35; i++) {
    const box = await locator.boundingBox().catch(() => null);
    const viewport = page.viewportSize();
    if (box && box.y >= 65 && box.y + box.height < viewport.height - 20) return locator;
    await page.mouse.move(viewport.width - 30, viewport.height - 150);
    await page.mouse.wheel(0, box ? box.y - 200 : 450);
    await page.waitForTimeout(100);
  }
  throw new Error('Cannot reach UI control: ' + locator.toString());
}
async function shot(name) {
  await page.screenshot({ path: path.join(output, name + '.png') });
  fs.writeFileSync(path.join(output, name + '.txt'), await page.locator('body').ariaSnapshot());
}
async function dark(width) {
  if (width < 1180) await page.getByRole('button', { name: 'Open navigation menu' }).click();
  const toggle = page.getByText('โหมดมืด', { exact: true });
  if (await toggle.count()) await toggle.click();
  await page.getByText('โหมดสว่าง', { exact: true }).waitFor();
  if (width < 1180) {
    await page.keyboard.press('Escape');
  }
  await page.waitForTimeout(250);
}
async function section(label) {
  const target = page.getByRole('tab', { name: label, exact: true });
  for (let attempt = 0; attempt < 8; attempt++) {
    if (await target.count()) {
      const box = await target.boundingBox();
      if (box && box.x >= 0 && box.x + box.width <= page.viewportSize().width) break;
    }
    for (const anchorLabel of ['ภาพรวม', 'คำแนะนำ', 'ข้อความถอดเสียง', 'หลักฐานอ้างอิง']) {
      const anchor = page.getByRole('tab', { name: anchorLabel, exact: true });
      if (!await anchor.count()) continue;
      const box = await (await seek(anchor)).boundingBox();
      if (!box || box.x < 0 || box.x >= page.viewportSize().width) continue;
      await page.mouse.move(Math.min(box.x + 20, page.viewportSize().width - 20), box.y + box.height / 2);
      await page.mouse.wheel(label === 'ภาพรวม' ? -350 : 350, 0);
      await page.waitForTimeout(150);
      break;
    }
  }
  await (await seek(target)).click();
  await page.waitForTimeout(250);
  const box = await target.boundingBox();
  if (box && box.y > 200) {
    const viewport = page.viewportSize();
    await page.mouse.move(viewport.width - 30, viewport.height - 100);
    await page.mouse.wheel(0, box.y - 100);
    await page.waitForTimeout(250);
  }
}
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ timezoneId: 'Asia/Bangkok', serviceWorkers: 'block' });
    assert.equal((await context.request.get(api + '/health')).status(), 200);
    auth = JSON.parse(execFileSync('py', ['-X', 'utf8', '-c', `
import json
from datetime import timedelta
from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import UserContent
from app.services.trend_watch_sessions import start_trend_watch_session
with SessionLocal() as db:
    content = db.get(UserContent, 41)
    user = content.owner
    assert user.is_active
    watch = start_trend_watch_session(db, user=user, region='TH')
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=60), session_key=watch.session_key)
    print(json.dumps({'token':token,'session':watch.session_key,'user':{'user_id':user.user_id,'username':user.username,'email':user.email,'role':user.role}}))
`], { cwd: root, env: { ...process.env, CONTENT_AI_SKIP_DB_BOOTSTRAP: '1' }, encoding: 'utf8', windowsHide: true }));
    const headers = { Authorization: 'Bearer ' + auth.token, 'X-Trend-Session-Key': auth.session };
    const contentUrl = api + '/contents/41';
    const beforeResponse = await context.request.get(contentUrl, { headers });
    assert.equal(beforeResponse.status(), 200);
    const before = await beforeResponse.json();
    const historyBefore = await (await context.request.get(api + '/contents/my?limit=50&offset=0', { headers })).json();
    await context.addInitScript(auth => {
      localStorage.setItem('flutter.access_token', JSON.stringify(auth.token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(auth.session));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(auth.user)));
    }, auth);
    for (const width of workflowOnly ? [] : [390, 768, 1280, 1600]) {
      for (const mode of ['light', 'dark']) {
        page = await context.newPage();
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
        page.on('pageerror', error => report.errors.push(error.message));
        page.on('console', message => {
          if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
        });
        page.on('response', response => {
          if (/ytimg|youtube.*thumbnail/.test(response.url())) {
            report.thumbnailResponses.push({ status: response.status(), url: response.url() });
          }
          if (response.status() >= 400 && response.url().startsWith(api)) {
            report.networkWarnings.push(response.status() + ' ' + new URL(response.url()).pathname);
          }
        });
        for (const route of ['/upload', '/dashboard', '/history', ...(auth.user.role === 'admin' ? ['/admin-analysis-settings'] : [])]) {
          await open(route);
          if (mode === 'dark') await dark(width);
          const aria = await page.locator('body').ariaSnapshot();
          assert.ok(!aria.includes('เข้าสู่ระบบเพื่อดำเนินการต่อ'), 'Authenticated route unexpectedly redirects');
          if (route === '/upload') {
            assert.ok(aria.includes('เลือกไฟล์วิดีโอ'));
            assert.ok(aria.includes('วิเคราะห์คลิปของคุณ'));
          }
          await shot(route.slice(1) + '-' + width + '-' + mode);
          report.checks.push({ route, width, mode });
          save();
        }
        // Keep actual records; isolate the audited ID only for the result-navigation check.
        await page.route(api + '/contents/my?*', async route => {
          const response = await route.fetch();
          const history = await response.json();
          const items = history.items.filter(item => Number(item.content_id) === 41);
          assert.equal(items.length, 1);
          await route.fulfill({ response, json: { ...history, total: 1, items } });
        });
        await open('/history');
        if (mode === 'dark') await dark(width);
        const savedCard = await seek(page.getByRole('button', { name: /review camera/ }).first());
        const [resultResponse] = await Promise.all([
          page.waitForResponse(r => r.url() === contentUrl),
          savedCard.click(),
        ]);
        assert.equal(resultResponse.status(), 200);
        await page.waitForTimeout(800);
        assert.ok((await page.locator('body').ariaSnapshot()).includes('ผลวิเคราะห์บันทึกแล้ว · #41'));
        await shot('result-overview-' + width + '-' + mode);
        for (const label of ['คำแนะนำ', 'ข้อความถอดเสียง', 'หลักฐานอ้างอิง']) {
          await section(label);
          await shot('result-' + ({'คำแนะนำ':'advice','ข้อความถอดเสียง':'transcript','หลักฐานอ้างอิง':'evidence'})[label] + '-' + width + '-' + mode);
        }
        report.checks.push({ route: '/result', width, mode, saved_content: 41, tabs: true,
          test_history_filtered_to_id: true });
        save();
        await page.close();
      }
    }
    page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => {
      if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
    });
    await page.setViewportSize({ width: 1280, height: 1000 });
    let submissions = 0;
    let polls = 0;
    const stages = ['queued', 'transcribing', 'classifying', 'recommending', 'saving', 'completed'];
    await page.route(api + '/analyze/save', async route => {
      const body = route.request().postDataBuffer().toString();
      assert.ok(body.includes('filename='));
      assert.ok(!body.includes('name="reference_age_context"'));
      assert.ok(!body.includes('name="confirmed_format"'));
      submissions++;
      polls = 0;
      await route.fulfill({ json: { job_id: 'workspace-fixture' } });
    });
    await page.route(api + '/jobs/workspace-fixture', async route => {
      if (submissions === 1) return route.fulfill({ json: { status: 'failed', stage: 'transcribing', error: 'Browser test: retry required' } });
      const stage = stages[Math.min(polls++, stages.length - 1)];
      await route.fulfill({ json: { status: stage === 'completed' ? 'completed' : 'running', stage, message: stage,
        ...(stage === 'completed' ? { result: before } : {}) } });
    });
    await open('/upload');
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'เลือกไฟล์วิดีโอ', exact: true }).click();
    await (await chooser).setFiles(path.join(root, 'artifacts/browser/revision-comparison/revision-fixture.mp4'));
    await waitForAccessibleText('ตรวจความยาวแล้ว');
    await shot('upload-real-file-selected');
    await page.getByRole('button', { name: 'เริ่มวิเคราะห์', exact: true }).click();
    await waitForAccessibleText('Browser test: retry required');
    await shot('upload-fixture-error');
    await (await seek(page.getByRole('button', { name: 'ลองอีกครั้ง', exact: true }))).click();
    await waitForAccessibleText('กำลังถอดเสียงทั้งคลิปเป็นข้อความ...');
    await shot('upload-fixture-progress');
    await page.waitForURL(/#\/result$/, { timeout: 60000 });
    assert.equal(submissions, 2);
    report.checks.push({ workflow: 'file picker, real browser metadata, isolated job failure/retry/poll/completion', real_asr: false });
    assert.deepEqual(await (await context.request.get(contentUrl, { headers })).json(), before);
    assert.deepEqual(await (await context.request.get(api + '/contents/my?limit=50&offset=0', { headers })).json(), historyBefore);
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
        }});
        report.temporary_session_ended = response.ok();
      } catch (error) {
        report.temporary_session_ended = false;
        report.errors.push('Temporary session cleanup failed: ' + error.message);
        report.passed = false;
        process.exitCode = 1;
      }
    }
    save();
    if (browser) await browser.close();
  }
})();
