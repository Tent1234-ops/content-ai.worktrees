/* Read-only UI verification: preview a fresh API recommendation without replacing saved results. */
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8001';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8081';
const out = path.join(root, 'artifacts/browser/current-trend-ideas');
fs.mkdirSync(out, { recursive: true });

async function findOnScreen(page, text) {
  const targets = [page.getByRole('heading', { name: text, exact: false }),
    page.getByLabel(text, { exact: false }), page.getByText(text, { exact: false })];
  for (let i = 0; i < 70; i++) {
    let locatedBox = null;
    for (const targetsOfType of targets) {
      for (const target of await targetsOfType.all()) {
        const box = await target.boundingBox({ timeout: 500 }).catch(() => null);
        if (box && box.y > 60 && box.y < page.viewportSize().height - 100) return target;
        locatedBox ||= box;
      }
    }
    await page.mouse.move(page.viewportSize().width - 120, 650);
    await page.mouse.wheel(0, locatedBox && locatedBox.y < 60 ? -400 : 550);
    await page.waitForTimeout(200);
  }
  await page.screenshot({ path: path.join(out, 'unreachable-section.png') });
  fs.writeFileSync(path.join(out, 'unreachable-section.txt'), await page.locator('body').ariaSnapshot());
  throw new Error(`Unable to reach section: ${text}`);
}

(async () => {
  const session = JSON.parse(execFileSync(
    'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'], { cwd: root, encoding: 'utf8' }).trim());
  const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
  let browser;
  const report = { started_at: new Date().toISOString(), preview_only: true, states: [], errors: [] };
  try {
    async function read(url) {
      const response = await fetch(api + url, { headers });
      assert.equal(response.status, 200, `${url}: ${response.status}`);
      return response.json();
    }
    const history = await read('/contents/my?limit=50');
    const item = history.items.find(row => row.domain === 'phone') || history.items[0];
    assert.ok(item, 'An existing owned analysis is required for read-only verification');
    const original = await read(`/contents/${item.content_id}`);
    const recommendation = await read(`/recommendations/from-content/${item.content_id}`);
    const ideas = recommendation.current_trend_ideas;
    assert.ok(ideas?.method_version);
    // Populated/expired layouts remain testable when real data correctly abstains.
    const fixtureIdeas = { status: 'ready', generated_at: new Date().toISOString(), items: [{
      topic: 'iPhone 27 Pro (UI fixture)', suggestion: 'ลองเปรียบเทียบเรื่องแบตเตอรี่กับสิ่งที่คุณทดสอบในคลิป',
      support_count: 1, user_evidence: [{ text: 'แบตเตอรี่' }],
      expires_at: new Date(Date.now() + 3600000).toISOString(), sources: [{
        platform: 'youtube', title: 'iPhone 27 Pro ทดสอบแบตเตอรี่ (UI fixture)',
        url: 'https://www.youtube.com/', thumbnail_url: '', evidence_field: 'title',
        evidence_text: 'iPhone 27 Pro ทดสอบแบตเตอรี่ (UI fixture)',
        snapshot_run_id: 0, snapshot_item_id: 0, observed_at: new Date().toISOString(),
        published_at: new Date(Date.now() - 3600000).toISOString(),
      }],
    }] };
    report.api = { content_id: item.content_id, domain: recommendation.domain,
      status: ideas.status, topics: ideas.items.map(row => row.topic),
      source_ids: ideas.items.flatMap(row => row.sources.map(s => s.snapshot_item_id)) };
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(data => {
      localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
    }, session);
    let mode = 'fresh';
    await context.route(`**/contents/${item.content_id}`, async route => {
      const payload = structuredClone(original);
      if (mode !== 'legacy') {
        payload.recommendation = structuredClone(recommendation);
        if (mode === 'populated-fixture' || mode === 'expired') {
          payload.recommendation.current_trend_ideas = structuredClone(fixtureIdeas);
        }
        if (mode === 'expired') {
          payload.recommendation.current_trend_ideas.items.forEach(row => {
            row.expires_at = '2020-01-01T00:00:00Z';
          });
        }
        if (mode === 'unrelated') {
          payload.recommendation.current_trend_ideas.items = [];
          payload.recommendation.current_trend_ideas.status = 'no_related';
        }
      } else {
        delete payload.recommendation.current_trend_ideas;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
    });
    for (const [state, width] of [['fresh', 1440], ['fresh', 900], ['populated-fixture', 1440],
      ['populated-fixture', 900], ['expired', 1440], ['unrelated', 1440], ['legacy', 1440]]) {
      mode = state;
      const page = await context.newPage();
      await page.setViewportSize({ width, height: 1000 });
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', msg => {
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(msg.text())) report.errors.push(msg.text());
      });
      await page.goto(`${web}/#/history`, { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
      await page.waitForTimeout(1000);
      await (await findOnScreen(page, item.title.slice(0, 60))).click();
      await page.waitForTimeout(1000);
      const heading = state === 'expired' ? 'ไอเดียกระแสที่บันทึกไว้' : 'ไอเดียจากกระแสล่าสุด';
      await findOnScreen(page, heading);
      await page.waitForTimeout(1000);
      const semantics = await page.locator('body').ariaSnapshot();
      if (state === 'expired') assert.ok(semantics.includes('ข้อมูลกระแสที่บันทึกไว้หมดอายุแล้ว'));
      if (state === 'unrelated') assert.ok(semantics.includes('ยังไม่พบกระแสล่าสุดที่เกี่ยวข้อง'));
      if (state === 'legacy') assert.ok(semantics.includes('ยังไม่ได้ตรวจไอเดียจากกระแสล่าสุด'));
      if (state === 'populated-fixture') assert.ok(semantics.includes('iPhone 27 Pro (UI fixture)'));
      if (state === 'fresh' && ideas.items.length) {
        assert.ok(semantics.includes(ideas.items[0].topic));
        assert.ok(semantics.includes('ไม่ใช่หลักฐานคำพูดใน Transcript'));
        const source = ideas.items[0].sources[0];
        assert.ok(semantics.includes(`รอบ #${source.snapshot_run_id}`));
      }
      const screenshot = `${state}-${width}.png`;
      await page.screenshot({ path: path.join(out, screenshot) });
      fs.writeFileSync(path.join(out, `${state}-${width}.txt`), semantics);
      report.states.push({ state, width, screenshot });
      await page.close();
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } finally {
    if (browser) await browser.close();
    await fetch(api + '/auth/logout', { method: 'POST', headers }).catch(() => {});
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
