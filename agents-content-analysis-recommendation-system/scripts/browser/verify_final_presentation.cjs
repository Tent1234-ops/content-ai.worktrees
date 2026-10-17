// Real API and rendered pages. Activation requires explicit --approve-current.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.argv[2]);
let modelId = Number(process.argv[3]);
const planContentId = /^\d+$/.test(process.argv[4] || '') ? Number(process.argv[4]) : null;
const verifySavedPlan = process.argv.includes('--verify-saved-plan');
const approveCurrent = process.argv.includes('--approve-current');
const referenceResultsOnly = process.argv.includes('--reference-results-only');
if (referenceResultsOnly && approveCurrent) throw new Error('Result-only verification cannot activate a model');
if (!output || !Number.isInteger(modelId)) throw new Error('Output directory and expected model ID required');
fs.mkdirSync(output, { recursive: false });
const report = { evidence: 'live API, temporary admin session; no login-form claim', checks: [], errors: [] };
let browser, context, auth, page;
const planRequests = [];
const redact = value => value
  .replace(/Bearer [A-Za-z0-9._-]+/g, 'Bearer [REDACTED]')
  .replace(/X-Trend-Session-Key: [A-Za-z0-9_-]+/gi, 'X-Trend-Session-Key: [REDACTED]');
const save = () => fs.writeFileSync(path.join(output, 'verification.json'), redact(JSON.stringify(report, null, 2)));
async function open(route) {
  await page.goto(`http://127.0.0.1:8080/#/${route}`, { waitUntil: 'networkidle', timeout: 90000 });
  await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
  await page.waitForTimeout(1500);
}
async function capture(name) {
  const aria = await page.locator('body').ariaSnapshot();
  assert.ok(aria.length > 100, `${name}: empty rendered page`);
  fs.writeFileSync(path.join(output, `${name}.txt`), aria);
  await page.screenshot({ path: path.join(output, `${name}.png`) });
  return aria;
}
async function waitForContent(text) {
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    if ((await page.locator('body').ariaSnapshot()).includes(text)) return;
    await page.waitForTimeout(500);
  }
  throw new Error(`Loaded content missing: ${text}`);
}
async function frameText(text, top = 130) {
  const locator = page.getByText(text, { exact: true }).first();
  for (let attempt = 0; attempt < 20; attempt++) {
    const bounds = await locator.boundingBox();
    if (bounds && bounds.y >= top - 35 && bounds.y < top + 80) return;
    await page.mouse.move(Math.min(page.viewportSize().width - 25, 900), 500);
    await page.mouse.wheel(0, bounds ? bounds.y - top : 400);
    await page.waitForTimeout(250);
  }
  throw new Error(`Could not frame text for screenshot: ${text}`);
}
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
    const health = await context.request.get('http://127.0.0.1:8000/health');
    assert.equal(health.status(), 200);
    const healthData = await health.json();
    assert.equal(healthData.database.status, 'ok');
    assert.equal(healthData.ai_models.faster_whisper.ready, true);
    assert.ok(!('tiktok' in healthData.live_trends.providers));
    assert.equal((await context.request.get('http://127.0.0.1:8000/admin/training')).status(), 401);
    page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    page.on('console', m => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text()); });
    page.on('response', r => { if (r.status() >= 500 && r.url().includes('127.0.0.1:8000')) report.errors.push(`${r.status()} ${new URL(r.url()).pathname}`); });
    page.on('request', r => { if (/\/contents\/\d+\/revision-plan/.test(r.url())) planRequests.push(r.url()); });
    await open('dashboard');
    await waitForContent('YouTube');
    assert.ok((await capture('public-dashboard')).includes('YouTube'));
    report.checks.push('Public dashboard and anonymous admin denial');
    auth = JSON.parse(execFileSync('py', ['-X', 'utf8', '-c', `
import json
from datetime import timedelta
from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import User
from app.services.trend_watch_sessions import start_trend_watch_session
with SessionLocal() as db:
    user = db.query(User).filter_by(role='admin', is_active=True).order_by(User.user_id).first()
    watch = start_trend_watch_session(db, user=user, region='TH')
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=30), session_key=watch.session_key)
    print(json.dumps({'token':token,'session':watch.session_key,'user':{'user_id':user.user_id,'username':user.username,'email':user.email,'role':user.role}}))
`], { cwd: root, env: { ...process.env, CONTENT_AI_SKIP_DB_BOOTSTRAP: '1' }, encoding: 'utf8', windowsHide: true }));
    const headers = { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session };
    let overview;
    if (!referenceResultsOnly) {
      const overviewResponse = await context.request.get('http://127.0.0.1:8000/admin/training', { headers, timeout: 90000 });
      assert.equal(overviewResponse.status(), 200);
      overview = await overviewResponse.json();
      assert.equal(overview.active_model.model_id, modelId);
      assert.equal(overview.active_model.readiness.can_accept_predictions, true);
      assert.ok(['qualified', 'presentation_only', 'admin_approved'].includes(overview.active_model.status));
      if (overview.active_model.status !== 'admin_approved') {
        assert.equal(overview.active_model.qualification.passed, overview.active_model.status === 'qualified');
      }
      fs.writeFileSync(path.join(output, 'active-model.json'), JSON.stringify(overview.active_model, null, 2));
    }
    await context.addInitScript(auth => {
      localStorage.setItem('flutter.access_token', JSON.stringify(auth.token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(auth.session));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(auth.user)));
    }, auth);
    // Hash-only navigation does not execute init scripts on the existing page.
    await page.reload({ waitUntil: 'networkidle' });
    if (approveCurrent) {
      assert.equal(overview.active_model.status, 'presentation_only');
      assert.equal(overview.active_model.can_activate, true);
      const sourceId = modelId;
      const savedBefore = await (await context.request.get('http://127.0.0.1:8000/contents/40', { headers })).json();
      const planBefore = await (await context.request.get('http://127.0.0.1:8000/contents/40/revision-plan', { headers })).json();
      await open('admin-training');
      await waitForContent('โมเดลจำแนกหมวดที่ใช้งานอยู่');
      await page.getByRole('tab', { name: 'เปรียบเทียบโมเดล', exact: true }).click();
      await page.getByRole('button', { name: `เปิดใช้โมเดล #${sourceId}`, exact: true }).click();
      await waitForContent('ไม่กำหนดคะแนนขั้นต่ำ');
      await capture('approval-confirmation');
      const responsePromise = page.waitForResponse(r => r.url().endsWith(`/models/${sourceId}/activate`) && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'ยืนยันเปิดใช้', exact: true }).click();
      const response = await responsePromise;
      assert.equal(response.status(), 200);
      const activated = await response.json();
      assert.equal(activated.status, 'admin_approved');
      modelId = activated.model_id;
      assert.notEqual(modelId, sourceId);
      await waitForContent(`เปิดใช้โมเดล #${modelId} แล้ว`);
      fs.writeFileSync(path.join(output, 'activation.json'), JSON.stringify(activated, null, 2));
      const after = await (await context.request.get('http://127.0.0.1:8000/admin/training', { headers, timeout: 90000 })).json();
      assert.equal(after.active_model.model_id, modelId);
      assert.equal(after.active_model.readiness.can_accept_predictions, true);
      assert.equal(after.active_model.readiness.status, 'admin_approved');
      assert.equal(after.active_model.readiness.presentation_expires_at, undefined);
      assert.equal(after.policy.promotion_threshold, null);
      assert.deepEqual(after.active_model.activation_review.selected_validation, overview.active_model.activation_review.selected_validation);
      assert.deepEqual(await (await context.request.get('http://127.0.0.1:8000/contents/40', { headers })).json(), savedBefore);
      assert.deepEqual(await (await context.request.get('http://127.0.0.1:8000/contents/40/revision-plan', { headers })).json(), planBefore);
      fs.writeFileSync(path.join(output, 'approved-model.json'), JSON.stringify(after.active_model, null, 2));
      report.checks.push(`UI approved #${sourceId} as #${modelId}; unchanged Validation point, saved result and plan`);
    }
    const routes = [
      ['upload', 'วิเคราะห์คลิป'], ['history', 'ไอเดียและประวัติ'],
      ['admin-training', 'เทรนโมเดล'], ['admin-analysis-settings', 'ตั้งค่าการวิเคราะห์'],
      ['admin-datasets', 'จัดการ Dataset'], ['admin-users', 'ผู้ใช้'],
      ['admin-logs', 'บันทึกการทำงานระบบ'],
    ];
    for (const width of verifySavedPlan ? [] : [1440, 1000, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const [route, heading] of referenceResultsOnly ? [] : routes) {
        await open(route);
        if (route === 'admin-training') await waitForContent('โมเดลจำแนกหมวดที่ใช้งานอยู่');
        const aria = await capture(`${route}-${width}`);
        assert.ok(!aria.includes('heading "เข้าสู่ระบบ"'), `${route}: authentication missing`);
        assert.ok(aria.toLowerCase().includes(heading.toLowerCase()), `${route}: heading missing`);
        report.checks.push(`${route} rendered at ${width}px`);
        if (route === 'admin-training') {
          assert.ok(aria.includes(`#${modelId} `), 'Rendered active model differs from API');
          await page.getByRole('button', { name: 'ประเมินผลตอบรับ', exact: true }).click();
          await waitForContent('ยังไม่มี Outcome model ที่เปิดใช้งาน');
          const outcome = await capture(`outcome-unavailable-${width}`);
          assert.ok(outcome.includes('ยังเริ่มเทรนไม่ได้'));
          assert.equal(await page.getByRole('button', { name: 'เริ่มเทรน Outcome', exact: true }).isEnabled(), false);
          report.checks.push(`Outcome preflight correctly withheld at ${width}px`);
        }
        save();
      }
      await open('history');
      const savedResponse = page.waitForResponse(r => /\/contents\/\d+$/.test(new URL(r.url()).pathname) && r.request().method() === 'GET');
      await page.getByRole('button', { name: /^review camera คำแนะนำ:/ }).first().click();
      const saved = await (await savedResponse).json();
      await waitForContent('1. พบอะไรในคลิป');
      const result = await capture(`saved-camera-result-${width}`);
      assert.ok(result.includes('ผลวิเคราะห์คลิป'), 'Saved result did not open');
      assert.equal(await page.getByRole('checkbox', { name: 'เลือกนำไปปรับ', exact: true }).count(), 0);
      assert.equal(await page.getByRole('button', { name: 'บันทึกแผนปรับคลิป', exact: true }).count(), 0);
      await page.getByRole('button', { name: 'คำสำคัญและข้อความถอดเสียง', exact: true }).click();
      await page.getByRole('button', { name: 'ข้อความถอดเสียง', exact: true }).click();
      await page.waitForTimeout(300);
      const transcriptView = await capture(`original-transcript-${width}`);
      assert.ok(transcriptView.includes('ข้อความต้นฉบับ'));
      assert.ok(!transcriptView.includes('ข้อความหลังปรับศัพท์'));
      await page.getByRole('button', { name: 'คำสำคัญและข้อความถอดเสียง', exact: true }).click();
      let scannedText = result + transcriptView;
      for (let i = 0; i < 40 && !(await page.locator('body').ariaSnapshot()).includes('หลักฐานที่เปิดดูได้'); i++) {
        scannedText += await page.locator('body').ariaSnapshot();
        await page.mouse.move(Math.min(width - 30, 900), 800);
        await page.mouse.wheel(0, 450);
        await page.waitForTimeout(250);
      }
      await frameText('3. ผลตอบรับจากคลิปอ้างอิง');
      const reference = await capture(`reference-response-${width}`);
      assert.ok(reference.includes('3. ผลตอบรับจากคลิปอ้างอิง'));
      assert.ok(reference.includes('ไม่ใช่เปอร์เซ็นต์ทำนาย'));
      const bundle = saved.recommendation.evidence_bundle;
      const advice = saved.recommendation.actionable_recommendations.items[0];
      const topic = bundle.action_topics.find(t => t.topic_id === advice.evidence_topic_id);
      assert.ok(topic && topic.references.length > 0);
      const doc = bundle.reference_documents.find(d => d.dataset_id === topic.references[0].dataset_id);
      assert.ok(doc && doc.statistics_captured_at && Number.isInteger(doc.statistics.views));
      assert.ok(doc.transcript.includes(topic.references[0].occurrences[0].quote));
      for (let i = 0; i < 8 && !(await page.locator('body').ariaSnapshot()).includes(doc.title); i++) {
        await page.mouse.wheel(0, 200);
        await page.waitForTimeout(250);
      }
      await frameText(doc.title);
      const source = await capture(`reference-source-${width}`);
      assert.ok(source.includes(doc.title));
      const expectedViews = doc.statistics.views.toLocaleString('en-US');
      for (let i = 0; i < 6 && !(await page.locator('body').ariaSnapshot()).includes(expectedViews); i++) {
        await page.mouse.wheel(0, 150);
        await page.waitForTimeout(250);
      }
      assert.ok((await capture(`reference-statistics-${width}`)).includes(expectedViews));
      await page.getByRole('button', { name: 'ข้อความที่พบในคลิปอ้างอิง', exact: true }).first().click();
      await page.waitForTimeout(300);
      assert.ok((await capture(`reference-quote-${width}`)).includes(topic.references[0].occurrences[0].quote.trim()));
      fs.writeFileSync(path.join(output, `reference-proof-${width}.json`), JSON.stringify({
        content_id: saved.content_id, topic_id: topic.topic_id, dataset_id: doc.dataset_id,
        video_id: doc.video_id, statistics: doc.statistics, statistics_captured_at: doc.statistics_captured_at,
        compared_with: 'unchanged saved analysis response',
      }, null, 2));
      let allResultText = scannedText + reference + source;
      for (let i = 0; i < 45; i++) {
        allResultText += await page.locator('body').ariaSnapshot();
        const footerButton = page.getByRole('button', { name: 'กลับ Dashboard', exact: true });
        const footer = await footerButton.count() ? await footerButton.boundingBox() : null;
        if (footer && footer.y >= 65 && footer.y + footer.height <= page.viewportSize().height) break;
        await page.mouse.wheel(0, 650);
        await page.waitForTimeout(100);
      }
      assert.ok(allResultText.includes('กลับ Dashboard'), 'Did not reach the result footer');
      for (const removed of ['เลือกนำไปปรับ', 'แผนปรับคลิปของฉัน', 'รายละเอียดแผนปรับคลิป', 'บันทึกแผนปรับคลิป', 'โหลดแผนที่บันทึก', 'คัดลอกประโยคตัวอย่าง', 'ข้อความหลังปรับศัพท์', 'เปิดดูหลักฐานและเวอร์ชัน']) {
        assert.ok(!allResultText.includes(removed), `Removed result control still rendered: ${removed}`);
      }
      assert.ok(!allResultText.includes('โอกาสอยู่ในกลุ่มยอดวิวสูงกว่า'));
      assert.deepEqual(planRequests, []);
      report.checks.push(`Existing camera result reopened at ${width}px`);
      report.checks.push(`Real saved reference counters matched at ${width}px; planner absent through footer; no plan API calls`);
      report.checks.push(`Copy button, normalized transcript and audit expander absent at ${width}px; original transcript retained`);
    }
    if (planContentId !== null) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await open('history');
      await page.getByRole('button', { name: /^review camera คำแนะนำ:/ }).first().click();
      await waitForContent(`บันทึกแล้ว · #${planContentId}`);
      const planUrl = `http://127.0.0.1:8000/contents/${planContentId}/revision-plan`;
      const before = await (await context.request.get(planUrl, { headers })).json();
      assert.equal(before.revision, verifySavedPlan ? 1 : 0,
        'Only a new audit plan may be edited; verify mode never saves again');
      const choice = page.getByRole('checkbox', { name: 'เลือกนำไปปรับ', exact: true }).first();
      const deadline = Date.now() + 60000;
      while (!(await choice.isEnabled()) && Date.now() < deadline) await page.waitForTimeout(500);
      assert.equal(await choice.isEnabled(), true, 'Recommendation selection never became ready');
      if (verifySavedPlan) assert.equal(await choice.isChecked(), true);
      else await choice.click();
      const saveButton = page.getByRole('button', { name: 'บันทึกแผนปรับคลิป', exact: true });
      for (let i = 0; i < 15 && !(await saveButton.count()); i++) {
        await page.mouse.move(1100, 800);
        await page.mouse.wheel(0, 700);
        await page.waitForTimeout(300);
      }
      if (!verifySavedPlan) await saveButton.click({ timeout: 20000 });
      await waitForContent('แผนที่บันทึกแล้ว · ฉบับ 1');
      const after = await (await context.request.get(planUrl, { headers })).json();
      assert.equal(after.revision, 1);
      assert.equal(after.selected_advice_ids.length, 1);
      fs.writeFileSync(path.join(output, 'saved-plan.json'), JSON.stringify(after, null, 2));
      await capture('saved-plan');
      report.checks.push(verifySavedPlan
        ? `Reopened previously UI-saved plan and confirmed checkbox, revision and selected IDs for #${planContentId}`
        : `Selected one recommendation and persisted revision plan for audit result #${planContentId}`);
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.error = String(error.message);
    report.error_stack = error.stack;
    if (page) await capture('failure').catch(() => {});
    process.exitCode = 1;
  } finally {
    if (auth && context) {
      const response = await context.request.post('http://127.0.0.1:8000/auth/logout', {
        headers: { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session }, data: {},
      }).catch(() => null);
      report.temporary_session_ended = response?.status() === 200;
      if (!report.temporary_session_ended) { report.passed = false; process.exitCode = 1; }
    }
    save();
    if (browser) await browser.close();
  }
  console.log(redact(JSON.stringify(report)));
})();
