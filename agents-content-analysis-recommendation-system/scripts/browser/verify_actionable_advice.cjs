// Read-only browser check. Recommendation responses are explicit synthetic fixtures.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/actionable-advice');
const python = 'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe';
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8005';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8085';
fs.mkdirSync(out, { recursive: true });
const fixtures = JSON.parse(execFileSync(python, ['-B', '-X', 'utf8', '-c', `
import json
from tests.test_actionable_recommendations import fixture_result
from app.services.actionable_recommendations import build_actionable_recommendations
cases = [('phone', 'รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง'),
         ('camera', 'รีวิวกล้อง โฟกัสได้ไว เหมาะสำหรับถ่ายภาพท่องเที่ยว'),
         ('laptop', 'รีวิวโน้ตบุ๊ก ซีพียูสำหรับทำงานตัดต่อ')]
results = []
for index, (domain, text) in enumerate(cases):
    result = fixture_result(domain, text)
    result['actionable_recommendations'] = build_actionable_recommendations(result)
    result['dataset_profile'].update(sample_size=4, domain=domain)
    result['content_keywords'] = [text]
    result['comparable_keywords'] = [t['title_th'] for t in result['evidence_bundle']['action_topics'] if t['user']['status'] == 'detected']
    result['evidence_bundle']['generated_at'] = '2026-09-29T00:00:00Z'
    result['classification'] = {'taxonomy_leaf_key': domain, 'category_level_3': domain.title(), 'is_unknown': False, 'confidence': 0.9}
    results.append({'content_id':990001+index, 'title':'TEST FIXTURE: actions ' + domain,
                    'transcript':text, 'raw_transcript':text, 'recommendation':result})
print(json.dumps(results, ensure_ascii=False))
`], { cwd: root, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }));

(async () => {
  const session = JSON.parse(execFileSync(python, ['artifacts/settings_browser_session.py'],
    { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  const report = { synthetic_fixtures: true, errors: [], mutation_requests: [], cases: [], screenshots: [] };
  let browser, page;
  try {
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
      await page.route('**/contents/**', async route => {
        const request = route.request();
        if (request.method() !== 'GET') {
          report.mutation_requests.push(request.url());
          return route.abort();
        }
        const url = new URL(request.url());
        if (url.pathname === '/contents/my') {
          return route.fulfill({ json: { total: fixtures.length, items: fixtures.map(f => ({
            content_id: f.content_id, title: f.title, domain: f.recommendation.domain,
            transcript_preview: f.transcript, recommended_keywords: [], recommended_duration: null,
          })) } });
        }
        const fixture = fixtures.find(f => url.pathname === `/contents/${f.content_id}`);
        return fixture ? route.fulfill({ json: fixture }) : route.continue();
      });
      async function seek(text, buttonOnly = false) {
        for (let step = 0; step < 55; step++) {
          let position;
          const finders = [page.getByRole('button', { name: text, exact: false })];
          if (!buttonOnly) finders.push(page.getByText(text, { exact: false }));
          for (const finder of finders) {
            for (const locator of await finder.all()) {
              const box = await locator.boundingBox({ timeout: 300 }).catch(() => null);
              if (box && box.y > 64 && box.y + box.height / 2 < 976) return locator;
              position ||= box;
            }
          }
          await page.mouse.move(width / 2, 600);
          await page.mouse.wheel(0, position && position.y < 64 ? -280 : 280);
          await page.waitForTimeout(150);
        }
        throw new Error(`Cannot find ${text}`);
      }
      async function shot(name) {
        const prefix = `${width}-${name}`;
        await page.screenshot({ path: path.join(out, prefix + '.png') });
        fs.writeFileSync(path.join(out, prefix + '.txt'), await page.locator('body').ariaSnapshot());
        report.screenshots.push(prefix);
      }
      for (const fixture of fixtures) {
        const advice = fixture.recommendation.actionable_recommendations;
        assert.ok(advice.items.length >= 2 && advice.items.length <= 3);
        await page.goto(web + '/#/history', { waitUntil: 'networkidle' });
        await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
        await page.waitForTimeout(400);
        await (await seek(fixture.title)).click();
        await page.waitForTimeout(400);
        const heading = await seek(`1. ${advice.items[0].title}`);
        const headingBox = await heading.boundingBox();
        await page.mouse.move(width / 2, 600);
        await page.mouse.wheel(0, headingBox.y - 100);
        await page.waitForTimeout(300);
        await shot(`${fixture.recommendation.domain}-advice`);
        await (await seek('ดูข้อความและคลิปอ้างอิง', true)).click();
        await page.waitForTimeout(300);
        assert.ok((await page.locator('body').ariaSnapshot()).includes('หลักฐาน:'));
        await (await seek('TEST FIXTURE 1', true)).click();
        await page.waitForTimeout(300);
        await seek('เก็บสถิติ');
        const tree = await page.locator('body').ariaSnapshot();
        assert.ok(tree.includes('Dataset #1'));
        assert.ok(tree.includes('ไม่มี Timestamp จากต้นทาง'));
        assert.ok(tree.includes('ยอดวิว 1000'));
        await shot(`${fixture.recommendation.domain}-evidence`);
        await page.getByRole('button', { name: 'ปิด', exact: true }).click();
        await seek('3. เพราะอะไรจึงแนะนำ');
        await (await seek('เปิดดูหลักฐานและเวอร์ชัน', true)).click();
        await page.waitForTimeout(300);
        await (await seek(advice.items[0].title, true)).click();
        await page.waitForTimeout(300);
        assert.ok((await page.locator('body').ariaSnapshot()).includes('คำที่ใช้ตรวจ:'));
        await shot(`${fixture.recommendation.domain}-topic-audit`);
        report.cases.push({ width, domain: fixture.recommendation.domain, advice_count: advice.items.length });
      }
      await context.close();
    }
    assert.deepEqual(report.mutation_requests, []);
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
