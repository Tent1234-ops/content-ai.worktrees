// Browser-only Phase 5 verification. All API responses are synthetic and read-only.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/topic-comparisons-phase5');
const python = 'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8087';
fs.mkdirSync(out, { recursive: true });

const fixture = JSON.parse(execFileSync(python, ['-B', '-X', 'utf8', '-c', `
import json
from tests.test_actionable_recommendations import fixture_result
from app.services.actionable_recommendations import build_actionable_recommendations

result = fixture_result('phone', 'รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง',
                        reference_text='แบตเตอรี่ การชาร์จเร็ว charging Snapdragon AMOLED กล้อง เครื่องร้อน')
result['actionable_recommendations'] = build_actionable_recommendations(result)
result['dataset_profile'].update(sample_size=4, domain='phone')
result['content_keywords'] = ['แบตเตอรี่']
result['comparable_keywords'] = ['battery life']
result['hook_terms'] = ['รีวิวมือถือ']
result['classification'] = {'taxonomy_leaf_key':'phone', 'category_level_3':'Phone',
                            'is_unknown':False, 'confidence':0.94}
result['evidence_bundle']['generated_at'] = '2026-09-29T12:00:00Z'
topic_id = result['actionable_recommendations']['items'][0]['evidence_topic_id']
result['evidence_bundle']['topic_comparisons'] = {
  'as_of':'2026-09-29T12:00:00Z', 'schema_version':'topic-comparison-evidence-v1',
  'items':[{
    'evidence_topic_id':topic_id,
    'cohort':{'detected_count':20, 'not_detected_count':10,
              'support_cohort_video_count':12, 'comparison_pool_video_count':18},
    'metrics':{
      'views':{'status':'comparison_supported','detected':{'count':20,'median':2400,'p25':1800,'p75':3000},
               'not_detected':{'count':10,'median':1300,'p25':900,'p75':1600},
               'paired_channel_count':10,'within_channel_median_difference':700,
               'uncertainty':{'status':'available','low':180,'high':920}},
      'likes_per_1000_views':{'status':'comparison_uncertain','detected':{'count':20,'median':32,'p25':20,'p75':45},
               'not_detected':{'count':10,'median':30,'p25':18,'p75':48},
               'paired_channel_count':10,'within_channel_median_difference':1.5,
               'uncertainty':{'status':'available','low':-4,'high':6}},
      'comments_per_1000_views':{'status':'comparison_supported','detected':{'count':20,'median':3,'p25':2,'p75':4},
               'not_detected':{'count':10,'median':5,'p25':4,'p75':6},
               'paired_channel_count':10,'within_channel_median_difference':-2,
               'uncertainty':{'status':'available','low':-3,'high':-1}},
      'views_per_hour':{'status':'reference_only','detected':{'count':5,'median':25,'p25':20,'p75':30},
               'not_detected':{'count':3,'median':18,'p25':14,'p75':20},
               'paired_channel_count':2,'within_channel_median_difference':6,
               'uncertainty':{'status':'uncertainty_unavailable','reason':'descriptive_minimum_not_met','low':None,'high':None}}
    },
    'limitation':'เป็นความแตกต่างที่พบในคลิปอ้างอิง ไม่ได้พิสูจน์ว่าหัวข้อนี้เป็นสาเหตุของยอดเพิ่ม'
  }]
}
print(json.dumps({'content_id': 995001, 'title':'TEST FIXTURE: Phase 5 comparison',
                  'transcript':'รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง',
                  'raw_transcript':'รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง',
                  'recommendation':result}, ensure_ascii=False))
`], { cwd: root, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }));

(async () => {
  const report = { synthetic_fixture: true, errors: [], mutation_requests: [], screenshots: [] };
  let browser;
  let page;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: 'block' });
      await context.addInitScript(() => {
        localStorage.setItem('flutter.access_token', JSON.stringify('phase5-fixture-token'));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify('phase5-fixture-session'));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify({
          user_id: 995001, username: 'phase5-fixture', email: 'fixture@example.test', role: 'creator', is_active: true,
        })));
      });
      page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) report.errors.push(message.text());
      });
      await page.route('**/*', async route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/contents/my') {
          return route.fulfill({ json: { total: 1, items: [{ content_id: fixture.content_id,
            title: fixture.title, domain: 'phone', transcript_preview: fixture.transcript,
            recommended_keywords: [], recommended_duration: null }] } });
        }
        if (url.pathname === `/contents/${fixture.content_id}`) return route.fulfill({ json: fixture });
        if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/dashboard') ||
            url.pathname.startsWith('/notifications')) {
          if (request.method() !== 'GET') report.mutation_requests.push(url.pathname);
          return route.fulfill({ json: url.pathname === '/auth/me' ? {
            user_id: 995001, username: 'phase5-fixture', email: 'fixture@example.test', role: 'creator', is_active: true,
          } : {} });
        }
        return route.continue();
      });
      async function seek(text) {
        for (let step = 0; step < 70; step++) {
          let position;
          const finders = [page.getByRole('button', { name: text, exact: false }),
                           page.getByText(text, { exact: false })];
          for (const finder of finders) {
            for (const locator of await finder.all()) {
              const box = await locator.boundingBox().catch(() => null);
              if (box && box.y > 60 && box.y + box.height < 980) return locator;
              position ||= box;
            }
          }
          await page.mouse.move(width / 2, 600);
          await page.mouse.wheel(0, position && position.y < 60 ? -300 : 300);
          await page.waitForTimeout(120);
        }
        throw new Error(`Cannot find ${text}`);
      }
      async function shot(name) {
        const file = `${width}-${name}`;
        await page.screenshot({ path: path.join(out, file + '.png') });
        fs.writeFileSync(path.join(out, file + '.txt'), await page.locator('body').ariaSnapshot());
        report.screenshots.push(file);
      }
      await page.goto(web + '/#/history', { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
      await (await seek(fixture.title)).click();
      await page.waitForTimeout(300);
      await (await seek('ดูข้อความและคลิปอ้างอิง')).click();
      await page.waitForTimeout(300);
      await (await seek('เปรียบเทียบผลตอบรับของคลิปอ้างอิง')).click();
      await page.waitForTimeout(250);
      const firstTree = await page.locator('body').ariaSnapshot();
      assert.ok(firstTree.includes('ตรวจพบ 20'));
      assert.ok(firstTree.includes('คลิปอ้างอิงอื่น 18'));
      await shot('cohort');
      await (await seek('ยอดวิวสะสม ณ เวลาเก็บข้อมูล')).click();
      await page.waitForTimeout(200);
      let tree = await page.locator('body').ariaSnapshot();
      assert.ok(tree.includes('ผลต่างค่ากลางภายในช่อง 700'));
      assert.ok(tree.includes('ไม่ใช่ผลเชิงสาเหตุ'));
      await shot('positive-evidence');
      await (await seek('ความคิดเห็นต่อ 1,000 วิว')).click();
      await page.waitForTimeout(200);
      tree = await page.locator('body').ariaSnapshot();
      assert.ok(tree.includes('ผลต่างค่ากลางภายในช่อง -2'));
      await shot('negative-evidence');
      await (await seek('ยอดวิวเพิ่มเฉลี่ยต่อชั่วโมงจริง')).click();
      await page.waitForTimeout(200);
      tree = await page.locator('body').ariaSnapshot();
      assert.ok(tree.includes('กลุ่มเปรียบเทียบยังเล็กเกิน'));
      assert.ok(tree.includes('descriptive_minimum_not_met'));
      await shot('insufficient-evidence');
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
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
