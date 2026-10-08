// Real web/API/Whisper check. Temporary admin session, no login-form claim.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.resolve(process.argv[2] || 'artifacts/laptop-scope-20261004/presentation-browser');
if (fs.existsSync(path.join(out, 'verification.json'))) throw new Error('Choose a new output directory');
fs.mkdirSync(out, { recursive: true });
const expectedModelId = Number(process.argv[5] || 43);
const savedContentId = /^content:\d+$/.test(process.argv[3] || '') ? Number(process.argv[3].split(':')[1]) : null;
const report = { checks: [], errors: [], real_asr: false, fresh_test: false, model_id: expectedModelId };
const resumeJobPath = process.argv[3] && process.argv[3] !== '-' && !savedContentId ? path.resolve(process.argv[3]) : null;
const cameraFile = process.argv[4] ? path.resolve(process.argv[4]) : null;
let browser, context, page, auth;
function safeMessage(error) {
  let message = String(error.message || error);
  for (const secret of [auth?.token, auth?.session]) {
    if (secret) message = message.split(secret).join('[redacted]');
  }
  return message;
}
function save(name, value) { fs.writeFileSync(path.join(out, name), JSON.stringify(value, null, 2)); }
function pass(name) { report.checks.push(name); save('verification.json', report); console.log(name); }
async function open(route) {
  await page.goto(`http://127.0.0.1:8080/#${route}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await page.locator('flt-semantics-placeholder').evaluateAll(ns => ns.forEach(n => n.click()));
  await page.waitForTimeout(500);
}
async function shot(name) {
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
}
async function seek(name, role = 'button') {
  for (let i = 0; i < 35; i++) {
    for (const locator of await page.getByRole(role, { name, exact: false }).all()) {
      const box = await locator.boundingBox();
      if (box && box.y > 65 && box.y + box.height / 2 < 950) return locator;
    }
    await page.mouse.move(850, 650);
    await page.mouse.wheel(0, 340);
    await page.waitForTimeout(180);
  }
  throw new Error(`Cannot reach ${role}: ${name}`);
}
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
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
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=60), session_key=watch.session_key)
    print(json.dumps({'token':token,'session':watch.session_key,'user':{'user_id':user.user_id,'username':user.username,'email':user.email,'role':user.role}}))
`], { encoding: 'utf8', windowsHide: true }));
    const headers = { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session };
    async function get(route) {
      const response = await context.request.get(`http://127.0.0.1:8000${route}`, { headers, timeout: 90000 });
      assert.equal(response.status(), 200, route);
      return response.json();
    }
    const overview = await get('/admin/training');
    assert.equal(overview.active_model.model_id, expectedModelId);
    assert.equal(overview.active_model.status, 'presentation_only');
    const expired = overview.active_model.readiness.reason_codes.includes('presentation_expired');
    assert.equal(overview.active_model.readiness.status, savedContentId && expired ? 'blocked' : 'presentation');
    report.current_model_expired = expired;
    assert.equal(overview.active_model.readiness.scope_policy_valid, false);
    assert.equal(overview.active_model.readiness.scope_validation_required, true);
    assert.equal(overview.active_model.can_activate, false);
    assert.equal(overview.policy.promotion_threshold, 0.8);
    save('active-model.json', overview.active_model);
    pass(`Registry model ${expectedModelId} is explicitly unqualified; normal gates remain enabled`);
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
      await open('/admin-training');
      const warning = expired ? 'สิทธิ์ใช้โมเดลสาธิตหมดอายุแล้ว' : 'เปิดใช้ชั่วคราวสำหรับสาธิต';
      await page.getByText(warning, { exact: false }).first().waitFor({ timeout: 90000 });
      const aria = await page.locator('body').ariaSnapshot();
      assert.ok(aria.includes(warning));
      await shot(`training-${width}`);
      pass(`Admin presentation warning at ${width}px`);
    }
    let result;
    if (savedContentId) {
      const stored = await get(`/contents/${savedContentId}`);
      result = {...stored, analysis_settings: stored.analysis.analysis_settings};
      report.readonly_saved_content_id = savedContentId;
      pass('Checking a persisted result only; no new upload, ASR, or classification claimed');
    } else if (resumeJobPath) {
      const previousJob = JSON.parse(fs.readFileSync(resumeJobPath, 'utf8'));
      assert.equal(previousJob.status, 'completed');
      assert.ok(previousJob.result.content_id > 0);
      result = previousJob.result;
      report.resumed_job_evidence = resumeJobPath;
      pass('Resuming saved-result checks; no new ASR run claimed');
    } else {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await open('/upload');
    const video = fs.readFileSync(cameraFile || path.join(root, 'videos/Review_Phone.mp4'));
    report.video_sha256 = crypto.createHash('sha256').update(video).digest('hex');
    const name = cameraFile ? 'camera-keywords-fixed-review_camera.mp4' : 'presentation-check-20261004-Review_Phone.mp4';
    const chooseButton = await seek('เลือกไฟล์วิดีโอ');
    const chooser = page.waitForEvent('filechooser');
    await chooseButton.click();
    await (await chooser).setFiles({ name, mimeType: 'video/mp4', buffer: video });
    await page.waitForTimeout(1200);
    await shot('upload-selected');
    const analyzeButton = await seek('เริ่มวิเคราะห์');
    const upload = page.waitForResponse(r => r.url().endsWith('/analyze/save') && r.request().method() === 'POST', { timeout: 90000 });
    await analyzeButton.click();
    const response = await upload;
    assert.equal(response.status(), 200, await response.text());
    report.job_id = (await response.json()).job_id;
    pass(`Uploaded actual ${cameraFile ? 'review_camera.mp4' : 'Review_Phone.mp4'} through the web`);
    const deadline = Date.now() + 15 * 60 * 1000;
    let job, stage;
    while (Date.now() < deadline) {
      job = await get(`/jobs/${report.job_id}`);
      save('analysis-job.json', job);
      if (job.stage !== stage) { stage = job.stage; console.log(`Analysis: ${stage}`); }
      if (job.status === 'failed') throw new Error(job.error || 'Analysis failed');
      if (job.status === 'completed') break;
      await page.waitForTimeout(4000);
    }
    assert.equal(job.status, 'completed');
    report.real_asr = true;
    result = job.result;
    await page.waitForTimeout(2500);
    await shot('result-1440');
    }
    report.content_id = result.content_id;
    const classification = result.recommendation.classification;
    assert.equal(classification.model_id, savedContentId ? result.analysis_settings.classification_model.model_id : expectedModelId);
    assert.equal(classification.domain, cameraFile ? 'camera' : 'phone');
    if (cameraFile) {
      const recommendation = result.recommendation;
      const missing = recommendation.missing_keywords.map(item => item.keyword);
      assert.ok(missing.includes('low light'));
      assert.ok(!missing.some(word => ['ผม', 'ดู', 'อ่ะ', 'ถ่าย', 'autofocus', 'video recording'].includes(word)));
      assert.ok(recommendation.comparable_keywords.includes('autofocus'));
      assert.ok(recommendation.comparable_keywords.includes('video recording'));
      assert.ok(recommendation.actionable_recommendations.items.some(item => item.template_key === 'low light'));
      assert.ok(!recommendation.actionable_recommendations.items.some(item => ['autofocus', 'video recording'].includes(item.template_key)));
      pass('Camera detects spoken focus/video concepts and recommends supported missing topics, not filler');
    }
    assert.equal(classification.acceptance.presentation_only, true);
    assert.equal(classification.acceptance.validation_passed, false);
    assert.ok(classification.warning.includes('โหมดสาธิตชั่วคราว'));
    assert.equal(result.analysis_settings.classification_model.status, 'presentation_only');
    report.classification = classification;
    report.recommendation_status = result.recommendation.status;
    report.reference_count = result.recommendation.dataset_profile.sample_size;
    assert.ok(report.reference_count > 0);
    const saved = await get(`/contents/${report.content_id}`);
    save('saved-result.json', saved);
    assert.deepEqual(saved.recommendation, result.recommendation);
    assert.deepEqual(saved.analysis.analysis_settings, result.analysis_settings);
    pass('Saved recommendations and settings match the completed analysis, including presentation disclosure');
    const name = saved.title;
    for (const width of [1440, 1000]) {
      await page.setViewportSize({ width, height: 1000 });
      await open('/history');
      await page.getByRole('button', { name, exact: false }).first().waitFor({ timeout: 90000 });
      await (await seek(name)).click();
      await page.getByText('โหมดสาธิตชั่วคราว', { exact: false }).first().waitFor({ timeout: 90000 });
      await page.getByRole('progressbar').first().waitFor({ state: 'hidden', timeout: 90000 });
      const aria = await page.locator('body').ariaSnapshot();
      assert.ok(aria.includes('โหมดสาธิตชั่วคราว'), 'Warning missing on reopened result');
      if (cameraFile) {
        assert.ok(aria.includes('คำสำคัญที่แนะนำให้เพิ่ม'));
        assert.ok(aria.includes('คำสำคัญที่เสนอสำหรับช่วงเปิดคลิป'));
        assert.ok(aria.includes('ภาพในสภาพแสงน้อย'));
      }
      await shot(`reopened-${width}`);
      await page.mouse.move(850, 650);
      await page.mouse.wheel(0, 570);
      await page.waitForTimeout(400);
      await shot(`advice-${width}`);
      const duration = saved.recommendation.recommended_duration;
      const durationLabel = `ค่ากลาง ${duration.median_seconds} วินาที · ช่วง ${duration.percentile_low_seconds}–${duration.percentile_high_seconds} วินาที`;
      if (!cameraFile) assert.ok((await page.locator('body').ariaSnapshot()).includes(durationLabel));
      pass(`Saved result reopened with warning at ${width}px`);
    }
    assert.deepEqual(await get(`/contents/${report.content_id}`), saved);
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.failure = safeMessage(error);
    if (page) await shot('failure').catch(() => {});
    throw error;
  } finally {
    try {
    if (auth && context) {
      const response = await context.request.post('http://127.0.0.1:8000/auth/logout', {
        headers: { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session }, data: {},
      });
      assert.equal(response.status(), 200, 'Temporary session logout');
      report.temporary_session_ended = true;
    }
    } catch (error) {
      report.passed = false;
      report.temporary_session_ended = false;
      report.cleanup_error = safeMessage(error);
      // Revoke only this harness's session if the API is unavailable.
      execFileSync('python', ['-X', 'utf8', '-c', `
import sys
from app.database.db import SessionLocal
from app.database.models import UserTrendWatchSession
from app.services.trend_watch_sessions import end_trend_watch_session
with SessionLocal() as db:
    row = db.query(UserTrendWatchSession).filter_by(user_id=2, session_key=sys.stdin.read()).one()
    end_trend_watch_session(db, watch_session=row)
`], { input: auth.session, windowsHide: true, stdio: ['pipe', 'ignore', 'ignore'] });
      report.temporary_session_ended = true;
    } finally {
    save('verification.json', report);
    if (browser) await browser.close();
    }
  }
  console.log(JSON.stringify({ passed: report.passed, content_id: report.content_id, checks: report.checks.length, output: out }));
})().catch(e => { console.error(safeMessage(e)); process.exitCode = 1; });
