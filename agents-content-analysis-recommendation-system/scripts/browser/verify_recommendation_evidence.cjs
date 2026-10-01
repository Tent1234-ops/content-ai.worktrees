// Approval dialog is read-only against the real DB. Evidence uses an isolated SQLite fixture.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/recommendation-evidence');
const python = 'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe';
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8004';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8084';
fs.mkdirSync(out, { recursive: true });
const fixture = JSON.parse(execFileSync(python, ['-B', '-X', 'utf8', '-c', `
import json
from tests.test_recommendation_evidence import EvidenceBundleTests
from app.database.models import DatasetContent
from app.services.recommendation_evidence import user_context
case = EvidenceBundleTests()
case.setUp()
try:
    for row in case.db.query(DatasetContent).all():
        row.title = 'TEST FIXTURE: reference ' + str(row.dataset_id)
    case.db.commit()
    result = case.build('camera photo', evidence_context=user_context(transcript='camera photo',
        stt_meta={'transcript_source':'speech_to_text', 'hook_seconds_analyzed':60},
        segments=[{'text':'camera photo','start':4,'end':9}]))
    result['content_keywords'] = ['camera', 'photo']
    result['hook_terms'] = ['camera']
    result['comparable_keywords'] = ['camera quality']
    print(json.dumps({'content_id':999999, 'title':'TEST FIXTURE: evidence contract',
        'transcript':'camera photo', 'raw_transcript':'camera photo', 'recommendation':result}, ensure_ascii=False))
finally:
    case.tearDown()
`], { cwd: root, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }));

(async () => {
  const session = JSON.parse(execFileSync(python, ['artifacts/settings_browser_session.py'],
    { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const report = { fixture_evidence: true, review_posts: [], errors: [], screenshots: [] };
  let browser, page;
  async function summary() {
    const response = await fetch(api + '/admin/dataset-review/queue?status=pending&limit=100', { headers });
    assert.equal(response.status, 200);
    return (await response.json()).summary;
  }
  try {
    report.before = await summary();
    report.review_dialog_fixture = report.before.pending === 0;
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: 'block' });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
      });
      await page.route('**/admin/dataset-review/**', async route => {
        if (route.request().method() !== 'POST') {
          if (report.review_dialog_fixture && route.request().url().includes('/queue?')) {
            return route.fulfill({ json: {
              total: 3, limit: 100, offset: 0, summary: { total: 3, pending: 3, approved: 0, rejected: 0 },
              runs: [], taxonomy: [], items: ['phone', 'camera', 'laptop'].map((leaf, index) => ({
                collection_run_id: 999999, source_youtube_id: `fixture${index}`, title: `TEST FIXTURE: ${leaf}`,
                channel_title: 'Test channel', proposed_leaf_key: leaf, candidate_sha256: 'a'.repeat(64),
                transcript: 'Test transcript only', transcript_preview: 'Test transcript only', review_status: 'pending',
              })),
            } });
          }
          return route.continue();
        }
        report.review_posts.push(route.request().url());
        return route.abort();
      });
      await page.route('**/contents/my?*', route => route.fulfill({ json: { total: 1, items: [{
        content_id: 999999, title: fixture.title, domain: 'phone', transcript_preview: 'camera photo',
        recommended_keywords: ['battery life'], recommended_duration: null,
      }] } }));
      await page.route('**/contents/999999', route => route.fulfill({ json: fixture }));
      async function open(hash) {
        await page.goto(web + '/#' + hash, { waitUntil: 'networkidle' });
        await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
        await page.waitForTimeout(500);
      }
      async function shot(name) {
        const prefix = `${width}-${name}`;
        await page.screenshot({ path: path.join(out, prefix + '.png') });
        fs.writeFileSync(path.join(out, prefix + '.txt'), await page.locator('body').ariaSnapshot());
        report.screenshots.push(prefix);
      }
      async function seek(text, buttonOnly = false) {
        for (let step = 0; step < 50; step++) {
          let position;
          const finders = [page.getByRole('button', { name: text, exact: false })];
          if (!buttonOnly) finders.push(page.getByText(text, { exact: false }));
          for (const finder of finders) {
            for (const locator of await finder.all()) {
              const box = await locator.boundingBox({ timeout: 300 }).catch(() => null);
              if (box && box.y > 64 && box.y < 840) return locator;
              position ||= box;
            }
          }
          await page.mouse.move(width - 50, 600);
          await page.mouse.wheel(0, position && position.y < 64 ? -320 : 320);
          await page.waitForTimeout(150);
        }
        throw new Error(`Cannot find ${text}`);
      }
      await open('/admin-dataset-review');
      await (await seek('อนุมัติทั้งหมด')).click();
      await page.getByRole('checkbox', { name: /ฉันตรวจ Transcript/ }).waitFor({ state: 'visible' });
      assert.ok((await page.locator('body').ariaSnapshot()).includes('ฉันตรวจ Transcript'));
      await shot('approve-confirmation');
      await page.getByRole('button', { name: 'ยกเลิก', exact: true }).click();
      await open('/history');
      await (await seek(fixture.title)).click();
      await page.waitForTimeout(500);
      await shot('result');
      await seek('3. เพราะอะไรจึงแนะนำ');
      await page.getByRole('button', { name: 'เปิดดูหลักฐานและเวอร์ชัน', exact: true }).click();
      await page.waitForTimeout(300);
      const evidenceTopics = fixture.recommendation.evidence_bundle.action_topics ||
        fixture.recommendation.evidence_bundle.topics || [];
      const referenceTopic = evidenceTopics.find(topic => (topic.references || []).length > 0);
      assert.ok(referenceTopic, 'Fixture must expose at least one topic with source references');
      const referenceTopicTitle = referenceTopic.title_th || referenceTopic.canonical_topic;
      await page.getByRole('button', { name: referenceTopicTitle, exact: false }).click();
      await page.waitForTimeout(300);
      await (await seek('TEST FIXTURE: reference', true)).click();
      await page.waitForTimeout(300);
      await seek('ไม่มี Timestamp จากต้นทาง');
      await shot('reference-evidence');
      const tree = await page.locator('body').ariaSnapshot();
      assert.ok(tree.includes('เก็บสถิติ') && tree.includes('Dataset #'));
      await context.close();
    }
    report.after = await summary();
    assert.deepEqual(report.after, report.before);
    assert.deepEqual(report.review_posts, []);
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
