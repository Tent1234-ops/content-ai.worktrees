// Render a fresh, read-only calculation from real data; never overwrite saved history.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const auditDir = path.resolve(process.argv[2]);
const output = path.resolve(process.argv[3]);
const api = 'http://127.0.0.1:8011';
const web = 'http://127.0.0.1:8081';
const audit = JSON.parse(fs.readFileSync(path.join(auditDir, 'audit.json'), 'utf8'));
const recommendation = JSON.parse(fs.readFileSync(path.join(auditDir, 'fresh-recommendation.json'), 'utf8'));
fs.mkdirSync(output, { recursive: true });
const report = {
  mode: 'real_database_read_only_recalculation_rendered_via_test_response_overlay',
  note: 'New calculation is NOT saved to user history; auth session is temporary.',
  target_content_id: Number(audit.source_content_id),
  checks: [], errors: [],
};
let browser, context, auth;
const save = () => fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(report, null, 2));
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ timezoneId: 'Asia/Bangkok', serviceWorkers: 'block' });
    assert.equal((await context.request.get(`${api}/health`)).status(), 200);
    auth = JSON.parse(execFileSync('py', ['-X', 'utf8', '-c', `
import json
from datetime import timedelta
from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import UserContent
from app.services.trend_watch_sessions import start_trend_watch_session
with SessionLocal() as db:
    content = db.get(UserContent, ${Number(audit.source_content_id)})
    user = content.owner
    watch = start_trend_watch_session(db, user=user, region='TH')
    token = create_access_token(str(user.user_id), user.role, expires_delta=timedelta(minutes=30), session_key=watch.session_key)
    print(json.dumps({'token':token,'session':watch.session_key,'user':{'user_id':user.user_id,'username':user.username,'email':user.email,'role':user.role}}))
`], { cwd: root, env: { ...process.env, CONTENT_AI_SKIP_DB_BOOTSTRAP: '1' }, encoding: 'utf8', windowsHide: true }));
    const headers = { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session };
    const contentUrl = `${api}/contents/${audit.source_content_id}`;
    const beforeResponse = await context.request.get(contentUrl, { headers });
    assert.equal(beforeResponse.status(), 200);
    const before = await beforeResponse.json();
    await context.addInitScript(auth => {
      localStorage.setItem('flutter.access_token', JSON.stringify(auth.token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(auth.session));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(auth.user)));
    }, auth);
    const firstTopic = recommendation.actionable_recommendations.items.find(item =>
      recommendation.evidence_bundle.topic_comparisons.items.some(topic =>
        topic.evidence_topic_id === item.evidence_topic_id && topic.group_response_summary.status === 'available'));
    assert.ok(firstTopic, 'Real calculation has no supported group');
    const group = recommendation.evidence_bundle.topic_comparisons.items.find(topic =>
      topic.evidence_topic_id === firstTopic.evidence_topic_id).group_response_summary.groups[0];
    const threshold = new Intl.NumberFormat('en-US').format(group.threshold_views);
    const sentence = `ในกลุ่มคลิปอ้างอิงหมวด Camera ที่กล่าวถึง “${firstTopic.title}” มีคลิปที่มียอดวิวสะสมมากกว่า ${threshold} ครั้ง ณ วันที่เก็บสถิติ จำนวน ${group.passing_count} จาก ${group.sample_size} คลิป คิดเป็น ${group.percentage}% จากทั้งหมด ${group.channel_count} ช่อง สำหรับคลิปของคุณ ระบบเสนอให้ลอง${firstTopic.proposal} ${firstTopic.condition.trim() ? `ทั้งนี้ ${firstTopic.condition.trim()} ` : ''}แล้วติดตามผลตอบรับหลังเผยแพร่`;
    for (const width of [1440, 390]) {
      const page = await context.newPage();
      await page.setViewportSize({ width, height: 1000 });
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
      });
      let overlayRequests = 0;
      await page.route(contentUrl, route => {
        overlayRequests++;
        return route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ ...before, recommendation }),
        });
      });
      // Titles are not unique. Limit the test history response to the audited ID.
      await page.route(`${api}/contents/my?*`, async route => {
        const response = await route.fetch();
        const history = await response.json();
        const items = history.items.filter(item => Number(item.content_id) === Number(audit.source_content_id));
        assert.equal(items.length, 1, 'Audited content must exist in the history page');
        await route.fulfill({ response, json: { ...history, total: 1, items } });
      });
      await page.goto(`${web}/#/history`, { waitUntil: 'networkidle', timeout: 90000 });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
      await page.getByRole('button', { name: /^review camera คำแนะนำ:/ }).first().click({ timeout: 60000 });
      await page.waitForTimeout(1500);
      assert.ok(overlayRequests > 0, 'The target analysis response overlay was never requested');
      assert.ok((await page.locator('body').ariaSnapshot()).includes(`ผลวิเคราะห์บันทึกแล้ว · #${audit.source_content_id}`));
      await page.screenshot({ path: path.join(output, `report-${width}.png`) });
      for (const target of ['2. ควรเพิ่มอะไร', sentence]) {
        for (let attempt = 0; attempt < 50; attempt++) {
          const locator = page.getByText(target, { exact: true }).first();
          const bounds = await locator.count() ? await locator.boundingBox() : null;
          if (bounds && bounds.y >= 90 && bounds.y < 180) break;
          await page.mouse.move(width - 30, 700);
          await page.mouse.wheel(0, bounds ? bounds.y - 130 : 450);
          await page.waitForTimeout(150);
        }
        if (target !== sentence) await page.screenshot({ path: path.join(output, `advice-${width}.png`) });
      }
      const text = await page.locator('body').ariaSnapshot();
      assert.ok(text.includes(sentence), 'X/N/Y/Z missing or different from actual calculation');
      for (const hidden of [
        'ไม่ใช่คะแนนคุณภาพคลิป', 'มีข้อมูลความยาว', 'ไอเดียจากกระแสล่าสุด',
        'คลิปอ้างอิงในหมวดเดียวกันที่กล่าวถึงประเด็นที่แนะนำ', 'เป็นตัวอย่างที่ระบบคัดไว้',
        'เปรียบเทียบภายในหมวด', 'ค่าอ้างอิงยอดวิวสะสม:',
        'เนื้อหาใกล้เคียงหมายถึงตรวจพบประเด็นนี้ใน Transcript', 'เป็นสัดส่วนในข้อมูลที่คัดเก็บ',
        'คลิปที่ใช้คำนวณ',
      ]) assert.ok(!text.includes(hidden), `Removed text is still visible: ${hidden}`);
      await page.screenshot({ path: path.join(output, `group-${width}.png`) });
      fs.writeFileSync(path.join(output, `group-${width}.txt`), text);
      assert.ok(text.includes('คลิปต้นแบบประกอบคำแนะนำ'));
      report.checks.push({ width, sentence, target_response_loaded: overlayRequests > 0, requested_details_hidden: true, illustrative_sources_preserved: true });
      await page.close();
    }
    assert.deepEqual(await (await context.request.get(contentUrl, { headers })).json(), before);
    report.saved_result_unchanged = true;
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.errors.push(error.stack || String(error));
    report.passed = false;
    process.exitCode = 1;
  } finally {
    if (context && auth) {
      const response = await context.request.post(`${api}/auth/logout`, {
        headers: { Authorization: `Bearer ${auth.token}`, 'X-Trend-Session-Key': auth.session },
      });
      report.temporary_session_ended = response.ok();
    }
    save();
    if (browser) await browser.close();
  }
})();
